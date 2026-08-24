# Phase 6 Report — Fundraising Potential Scoring

Weights, as agreed (locale dropped entirely, its 10% redistributed to enrollment and FRL):

| Component | Weight | Signal |
|---|---|---|
| Enrollment | 0.35 | Percentile rank among all 557 open schools |
| PTO financial capacity | 0.25 | Percentile rank (log scale) of `total_revenue`, real 990/990-EZ filings only (10 schools) — everyone else neutral 5.0, not 0 |
| Household spending power (FRL, inverted) | 0.25 | `(1 - frl_pct/100) x 10`; missing FRL defaults to the statewide median |
| Segment | 0.15 | combined=10, elementary=7, high=7, middle=6, other=3 |

Score is 0-10, stored in `scores` with a per-component breakdown (`components` jsonb) and
an auto-generated rationale sentence — no model call, `scores.model` is NULL, since the
formula is fully deterministic. **557 schools scored**; PTO capacity had real (non-default)
data for 10 of them.

Two real data bugs surfaced and fixed while building this (both predate Phase 6, caught
because this phase was the first to actually need `segment` and `locale_code`):
`classify_segment()`'s grade-span thresholds were missing ND's common K-6/PK-8/7-12
configurations (268 of 557 schools, 48%, were landing in a generic `other` bucket); and
the public-school geocode parser had its columns shifted by one, so `lat` held the locale
code, `lon` held the true latitude, `locale_code` held the county name, and true longitude
was never captured at all. Both fixed; `v_combined_sites` grew from 9 to 17 rows once the
geometry was actually correct.

## Top 25

| School | City | Segment | Enroll. | FRL% | Score | Why |
|---|---|---|---|---|---|---|
| Oak Grove Lutheran School | Fargo | combined | 656 | — | 9.03 | enrollment 9.4/10; segment 10/10 |
| Dickinson High School | Dickinson | high | 1,022 | 24.3 | 8.55 | enrollment 9.7/10 |
| Light of Christ Catholic Schools | Bismarck | combined | 1,212 | — | 7.94 | enrollment 9.9/10; PTO 5.0/10 (no filing) |
| Century High School | Bismarck | high | 1,406 | 14.8 | 7.92 | enrollment 10/10 |
| Horace High School | Horace | high | 785 | 8.9 | 7.90 | enrollment 9.5/10 |
| Elk Ridge Elementary | Bismarck | elementary | 510 | 2.2 | 7.89 | enrollment 9.0/10 |
| St John Paul II Catholic Schools | Fargo | combined | 1,081 | — | 7.89 | enrollment 9.7/10 |
| Legacy High School | Bismarck | high | 1,419 | 17.8 | 7.85 | enrollment 10/10 |
| Kindred High School | Kindred | high | 258 | 7.8 | 7.78 | balanced across components |
| Fargo Davies High School | Fargo | high | 1,277 | 20.3 | 7.75 | enrollment 9.9/10 |
| Discovery Elementary | Grand Forks | elementary | 567 | 12.4 | 7.74 | enrollment 9.3/10 |
| Liberty Elementary | Bismarck | elementary | 470 | 5.7 | 7.73 | enrollment 8.8/10 |
| Red River High School | Grand Forks | high | 1,190 | 20.4 | 7.73 | enrollment 9.8/10 |
| Trinity Catholic Schools | Dickinson | combined | 562 | — | 7.72 | enrollment 9.2/10; PTO 5.0/10 |
| Trinity Elementary North | Dickinson | combined | 560 | — | 7.71 | enrollment 9.2/10; PTO 5.0/10 |
| Horace Elementary | Horace | elementary | 548 | 12.4 | 7.68 | enrollment 9.1/10 |
| Horizon Middle School | Bismarck | middle | 1,124 | 15.8 | 7.68 | enrollment 9.8/10 |
| Shiloh Christian School | Bismarck | combined | 538 | — | 7.66 | enrollment 9.1/10; PTO 5.0/10 |
| Heritage Middle School | Horace | middle | 799 | 12.6 | 7.66 | enrollment 9.5/10 |
| Bismarck High School | Bismarck | high | 1,367 | 24.4 | 7.65 | enrollment 9.9/10 |
| Williston High School | Williston | high | 1,370 | 26.5 | 7.61 | enrollment 9.9/10 |
| Mandan High School | Mandan | high | 1,175 | 25.0 | 7.61 | enrollment 9.8/10 |
| Minot North High School | Minot | high | 1,021 | 23.5 | 7.59 | enrollment 9.7/10 |
| Victor Solheim Elementary | Bismarck | elementary | 588 | 19.6 | 7.58 | enrollment 9.3/10 |
| Jamestown High School | Jamestown | high | 722 | 21.6 | 7.58 | enrollment 9.5/10 |

**Reads as expected:** the state's biggest schools (Fargo/Bismarck/Grand Forks/Williston/
Minot/Dickinson/Jamestown metro areas), plus every combined-K-12 private school gets a
real lift from the segment bonus on top of solid enrollment.

## Bottom 25

| School | City | Segment | Enroll. | FRL% | Score | Why |
|---|---|---|---|---|---|---|
| Fort Yates PK School | Fort Yates | elementary | 10 | 100 | 2.44 | FRL 0/10 |
| Four Winds Community PK | Fort Totten | elementary | 16 | 100 | 2.56 | FRL 0/10 |
| Selfridge High School | Selfridge | high | 30 | 100 | 2.68 | FRL 0/10 |
| Explorer Academy | Fargo | elementary | 34 | 100 | 2.70 | FRL 0/10 |
| Fort Yates Middle School | Fort Yates | middle | 46 | 100 | 2.73 | FRL 0/10 |
| Tiny Turtles Preschool | Belcourt | elementary | 38 | 100 | 2.78 | FRL 0/10 |
| Warwick Middle School | Warwick | middle | 52 | 100 | 2.84 | FRL 0/10 |
| Selfridge Elementary | Selfridge | elementary | 45 | 100 | 2.86 | FRL 0/10 |
| Willow Bank Colony School | Edgeley | elementary | 27 | 88.9 | 2.91 | FRL 1.1/10 |
| Warwick High School | Warwick | high | 48 | 100 | 2.91 | FRL 0/10 |
| LaMoure Colony School | LaMoure | elementary | 21 | 85.7 | 2.94 | enrollment 0.8/10 |
| Sundale Colony Elementary | Milnor | elementary | 35 | 91.4 | 2.94 | FRL 0.9/10 |
| Marmot School 6-12 | Mandan | high | 20 | 85.0 | 2.95 | enrollment 0.8/10 |
| Oberon Elementary | Oberon | elementary | 52 | 100 | 2.99 | FRL 0/10 |
| School for the Deaf PK-8 | Devils Lake | elementary | 16 | 81.3 | 3.01 | enrollment 0.7/10 |
| Twin Buttes Elementary | Halliday | elementary | 55 | 100 | 3.03 | FRL 0/10 |
| Sundale Colony High School | Milnor | high | 13 | 76.9 | 3.07 | enrollment 0.6/10 |
| Wheatland Colony School | Tower City | elementary | 10 | 70.0 | 3.20 | enrollment 0.4/10 |
| Minnewaukan High School | Minnewaukan | high | 71 | 91.6 | 3.44 | FRL 0.8/10 |
| South Central Alternative HS | Bismarck | high | 97 | 99.0 | 3.57 | FRL 0.1/10 |
| Solen High School | Solen | high | 99 | 100 | 3.59 | FRL 0/10 |
| Warwick Elementary | Warwick | elementary | 99 | 100 | 3.60 | FRL 0/10 |
| Cannon Ball Elementary | Cannon Ball | elementary | 115 | 100 | 3.75 | FRL 0/10 |
| Zeeland High School | Zeeland | high | 14 | 50.0 | 3.78 | enrollment 0.7/10 |
| Fairmount High School | Fairmount | high | 45 | 60.0 | 3.85 | PTO 5.0/10; enrollment 1.6/10 |

## A pattern worth your explicit sign-off, not just a sanity check

The entire bottom 25 is tiny schools (10-115 students) with very high FRL — mostly Standing
Rock and Spirit Lake reservation communities (Fort Yates, Selfridge, Cannon Ball, Four
Winds, Solen, Minnewaukan) and Hutterite colony schools (Willow Bank, LaMoure, Sundale,
Wheatland). That's the FRL-inverted and enrollment components doing exactly what they were
built to do — small, low-income communities score as lower *catalog-dollar* potential. It's
not a bug. But it's a real modeling choice with a real-world edge to it: this ranking would
deprioritize outreach to Native American reservation schools and colony schools as a class,
purely on a household-income proxy. Worth deciding consciously rather than letting the
formula make that call by default - whether that's the right call for how you want to sell,
or whether some of these communities warrant a different approach the score doesn't capture.

## What's not built yet

- `scores.territory_id` stays NULL for every row (no territories exist to score against -
  removed with the routing tables). If territories come back for some other reason later,
  scoring would need a territory-relative variant.
- Re-scoring on a schedule (next season's enrollment/FRL, more IRS filings) isn't automated -
  this is a one-time `v1` run. Re-running `phase6_scoring` inserts fresh `v1` rows rather
  than updating in place, per the schema's append-only-history principle.
