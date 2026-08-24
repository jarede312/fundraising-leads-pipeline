# Phase 3 Report — Email Pattern Derivation

Built entirely from the 986 contacts Phase 2 loaded (no Phase 3a site-crawl needed yet —
DPI's directory alone gave enough evidence to resolve nearly every operating district).

## Pattern distribution and confidence tiers

167 of 169 operating districts got a pattern from direct evidence; 2 tiny (1-school)
districts have zero contacts yet and stayed `unknown` (Ft Ransom 6, ND Vision
Services/School for the Blind) — both show up correctly in `v_email_pattern_gaps`.

| Confidence | Districts | Meaning (per schema) |
|---|---|---|
| high | 48 | 3+ known addresses confirm the pattern |
| medium | 119 | 1-2 known addresses confirm it |
| unknown | 2 | no contacts yet |

| Pattern | Districts |
|---|---|
| first.last | 153 |
| flast | 6 |
| custom | 4 |
| first_last | 1 |
| firstlast | 1 |
| lastf | 1 |
| firstl | 1 |

`first.last` dominates (92% of resolved districts) — North Dakota's schools are heavily
concentrated on a shared `k12.nd.us` mail platform (362 of 986 contacts, spanning dozens of
small districts) that uses this convention uniformly, plus most of the larger districts
running their own domain independently landed on the same convention.

**Added a pattern not in the brief's suggested list:** `firstlast` (full name concatenated,
no separator — e.g. `violaslater@mandareeschool.org`). The schema uses text+CHECK
specifically so this is easy to extend; no migration needed, no constraint to update.

**The 4 remaining `custom` districts are genuinely irreducible, not classifier failures** —
I caught and fixed two real bugs first (below) before accepting these as real:
- Kensal 19, Nesson 2: the on-file name is a nickname ("Matt" for Matthew, "Rob" for
  Robert) that doesn't match the real account's formal-name convention.
- Mandaree 36: resolved once I added `firstlast`.
- Menoken 33: a genuinely tiny district (personal Gmail + a bare-lastname address) — 1-2
  contacts, no real pattern to find yet.
- ND School for the Deaf: single sample, first.middle-initial.last — not enough evidence
  either way.

## Two real bugs I found and fixed before trusting any of this

1. **Case-sensitivity bug in my own classifier.** `Shannon.Faller@k12.nd.us` for Shannon
   Faller was being marked as not matching `first.last` — I normalized the person's name
   to lowercase for comparison but forgot to lowercase the email's local-part itself. Fixed;
   confidence tiers moved from 28 high/139 medium to the corrected 48 high/119 medium above.
   Flagging this plainly since it changed the numbers I'd have otherwise reported.
2. Not a bug, but worth stating: I do **not** attempt to resolve nicknames (Dave/David,
   Rob/Robert) or which half of a hyphenated surname a district's convention uses. Both
   showed up in the validation sample below and both are inherent limits, not something a
   smarter regex fixes.

## Validation demo (in place of "20 derived addresses" against real gaps)

There are currently **zero named-but-emailless contacts** to derive real addresses for —
Phase 2 came in at 100% email coverage, so there's nothing missing yet to demonstrate
against. That changes once Phase 5's site crawl finds staff names with no listed email.
To still give you a real signal now, I hid the known email for 20 real contacts, ran the
derivation formula blind, and compared:

**10/20 matched exactly** on a sample I deliberately skewed toward `high`-confidence
districts (to stress-test the strongest cases, not the easy ones) — see
`ingest/phase3_validate.py`. The misses were not random noise; they cluster into three
real, specific findings:

**1. Grand Forks 1 (18 schools, your #4 district by enrollment) requires an opaque numeric
ID that can't be derived from a name at all.** All 62 known Grand Forks addresses are
`flast` **plus a per-employee number** (`mnistler170`, `dwalters150`, `mdiischer130` —
these vary widely, not a simple sequential tiebreaker). I added a `requires_suffix` flag to
the evidence and it fired for exactly one district: Grand Forks. Its pattern is correctly
classified (`flast`, `high` confidence — 62 consistent addresses is real evidence), but
"high confidence this describes the known people" is not the same as "high confidence I
can build a working address for someone new," and for Grand Forks specifically those are
different answers. Derivation there needs a real address on file already, not a formula.

**2. Fargo 1 looks like a legacy truncated-username system, not clean `lastf`.** Short
names matched fine (`dietrik` for Dietrich, once you know it's not simply "last name +
first initial" but something closer to an 8-character SAM-account-style truncation), but
`mckennm@fargoschools.org` for "Mckenney" only makes sense as roughly
"last-name-truncated-to-6 + first-initial" — a real, different rule my classifier doesn't
model, that happened to coincidentally satisfy `lastf` for shorter names in the sample.

**3. Hyphenated surnames are handled inconsistently across districts**, not just
inconsistently by me. West Fargo kept a hyphen in a real address
(`jsjolin-nelson@west-fargo.k12.nd.us`); elsewhere (Starkweather) the real convention drops
everything after the hyphen (`sarah.beck`, not `sarah.beckconnot`). No single normalization
rule gets both right — this is genuine cross-district variance, not a bug to fix.

None of this changes the aggregate confidence tiers above (those measure something real:
consistency among known addresses), but it does mean **"high confidence" should not be
read as "safe to blind-derive" for every high-confidence district** — Grand Forks is the
clear case, and Fargo deserves a second look before you rely on derived addresses there.
Both are top-4 enrollment districts, so this isn't a tail concern.

## `v_email_pattern_gaps`, ranked

Only 2 rows — both tiny, both zero contacts, both `names_without_email = 0` (nothing to
chase yet, since there are no named contacts at either at all):

| district | confidence | names_without_email | schools |
|---|---|---|---|
| ND Vision Services/School for the Blind | unknown | 0 | 1 |
| Ft Ransom 6 | unknown | 0 | 1 |

This view will get more interesting once Phase 5 starts finding named staff without a
listed email — right now there's simply nothing in that bucket yet.

## Question

**Email verification service — before or after you test deliverability manually on a
few?** My recommendation: test manually first, and specifically on Grand Forks and Fargo
derived-not-verified addresses (where I've just shown real risk), not just anywhere. A
verification service is worth paying for once you know roughly what fraction of derived
(not directly-known) addresses actually deliver; right now nearly every address in the
database is a *directly observed* one from Phase 2 (real, not derived), so there's nothing
to verify yet — this becomes relevant once Phase 5 starts producing name-only records that
get filled in via `derive_email()`.
