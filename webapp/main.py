from datetime import date, timedelta
from pathlib import Path
from urllib.parse import urlencode

from fastapi import Depends, FastAPI, Form, Query, Request
from fastapi.responses import HTMLResponse, RedirectResponse
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
        if v in (None, "", False):
            continue
        params[k] = "true" if v is True else v
    return urlencode(params)


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
templates.env.filters["phone"] = format_phone

PAGE_SIZE = 50


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
        enrollment_min=int(enrollment_min) if enrollment_min.strip() else None,
        enrollment_max=int(enrollment_max) if enrollment_max.strip() else None,
        score_min=float(score_min) if score_min.strip() else None,
        score_max=float(score_max) if score_max.strip() else None,
        has_pto_contact=has_pto_contact, has_verified_email=has_verified_email,
    )


def _ensure_daily_priority_generated(conn, today: date) -> None:
    """Self-healing regen: if nobody/nothing has generated today's follow-ups and
    priority snapshot yet, do it now, inline. Keeps the Phase 3/4 nightly-batch design
    (a real snapshot table, not a live view - see migrations/007_crm_layer.sql) without
    depending on an OS-level cron/Task Scheduler entry actually existing and firing."""
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
        already_ran = cur.fetchone() is not None
    if already_ran:
        return

    # A dedicated plain-tuple-row connection, not the webapp's dict_row `conn` -
    # phase8/phase9's generate() unpack rows positionally (`for a, b, c in rows`),
    # which silently iterates dict *keys* instead of values against a dict_row cursor.
    ingest_conn = ingest_db.connect()
    try:
        with ingest_db.ingest_run(
            ingest_conn, "manual", "Auto daily-priority regen (webapp)", "ND",
        ) as (run_id, counts):
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
    limit = 30 if show_more else 15
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

    ctx = {
        "request": request, "schools": rows, "total": total,
        "page": page, "total_pages": total_pages, "page_size": PAGE_SIZE,
        "sort": sort, "dir": dir, "filters": filters, "qs_state": qs_state,
        "segments": queries.SEGMENTS,
    }
    template = "_school_table.html" if request.headers.get("HX-Request") else "school_list.html"
    return templates.TemplateResponse(request, template, ctx)


@app.get("/schools/{school_id}", response_class=HTMLResponse)
def school_detail(request: Request, school_id: int, conn=Depends(get_conn)):
    ctx = _contacts_ctx(conn, school_id)
    if ctx["school"] is None:
        return HTMLResponse("School not found", status_code=404)
    return templates.TemplateResponse(request, "school_detail.html", ctx)


@app.get("/queue", response_class=HTMLResponse)
def queue(
    request: Request,
    filters: dict = Depends(filter_params),
    sort: str = "score",
    dir: str = "desc",
    pos: int = Query(0, ge=0),
    conn=Depends(get_conn),
):
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
    conn=Depends(get_conn),
):
    org_id, user_id = queries.get_default_org_user(conn)
    queries.log_action(
        conn, org_id, user_id, school_id, contact_id,
        buying_entity, channel, outcome or None, notes.strip() or None,
    )
    if needs_follow_up:
        due = (
            date.fromisoformat(follow_up_date) if follow_up_date.strip()
            else date.today() + timedelta(days=queries.MANUAL_FOLLOW_UP_DEFAULT_DAYS)
        )
        queries.set_manual_follow_up(
            conn, school_id, buying_entity, due,
            f"Follow-up requested when logging a {channel} attempt"
            + (f': "{notes.strip()}"' if notes.strip() else ""),
        )
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
    queries.update_action_outcome(conn, action_id, outcome)
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
    queries.update_action_notes(conn, action_id, notes.strip() or None)
    groups = queries.get_activity_grouped(conn, school_id)
    return templates.TemplateResponse(
        request, "_activity_timeline.html",
        {"activity_groups": groups, "school_id": school_id},
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


@app.patch("/contacts/{contact_id}", response_class=HTMLResponse)
def patch_contact_info(
    request: Request,
    contact_id: int,
    school_id: int = Form(...),
    email: str = Form(""),
    phone: str = Form(""),
    conn=Depends(get_conn),
):
    queries.update_contact_info(conn, contact_id, email.strip() or None, phone.strip() or None)
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
    school_id = queries.update_buying_window(
        conn, window_id, season,
        decision_start_month, decision_start_day,
        decision_end_month, decision_end_day,
        source, notes.strip() or None,
    )
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
    conn=Depends(get_conn),
):
    today = date.today()
    snoozed_until = (
        today + timedelta(days=DISMISS_DURATIONS[duration])
        if duration in ("1w", "2w") else None
    )
    queries.dismiss_follow_up(conn, school_id, buying_entity, snoozed_until, today)

    org_id, user_id = queries.get_default_org_user(conn)
    notes = DISMISS_NOTES[duration]
    if snoozed_until:
        notes += f" (until {snoozed_until.isoformat()})"
    queries.log_action(
        conn, org_id, user_id, school_id, None, buying_entity,
        None, None, notes, action_type=DISMISS_ACTION_TYPE[duration],
    )

    rows, total = queries.get_daily_priority(conn, today, 15, 0)
    next_window = queries.get_next_window_summary(conn) if total == 0 else None
    return templates.TemplateResponse(
        request, "_priority_list.html",
        {"rows": rows, "total": total, "show_more": False, "next_window": next_window, "today": today},
    )
