import csv
import io
import logging
from datetime import date, datetime, timedelta
from pathlib import Path
from urllib.parse import urlencode

import psycopg
from fastapi import Depends, FastAPI, Form, HTTPException, Query, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import HTMLResponse, RedirectResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates

from ingest import db as ingest_db
from ingest import phase8_follow_ups, phase9_daily_priority

from . import queries
from .db import get_conn

BASE_DIR = Path(__file__).resolve().parent


def format_phone(raw: str | None) -> str:
    """(701) 555-0100 everywhere, regardless of how a source stored it - scraped data
    arrives as 701-555-0100, 7015550100, 701.555.0100, etc. Anything that isn't a
    plain 10 (or 11 with a leading 1) digit US number is left alone rather than
    mangled - better an unformatted oddity than a silently wrong-looking number."""
    if not raw:
        return raw
    digits = "".join(ch for ch in raw if ch.isdigit())
    if len(digits) == 11 and digits[0] == "1":
        digits = digits[1:]
    if len(digits) != 10:
        return raw
    return f"({digits[0:3]}) {digits[3:6]}-{digits[6:10]}"


def build_qs(state: dict, overrides: dict | None = None) -> str:
    """Query string for a link that preserves the current filters/sort/page, with
    `overrides` applied on top - keeps every sort-header and pagination link a plain
    <a href>, no client-side state to keep in sync with the server."""
    merged = {**state, **(overrides or {})}
    params = {}
    for k, v in merged.items():
        # `v in (None, "", False)` looks equivalent but drops 0 as well, since
        # 0 == False in Python - which silently deleted a "score min 0" bound from
        # every sort, pagination and Work-this-list link on the page.
        if v is None or v == "" or v is False:
            continue
        params[k] = "true" if v is True else v
    return urlencode(params)


log = logging.getLogger("prospect_engine")

app = FastAPI()
app.mount("/static", StaticFiles(directory=BASE_DIR / "static"), name="static")
templates = Jinja2Templates(directory=BASE_DIR / "templates")
templates.env.globals["ROLE_LABELS"] = queries.ROLE_LABELS
templates.env.globals["ROLE_PRIORITY"] = queries.ROLE_PRIORITY
templates.env.globals["build_qs"] = build_qs
templates.env.globals["CHANNEL_BUTTONS"] = queries.CHANNEL_BUTTONS
templates.env.globals["OUTCOME_LABELS"] = queries.OUTCOME_LABELS
templates.env.globals["ACTION_TYPE_LABELS"] = queries.ACTION_TYPE_LABELS
templates.env.globals["OUTCOME_OPTIONS_BY_CHANNEL"] = queries.OUTCOME_OPTIONS_BY_CHANNEL
templates.env.globals["BUYING_ENTITY_LABELS"] = queries.BUYING_ENTITY_LABELS
templates.env.globals["BUYING_ENTITY_ORDER"] = queries.BUYING_ENTITY_ORDER
templates.env.globals["SCORE_METHODOLOGY"] = queries.SCORE_METHODOLOGY
templates.env.globals["STAGE_LABELS"] = queries.STAGE_LABELS
templates.env.globals["STAGE_NEXT"] = queries.STAGE_NEXT
templates.env.filters["phone"] = format_phone
templates.env.filters["score_tier"] = queries.score_tier

PAGE_SIZE = 50


def _error_response(request: Request, status: int, message: str) -> HTMLResponse:
    """One error surface for both kinds of request.

    htmx never swaps a non-2xx response, so before this existed a failed save was
    completely invisible: the rep clicked Save, nothing on screen moved, and the only
    record of the failure was a traceback in the server log. htmx requests get a small
    fragment that app.js retargets into a banner; full navigations get a real page
    instead of Starlette's bare "Internal Server Error" text.
    """
    if request.headers.get("HX-Request"):
        return templates.TemplateResponse(
            request, "_error_banner.html", {"message": message},
            status_code=status, headers={"HX-Reswap": "none"},
        )
    return templates.TemplateResponse(
        request, "error.html", {"status": status, "message": message}, status_code=status,
    )


@app.exception_handler(HTTPException)
def http_exception_handler(request: Request, exc: HTTPException):
    return _error_response(request, exc.status_code, exc.detail)


@app.exception_handler(RequestValidationError)
def validation_exception_handler(request: Request, exc: RequestValidationError):
    return _error_response(
        request, 400,
        "That request had a value this page can't use. If you edited the address bar, "
        "try loading the page fresh.",
    )


@app.exception_handler(Exception)
def unhandled_exception_handler(request: Request, exc: Exception):
    """Database CHECK/FK violations reach here. They are genuine bugs - the endpoint
    should have rejected the value first - so they are logged in full, but the rep gets
    a sentence instead of a stack trace and, crucially, gets *something*."""
    log.exception("unhandled error on %s %s", request.method, request.url.path)
    return _error_response(
        request, 500,
        "Something went wrong saving that, and it wasn't saved. "
        "The error has been logged - please try again.",
    )

# Today stays deliberately bounded (WEBAPP_PLAN.md 2: "a bounded list that's always
# achievable beats a complete one that never is").
PRIORITY_LIMIT = 15
PRIORITY_LIMIT_MORE = 30


def _opt_number(raw: str, cast):
    """A filter bound from the query string, or None if it isn't a usable number.

    Bad input is ignored rather than raised: these values arrive from a URL, and the
    guide tells reps to bookmark and share filtered views, so a hand-edited or
    truncated link has to degrade to 'no bound' instead of a 500. Floats are accepted
    for the int fields ("1.5" -> 1) rather than rejected - a pasted value shouldn't
    lose the whole filter over its decimal point."""
    raw = (raw or "").strip()
    if not raw:
        return None
    try:
        return cast(raw)
    except ValueError:
        pass
    try:
        return cast(float(raw))
    except (ValueError, OverflowError):
        return None


def filter_params(
    q: str = "",
    state: str = "",
    segment: str = "",
    enrollment_min: str = "",
    enrollment_max: str = "",
    score_min: str = "",
    score_max: str = "",
    has_pto_contact: bool = False,
    has_verified_email: bool = False,
) -> dict:
    """Shared by the list and the queue - both walk the same filtered set.

    The numeric fields arrive as plain strings, not int/float | None, because a
    blank <input type=number> submits as an empty string, not an absent param -
    FastAPI 422s trying to coerce "" straight to int/float.
    """
    return dict(
        q=q.strip(), state=state, segment=segment,
        enrollment_min=_opt_number(enrollment_min, int),
        enrollment_max=_opt_number(enrollment_max, int),
        score_min=_opt_number(score_min, float),
        score_max=_opt_number(score_max, float),
        has_pto_contact=has_pto_contact, has_verified_email=has_verified_email,
    )


# Arbitrary constant, shared by every process that regenerates the snapshot. Advisory
# locks are namespaced only by this number, so it just has to be unique within this DB.
DAILY_PRIORITY_LOCK_KEY = 8_123_456_789


def _regen_ran_today(conn, today: date) -> bool:
    with conn.cursor() as cur:
        cur.execute(
            """
            SELECT 1 FROM ingest_runs
            WHERE source_detail = 'Auto daily-priority regen (webapp)'
              AND status = 'ok' AND started_at::date = %s
            LIMIT 1
            """,
            (today,),
        )
        return cur.fetchone() is not None


def _ensure_daily_priority_generated(conn, today: date) -> None:
    """Self-healing regen: if nobody/nothing has generated today's follow-ups and
    priority snapshot yet, do it now, inline. Keeps the Phase 3/4 nightly-batch design
    (a real snapshot table, not a live view - see migrations/007_crm_layer.sql) without
    depending on an OS-level cron/Task Scheduler entry actually existing and firing.

    Serialized on a Postgres advisory lock. The check and the write are far apart in
    wall-clock terms (generation takes ~0.5s over 557 schools), and the first load of
    the day is exactly when a second tab, a refresh, or a second device is most likely
    to land in that gap. Unserialized, each one deletes only the rows it can see and
    inserts its own: three concurrent loads produced three complete copies of the
    snapshot, three rows at rank 1, and every school listed three times on Today.
    """
    if _regen_ran_today(conn, today):
        return

    # A dedicated plain-tuple-row connection, not the webapp's dict_row `conn` -
    # phase8/phase9's generate() unpack rows positionally (`for a, b, c in rows`),
    # which silently iterates dict *keys* instead of values against a dict_row cursor.
    # Closing it also releases the advisory lock, whatever happened in between.
    ingest_conn = ingest_db.connect()
    try:
        with ingest_conn.cursor() as cur:
            # Wait for whoever is generating, but never wedge the home page behind a
            # stuck one - on timeout, fall through and render the snapshot as it
            # stands rather than raising.
            cur.execute("SET lock_timeout = '15s'")
            try:
                cur.execute("SELECT pg_advisory_lock(%s)", (DAILY_PRIORITY_LOCK_KEY,))
            except psycopg.errors.LockNotAvailable:
                ingest_conn.rollback()
                log.warning("daily-priority regen: timed out waiting for the lock")
                return

        # Re-check under the lock: if we queued behind the request that did the work,
        # its ingest_runs row is committed by now and there is nothing left to do.
        if _regen_ran_today(ingest_conn, today):
            return

        with ingest_db.ingest_run(
            ingest_conn, "manual", "Auto daily-priority regen (webapp)", "ND",
        ) as (run_id, counts):
            reopened = phase8_follow_ups.reopen_due_snoozes(ingest_conn, today)
            counts["in"] += reopened
            to_create = phase8_follow_ups.generate(ingest_conn, today)
            phase8_follow_ups.commit_follow_ups(ingest_conn, to_create, today, counts)
            rows = phase9_daily_priority.generate(ingest_conn, today)
            phase9_daily_priority.commit_daily_priority(ingest_conn, rows, today, counts)
            ingest_conn.commit()
    finally:
        ingest_conn.close()


@app.get("/", response_class=HTMLResponse)
def home(request: Request, show_more: bool = False, conn=Depends(get_conn)):
    today = date.today()
    _ensure_daily_priority_generated(conn, today)
    limit = PRIORITY_LIMIT_MORE if show_more else PRIORITY_LIMIT
    rows, total = queries.get_daily_priority(conn, today, limit, 0)
    next_window = queries.get_next_window_summary(conn) if total == 0 else None
    return templates.TemplateResponse(
        request, "home.html",
        {"rows": rows, "total": total, "show_more": show_more, "next_window": next_window, "today": today},
    )


@app.get("/guide", response_class=HTMLResponse)
def guide(request: Request):
    return templates.TemplateResponse(request, "guide.html", {})


@app.get("/schools", response_class=HTMLResponse)
def school_list(
    request: Request,
    filters: dict = Depends(filter_params),
    sort: str = "score",
    dir: str = "desc",
    page: int = Query(1, ge=1),
    conn=Depends(get_conn),
):
    rows, total = queries.list_schools(conn, filters, sort, dir, page, PAGE_SIZE)
    total_pages = max(1, -(-total // PAGE_SIZE))
    qs_state = {**filters, "sort": sort, "dir": dir, "page": page}

    is_htmx = bool(request.headers.get("HX-Request"))
    ctx = {
        "schools": rows, "total": total,
        "page": page, "total_pages": total_pages, "page_size": PAGE_SIZE,
        "sort": sort, "dir": dir, "filters": filters, "qs_state": qs_state,
        "segments": queries.SEGMENTS,
        "directory_as_of": queries.get_directory_freshness(conn),
        # The header count lives outside #results, so on a filter swap it has to be
        # updated out-of-band or it keeps reading "557 open schools" over a table
        # showing 18. Only emitted on the htmx path - on a full render the header
        # template already prints it, and two copies would both land on the page.
        "is_htmx": is_htmx,
    }
    template = "_school_table.html" if is_htmx else "school_list.html"
    return templates.TemplateResponse(request, template, ctx)


# Large enough to be "all of them" at this scale (573 schools) without a second query
# shape just for export - see list_schools' own docstring on why a live re-query
# instead of a snapshot is fine here. Revisit if/when this expands past one state.
EXPORT_PAGE_SIZE = 10_000


@app.get("/schools/export.csv")
def export_schools_csv(
    filters: dict = Depends(filter_params),
    sort: str = "score",
    dir: str = "desc",
    conn=Depends(get_conn),
):
    rows, _ = queries.list_schools(conn, filters, sort, dir, 1, EXPORT_PAGE_SIZE)
    buf = io.StringIO()
    writer = csv.writer(buf)
    writer.writerow([
        "School", "District", "City", "State", "Segment", "Enrollment",
        "Score", "Tier", "Last Activity",
        "Best Contact", "Contact Role", "Contact Confidence",
    ])
    for r in rows:
        tier = queries.score_tier(r["score"])
        writer.writerow([
            r["name"], r["district_name"] or "", r["city"] or "", r["state_code"],
            r["segment"] or "", r["enrollment"] if r["enrollment"] is not None else "",
            f"{r['score']:.2f}" if r["score"] is not None else "",
            tier[0] if tier else "",
            r["last_activity_at"].strftime("%Y-%m-%d") if r["last_activity_at"] else "",
            f"{r['contact_first_name']} {r['contact_last_name']}" if r["contact_first_name"] else "",
            queries.ROLE_LABELS.get(r["contact_role"], r["contact_role"] or ""),
            r["contact_email_confidence"] or "",
        ])
    buf.seek(0)
    return StreamingResponse(
        iter([buf.getvalue()]), media_type="text/csv",
        headers={"Content-Disposition": 'attachment; filename="prospect_engine_schools.csv"'},
    )


@app.get("/schools/{school_id}", response_class=HTMLResponse)
def school_detail(request: Request, school_id: int, conn=Depends(get_conn)):
    ctx = _contacts_ctx(conn, school_id)
    if ctx["school"] is None:
        raise HTTPException(404, "No school with that id.")
    return templates.TemplateResponse(request, "school_detail.html", ctx)


@app.get("/queue", response_class=HTMLResponse)
def queue(
    request: Request,
    filters: dict = Depends(filter_params),
    sort: str = "score",
    dir: str = "desc",
    pos: int = Query(0, ge=0),
    next_of: int | None = Query(None),
    prev_of: int | None = Query(None),
    conn=Depends(get_conn),
):
    # Next/Previous re-anchor on the school just being looked at rather than trusting
    # the pos number from before whatever action was just logged - see
    # queries.school_position for why. Falls back to the raw pos (old behavior) if the
    # anchor school dropped out of the current filtered set entirely.
    if next_of is not None:
        anchor = queries.school_position(conn, filters, sort, dir, next_of)
        if anchor is not None:
            pos = anchor + 1
    elif prev_of is not None:
        anchor = queries.school_position(conn, filters, sort, dir, prev_of)
        if anchor is not None:
            pos = max(0, anchor - 1)

    school_id, total = queries.queue_school_at(conn, filters, sort, dir, pos)
    qs_state = {**filters, "sort": sort, "dir": dir, "pos": pos}

    if school_id is None:
        if total > 0 and pos >= total:
            # filters changed size out from under this position (an action just
            # taken can do this) - land on the last valid school instead of a dead end
            qs = build_qs(qs_state, {"pos": total - 1})
            return RedirectResponse(f"/queue?{qs}", status_code=303)
        return templates.TemplateResponse(
            request, "queue_empty.html", {"qs_state": qs_state},
        )

    ctx = _contacts_ctx(conn, school_id)
    ctx.update(pos=pos, total=total, qs_state=qs_state)
    return templates.TemplateResponse(request, "queue.html", ctx)


@app.post("/schools/{school_id}/actions", response_class=HTMLResponse)
def create_action(
    request: Request,
    school_id: int,
    channel: str = Form(...),
    outcome: str | None = Form(None),
    contact_id: int | None = Form(None),
    buying_entity: str = Form("unknown"),
    notes: str = Form(""),
    needs_follow_up: bool = Form(False),
    follow_up_date: str = Form(""),
    occurred_at: str = Form(""),
    conn=Depends(get_conn),
):
    # Everything that can be rejected is rejected before anything is written. The
    # attempt and its follow-up are one user action and have to land together: parsing
    # the date *after* logging the call meant a bad date left the attempt recorded with
    # no follow-up, no visible change on screen, and a rep who logged the call twice.
    if not queries.school_exists(conn, school_id):
        raise HTTPException(404, "No school with that id.")
    if channel not in queries.VALID_CHANNELS:
        raise HTTPException(400, "Unknown contact channel.")
    if buying_entity not in queries.BUYING_ENTITY_LABELS:
        raise HTTPException(400, "Unknown buying entity.")
    if outcome and outcome not in queries.OUTCOME_LABELS:
        raise HTTPException(400, "Unknown outcome.")
    if contact_id is not None and queries.contact_school_id(conn, contact_id) != school_id:
        raise HTTPException(400, "That contact doesn't belong to this school.")

    # Back-dating (§4.5): a rep logging from the car or that night should be able to
    # say when the call actually happened, not just accept the click timestamp. Blank
    # (the default) means "now", handled in queries.log_action. A future timestamp is
    # rejected - a call can't have happened yet.
    logged_at = None
    if occurred_at.strip():
        try:
            logged_at = datetime.fromisoformat(occurred_at.strip())
        except ValueError:
            raise HTTPException(400, "That activity date/time isn't valid.")
        if logged_at > datetime.now() + timedelta(minutes=5):
            raise HTTPException(400, "Activity can't be logged in the future.")

    due = None
    if needs_follow_up:
        if follow_up_date.strip():
            try:
                due = date.fromisoformat(follow_up_date.strip())
            except ValueError:
                raise HTTPException(400, "Follow-up date must be a real date (YYYY-MM-DD).")
        else:
            due = date.today() + timedelta(days=queries.MANUAL_FOLLOW_UP_DEFAULT_DAYS)

    org_id, user_id = queries.get_default_org_user(conn)
    queries.log_action(
        conn, org_id, user_id, school_id, contact_id,
        buying_entity, channel, outcome or None, notes.strip() or None,
        occurred_at=logged_at,
    )
    if due is not None:
        queries.set_manual_follow_up(
            conn, school_id, buying_entity, due,
            f"Follow-up requested when logging a {channel} attempt"
            + (f': "{notes.strip()}"' if notes.strip() else ""),
        )
    conn.commit()
    groups = queries.get_activity_grouped(conn, school_id)
    return templates.TemplateResponse(
        request, "_activity_timeline.html",
        {"activity_groups": groups, "school_id": school_id},
    )


@app.patch("/actions/{action_id}/outcome", response_class=HTMLResponse)
def patch_action_outcome(
    request: Request,
    action_id: int,
    school_id: int = Form(...),
    outcome: str = Form(...),
    conn=Depends(get_conn),
):
    if outcome not in queries.OUTCOME_LABELS:
        raise HTTPException(400, "Unknown outcome.")
    if not queries.update_action_outcome(conn, action_id, school_id, outcome):
        raise HTTPException(404, "That activity entry no longer exists.")
    groups = queries.get_activity_grouped(conn, school_id)
    return templates.TemplateResponse(
        request, "_activity_timeline.html",
        {"activity_groups": groups, "school_id": school_id},
    )


@app.patch("/actions/{action_id}/notes", response_class=HTMLResponse)
def patch_action_notes(
    request: Request,
    action_id: int,
    school_id: int = Form(...),
    notes: str = Form(""),
    conn=Depends(get_conn),
):
    if not queries.update_action_notes(conn, action_id, school_id, notes.strip() or None):
        raise HTTPException(404, "That activity entry no longer exists.")
    groups = queries.get_activity_grouped(conn, school_id)
    return templates.TemplateResponse(
        request, "_activity_timeline.html",
        {"activity_groups": groups, "school_id": school_id},
    )


@app.delete("/actions/{action_id}", response_class=HTMLResponse)
def delete_action(
    request: Request,
    action_id: int,
    school_id: int = Form(...),
    conn=Depends(get_conn),
):
    if not queries.delete_action(conn, action_id, school_id):
        raise HTTPException(404, "That activity entry no longer exists.")
    groups = queries.get_activity_grouped(conn, school_id)
    return templates.TemplateResponse(
        request, "_activity_timeline.html",
        {"activity_groups": groups, "school_id": school_id},
    )


# action_type a pipeline stage change also gets logged as, so a win/loss shows up in
# the Activity timeline too - Interested/Proposal Out are pipeline-internal judgment
# calls, not a contact event, so they don't get a matching rep_action.
OPPORTUNITY_ACTION_TYPE = {"closed_won": "won", "closed_lost": "lost"}


@app.post("/schools/{school_id}/opportunities", response_class=HTMLResponse)
def create_or_advance_opportunity(
    request: Request,
    school_id: int,
    buying_entity: str = Form(...),
    stage: str = Form(...),
    contact_id: int | None = Form(None),
    amount: str = Form(""),
    notes: str = Form(""),
    conn=Depends(get_conn),
):
    if not queries.school_exists(conn, school_id):
        raise HTTPException(404, "No school with that id.")
    if buying_entity not in queries.BUYING_ENTITY_LABELS:
        raise HTTPException(400, "Unknown buying entity.")
    if stage not in queries.STAGE_LABELS:
        raise HTTPException(400, "Unknown pipeline stage.")
    if contact_id is not None and queries.contact_school_id(conn, contact_id) != school_id:
        raise HTTPException(400, "That contact doesn't belong to this school.")

    parsed_amount = None
    if amount.strip():
        try:
            parsed_amount = round(float(amount.strip()), 2)
        except ValueError:
            raise HTTPException(400, "Amount must be a number.")
        if parsed_amount < 0:
            raise HTTPException(400, "Amount can't be negative.")

    org_id, user_id = queries.get_default_org_user(conn)
    queries.upsert_opportunity(
        conn, org_id, user_id, school_id, buying_entity, contact_id, stage,
        parsed_amount, notes.strip() or None,
    )
    # A close is a real, historically-meaningful event worth its own timeline entry,
    # same reasoning as the Today dismiss buttons (see DISMISS_ACTION_TYPE above).
    action_type = OPPORTUNITY_ACTION_TYPE.get(stage)
    if action_type:
        close_note = f"Marked {queries.STAGE_LABELS[stage]}"
        if parsed_amount is not None:
            close_note += f" (${parsed_amount:,.2f})"
        queries.log_action(
            conn, org_id, user_id, school_id, contact_id, buying_entity,
            None, None, close_note, action_type=action_type,
        )
    conn.commit()

    return templates.TemplateResponse(
        request, "_pipeline_response.html", _contacts_ctx(conn, school_id),
    )


@app.get("/pipeline", response_class=HTMLResponse)
def pipeline(request: Request, conn=Depends(get_conn)):
    opportunities = queries.list_open_opportunities(conn)
    won_by_segment, won_totals = queries.get_won_summary(conn)
    dials_7d = queries.get_dial_report(conn, date.today() - timedelta(days=7))
    return templates.TemplateResponse(
        request, "pipeline.html",
        {
            "opportunities": opportunities,
            "won_by_segment": won_by_segment,
            "won_totals": won_totals,
            "dials_7d": dials_7d,
        },
    )


def _contacts_ctx(conn, school_id: int) -> dict:
    school = queries.get_school_detail(conn, school_id)
    if school is None:
        return {"school": None, "contacts_by_role": {}}
    last_entity_by_contact = queries.get_last_entity_by_contact(conn, school_id)
    merged_contacts = queries.merge_duplicate_contacts(school["contacts"], last_entity_by_contact)
    contacts_by_role = {}
    for c in merged_contacts:
        contacts_by_role.setdefault(c["role"], []).append(c)
    return {"school": school, "contacts_by_role": contacts_by_role}


@app.post("/schools/{school_id}/contacts", response_class=HTMLResponse)
def add_contact(
    request: Request,
    school_id: int,
    role: str = Form(...),
    first_name: str = Form(""),
    last_name: str = Form(""),
    role_detail: str = Form(""),
    email: str = Form(""),
    phone: str = Form(""),
    conn=Depends(get_conn),
):
    if not queries.school_exists(conn, school_id):
        raise HTTPException(404, "No school with that id.")
    if role not in queries.ROLE_LABELS:
        raise HTTPException(400, "Unknown role.")
    if not first_name.strip() and not last_name.strip():
        raise HTTPException(400, "Enter at least a first or last name.")
    queries.create_contact(
        conn, school_id, role,
        first_name.strip() or None, last_name.strip() or None,
        role_detail.strip() or None, email.strip() or None, phone.strip() or None,
    )
    return templates.TemplateResponse(
        request, "_contacts_section.html", _contacts_ctx(conn, school_id),
    )


@app.patch("/contacts/{contact_id}", response_class=HTMLResponse)
def patch_contact_info(
    request: Request,
    contact_id: int,
    school_id: int = Form(...),
    email: str = Form(""),
    phone: str = Form(""),
    conn=Depends(get_conn),
):
    if not queries.update_contact_info(
        conn, contact_id, school_id, email.strip() or None, phone.strip() or None
    ):
        raise HTTPException(404, "That contact no longer exists at this school.")
    return templates.TemplateResponse(
        request, "_contacts_section.html", _contacts_ctx(conn, school_id),
    )


@app.post("/buying_windows/{window_id}", response_class=HTMLResponse)
def update_buying_window(
    request: Request,
    window_id: int,
    season: str = Form(...),
    decision_start_month: int = Form(...),
    decision_start_day: int = Form(...),
    decision_end_month: int = Form(...),
    decision_end_day: int = Form(...),
    source: str = Form(...),
    notes: str = Form(""),
    conn=Depends(get_conn),
):
    # The form's min/max bound month and day independently, so the browser happily
    # accepts Feb 30 - and so did the CHECK constraints, which validate each column on
    # its own. That combination wrote a date that doesn't exist, which then raised
    # every time the school's page tried to render it: one save, and that school 500'd
    # permanently. Validate the pair, here, before it can be stored.
    for label, month, day in (
        ("Opens", decision_start_month, decision_start_day),
        ("Closes", decision_end_month, decision_end_day),
    ):
        if not queries.valid_month_day(month, day):
            raise HTTPException(
                400,
                f"{label}: {month:02d}/{day:02d} isn't a real date. "
                "(February 29 isn't accepted either - a window that recurs every year "
                "can't start on a day three years in four don't have.)",
            )
    if season not in ("fall", "spring"):
        raise HTTPException(400, "Season must be fall or spring.")
    if source not in ("assumed", "observed", "stated"):
        raise HTTPException(400, "Source must be assumed, observed or stated.")

    school_id = queries.update_buying_window(
        conn, window_id, season,
        decision_start_month, decision_start_day,
        decision_end_month, decision_end_day,
        source, notes.strip() or None,
    )
    if school_id is None:
        raise HTTPException(404, "That decision window no longer exists.")
    school = {"buying_windows": queries.get_buying_windows(conn, school_id)}
    return templates.TemplateResponse(
        request, "_window_section.html", {"school": school},
    )


DISMISS_DURATIONS = {
    "1w": 7, "2w": 14, "done": None, "not_interested": None,
}
# What dismissing from Today means for the activity log and for future auto-generation.
# "not_interested" maps to do_not_contact specifically so it also suppresses future
# cadence/signal follow-ups for this (school, entity) - see suppressed() in
# ingest/phase8_follow_ups.py. The other three are non-terminal (temporary), so they use
# 'acknowledged' and don't suppress anything.
DISMISS_ACTION_TYPE = {
    "1w": "acknowledged", "2w": "acknowledged",
    "done": "acknowledged", "not_interested": "do_not_contact",
}
DISMISS_NOTES = {
    "1w": "Snoozed 1 week from Today's list",
    "2w": "Snoozed 2 weeks from Today's list",
    "done": "Marked done for now from Today's list",
    "not_interested": "Marked not interested from Today's list",
}


@app.post("/priority/dismiss", response_class=HTMLResponse)
def dismiss_priority_item(
    request: Request,
    school_id: int = Form(...),
    buying_entity: str = Form(...),
    duration: str = Form(...),
    show_more: bool = Form(False),
    conn=Depends(get_conn),
):
    if duration not in DISMISS_DURATIONS:
        raise HTTPException(400, "Unknown dismiss option.")
    if buying_entity not in queries.BUYING_ENTITY_LABELS:
        raise HTTPException(400, "Unknown buying entity.")
    if not queries.school_exists(conn, school_id):
        raise HTTPException(404, "No school with that id.")

    today = date.today()
    snoozed_until = (
        today + timedelta(days=DISMISS_DURATIONS[duration])
        if duration in ("1w", "2w") else None
    )
    # Dismissal and the log entry explaining it commit together - a follow-up that
    # vanished with no matching activity row is a hole in the history the rep relies on.
    queries.dismiss_follow_up(conn, school_id, buying_entity, snoozed_until, today)

    org_id, user_id = queries.get_default_org_user(conn)
    notes = DISMISS_NOTES[duration]
    if snoozed_until:
        notes += f" (until {snoozed_until.isoformat()})"
    queries.log_action(
        conn, org_id, user_id, school_id, None, buying_entity,
        None, None, notes, action_type=DISMISS_ACTION_TYPE[duration],
    )
    conn.commit()

    # Re-render at whatever length the rep is actually looking at. Hardcoding 15 here
    # collapsed an expanded list back down on every dismissal and re-offered "Show
    # more" - the list shrank as a *result* of working it.
    rows, total = queries.get_daily_priority(conn, today, PRIORITY_LIMIT_MORE if show_more else PRIORITY_LIMIT, 0)
    next_window = queries.get_next_window_summary(conn) if total == 0 else None
    return templates.TemplateResponse(
        request, "_priority_list.html",
        {"rows": rows, "total": total, "show_more": show_more, "next_window": next_window, "today": today},
    )
