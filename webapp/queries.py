"""Read-only queries backing the Phase 1 school list and detail screens.

Score and buying-window lookups always take the latest row for a school rather than a
hardcoded version/date - the same staleness bug fixed in migration 008 for the
verification-queue view would otherwise resurface here the next time either table
grows a new version.
"""
import calendar
import re
from datetime import date

ROLE_LABELS = {
    "principal": "Principal",
    "assistant_principal": "Assistant Principal",
    "office_manager": "Office Manager",
    "music_teacher": "Music Teacher",
    "band_director": "Band Director",
    "choir_director": "Choir Director",
    "drama_director": "Drama Director",
    "activities_director": "Activities Director",
    "athletic_director": "Athletic Director",
    "pto_president": "PTO President",
    "pto_fundraising_chair": "PTO Fundraising Chair",
    "pto_treasurer": "PTO Treasurer",
    "booster_president": "Booster President",
    "superintendent": "Superintendent",
    "other": "Other",
}

# Priority for picking one "best-known contact" per school on the list screen -
# buying-entity roles first (that's who actually says yes), then the office.
ROLE_PRIORITY = [
    "pto_president", "pto_fundraising_chair", "pto_treasurer", "booster_president",
    "principal", "office_manager", "assistant_principal", "superintendent",
    "activities_director", "athletic_director",
    "band_director", "choir_director", "drama_director", "music_teacher", "other",
]
_ROLE_PRIORITY_SQL = " ".join(
    f"WHEN '{r}' THEN {i}" for i, r in enumerate(ROLE_PRIORITY)
)

_EMAIL_CONF_SQL = (
    "CASE email_confidence "
    "WHEN 'verified' THEN 1 WHEN 'high' THEN 2 WHEN 'medium' THEN 3 "
    "WHEN 'low' THEN 4 ELSE 5 END"
)

SEGMENTS = ["elementary", "middle", "high", "combined", "other"]

SCORE_METHODOLOGY = (
    "0-10 composite score, weighted: enrollment size (30%), contactability - do we "
    "have a working email or phone (20%), estimated household income via free/reduced "
    "lunch rate, inverted (20%), PTO/booster fundraising capacity (15%), and school "
    "segment (15%). Higher = better prospect to call right now. Recalculated "
    "periodically as new data comes in - see the version tag for which run produced it."
)

PTO_BOOSTER_ROLES = (
    "pto_president", "pto_fundraising_chair", "pto_treasurer", "booster_president",
)

# Phase 2: activity logging.
# Each primary-action button is a (label, channel, default_outcome, keyboard_shortcut)
# tuple. "Called" and "Left message" share a channel but log a different default
# outcome - the schema has no separate channel for them, the outcome column is what
# tells them apart. Mailed has no outcome yet: nothing about mail is knowable at the
# moment of sending it.
CHANNEL_BUTTONS = [
    ("Called", "phone", "spoke", "c"),
    ("Left message", "phone", "left_voicemail", "l"),
    ("Emailed", "email", "email_sent", "e"),
    ("Video call", "video", "spoke", "v"),
    ("Mailed", "mail", None, "m"),
]

OUTCOME_LABELS = {
    "no_answer": "No answer", "left_voicemail": "Left voicemail",
    "gatekept": "Gatekept", "spoke": "Spoke", "declined": "Declined",
    "email_sent": "Email sent", "email_replied": "Replied",
    "email_bounced": "Bounced", "meeting_set": "Meeting set",
    "no_response": "No response",
}

# Non-'contacted' rep_actions rows (dismissing a Today item, marking a deal won/lost)
# get a plain label instead of the usual channel/outcome line in the activity
# timeline - there's no channel or outcome to speak of for "marked not interested."
ACTION_TYPE_LABELS = {
    "acknowledged": "Acknowledged",
    "meeting_set": "Meeting set",
    "quoted": "Quoted",
    "won": "Won",
    "lost": "Lost",
    "do_not_contact": "Marked do-not-contact",
}

# Shown as "not right? -> " refine chips on a logged entry, scoped to what's actually
# possible for that channel.
OUTCOME_OPTIONS_BY_CHANNEL = {
    "phone": ["no_answer", "left_voicemail", "gatekept", "spoke", "declined"],
    "video": ["spoke", "meeting_set", "no_answer", "declined"],
    "email": ["email_sent", "email_replied", "email_bounced", "declined", "no_response"],
    "mail": ["no_response", "declined"],
}

BUYING_ENTITY_LABELS = {
    "pto": "PTO", "pta": "PTA",
    "boosters_band": "Band Boosters", "boosters_choir": "Choir Boosters",
    "boosters_drama": "Drama Boosters", "boosters_athletic": "Athletic Boosters",
    "school_admin": "School Admin", "unknown": "Unknown",
}
BUYING_ENTITY_ORDER = [
    "school_admin", "pto", "pta",
    "boosters_band", "boosters_choir", "boosters_drama", "boosters_athletic",
    "unknown",
]
_BOOSTER_KEYWORDS = {
    "band": "boosters_band",
    "choir": "boosters_choir", "vocal": "boosters_choir",
    "drama": "boosters_drama", "theatre": "boosters_drama", "theater": "boosters_drama",
    "athletic": "boosters_athletic", "basketball": "boosters_athletic",
    "football": "boosters_athletic", "volleyball": "boosters_athletic",
    "wrestling": "boosters_athletic", "baseball": "boosters_athletic",
    "softball": "boosters_athletic", "soccer": "boosters_athletic",
    "hockey": "boosters_athletic", "track": "boosters_athletic",
    "golf": "boosters_athletic", "swim": "boosters_athletic",
}


def buying_entity_for_contact(role: str, role_detail: str | None) -> str:
    """Per-contact default, so each logging action carries its own entity instead of
    one page-level guess - a school can have a live PTO relationship and a live
    booster relationship at the same time, and they must not collide in the log."""
    if role in ("pto_president", "pto_fundraising_chair", "pto_treasurer"):
        return "pto"
    if role == "booster_president":
        detail = (role_detail or "").lower()
        for kw, val in _BOOSTER_KEYWORDS.items():
            if kw in detail:
                return val
        return "unknown"
    return "school_admin"


def get_last_entity_by_contact(conn, school_id: int) -> dict:
    """The buying_entity actually used the last time each contact was logged against -
    what the per-contact entity picker should default to on reload, instead of always
    falling back to the role-based guess (which made a picked value look like it never
    saved)."""
    with conn.cursor() as cur:
        cur.execute(
            """
            SELECT DISTINCT ON (contact_id) contact_id, buying_entity
            FROM rep_actions
            WHERE school_id = %(id)s AND contact_id IS NOT NULL AND buying_entity IS NOT NULL
            ORDER BY contact_id, occurred_at DESC
            """,
            {"id": school_id},
        )
        return {r["contact_id"]: r["buying_entity"] for r in cur.fetchall()}


_EMAIL_CONF_RANK = {"verified": 0, "high": 1, "medium": 2, "low": 3, "unknown": 4, "invalid": 5}


def _norm_email(v):
    return (v or "").strip().lower() or None


def _norm_phone(v):
    return re.sub(r"\D", "", v or "") or None


def dedupe_contact_methods(rows: list) -> list:
    """Two source rows for the same person that carry the *same* email and phone are
    not a disagreement worth showing - they're one fact scraped twice, and rendering
    them side by side with contradictory confidence badges ("high" next to "medium" on
    a byte-identical address) undermines the badge everywhere else. Keep best-confidence
    first, then drop any row whose email and phone are both already covered.

    A row that adds a genuinely new address or number is always kept, so a real
    source disagreement still surfaces - that's the case the merge exists for.
    """
    ordered = sorted(rows, key=lambda r: _EMAIL_CONF_RANK.get(r.get("email_confidence"), 9))
    kept, seen_emails, seen_phones = [], set(), set()
    for r in ordered:
        email, phone = _norm_email(r.get("email")), _norm_phone(r.get("phone"))
        adds_email = email is not None and email not in seen_emails
        adds_phone = phone is not None and phone not in seen_phones
        if kept and not adds_email and not adds_phone:
            continue
        # A contact with no email and no phone at all still needs one row rendered:
        # that empty row is what carries the "+ Add email / + Add phone" affordance.
        kept.append(r)
        seen_emails.add(email)
        seen_phones.add(phone)
    return kept


def merge_duplicate_contacts(contacts: list, last_entity_by_contact: dict | None = None) -> list:
    """The same person routinely gets written twice - once from the state directory,
    once from the site crawl - sometimes with different confidence, sometimes even a
    different role (a genuine promotion, or just two sources disagreeing). Merge by
    (school, name) so they show as one person, keeping every *distinct* contact method
    intact rather than picking a winner: the disagreement itself is information a rep
    should be able to see. Byte-identical repeats are collapsed first - see
    dedupe_contact_methods.
    """
    last_entity_by_contact = last_entity_by_contact or {}
    groups, order = {}, []
    for c in contacts:
        fn, ln = (c.get("first_name") or "").strip().lower(), (c.get("last_name") or "").strip().lower()
        key = (fn, ln) if (fn or ln) else ("__id__", c["id"])
        if key not in groups:
            groups[key] = []
            order.append(key)
        groups[key].append(c)

    merged = []
    for key in order:
        rows = groups[key]
        primary = min(
            rows,
            key=lambda r: ROLE_PRIORITY.index(r["role"]) if r["role"] in ROLE_PRIORITY else 99,
        )
        other_roles = sorted({r["role"] for r in rows if r["role"] != primary["role"]})
        # Any method row sharing this merged person may carry the logged history -
        # check them all, not just the one picked as "primary" for display.
        last_used = next(
            (last_entity_by_contact[r["id"]] for r in rows if r["id"] in last_entity_by_contact),
            None,
        )
        merged.append({
            "id": primary["id"],
            "first_name": primary["first_name"],
            "last_name": primary["last_name"],
            "role": primary["role"],
            "role_detail": primary["role_detail"],
            "other_roles": other_roles,
            "methods": dedupe_contact_methods(rows),
            "default_entity": last_used or buying_entity_for_contact(primary["role"], primary["role_detail"]),
        })
    return merged

SORT_COLUMNS = {
    "name": "s.name",
    "district": "d.name",
    "city": "s.city",
    "segment": "s.segment",
    "enrollment": "s.enrollment",
    "score": "sc.score",
    "last_activity": "la.last_activity_at",
}


def valid_month_day(month: int, day: int) -> bool:
    """Is (month, day) a real calendar date in a non-leap year? Feb 29 is deliberately
    rejected: a window that recurs every year can't anchor on a day that doesn't exist
    in three years out of four."""
    if not (1 <= month <= 12 and 1 <= day <= 31):
        return False
    return day <= calendar.monthrange(2001, month)[1]


def recurring_date(year: int, month: int, day: int) -> date:
    """A recurring (month, day) resolved against a specific year, clamped to that
    month's real length. Callers should reject impossible input up front (see
    valid_month_day), but rows written before that check existed still have to render:
    a stored Feb 30 must degrade to Feb 28, never raise. A bare date() here is what
    turned one bad window row into a permanent 500 on that school's page."""
    return date(year, month, min(day, calendar.monthrange(year, month)[1]))


def window_status(start_month, start_day, end_month, end_day, today: date):
    """(status, human label) for a recurring month/day decision window, evaluated
    against `today`. status is one of 'in_window' / 'upcoming' / 'passed'."""
    start_this_year = recurring_date(today.year, start_month, start_day)
    end_this_year = recurring_date(today.year, end_month, end_day)
    if end_this_year < start_this_year:
        end_this_year = recurring_date(today.year + 1, end_month, end_day)

    if start_this_year <= today <= end_this_year:
        days_left = (end_this_year - today).days
        return "in_window", f"In window now, closes in {days_left} day{'s' if days_left != 1 else ''}"

    if today < start_this_year:
        days_out = (start_this_year - today).days
        weeks = days_out // 7
        label = f"Decision window opens in {weeks} week{'s' if weeks != 1 else ''}" if weeks else \
            f"Decision window opens in {days_out} day{'s' if days_out != 1 else ''}"
        return "upcoming", label

    next_start = recurring_date(today.year + 1, start_month, start_day)
    days_out = (next_start - today).days
    weeks = days_out // 7
    return "passed", f"Window closed; opens again in {weeks} weeks"


def _build_where(filters: dict):
    """Shared by list_schools (paged table) and queue_school_at (one-at-a-time work
    mode) so a queue session walks the exact same ordered set the list showed - moving
    to a school in the queue can never surface one that wouldn't be on the list."""
    where = ["s.status = 'open'"]
    params = {}

    if filters.get("q"):
        q = filters["q"]
        conditions = [
            "s.name ILIKE %(q)s",
            "d.name ILIKE %(q)s",
            "s.city ILIKE %(q)s",
            """EXISTS (
                SELECT 1 FROM contacts c3 WHERE c3.school_id = s.id AND (
                    c3.first_name ILIKE %(q)s OR c3.last_name ILIKE %(q)s OR
                    (coalesce(c3.first_name,'') || ' ' || coalesce(c3.last_name,'')) ILIKE %(q)s
                )
            )""",
        ]
        params["q"] = f"%{q}%"

        # A search term with digits in it is a phone lookup - compare digits-only on
        # both sides so it matches regardless of how a source formatted the number
        # (dashes, dots, parens - see format_phone in webapp/main.py for the same problem
        # on the display side).
        q_digits = "".join(ch for ch in q if ch.isdigit())
        if q_digits:
            conditions.append("regexp_replace(coalesce(s.phone,''), '[^0-9]', '', 'g') LIKE %(q_digits)s")
            conditions.append(
                """EXISTS (
                    SELECT 1 FROM contacts c4 WHERE c4.school_id = s.id
                    AND regexp_replace(coalesce(c4.phone,''), '[^0-9]', '', 'g') LIKE %(q_digits)s
                )"""
            )
            params["q_digits"] = f"%{q_digits}%"

        where.append("(" + " OR ".join(conditions) + ")")

    if filters.get("state"):
        where.append("s.state_code = %(state)s")
        params["state"] = filters["state"]
    if filters.get("segment"):
        where.append("s.segment = %(segment)s")
        params["segment"] = filters["segment"]
    if filters.get("enrollment_min") is not None:
        where.append("s.enrollment >= %(enrollment_min)s")
        params["enrollment_min"] = filters["enrollment_min"]
    if filters.get("enrollment_max") is not None:
        where.append("s.enrollment <= %(enrollment_max)s")
        params["enrollment_max"] = filters["enrollment_max"]
    if filters.get("score_min") is not None:
        where.append("sc.score >= %(score_min)s")
        params["score_min"] = filters["score_min"]
    if filters.get("score_max") is not None:
        where.append("sc.score <= %(score_max)s")
        params["score_max"] = filters["score_max"]
    if filters.get("has_pto_contact"):
        where.append(
            "EXISTS (SELECT 1 FROM contacts c2 WHERE c2.school_id = s.id "
            f"AND c2.role IN {tuple(PTO_BOOSTER_ROLES)})"
        )
    if filters.get("has_verified_email"):
        where.append(
            "EXISTS (SELECT 1 FROM contacts c2 WHERE c2.school_id = s.id "
            "AND c2.email_confidence IN ('verified','high'))"
        )

    return where, params


def list_schools(conn, filters: dict, sort: str, sort_dir: str, page: int, page_size: int):
    where, params = _build_where(filters)
    sort_sql = SORT_COLUMNS.get(sort, "sc.score")
    dir_sql = "ASC" if sort_dir == "asc" else "DESC"

    sql = f"""
        SELECT
            s.id, s.name, s.city, s.state_code, s.segment, s.enrollment,
            d.name AS district_name,
            sc.score, sc.rationale,
            la.last_activity_at,
            bc.first_name AS contact_first_name, bc.last_name AS contact_last_name,
            bc.role AS contact_role, bc.email_confidence AS contact_email_confidence
        FROM schools s
        LEFT JOIN districts d ON d.id = s.district_id
        LEFT JOIN LATERAL (
            SELECT score, rationale FROM scores
            WHERE school_id = s.id ORDER BY generated_at DESC LIMIT 1
        ) sc ON true
        LEFT JOIN LATERAL (
            SELECT max(occurred_at) AS last_activity_at FROM rep_actions WHERE school_id = s.id
        ) la ON true
        LEFT JOIN LATERAL (
            SELECT first_name, last_name, role, email_confidence FROM contacts
            WHERE school_id = s.id
            ORDER BY CASE role {_ROLE_PRIORITY_SQL} ELSE 99 END, {_EMAIL_CONF_SQL}
            LIMIT 1
        ) bc ON true
        WHERE {' AND '.join(where)}
        ORDER BY {sort_sql} {dir_sql} NULLS LAST, s.name ASC
        LIMIT %(limit)s OFFSET %(offset)s
    """
    params["limit"] = page_size
    params["offset"] = (page - 1) * page_size

    count_sql = f"""
        SELECT count(*) AS n
        FROM schools s
        LEFT JOIN districts d ON d.id = s.district_id
        LEFT JOIN LATERAL (
            SELECT score FROM scores WHERE school_id = s.id ORDER BY generated_at DESC LIMIT 1
        ) sc ON true
        WHERE {' AND '.join(where)}
    """

    with conn.cursor() as cur:
        cur.execute(sql, params)
        rows = cur.fetchall()
        cur.execute(count_sql, params)
        total = cur.fetchone()["n"]

    return rows, total


def queue_school_at(conn, filters: dict, sort: str, sort_dir: str, pos: int):
    """The school at position `pos` (0-indexed) in the same ordered, filtered set
    list_schools would show - and the total count, so the queue can render 'N of M'
    and disable Next/Previous at the ends. Recomputed per request rather than storing
    a snapshot list of ids: cheap at this scale (557 schools), and it means a school
    someone else's edit removes from the filter mid-session just quietly drops out
    instead of the queue pointing at a now-wrong id."""
    where, params = _build_where(filters)
    sort_sql = SORT_COLUMNS.get(sort, "sc.score")
    dir_sql = "ASC" if sort_dir == "asc" else "DESC"

    sql = f"""
        SELECT s.id
        FROM schools s
        LEFT JOIN districts d ON d.id = s.district_id
        LEFT JOIN LATERAL (
            SELECT score, rationale FROM scores
            WHERE school_id = s.id ORDER BY generated_at DESC LIMIT 1
        ) sc ON true
        LEFT JOIN LATERAL (
            SELECT max(occurred_at) AS last_activity_at FROM rep_actions WHERE school_id = s.id
        ) la ON true
        WHERE {' AND '.join(where)}
        ORDER BY {sort_sql} {dir_sql} NULLS LAST, s.name ASC
        LIMIT 1 OFFSET %(pos)s
    """
    count_sql = f"""
        SELECT count(*) AS n
        FROM schools s
        LEFT JOIN districts d ON d.id = s.district_id
        LEFT JOIN LATERAL (
            SELECT score FROM scores WHERE school_id = s.id ORDER BY generated_at DESC LIMIT 1
        ) sc ON true
        WHERE {' AND '.join(where)}
    """
    with conn.cursor() as cur:
        cur.execute(sql, {**params, "pos": pos})
        row = cur.fetchone()
        cur.execute(count_sql, params)
        total = cur.fetchone()["n"]

    return (row["id"] if row else None), total


def get_school_detail(conn, school_id: int):
    with conn.cursor() as cur:
        cur.execute(
            """
            SELECT s.*, d.name AS district_name, d.website_url AS district_website
            FROM schools s LEFT JOIN districts d ON d.id = s.district_id
            WHERE s.id = %(id)s
            """,
            {"id": school_id},
        )
        school = cur.fetchone()
        if school is None:
            return None

        cur.execute(
            """
            SELECT score, components, rationale, score_version, generated_at
            FROM scores WHERE school_id = %(id)s
            ORDER BY generated_at DESC LIMIT 1
            """,
            {"id": school_id},
        )
        school["score_row"] = cur.fetchone()

        cur.execute(
            f"""
            SELECT * FROM contacts WHERE school_id = %(id)s
            ORDER BY CASE role {_ROLE_PRIORITY_SQL} ELSE 99 END, {_EMAIL_CONF_SQL}, last_name
            """,
            {"id": school_id},
        )
        school["contacts"] = cur.fetchall()

        cur.execute(
            """
            SELECT * FROM (
                SELECT DISTINCT ON (n.ein)
                    n.name, n.org_type, n.filing_type, n.fiscal_year,
                    n.gross_receipts, n.total_revenue, n.principal_officer_name,
                    l.confirmed, l.match_method, l.match_score
                FROM school_org_links l JOIN nonprofit_orgs n ON n.ein = l.ein
                WHERE l.school_id = %(id)s
                ORDER BY n.ein, n.fiscal_year DESC
            ) latest_per_org
            ORDER BY confirmed DESC, fiscal_year DESC
            """,
            {"id": school_id},
        )
        school["org_links"] = cur.fetchall()

        cur.execute(
            """
            SELECT * FROM signals WHERE school_id = %(id)s ORDER BY detected_at DESC
            """,
            {"id": school_id},
        )
        school["signals"] = cur.fetchall()

    school["buying_windows"] = get_buying_windows(conn, school_id)
    school["activity_groups"] = get_activity_grouped(conn, school_id)
    school["default_buying_entity"] = get_default_buying_entity(
        conn, school_id, school["contacts"]
    )

    return school


def get_buying_windows(conn, school_id: int):
    with conn.cursor() as cur:
        cur.execute(
            "SELECT * FROM buying_windows WHERE school_id = %(id)s ORDER BY updated_at DESC",
            {"id": school_id},
        )
        rows = cur.fetchall()
    today = date.today()
    for bw in rows:
        bw["status"], bw["label"] = window_status(
            bw["decision_start_month"], bw["decision_start_day"],
            bw["decision_end_month"], bw["decision_end_day"], today,
        )
    return rows


def get_activity_grouped(conn, school_id: int):
    """Reverse-chronological activity, grouped by buying_entity (brief's Phase 2 spec).
    Groups are ordered by their own most recent entry, newest group first."""
    with conn.cursor() as cur:
        cur.execute(
            """
            SELECT ra.*, u.display_name AS user_name, c.first_name, c.last_name
            FROM rep_actions ra
            LEFT JOIN users u ON u.id = ra.user_id
            LEFT JOIN contacts c ON c.id = ra.contact_id
            WHERE ra.school_id = %(id)s
            ORDER BY ra.occurred_at DESC
            """,
            {"id": school_id},
        )
        rows = cur.fetchall()

    groups, order = {}, []
    for r in rows:
        key = r["buying_entity"] or "unknown"
        if key not in groups:
            groups[key] = []
            order.append(key)
        groups[key].append(r)
    order.sort(key=lambda k: groups[k][0]["occurred_at"], reverse=True)
    return [(k, groups[k]) for k in order]


def get_default_buying_entity(conn, school_id: int, contacts: list) -> str:
    """Defaulting logic per WEBAPP_BRIEF Phase 2: 'the last one used for that school',
    falling back to a guess from whichever contact roles are actually on file."""
    with conn.cursor() as cur:
        cur.execute(
            """
            SELECT buying_entity FROM rep_actions
            WHERE school_id = %(id)s AND buying_entity IS NOT NULL
            ORDER BY occurred_at DESC LIMIT 1
            """,
            {"id": school_id},
        )
        row = cur.fetchone()
    if row:
        return row["buying_entity"]

    for c in contacts:
        if c["role"] in ("pto_president", "pto_fundraising_chair", "pto_treasurer"):
            return "pto"
    for c in contacts:
        if c["role"] == "booster_president":
            detail = (c.get("role_detail") or "").lower()
            for kw, val in _BOOSTER_KEYWORDS.items():
                if kw in detail:
                    return val
            return "unknown"
    return "school_admin" if contacts else "unknown"


VALID_CHANNELS = {"email", "phone", "video", "mail", "other"}  # rep_actions_channel_check


def school_exists(conn, school_id: int) -> bool:
    with conn.cursor() as cur:
        cur.execute("SELECT 1 FROM schools WHERE id = %s", (school_id,))
        return cur.fetchone() is not None


def contact_school_id(conn, contact_id: int):
    """The school a contact belongs to, or None if no such contact exists - used to
    reject a contact_id that's missing, mistyped, or (worst case) copied from a
    different school's page before it can reach the FK and become a 500."""
    with conn.cursor() as cur:
        cur.execute("SELECT school_id FROM contacts WHERE id = %s", (contact_id,))
        row = cur.fetchone()
        return row["school_id"] if row else None


def get_default_org_user(conn):
    """Single-tenant placeholder: the one seeded org/user (WEBAPP_PLAN.md Checkpoint 0,
    Q3) until this tool has real auth."""
    with conn.cursor() as cur:
        cur.execute("SELECT id FROM orgs ORDER BY id LIMIT 1")
        org_id = cur.fetchone()["id"]
        cur.execute("SELECT id FROM users ORDER BY id LIMIT 1")
        user_id = cur.fetchone()["id"]
    return org_id, user_id


def log_action(conn, org_id, user_id, school_id, contact_id, buying_entity, channel, outcome, notes,
               action_type="contacted"):
    """Does not commit. Both callers pair this with a second write (a follow-up, a
    dismissal) and must land both or neither - committing here is what let a rejected
    follow-up date leave the attempt logged with no follow-up attached, so the rep saw
    no change on screen and logged the same call twice."""
    with conn.cursor() as cur:
        cur.execute(
            """
            INSERT INTO rep_actions
                (org_id, user_id, school_id, contact_id, action_type, channel, outcome, buying_entity, notes)
            VALUES (%(org_id)s, %(user_id)s, %(school_id)s, %(contact_id)s,
                    %(action_type)s, %(channel)s, %(outcome)s, %(buying_entity)s, %(notes)s)
            """,
            dict(org_id=org_id, user_id=user_id, school_id=school_id, contact_id=contact_id,
                 action_type=action_type, channel=channel, outcome=outcome,
                 buying_entity=buying_entity, notes=notes),
        )


def update_action_outcome(conn, action_id: int, school_id: int, outcome: str) -> int:
    """school_id is part of the WHERE, not just something the caller passes for
    re-rendering: without it an action id from one school could be edited while the
    response rendered a different school's timeline."""
    with conn.cursor() as cur:
        cur.execute(
            "UPDATE rep_actions SET outcome = %s WHERE id = %s AND school_id = %s",
            (outcome, action_id, school_id),
        )
        n = cur.rowcount
    conn.commit()
    return n


def get_daily_priority(conn, today: date, limit: int, offset: int):
    with conn.cursor() as cur:
        cur.execute(
            """
            SELECT dp.id, dp.school_id, s.name AS school_name, s.city, s.segment,
                   dp.buying_entity, dp.rank, dp.score, dp.reason_text, dp.due_date
            FROM daily_priority dp
            JOIN schools s ON s.id = dp.school_id
            WHERE dp.generated_for_date = %(today)s
            ORDER BY dp.rank
            LIMIT %(limit)s OFFSET %(offset)s
            """,
            {"today": today, "limit": limit, "offset": offset},
        )
        rows = cur.fetchall()
        cur.execute(
            "SELECT count(*) AS n FROM daily_priority WHERE generated_for_date = %(today)s",
            {"today": today},
        )
        total = cur.fetchone()["n"]
    return rows, total


def get_next_window_summary(conn):
    """A representative 'when does anything open next' line for the priority list's
    empty state. Simplification: takes one buying_windows row rather than computing
    the true minimum across all 557 - good enough while every school shares the same
    seeded default, worth revisiting once windows start diverging for real."""
    with conn.cursor() as cur:
        cur.execute(
            """
            SELECT decision_start_month, decision_start_day, decision_end_month, decision_end_day
            FROM buying_windows ORDER BY updated_at DESC LIMIT 1
            """
        )
        row = cur.fetchone()
    if not row:
        return None
    status, label = window_status(
        row["decision_start_month"], row["decision_start_day"],
        row["decision_end_month"], row["decision_end_day"], date.today(),
    )
    return label


def dismiss_follow_up(conn, school_id: int, buying_entity: str, snoozed_until, today: date):
    """daily_priority rows don't carry a follow_up_id (no FK there - see WEBAPP_PLAN.md
    Phase 4 notes), but Phase 3's own generation rule guarantees at most one open
    follow-up per (school, entity) at a time, so that pair is enough to find it.

    Also removes the row from *today's* already-generated daily_priority snapshot -
    dismissing should disappear it now, not just stop it from reappearing tomorrow.

    Does not commit: the caller pairs this with the rep_action that records *why* it
    was dismissed, and a dismissal with no matching log entry is a lie about history.
    """
    with conn.cursor() as cur:
        if snoozed_until:
            cur.execute(
                """
                UPDATE follow_ups SET status = 'snoozed', snoozed_until = %s
                WHERE school_id = %s AND buying_entity = %s AND status = 'open'
                """,
                (snoozed_until, school_id, buying_entity),
            )
        else:
            cur.execute(
                """
                UPDATE follow_ups SET status = 'dismissed', completed_at = now()
                WHERE school_id = %s AND buying_entity = %s AND status = 'open'
                """,
                (school_id, buying_entity),
            )
        cur.execute(
            """
            DELETE FROM daily_priority
            WHERE school_id = %s AND buying_entity = %s AND generated_for_date = %s
            """,
            (school_id, buying_entity, today),
        )


def update_contact_info(conn, contact_id: int, school_id: int, email: str | None,
                        phone: str | None) -> int:
    """Fills in a missing email/phone that a rep discovered by hand - the schema
    already anticipated this via email_source='provided' and
    last_verified_method='manual' (see migrations/001_init.sql), it just had no UI.

    Scoped to school_id for the same reason the action patchers are: the id in the URL
    and the school being re-rendered have to refer to the same row."""
    sets, params = [], {"id": contact_id, "school_id": school_id}
    if email:
        sets.append("email = %(email)s, email_source = 'provided', email_confidence = 'high'")
        params["email"] = email
    if phone:
        sets.append("phone = %(phone)s")
        params["phone"] = phone
    if not sets:
        return 0
    sets.append("last_verified_at = now(), last_verified_method = 'manual'")
    with conn.cursor() as cur:
        cur.execute(
            f"UPDATE contacts SET {', '.join(sets)} "
            "WHERE id = %(id)s AND school_id = %(school_id)s",
            params,
        )
        n = cur.rowcount
    conn.commit()
    return n


def create_contact(conn, school_id: int, role: str, first_name: str, last_name: str,
                   role_detail: str | None, email: str | None, phone: str | None) -> int:
    """A rep adding a person they found by hand - the office told them who runs the PTO,
    or they read a name off a newsletter. 25 open schools have no contacts at all, and
    the PTO/booster roles the whole buying-entity model is built around exist in almost
    no public dataset (WEBAPP_PLAN.md 1.6), so hand-entry is the only path those rows
    will ever have. Written as email_source='provided' / 'manual' so it is visibly a
    human-supplied fact, not something the crawler found."""
    with conn.cursor() as cur:
        cur.execute(
            """
            INSERT INTO contacts (school_id, role, role_detail, first_name, last_name,
                                   email, email_source, email_confidence, phone,
                                   last_verified_at, last_verified_method)
            VALUES (%(school_id)s, %(role)s, %(role_detail)s, %(first_name)s, %(last_name)s,
                    %(email)s, %(email_source)s, %(email_confidence)s, %(phone)s,
                    now(), 'manual')
            RETURNING id
            """,
            dict(school_id=school_id, role=role, role_detail=role_detail,
                 first_name=first_name, last_name=last_name, email=email,
                 email_source="provided" if email else "unknown",
                 email_confidence="high" if email else "unknown",
                 phone=phone),
        )
        new_id = cur.fetchone()["id"]
    conn.commit()
    return new_id


MANUAL_FOLLOW_UP_DEFAULT_DAYS = 10  # same interval as the automated cadence baseline


def set_manual_follow_up(conn, school_id: int, buying_entity: str, due_date, reason_text: str):
    """A rep flagging 'needs follow-up' while logging an attempt. Reuses whatever open/
    snoozed follow-up already exists for this (school, entity) rather than creating a
    second one - same one-open-item-per-relationship rule the automated generator
    (ingest/phase8_follow_ups.py) already follows.

    Does not commit: paired with the rep_action it was requested from."""
    with conn.cursor() as cur:
        cur.execute(
            """
            UPDATE follow_ups
            SET due_date = %(due_date)s, reason_type = 'manual', reason_text = %(reason_text)s,
                status = 'open', snoozed_until = NULL
            WHERE school_id = %(school_id)s AND buying_entity = %(buying_entity)s
              AND status IN ('open', 'snoozed')
            RETURNING id
            """,
            dict(due_date=due_date, reason_text=reason_text, school_id=school_id, buying_entity=buying_entity),
        )
        if cur.fetchone() is None:
            cur.execute(
                """
                INSERT INTO follow_ups (school_id, buying_entity, due_date, reason_type, reason_text)
                VALUES (%(school_id)s, %(buying_entity)s, %(due_date)s, 'manual', %(reason_text)s)
                """,
                dict(school_id=school_id, buying_entity=buying_entity, due_date=due_date, reason_text=reason_text),
            )


def update_action_notes(conn, action_id: int, school_id: int, notes: str | None) -> int:
    with conn.cursor() as cur:
        cur.execute(
            "UPDATE rep_actions SET notes = %s WHERE id = %s AND school_id = %s",
            (notes, action_id, school_id),
        )
        n = cur.rowcount
    conn.commit()
    return n


def update_buying_window(conn, window_id: int, season, start_month, start_day,
                          end_month, end_day, source, notes):
    with conn.cursor() as cur:
        cur.execute(
            """
            UPDATE buying_windows
            SET season = %s, decision_start_month = %s, decision_start_day = %s,
                decision_end_month = %s, decision_end_day = %s, source = %s,
                notes = %s, updated_at = now()
            WHERE id = %s
            RETURNING school_id
            """,
            (season, start_month, start_day, end_month, end_day, source, notes, window_id),
        )
        row = cur.fetchone()
    conn.commit()
    return row["school_id"] if row else None   # None = no such window; caller 404s
