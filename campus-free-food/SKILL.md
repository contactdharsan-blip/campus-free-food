---
name: campus-free-food
description: Finds campus events with free food that the student can attend and that fit their schedule, quoting the line that promises food. Use when a student asks where to get free food on campus, which events today have food, or what free food fits between classes.
---

# Campus Free Food

Reads the student's school event site and keeps the events whose description promises food. Each event is
checked against who it is for and against the student's busy times, and the reply quotes the sentence
about food.

The script reads these platforms directly, from public feeds with no sign-in:
- **CampusGroups**, for example ASU Sun Devil Central;
- **Campus Labs Engage**, for example Georgia Tech and Iowa;
- **Localist**, for example Stanford and CU Boulder;
- **any iCal (.ics) feed**, for example UW through Trumba.

For any other site you read the events yourself and pass them in a file. See `references/platforms.md`.

## When to use

- "Is there free food on campus today?"
- "Any events with food between my classes tomorrow?"
- "I'm broke until Friday, where can I eat for free this week?"

Do not use it for dining hall menus, meal plans or restaurants.

## Steps

1. **The school and its event site.**
   - Work out the student's school from Canvas (its web address names the school) or from this
     conversation. Otherwise ask: "Which school?".
   - Find the school's student-events site. `references/platforms.md` lists the ones already checked and
     how to find others; a web search for "<school> student organization events" usually finds it.
   - Run `python3 scripts/free_food.py --detect <site>`. It prints the platform. Exit code 5 means the
     script can't read that site; go to step 4b.
   - Don't save the site; find it again next time.
2. **Window and time zone.**
   - Use the time the student asked about: the rest of today is `--days 0.5`, today and tomorrow is
     `--days 2`, "this week" is `--days 7`. Default to `--days 2`.
   - Pass the student's local date and time with its UTC offset as `--now` (for example
     `2026-10-24T13:00-07:00`), and their time zone as `--tz` (for example `America/Chicago`). Don't use
     the sandbox clock; it may be in another time zone.
3. **Busy times.** The point is food that fits the student's day, so always check their schedule.
   - Read the student's Google Calendar events for the window, plus their class times from Canvas if
     Canvas is connected.
   - If neither is connected, ask one question before running: "When are you busy? Classes, work,
     anything fixed. Or say free". Use what they say; "free" is an empty list. If they'd rather not say,
     leave out `--busy` and say that the results were not checked against their schedule.
   - Write them to `busy.json` as a list of `{"start": "<ISO time>", "end": "<ISO time>", "title": "<name>"}`.
     Leave out all-day items (holidays, reminders, "out of office"); they would block the whole day.
4. **Run** from this Skill's folder.

   a. For a site the script reads:

   ```bash
   python3 scripts/free_food.py --site "<site>" --now "<local date and time>" --tz "<time zone>" --days <days> --level <undergrad|grad> [--campus "<campus>"] [--busy busy.json] [--honors] [--hall "<hall>"] [--org "<club>"]...
   ```

   b. For any other site: open its events page with web or browser and write the events in the window
   to `events.json`. Each event is `{"name", "start", "end", "location", "description", "url", "host"}`
   (times in ISO). Then run the same command with `--events-file events.json` in place of `--site`.

   On who the student is, use only what they've said in this conversation:
   - undergrad or grad;
   - their campus;
   - whether they're in the honors college;
   - their residence hall;
   - their clubs.

   If you don't know whether they're an undergrad or grad, ask one question with a default
   ("Undergrad?"). Leave out anything else that's unknown.

   It takes a few seconds; a CampusGroups site can take up to a minute. It prints JSON. Each item in
   `events` has:
   - `name`, `when`, `where`, `link`;
   - `food`: the description's own sentence about food;
   - `eligible`: `yes` or `check`, and `why`;
   - `conflicts_with`: the busy items it overlaps;
   - `fits` (whenever `--busy` is passed, even an empty list): `whole` (no overlap), `part` (overlaps, but `free_window` is a free
     stretch of 20 minutes or more inside the event) or `no`;
   - `started`: true if it began before `--now`.

   Events come sorted with open, schedule-fitting ones first.
5. **Reply** (see Replies). Then offer to fit the top one into their schedule, naming the event and the
   time it will hold, and do it only after the student says yes:
   - add it to their Google Calendar: "Add Donut Day to your calendar, Wed 9–10:30 AM?" When `fits` is
     `part`, offer the `free_window` instead of the whole event;
   - or, without Google Calendar, a reminder 30 minutes before it starts.
   If they pick a different event, offer the same for that one.

To try it without the network: `python3 scripts/free_food.py --sample --busy assets/sample_busy.json`.

## Replies

- Short, plain text, no Markdown.
- Lead with the best one to three events that are `eligible: yes` and `fits: whole`. If there are none,
  use `fits: part` ones.
- For each event:
  - one line with the name, day and time, and place;
  - one line on how it fits the day, from `busy.json`: "Free then: right after CHM 113" or, for
    `part`, "You can make 12:50–2:00, after CHM 113";
  - one line quoting the food sentence (shortened if long);
  - the link on its own line.
- After those, one line naming the `check` events and why ("2 more are for one residence hall"), and one
  line for good events that clash with the schedule.
- When `where` says the location shows after signing in, say so.
- Never promise more food than the quote says. "Sometimes bring snacks" is not a meal.
- Never register or RSVP for the student. Send the link; they register themselves.

Example:

```text
Free food that fits your day:

Downtown Donut Day, Wed 9–10:30 AM, UCENT Lobby
Free then: nothing else on Wed morning
"Grab free donuts and coffee on your way to class."
https://sundevilcentral.eoss.asu.edu/rsvp_boot?id=900006

Also: you can make 3–4:30 of Taco Tuesday before your lab, Pizza and Pitches clashes with CHM 113, and
there's an honors-only Halloween social Tue night.
Add Donut Day to your calendar, Wed 9–10:30 AM?
```

## When something fails

| Exit code | Meaning | What to do |
| --- | --- | --- |
| 0 with no events | Nothing with food in the window | Text: "No free-food events on <site> for that time. Want me to check the whole week?" |
| 2 | Bad arguments, busy file or events file | Fix the command (most often a missing `--now` or `--tz`) and run once more |
| 3 | The site is unreachable | Text: "<site> isn't loading right now. I can try again in a bit." Retry at most once |
| 4 | The site's format changed | Use step 4b with that site; if that fails too, say you couldn't read its events |
| 5 | Not a platform the script reads | Use step 4b |

Use only events the script returned. Never invent an event, a time or food.
