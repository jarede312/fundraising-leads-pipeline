# Prospect Engine — Beta Feedback

**To:** President
**From:** Senior Sales Rep / Regional Sales Manager (beta tester)
**Re:** 30-day evaluation of Prospect Engine, ND territory
**Date:** 2026-09-22

> **Note on this document:** this is *simulated* persona feedback written by an AI acting as a
> senior fundraising sales rep, based on a direct inspection of the running application and its
> live database on 2026-08-23. It is intended as a comparison baseline against feedback from a
> real rep. It is not a record of an actual person's experience. Every number cited was pulled
> from the actual database or source files, not invented.

---

## 1. Bottom line

**Keep building it. Do not roll it out to the team yet.**

In thirty days this thing replaced my spreadsheet, my sticky notes, and about half of my
Google searching. That's real. Before this, prospecting a new state meant me and a legal pad
and three hours on district websites before I dialed anything. Now I open a browser and there
are 557 North Dakota schools with a principal's name, a phone number, an enrollment count, and
a reason to call. That is genuinely the best prospecting asset anybody has handed me in fifteen
years of doing this.

But it is a **prospecting list with a call log stapled to it**, and right now it is being
presented as a system. Two things stop me from recommending you put this in front of the other
reps in its current state:

1. **It cannot tell me who bought.** There is no way to record a sale. Not a won deal, not a
   dollar amount, not a program type. Thirty days of my calls are in there and the tool cannot
   answer "did any of this work?" For me that's annoying. For you, running a sales org, that
   makes it unmanageable — you cannot coach off it, forecast off it, or justify it.
2. **It is a single-user tool with no login.** One user account exists, and it is literally
   named "Placeholder Rep." There is no ownership, no territory assignment, no way to stop two
   reps from calling the same principal on the same Tuesday. The moment a second person opens
   this, we have a problem, not a tool.

Fix those two and a handful of trust bugs below, and I'd fight to get this in front of everyone.

---

## 2. First impressions — day one

Honest reaction, in order:

**Minute 1: relief.** It's fast, it's plain, it loads instantly, and there is no onboarding
wizard. Three links across the top — Today, All Schools, Guide. I knew what to do without being
told. After the CRM we tried two years ago, that alone bought a lot of goodwill.

**Minute 3: skepticism.** The home screen said "Today" and showed me fifteen schools. My first
thought was *who decided these fifteen?* I clicked one, saw a score of 8.32, and immediately
wanted to know what that meant. There is a hover tooltip and there's a Guide page, which is more
than most tools give you — but a number I don't understand sitting at the top-right of every
page is a thing I distrust by default. Reps have all been handed a "lead score" before that
turned out to be someone's guess with decimals on it.

**Minute 10: genuine excitement.** The school detail page has the principal, the music teacher,
enrollment, the school's main line, the district, and — this is the part that got me — a linked
IRS nonprofit filing with the PTO's actual gross receipts. I have never had that. Knowing a PTO
cleared $84,000 last year before I dial changes the entire conversation. That is a real edge and
nobody else on our team has it.

**Day 3: the first crack.** I noticed that every single item on my Today list said the exact
same thing: *"Never contacted."* All fifteen. Same reason, every day. That's when I realized
Today isn't a smart list — it's the score list, top fifteen, with a sentence under each row.

---

## 3. What's genuinely good — keep all of this

- **The data itself.** 557 open ND schools, 221 districts, 1,269 contacts, 90% of schools with a
  usable phone number. Coverage is far better than anything I could assemble by hand.
- **The IRS nonprofit layer.** 43 confirmed PTO/booster org links with real 990 financials on 33
  of them. This is the single most differentiated thing in the tool. More on how to exploit it in
  §11.
- **Queue mode.** "Work this list" is the right idea and it's implemented correctly. Filter to
  "elementary, enrollment 300+, has a high-confidence email," hit Work this list, and I'm walking
  school-to-school without bouncing back to a table. This is how I actually work. Whoever
  designed this understood a calling session.
- **One-click logging.** Called / Left message / Emailed / Video / Mailed as five buttons with no
  modal is exactly right. The "Different result?" chips to correct an outcome after the fact are
  a genuinely thoughtful touch — I mis-click constantly and I've never once had to delete and
  re-enter.
- **Filters live in the URL.** I have four bookmarks in my browser bar that are really four saved
  prospect lists. Accidental feature, and one of the three things I use most.
- **The Guide page.** Rare and appreciated. Written like a person wrote it. It's also currently
  wrong in three places (§4), which is worse than not having it.
- **No red overdue badge.** Whoever made that call, thank you. Every CRM I've used punishes you
  for having a life. This one doesn't.

---

## 4. Things that are actually broken

These are bugs, not opinions. I hit each of them in normal use.

### 4.1 The keyboard shortcuts don't work — but the Guide says they do

The Guide has a whole table: `c` = Called, `l` = Left message, `e` = Emailed, `v` = Video,
`m` = Mailed, `n` = notes. I built my whole calling rhythm around this on day one. **None of
them fire on a school page or in queue mode.** I spent the better part of an afternoon thinking
I was doing something wrong.

The cause is in the code: the shortcut handler looks for a logging block marked `primary-log`,
but every logging block on the page renders as `compact` instead. So the handler finds nothing
and silently does nothing. Same for `n` — it looks for a notes field called `notes-default` that
doesn't exist; the real ones are named per-contact.

`Enter` for next-school in queue mode and `j`/`k` on the list *do* work, which made it more
confusing — some shortcuts work, so I assumed the others were my error.

**This is close to a one-line fix and it's the highest-value bug on this list.** The entire pitch
of this tool is "hands stay on the keyboard for a thirty-call session." Right now it's a mouse
tool.

### 4.2 "Snooze 1 week" deletes the school from Today permanently

I snoozed a couple of schools where the principal said "call me after Labor Day." They never
came back. I checked — nothing in the system ever un-snoozes a follow-up. It gets marked
snoozed, the date is stored, and then no job or page load ever flips it back to open. Worse, the
nightly generator treats a snoozed item as "already handled," so it won't create a new reminder
for that school either.

**Snooze is a black hole.** Two schools in my territory are currently invisible and I only know
because I went looking. If I'd trusted it, I'd have lost them. This is the bug that would cost
us real money, because it silently loses the *warmest* leads — the ones where someone told you
when to call back.

### 4.3 "Done for now" comes back in about ten days — the Guide says it clears permanently

The Guide states that *Done for now* and *Not interested* "clear it permanently." *Not
interested* does. *Done for now* reappears roughly ten days later on the cadence timer. I'm not
sure that behavior is wrong — arguably it's right — but the Guide describing it wrong meant I
used the wrong button for two weeks.

### 4.4 There is no undo on a logged action

I can change the outcome and add a note after the fact. I cannot delete an entry. I logged a
call against the wrong school twice in a month (queue mode moves fast). That wrong entry is now
permanent, it counts as a contact attempt, and it resets that school's cadence clock — so a
school I never actually called is now suppressed from Today for ten days because of my typo.
Every logging tool needs a delete. This one has none.

### 4.5 I can't back-date an activity

Every logged action is stamped with the moment I click the button. I make calls from the car and
from my kitchen and log them that night. All thirty show up in the timeline as 9:40pm–9:52pm,
which is nonsense for anyone reading it later, including me. A simple date/time field on the log
row — defaulted to now, editable — solves this.

### 4.6 Signals are advertised everywhere and have never fired once

The Guide dedicates a section to them. Every school page has a Signals card. The follow-up
engine has a whole branch for them. **The signals table has zero rows and has never had one.**
There is no job that creates them.

"New principal at a school you've been working" is *the* highest-value trigger in this business,
and the tool promises it on every single page and has never delivered one. After a month of
seeing "No signals detected yet" 200 times, I've stopped reading that section — which means when
it does start working, I won't notice. Either build the detector or take the section out until
you do.

---

## 5. The data — trust is the whole product, and the trust labels are backwards

This is the finding I'd most want you to read.

There are 1,269 contacts. Their confidence labels break down as: 1,060 "medium," 167 "high," 42
"unknown." **Zero have ever actually been validated** — no address in the system has been
confirmed deliverable or flagged bad.

Now the part that matters. I went and checked where those addresses actually came from:

| What the badge says | How many | Where the address actually came from |
|---|---|---|
| 🟠 "Derived — medium confidence" | 986 | **The official state DPI directory.** Real, published addresses. |
| 🟢 "High confidence" | 86 | **Guessed** from a name plus a district email pattern. |
| 🟢 "High confidence" | 77 | Found on a real page. Fine. |
| 🟠 "Derived — medium confidence" | 74 | Actually derived. Fine. |

**The two big buckets are inverted.** The 986 addresses pulled straight out of the state's own
directory are labeled *"Derived"* in amber — the word literally means "we guessed this." And 86
addresses that genuinely *are* guesses render in green as *"High confidence."*

I spent my first two weeks avoiding amber contacts because I'd been told amber meant guessed.
I was avoiding the best data in the system and preferentially emailing the guesses. The design
principle in your own docs is "if the user can't tell good data from guesses, they'll distrust
all of it." That's right — and the current mapping does exactly the harm it was written to
prevent.

**Fix:** label by *source*, not by an internal confidence rating. "State directory," "Found on
school site," "Pattern guess — unverified," "Confirmed by me." A rep understands those four
phrases instantly and needs no legend.

### 5.1 The PTO data isn't there, and PTO is who signs

This is the gap between what the tool is *designed* for and what it can *do*.

- 26 schools out of 557 have a PTO president name. **One** has an email. **Zero** have a phone.
- 9 booster contacts. Zero emails, zero phones.
- 4 office managers — and the office manager is the person who actually gets me to the PTO.
- Meanwhile: 634 principals and 356 music teachers.

The entire "buying entity" model — PTO, PTA, Band Boosters, Choir, Drama, Athletic — is built
and working, and **all 546 open follow-ups are filed under "School Admin"** because there is
nothing else to file them under. It's a beautifully constructed filing cabinet with one folder
in it.

I don't sell to principals. I sell to whoever runs the fundraiser, and in elementary that's the
PTO president, and in high school it's a band or athletic booster parent. This tool gets me to
the front office and stops. That's still useful — the front office is how you find the PTO
president — but let's be honest that the last mile is entirely manual.

**Highest-leverage data work you could fund:** the IRS layer already has 143 nonprofit orgs with
a principal officer's name on them. That's a named PTO officer, sitting in the database, not
surfaced as a contact. Turning those into real contact records — even name-only, no email —
would multiply the PTO coverage several times over for basically no new data acquisition. The
name alone changes a cold call: *"I'm trying to reach Jennifer Halvorson, I think she's with the
PTO?"* gets transferred. *"Can I speak to whoever runs your fundraisers?"* gets voicemail.

### 5.2 Deliverability — a real risk before anyone hits Send

986 unvalidated addresses. If we ever add email sending, or if a rep exports and blasts from
their Outlook, we'll bounce hard enough to hurt our sending domain. Nothing in the tool warns
about this. Validate before we build sending, not after.

---

## 6. The score — I don't trust it yet, and here's specifically why

I like that a score exists. I like the rationale sentence. Three real problems:

**It barely discriminates.** Every school in the state scores between 3.33 and 8.45, and 63% of
them land between 5.0 and 6.9. The standard deviation is about 1.0. Ten percent of schools are
below 4.6 and ten percent are above 7.3, so the entire middle 80% of my territory is compressed
into a 2.7-point band. Practically, that means the score sorts my top 30 and my bottom 30 and
tells me nothing at all about the 500 in between. A 6.1 and a 5.4 are indistinguishable in real
life but the tool renders them to two decimals as if the difference were meaningful.

**It's mostly enrollment wearing a costume.** The correlation between enrollment and score is
0.73. Enrollment is 30% of the formula directly — but "PTO capacity" is a flat 5.0 for 98% of
schools (only 10 have real 990 financials), so 15% of the score is a constant that discriminates
nothing, and enrollment effectively dominates what's left. I could sort by enrollment and get
nearly the same call list.

**It doesn't know anything about selling.** Look at the top 20: it's Bismarck, Mandan, Fargo,
Minot, Dickinson. Big metro schools. Those are also the schools with three vendors already in
the building and a district purchasing policy. Meanwhile the 320-student school in Bottineau
where the AD answers his own phone and the booster club will run whatever you put in front of
them barely clears the cut, and the 200-student version of it scores a 5.4 and I'll never see it
on Today.

**The score is measuring size, not winnability.** Those aren't the same thing and in this
business they're often opposed.

What I'd actually want weighted in, roughly in order of how much it would change my day:

1. **Do we have a named PTO/booster contact?** (Currently folded into "contactability" at 20%,
   but a principal's guessed email scores the same 10/10 as a verified PTO president's. Those
   are not the same lead.)
2. **Have they run a fundraiser before?** The 990 filings tell you this. A PTO that files a
   990-EZ with $40K of revenue is *already buying from somebody.* That's a competitive takeaway,
   which is the easiest sale in this business, and the tool treats it as one-fifteenth of a
   score.
3. **Are we already in the district?** If we sold the middle school, the elementary is a warm
   call. The tool has districts and knows nothing about this.
4. **Enrollment.** Yes, it matters. Not 30% worth, and not as a percentile against a state where
   most schools are small.
5. **Segment.** Fine as-is.

And practically: **show it as a letter or a band, not 8.32.** A / B / C tiers, or just Hot /
Good / Cold. Two decimals on a number this soft is false precision and it invites exactly the
argument I'm having with you right now.

One thing the scoring did do that impressed me: it caught that 22 schools sitting at 100%
free-and-reduced-lunch were CEP schools, where that number is a funding formula artifact rather
than actual household income, and stopped penalizing them for it. Those are reservation and
colony schools. Getting that wrong would have quietly buried a set of communities that in my
experience fundraise *hard*. Somebody was paying attention.

---

## 7. "Today" — the best idea in the tool and the least finished

The concept is right: open the laptop, get a short list, work it, close the laptop. No backlog
counter. I want this to work.

Here's what it actually is right now. There are 531 items in the Today queue. **545 of the 546
open follow-ups say "Never contacted."** All of them are filed under School Admin. So the
ranking degenerates to: *every school in North Dakota, sorted by score, fifteen at a time.*

Which means:

- **Every reason line is identical.** "Never contacted." Fifteen times, every morning, for a
  month. The design doc says a row without a "why" is noise — correct — but fifteen rows with the
  *same* why is the same noise with extra steps.
- **Today and All Schools are the same screen.** Today is All Schools sorted by score, truncated
  to fifteen. I stopped using Today around week two and just worked filtered lists from All
  Schools, because at least there I chose the filter.
- **The math doesn't close.** 531 items at 15/day is 35 days to get through the state — but the
  cadence timer re-fires every 10 days on anything I've touched. The list can never be worked
  down. That's fine philosophically ("it just competes for a slot tomorrow"), but combined with
  identical reasons it means Today has no memory and no narrative. It never says *"you talked to
  this person three weeks ago and she asked you to call back."* That's the reminder I actually
  need, and it's the one thing this list will never surface until there's real history in it.
- **Decision windows were switched off.** All 557 schools got seeded with the same placeholder
  window (April 1 – June 15) and the window trigger was disabled because "everybody is in-window"
  made it meaningless. Understandable call. But it means the single most important thing about
  school fundraising — *timing* — is currently not an input to anything.

That last point deserves emphasis, because it's a sales fact the tool doesn't yet know:

> **Fall fundraiser decisions get made in April, May, and early June, before school lets out.
> Spring decisions get made in October and November.** A call in late July to an elementary
> school is a call to an empty building. A call in mid-May to that same school is the whole
> ballgame. Right now the tool will hand me the same fifteen schools in July that it hands me
> in May.

If you fix one thing about Today, make it **seasonally aware**. Even crudely: elementary/PTO
gets pushed hard April–June, high school boosters get pushed August–September for spirit wear
and October–November for spring programs, and almost nothing gets pushed in July. That single
change makes Today worth opening.

---

## 8. Interface and usability notes

Mostly small. The UI is clean and I have very few complaints about how it looks.

- **The Today reason text is smaller than the school name it explains.** Reverse that. The reason
  is the reason I'm calling.
- **"Dismiss" is hidden behind a disclosure triangle** and the options only appear after a click.
  That's two clicks to snooze. Make them inline buttons.
- **Contact cards on big schools are exhausting.** 28 schools have more than six contacts. Some
  detail pages are a lot of scrolling to find one phone number. Collapse everything below the
  top two roles by default.
- **Every contact card has its own five logging buttons.** Visually that's 30+ buttons on a busy
  page. I'd rather have one logging bar pinned to the bottom of the screen with a "who did you
  talk to?" dropdown.
- **No global search.** Search only exists on All Schools. When a principal calls me back, I want
  to type their name from wherever I am. Put the search box in the top nav.
- **Two decimal places on the score.** See §6.
- **There is no district page.** 221 districts, 49 superintendents on file, and no way to see them
  as a unit. In this business you sell a district, not a school — the same superintendent, the
  same purchasing policy, often the same PTO parents across two buildings. Also, 43 open schools
  have no district linked at all and there's no way to see or fix that from the app.
- **Queue mode navigates by position, not by school.** If I sort by "Last Activity" and then log
  a call, the list reorders underneath me and Next can skip or repeat a school. Sorting by score
  is stable, so this only bites on some sorts, but it bit me twice.
- **No print/export.** I still want a CSV sometimes, for a call sheet or to hand my manager a
  list. Right now that requires someone running a script.
- **Nothing tells me the data's age.** Principals turn over in June and July. A directory pulled
  in August is good for a year; one pulled two years ago is a liability. Put "Directory data as
  of [date]" somewhere visible.

---

## 9. What's missing for a rep — the sales workflow gaps

Ranked by how much I felt the absence.

**1. I cannot record a sale.** Not a proposal, not a quote, not a close, not a dollar. The
database has slots for "quoted," "won," and "lost" and there is no button anywhere that writes
one. So the tool knows I made 29 calls and has no idea that three of them turned into programs.
This is the thing that makes it a call log instead of a sales tool.

**2. No pipeline view.** Everything is either "a school" or "an activity." There's no concept of
an opportunity with a stage, a dollar value, and a close date. I don't need a fourteen-stage
enterprise pipeline — four stages would do it: Contacted → Interested → Proposal Out → Closed.

**3. No account history across seasons.** School fundraising is a renewal business. Whether they
ran with us last fall, what they sold, what they made, and who ran it is more predictive than
every scoring input combined. The tool has no memory of prior business, which means it treats a
school we've served for six years exactly like a cold one.

**4. No competitor field.** "They're with [competitor], contract's up in spring" is the single
most valuable sentence I collect on a call. Right now it goes in a free-text note that nothing
can search or report on. Make it a field.

**5. No email templates or send.** I understand this was deliberately out of scope, and I'm not
asking for a sequencer. But I retype the same three intro emails forty times a week. Even a
copy-to-clipboard template with the school name and contact merged in would save me an hour a
week. (See §5.2 before enabling actual sending.)

**6. No call script or talk track on the page.** Especially for new reps. A small collapsible
panel with the opener and the three objection responses, right next to the dial button, would
cut ramp time for a new hire substantially.

**7. No task or reminder that isn't tied to a school.** "Send Jennifer the catalog PDF" has
nowhere to live.

**8. No mobile.** I know that was a deliberate scope decision and I understand why. But I make a
meaningful share of my calls away from my desk, and logging from my phone would materially
improve how complete the activity log is. Flagging it as a real cost of that decision, not
arguing the decision.

---

## 10. What's missing for a rollout — the blockers, from a manager's chair

You asked whether the rest of the company can use this. Not yet, and the reasons are structural
rather than cosmetic.

**No authentication and no users.** There is one account. It is named "Placeholder Rep." Anyone
who can reach the URL can see and change everything. That's fine for me alone on my laptop. It
is not fine for a team, and it is definitely not fine given we're storing named contact
information for public school employees across an entire state.

**No territory or ownership model.** There's a territories concept in the database with zero
rows in it. Nothing assigns a school to a rep. Two of us will call the same principal within a
week of each other and look like amateurs.

**No management reporting whatsoever.** I cannot answer, for myself or for you: how many dials
this week, contact rate, conversion by segment, which reps are working their lists. Since we
also can't record sales (§9.1), there is no closed loop at all — the tool can never learn or
prove which schools are actually worth calling.

**No audit trail across users.** Every action is stamped to the same placeholder user.

**One state.** This is ND-only by design. Whatever we do next needs to work when it's 15,000
schools, not 557 — the current pages re-query and re-count on every request, which is instant at
this size and worth load-checking before it isn't.

**No backup or data-loss story that I'm aware of.** Thirty days of my call notes exist in one
database on one machine. If that's not backed up, please make it so before anyone else's month
of work goes in there.

---

## 11. Ideas — where this gets genuinely valuable

Some of these are cheap. I've marked what I think each is worth.

- **Surface the IRS principal officers as contacts. [High value, low cost.]** Already discussed
  in §5.1. Names we already own, sitting unused, for the exact role we most need.
- **"Competitive takeaway" list. [High value, low cost.]** Filter: PTO files a 990 or 990-EZ with
  real revenue, and we've never sold them. That is a school that runs fundraisers, has money, and
  buys from somebody else. That list is 33 schools long today and I'd work it before anything
  else in the state. Build it as a one-click saved filter.
- **Seasonal mode on Today. [High value, medium cost.]** See §7. The tool should know it's
  October and behave differently than it does in April.
- **District rollup view. [Medium-high value, medium cost.]** Show me the district, the
  superintendent, all its schools, and everything we've ever done with any of them, on one page.
- **A "new principal" detector that actually runs. [High value, medium cost.]** Re-scrape the
  directory each summer and diff the principal names. Every change is a call worth making in
  August. This is the highest-ROI automation available and the plumbing for it is already built
  and idle.
- **Bring back saved views properly. [Medium value, low cost.]** The build spec called this "the
  cheapest feature here and the one that gets used most," and it was never built. It was right.
  I'm currently doing it with browser bookmarks.
- **Email validation pass. [Medium value, low cost, prerequisite for anything email.]**
- **A "verify this contact" flow. [Medium value, low cost.]** When I confirm a name on a call,
  let me mark it confirmed in one click. Reps checking data as a by-product of calling is the
  cheapest data-quality engine you'll ever build — but only if it takes one click.
- **Referral / relationship field. [Medium value, low cost.]** "Jennifer moved from Roosevelt
  Elementary to Lincoln" is how half my business happens and there's nowhere to put it.
- **Expand to a second state as a real test. [Strategic.]** North Dakota is small and unusually
  well-documented. Before we bet on this, prove the pipeline works somewhere with 5,000 schools
  and a less cooperative state directory.

---

## 12. Recommended priorities

**Fix before I'd let another rep touch it (days, not weeks):**

| # | Item | Why |
|---|---|---|
| 1 | Snooze never returns (§4.2) | Silently loses the warmest leads |
| 2 | Keyboard shortcuts don't fire (§4.1) | Near one-line fix, restores the core workflow |
| 3 | Confidence labels are inverted (§5) | Reps are avoiding the best data |
| 4 | Undo / delete a logged action (§4.4) | Bad data is currently permanent |
| 5 | Correct the Guide (§4.3, §4.6) | Docs that lie are worse than no docs |

**Build before rollout (weeks):**

| # | Item | Why |
|---|---|---|
| 6 | Record a sale — won/lost/amount (§9.1) | Without this there is no closed loop |
| 7 | Real users, login, ownership (§10) | Multi-rep is impossible today |
| 8 | Back-dating an activity (§4.5) | Otherwise the log is fiction |
| 9 | Basic activity reporting (§10) | You can't manage what you can't see |
| 10 | Rebalance the score, show tiers not decimals (§6) | Currently a proxy for enrollment |

**Next quarter:**

| # | Item |
|---|---|
| 11 | PTO officers from the IRS layer (§5.1) |
| 12 | Seasonal Today (§7) |
| 13 | Signals that actually fire (§4.6) |
| 14 | District view (§8) |
| 15 | Competitive takeaway list (§11) |

---

## 13. Verdict

**As a prospecting database: excellent. Best thing we've had. Ship the data access to the team
now, even if nothing else changes.**

**As a CRM: not yet.** It logs activity and cannot record an outcome, which means the most
important half of a sales record is missing.

**As a system of record for a sales team: no.** One user, no login, no ownership, no reporting.

What I'd do: fix the five bugs in the P0 table this week, give me and one other rep two more
weeks on it — separate databases if we have to, since there's no multi-user story — and then
decide about the sales-recording work with two months of real usage behind the decision instead
of one month of mine.

And whoever built this should know: the reason my feedback is this long is that the tool is good
enough to be worth arguing about. Most of what I get handed I stop opening by week two. I opened
this one every morning for a month, including the mornings I didn't have to.

---

*Every figure in this document was verified against the live database and source files on
2026-08-23. Bug claims in §4 were traced to specific code paths.*
