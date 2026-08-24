"""LLM-based contact extraction from a school/district staff page's plain text.
Shared by the Phase 5 prototype and (once approved) the full crawl.

Uses structured outputs (Pydantic + client.messages.parse()) rather than prompt-only JSON
instructions - an earlier prototype pass without this showed the model occasionally
prefacing its answer with prose or an echo of the page content before the JSON, which a
plain json.loads() correctly rejected rather than silently accepting. output_format
guarantees a schema-valid response, so that failure mode can't happen.
"""
from typing import Optional

import anthropic
from pydantic import BaseModel

from . import config

SCHEMA_ROLES = [
    "principal", "assistant_principal", "office_manager", "music_teacher",
    "band_director", "choir_director", "drama_director", "activities_director",
    "athletic_director", "pto_president", "pto_fundraising_chair", "pto_treasurer",
    "booster_president", "superintendent", "other",
]

SYSTEM_PROMPT = f"""You extract staff/board contact information from a school or school \
district web page's plain text, for a sales-prospecting database. You will be shown the \
raw text of one page.

Rules, followed exactly:
1. Never invent a contact, a name, a title, an email, or a phone number. If a fact is not \
literally present in the text, leave that field null. Do not guess someone's role from \
context clues like which section heading they appear under, unless the text itself states \
their title.
2. Only extract people whose name appears with at least some identifying context (a title, \
a role, or a clear staff-listing structure). Do not extract names from unrelated content \
(news stories, testimonials, alumni mentions).
3. For each person, classify their role into exactly one of these schema values if it \
clearly fits: {", ".join(SCHEMA_ROLES)}. Use "other" if a title is present but doesn't map \
cleanly to one of these (e.g. "Librarian", "Cook", "Secretary" of a school board). Use null \
for role if no title/role information exists for that person at all (e.g. a bare name list).
4. role_detail should be the title exactly as printed on the page (verbatim), or null if \
none was given.
5. If the page has no staff/contact information at all (navigation-only, JavaScript- \
rendered placeholder, unrelated content), return an empty contacts list.
"""


class ContactRecord(BaseModel):
    first_name: Optional[str] = None
    last_name: Optional[str] = None
    role: Optional[str] = None
    role_detail: Optional[str] = None
    email: Optional[str] = None
    phone: Optional[str] = None


class ExtractionResult(BaseModel):
    contacts: list[ContactRecord]
    page_had_staff_content: bool


# $ per 1M tokens (input, output), so cost_usd tracks whichever model LLM_MODEL is set to.
PRICING = {
    "claude-opus-5": (5.0, 25.0),
    "claude-sonnet-5": (3.0, 15.0),
}


def extract(page_text: str, source_url: str) -> dict:
    client = anthropic.Anthropic(api_key=config.ANTHROPIC_API_KEY)
    resp = client.messages.parse(
        model=config.LLM_MODEL,
        max_tokens=16000,
        system=SYSTEM_PROMPT,
        messages=[{"role": "user", "content": f"URL: {source_url}\n\nPAGE TEXT:\n{page_text}"}],
        output_format=ExtractionResult,
    )
    result: ExtractionResult = resp.parsed_output
    usage = resp.usage
    in_rate, out_rate = PRICING.get(config.LLM_MODEL, PRICING["claude-opus-5"])
    cost_usd = (usage.input_tokens * in_rate + usage.output_tokens * out_rate) / 1_000_000
    return {
        "contacts": [c.model_dump() for c in result.contacts],
        "page_had_staff_content": result.page_had_staff_content,
        "_usage": {
            "input_tokens": usage.input_tokens,
            "output_tokens": usage.output_tokens,
            "cost_usd": round(cost_usd, 5),
        },
    }
