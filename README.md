# Campus Free Food

A [Cubbie](https://cubbie.ai) Skill that finds campus events with free food that you can go to and that
fit your schedule. It quotes the line in each event's description that promises the food.

> "is there free food on campus today?"
>
> Pizza and Pitches, Mon 12–1 PM, Memorial Union 202
> "Free pizza will be provided for everyone who comes!"

## Install on Cubbie

Text Cubbie the link to the Skill folder:

```text
https://github.com/contactdharsan-blip/campus-free-food/tree/main/campus-free-food
```

Cubbie asks before it fetches it; reply "yes". Then ask it for free food.

## Where it works

The script reads these platforms' public event feeds, with no sign-in:

- **CampusGroups**: ASU Sun Devil Central;
- **Campus Labs Engage**: Georgia Tech, Iowa;
- **Localist**: Stanford, CU Boulder;
- **any iCal feed**: UW via Trumba.

Those six sites were checked on 2026-10-24. For any other site, Cubbie reads the events page itself and
the same rules apply. See [references/platforms.md](campus-free-food/references/platforms.md).

How it decides:
- **Food:** the event's description promises food. Donating, selling, packing or banning food doesn't
  count. Engage's own "Free Food" perk counts on its own.
- **Who can go:** audience tags, honors or residence-hall events, members-only wording, the platform's
  own restrictions, sold out, registration closed, and ticket prices.
- **Your schedule:** your Google Calendar and Canvas classes, or what you tell it when neither is connected.
  Each event says whether it fits whole, in part (with the free stretch) or not, and Cubbie offers to put
  the one you pick on your calendar.

It saves nothing between runs.

## Try it locally

```bash
cd campus-free-food
python3 scripts/free_food.py --sample --busy assets/sample_busy.json
python3 scripts/free_food.py --detect https://events.stanford.edu
python3 scripts/free_food.py --site https://events.stanford.edu --now 2026-10-24T13:00 --tz America/Los_Angeles
```

Python 3.9+ and the standard library only.

## Tests

```bash
python3 -m unittest discover -s tests
```

The tests run offline against responses saved from the six sites on 2026-10-24.

Built for the [Cubbie Hackathon](https://hackathon.cubbie.ai), Track 1.
