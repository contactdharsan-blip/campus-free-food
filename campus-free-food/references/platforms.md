# Finding a school's event site

Most universities list student-organization events on one of a few platforms. The script recognises
four of them from any address on the site (`python3 scripts/free_food.py --detect <url>`).

| Platform | How to recognise it | What the script reads |
| --- | --- | --- |
| CampusGroups (Ready Education) | Footer "©Ready Education"; addresses like `/rsvp_boot?id=` or `/events`; often a branded name | The public event list, then each event's public page for its description |
| Campus Labs Engage (Anthology) | `<school>.campuslabs.com/engage`, or a branded site that links there | The public event search, with the platform's own "Free Food" perk |
| Localist | Often `calendar.<school>.edu` or `events.<school>.edu`; `/api/2/events` on it returns JSON | The public events API |
| iCal (.ics) | A "Subscribe" or "iCal" link, often from Trumba, 25Live or Google Calendar | The feed's events (repeating events count only on their first date) |

## Checked on 2026-10-24

| School | Site | Platform |
| --- | --- | --- |
| Arizona State University | https://sundevilcentral.eoss.asu.edu | CampusGroups |
| Georgia Tech | https://gatech.campuslabs.com/engage | Engage |
| University of Iowa | https://uiowa.campuslabs.com/engage | Engage |
| Stanford University | https://events.stanford.edu | Localist |
| University of Colorado Boulder | https://calendar.colorado.edu | Localist |
| University of Washington (Seattle) | https://www.trumba.com/calendars/sea_campus.ics | iCal |

Every other school is unchecked. Run `--detect` first.

## Finding it

1. Search the web for "<school> student organization events" or "<school> get involved events".
2. If the result is a branded site (for example "TigerLink" or "Sun Devil Central"), run `--detect` on
   its address. Branded Engage sites usually link to `campuslabs.com/engage`, and the script follows that
   link.
3. If the school has a main events calendar as well as a student-org site, the student-org site usually
   lists more free food. Check both if the first finds nothing.
4. If `--detect` says `unknown` (exit 5), read the events page with web or browser and pass the events
   with `--events-file` (SKILL.md step 4b).

## Limits

- **Only public events.** Events a school shows only after sign-in aren't in the public feeds. The script
  also flags events the platform restricts to certain members.
- **Hidden locations.** Some CampusGroups events hide their location until the student signs in. The
  reply says so and links the event.
- **Repeating events.** In iCal feeds, repeating events are not expanded.
