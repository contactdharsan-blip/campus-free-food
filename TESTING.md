# Testing on Cubbie

## 2026-10-24: first install and run, ASU (Sun Devil Central)

On a real Cubbie account (Tempe undergrad, with Canvas and Google connected), over iMessage.
Cubbie fetched commit `f66ba6c`. The schedule-fit changes (`7b6d7c1` onward) have not been run on Cubbie yet.

| # | Sent | Cubbie's reply | Result |
|---|---|---|---|
| 1 | The branch link `…/tree/main/campus-free-food` | Said what the Skill is and what it reads ("Sun Devil Central's public feed without signing in"), and asked before installing third-party code | Pass |
| 2 | "yes" | About 5 minutes later: "Installed and ran it — three public events have confirmed food today, with no conflicts showing in your Google or Canvas schedule". Gave the best pick with its food quote and link, then two more, each with a quote and its time | Pass |
| — | A follow-up from the student: "can you check my schedule and hw to see if I can fit it in" | Checked Google Calendar and Canvas due dates, suggested a homework block and a window to go | Pass (Cubbie's own planning on top of the Skill) |

What it showed:
- Each event came with the description's own food sentence, as SKILL.md asks. For example, "Traditional-style chicken shawarma catered by Princess Pita."
- An event that had already started was reported as "still happening". An event whose location needs sign-in was reported that way.
- Cubbie noticed on its own that one event's listed time (4 PM) disagreed with its description (5 PM) and asked the student to confirm.
- Before the Skill, the same student asked Cubbie the same question on the same day. Cubbie found one event and said "the full event directory didn't load … members-only events remain unchecked".

Not tested yet:
- A near-miss request (a dining hall menu) that should not use the Skill.
- "What Skills do I have?"
- Any school other than ASU on Cubbie. The other platforms were tested only with the script, on 2026-10-24, against Georgia Tech, Iowa, Stanford, CU Boulder and UW.

## 2026-10-24: ASU scenarios, script only

Live Sun Devil Central, `--days 7` from Sat Oct 24 2:00 PM: 331 events, 79 with food, about 75 seconds.
One fetch, then each student profile run over the same events:

| Profile | Result |
|---|---|
| Campus tempe / downtown / poly / west | Other-campus events rank lower (12 / 33 / 32 / 34 of 79) and stay listed |
| `--barrett` | The 4 Barrett events become `yes` when the hall is Barrett too; Barrett-hall events otherwise stay `check` |
| `--hall "palo blanco"` | Palo Blanco's own event becomes `yes`; other halls' events stay `check` |
| `--international` | "Pumpkin Carving for International Students" becomes `yes` |
| `--level grad` | 3 events move from `yes` to `check` (listed for undergraduates) |
| A class schedule (10 blocks, Mon–Fri) | 45 fit whole, 27 in part with the right free window, 7 not at all |

Food matches read by hand: most are real. Wrong or weak ones seen: "Bring a picnic lunch" (bring-your-own),
"by Eden Coffee" (a place name), "the BT21 Happy Meal commercial" (a speaker's bio), "give-pie to the
President's face", and "sometimes bring snacks". The kit caps the script's output at 7,500 characters, so a
7-day ASU run shows about 14 of the 79.
