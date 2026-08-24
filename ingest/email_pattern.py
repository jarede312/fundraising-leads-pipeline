"""Shared email-derivation function: given a district's stored pattern + domain and a
person's name, construct the predicted address. Used by Phase 5 (staff crawl finds a name
with no listed email) and by the Checkpoint 3 validation demo (this module has no CLI of
its own)."""
import re


def normalize(s):
    return re.sub(r"[^a-z]", "", (s or "").lower())


def derive_email(first, last, pattern, domain):
    f, l = normalize(first), normalize(last)
    if not f or not l or not domain:
        return None
    local_by_pattern = {
        "first.last": f"{f}.{l}",
        "first_last": f"{f}_{l}",
        "firstlast": f"{f}{l}",
        "lastf": f"{l}{f[0]}",
        "flast": f"{f[0]}{l}",
        "firstl": f"{f}{l[0]}",
        "first": f,
    }
    local = local_by_pattern.get(pattern)
    if local is None:
        return None
    return f"{local}@{domain}"
