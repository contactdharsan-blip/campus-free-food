#!/usr/bin/env python3
"""Find campus events with free food that a student can go to and that fit their schedule.

Reads the school's public event site, keeps the events whose description promises food,
quotes the sentence that says so, checks who each event is for, and checks it against the
student's busy times. Works with CampusGroups, Campus Labs Engage, Localist and any iCal
(.ics) feed; for any other site, pass the events in a file with --events-file.

    python3 scripts/free_food.py --detect https://sundevilcentral.eoss.asu.edu
    python3 scripts/free_food.py --site <url> --now 2026-10-24T13:00 --tz America/Phoenix --days 2
    python3 scripts/free_food.py --events-file events.json --now ... --tz ...
    python3 scripts/free_food.py --sample          # bundled example, no network

Stateless: it saves nothing between runs. Standard library only (Python 3.9+).

Exit codes: 0 ok · 2 bad arguments or busy file · 3 the site is unreachable ·
4 the site's format changed · 5 the site isn't a platform this script reads
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Optional

sys.path.insert(0, str(Path(__file__).resolve().parent))
import platforms  # noqa: E402

HERE = Path(__file__).resolve().parent.parent
SAMPLE = HERE / "assets" / "sample_events.json"

FOOD = re.compile(
    r"\b(free food|food (?:will be |is )?(?:provided|served)|pizza|snacks?|refreshments?|lunch|dinner|"
    r"breakfast|brunch|tacos?|boba|donuts?|doughnuts?|cookies?|treats|ice cream|coffee|bbq|barbecue|"
    r"catered|catering|desserts?|cupcakes?|bagels?|burritos?|sandwich(?:es)?|popcorn|candy|"
    r"hot cocoa|hot chocolate|cider|meals?|food trucks?|s'?mores|pancakes?|wings|sushi|cake|"
    r"churros?|tamales?|empanadas?|pies?|food)\b",
    re.I,
)
# Food that is not free food for the student: donating it, selling it, packing it, studying it, or bringing it.
NOT_FREE = re.compile(
    r"\b(food drive|donat\w*|canned (?:food|goods)|non-?perishable|for sale|for purchase|"
    r"available to purchase|bake sale|fundrais\w*|bring (?:a|your own|some) (?:snack|dish|food|lunch)|"
    r"potluck|food insecurity awareness|delivered to children|pack(?:ing)? (?:\w+ )?meals|meal[- ]packing|"
    r"hope starts with food|feed (?:the|those|families|kids|children)|hunger|food bank|food pantry donations|"
    r"food (?:distribution|insecurity|security|systems?|science|justice|waste|sustainab\w*|policy|access|"
    r"recovery|rescue|industry|studies|for thought)|eye candy|"
    r"(?:food|drinks?|snacks?) (?:is |are )?not (?:allowed|permitted|provided)|no (?:food|outside food|snacks)|"
    r"not (?:be )?provided|bring your own)\b",
    re.I,
)
STRONG = re.compile(r"\b(free food|food (?:will be |is )?(?:provided|served)|free \w+|provided|served|catered|catering|complimentary)\b", re.I)
MEMBERS_TEXT = re.compile(r"\b(?:(?i:for (?:club |chapter )?members|members only|invite[- ]only|by invitation)|(?i:members of) (?!the\b|our\b|all\b|any\b)[A-Z][\w&']+)")
OPEN_TEXT = re.compile(r"\b(open to (?:all|everyone|any)|everyone is welcome|all are welcome|all students)\b", re.I)
HONORS = re.compile(r"\bBarrett\b|\bHonors (?:College|Program)\b|\bhonors students\b", re.I)


# ---------- food ----------

def sentences(text: str) -> list[str]:
    text = re.sub(r"\*\*|__", "", text or "")
    out = []
    for line in re.split(r"[\r\n]+", text):
        out += [s.strip() for s in re.split(r"(?<=[.!?])\s+", line) if s.strip()]
    return out


def food_evidence(name: str, description: str, flag: Optional[str] = None) -> Optional[dict]:
    """The sentence that promises food, or None. Food that is donated, sold or brought doesn't count.
    A platform's own free-food label (`flag`) is certain on its own."""
    best = None
    for s in [name] + sentences(description):
        if not FOOD.search(s) or NOT_FREE.search(s):
            continue
        score = 2 if STRONG.search(s) else 1
        if best is None or score > best[0]:
            best = (score, s)
    if best is None:
        return {"quote": flag, "certain": True} if flag else None
    quote = best[1]
    if len(quote) > 180:  # keep the food word in view
        at = FOOD.search(quote).start()
        lo = max(0, min(at - 70, len(quote) - 178))
        quote = ("…" if lo else "") + quote[lo:lo + 178].strip() + ("…" if lo + 178 < len(quote) else "")
    return {"quote": quote, "certain": best[0] == 2 or bool(flag)}


# ---------- who it's for ----------

def eligibility(ev: dict, me: argparse.Namespace) -> tuple[str, list[str]]:
    """'yes', 'check' or 'no', with the reasons in plain words."""
    reasons, verdict = [], "yes"
    tags, text, host = ev.get("tags", []), ev["name"] + " " + ev.get("description", ""), ev.get("host", "")
    aud = set(ev.get("audience") or ())

    def worse(v: str) -> None:
        nonlocal verdict
        order = {"yes": 0, "check": 1, "no": 2}
        if order[v] > order[verdict]:
            verdict = v

    if ev.get("sold_out"):
        worse("no"); reasons.append("sold out")
    if ev.get("closed"):
        worse("no"); reasons.append("registration is closed")
    if ev.get("register_by") and ev["register_by"] < me.now:
        worse("no"); reasons.append("registration closed " + ev["register_by"].strftime("%b %-d"))
    if aud and not aud & {"everyone", "students"}:
        if me.level == "undergrad" and "grad" in aud and "undergrad" not in aud:
            worse("no"); reasons.append("for graduate students")
        elif me.level == "grad" and "undergrad" in aud and "grad" not in aud:
            worse("check"); reasons.append("listed for undergraduates")
        elif aud <= {"faculty"}:
            worse("no"); reasons.append("for faculty and staff")
        elif aud <= {"alumni", "faculty"}:
            worse("check"); reasons.append("listed for alumni")
    if re.match(r"(?i)(faculty|staff)\b", ev["name"]) or re.search(r"(?i)\bfaculty (?:and|&) staff (?:only|lunch|appreciation)", text):
        worse("check"); reasons.append("looks like a faculty or staff event")
    if HONORS.search(host + " " + text) and not me.honors:
        worse("check"); reasons.append("honors-college event")
    housing = [t for t in tags if t.startswith("Housing")]
    hall_host = re.search(r"\b(Hall|Residential|Residence|Housing)\b", host) or re.search(r"\bresidents\b", text, re.I)
    if housing or hall_host:
        hall = me.hall.lower() if me.hall else ""
        if not hall or hall not in (text + " " + ev.get("location", "") + " " + host).lower():
            worse("check"); reasons.append("residence-hall event")
    if ev.get("restricted"):
        worse("check"); reasons.append("the event site limits it to certain members; sign in there to see if you qualify")
    elif MEMBERS_TEXT.search(text) and not OPEN_TEXT.search(text):
        if not any(o.lower() in host.lower() for o in me.orgs):
            worse("check"); reasons.append("says it's for members")
    if re.search(r"\binternational students\b", text, re.I) and not me.international and not OPEN_TEXT.search(text):
        worse("check"); reasons.append("for international students")
    if re.search(r"\b(veterans?|military[- ]affiliated)\b", text + " " + " ".join(tags), re.I) and not me.veteran:
        worse("check"); reasons.append("for military-affiliated students")
    price = (ev.get("price") or "").strip()
    if price and price.upper() not in ("FREE", "0", "$0", "0.00"):
        worse("check"); reasons.append("ticket price " + price)
    campus = ev.get("campus")
    if me.campus and campus and campus != me.campus:
        reasons.append("on the " + campus + " campus")
    if OPEN_TEXT.search(text) and verdict == "yes":
        reasons.append("says it's open to everyone")
    return verdict, reasons


# ---------- schedule ----------

def conflicts(ev: dict, busy: list[dict]) -> list[str]:
    return [b.get("title") or "busy" for b in busy if b["start"] < ev["end"] and ev["start"] < b["end"]]


def load_busy(path: Optional[str], tz) -> list[dict]:
    if not path:
        return []
    out = []
    for b in json.loads(Path(path).read_text()):
        s, e = datetime.fromisoformat(b["start"]), datetime.fromisoformat(b["end"])
        out.append({"start": s if s.tzinfo else s.replace(tzinfo=tz), "end": e if e.tzinfo else e.replace(tzinfo=tz),
                    "title": b.get("title")})
    return out


# ---------- report ----------

def report(events: list[dict], me: argparse.Namespace, busy: list[dict]) -> list[dict]:
    found = []
    for ev in events:
        food = food_evidence(ev["name"], ev.get("description", ""), ev.get("food_flag"))
        if not food:
            continue
        verdict, reasons = eligibility(ev, me)
        if verdict == "no" and not me.show_ineligible:
            continue
        s, f = ev["start"].astimezone(me.tz), ev["end"].astimezone(me.tz)
        where = ev.get("location") or ""
        found.append({
            "name": ev["name"],
            "host": ev.get("host", ""),
            "when": s.strftime("%a %b %-d, %-I:%M %p") + "–" + f.strftime("%-I:%M %p"),
            "start": s.isoformat(),
            "started": ev["start"] < me.now,
            "where": "location shown after signing in to the event site" if "sign in" in where.lower() else where,
            "food": food["quote"],
            "food_certain": food["certain"],
            "eligible": verdict,
            "why": reasons,
            "conflicts_with": conflicts(ev, busy),
            "spots_left": ev.get("spots_left"),
            "link": ev.get("url", ""),
        })
    rank = {"yes": 0, "check": 1, "no": 2}
    away = lambda f: any(r.startswith("on the ") for r in f["why"])  # another campus is a trip, not a no
    found.sort(key=lambda f: (bool(f["conflicts_with"]), rank[f["eligible"]], away(f), not f["food_certain"], f["start"]))
    return found


def sample_events(start: datetime, end: datetime) -> list[dict]:
    out = []
    for e in json.loads(SAMPLE.read_text()):
        e = platforms.blank(**e)
        e["start"], e["end"] = datetime.fromisoformat(e["start"]), datetime.fromisoformat(e["end"])
        e["audience"] = set(e["audience"])
        if start <= e["start"] <= end:
            out.append(e)
    return out


def emit(obj: dict) -> None:
    print(json.dumps(obj, ensure_ascii=False))


def main(argv: Optional[list[str]] = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    src = ap.add_mutually_exclusive_group()
    src.add_argument("--site", help="the school's event site, or an .ics feed URL")
    src.add_argument("--events-file", help="JSON list of events read from any other site")
    src.add_argument("--sample", action="store_true", help="use the bundled example instead of a live site")
    src.add_argument("--detect", metavar="URL", help="only say which platform a site runs on")
    ap.add_argument("--now", help="the student's local date and time, e.g. 2026-10-24T13:00")
    ap.add_argument("--tz", default="", help="the student's time zone, e.g. America/Phoenix (default: UTC offset in --now)")
    ap.add_argument("--days", type=float, default=2, help="how far ahead to look, 0.25 to 7 days (default 2)")
    ap.add_argument("--level", choices=["undergrad", "grad"], default="undergrad")
    ap.add_argument("--campus", help="the student's campus, as the site names it (e.g. tempe)")
    ap.add_argument("--honors", "--barrett", action="store_true", dest="honors", help="the student is in the honors college")
    ap.add_argument("--hall", default="", help="the student's residence hall, if they live on campus")
    ap.add_argument("--org", action="append", default=[], dest="orgs", help="a club the student belongs to (repeatable)")
    ap.add_argument("--international", action="store_true")
    ap.add_argument("--veteran", action="store_true", help="military-affiliated student")
    ap.add_argument("--busy", help='JSON file of busy times: [{"start": ISO, "end": ISO, "title": ...}]')
    ap.add_argument("--show-ineligible", action="store_true", help="also list events the student can't attend")
    ap.add_argument("--limit", type=int, default=12, help="most events to print (default 12)")
    me = ap.parse_args(argv)

    if me.detect:
        try:
            platform, base = platforms.detect(me.detect)
        except OSError:
            emit({"error": "that site is not reachable right now"})
            return 3
        emit({"platform": platform, "base": base, "supported": platform != "unknown"})
        return 0 if platform != "unknown" else 5

    if me.sample:
        me.now = me.now or "2026-10-26T10:00"
        me.tz = me.tz or "America/Phoenix"
    if not (me.site or me.events_file or me.sample):
        emit({"error": "pass --site, --events-file or --sample"})
        return 2
    if not me.now:
        emit({"error": "pass --now with the student's local date and time"})
        return 2
    try:
        now = datetime.fromisoformat(me.now)
    except ValueError:
        emit({"error": "--now must look like 2026-10-24T13:00"})
        return 2
    tz = platforms.zone(me.tz) if me.tz else (now.tzinfo or None)
    if tz is None:
        emit({"error": "pass --tz with the student's time zone, e.g. America/Phoenix"})
        return 2
    me.tz = tz
    me.now = now.replace(tzinfo=tz) if now.tzinfo is None else now.astimezone(tz)
    me.campus = (me.campus or "").strip().lower() or None
    if not 0.25 <= me.days <= 7:
        emit({"error": "--days must be between 0.25 and 7"})
        return 2
    try:
        busy = load_busy(me.busy, tz)
    except (OSError, ValueError, KeyError, TypeError):
        emit({"error": "the busy file must be a JSON list of {start, end, title}"})
        return 2

    start, end = me.now, me.now + timedelta(days=me.days)
    platform = "sample"
    if me.events_file:
        platform = "events-file"
        try:
            events = platforms.events_file(me.events_file, start, end, tz)
        except (OSError, ValueError, KeyError, TypeError):
            emit({"error": "the events file must be a JSON list of {name, start, ...}"})
            return 2
    try:
        if me.sample:
            events = sample_events(start, end)
        elif me.events_file:
            pass
        else:
            platform, base = platforms.detect(me.site)
            if platform == "unknown":
                emit({"error": "this site isn't CampusGroups, Engage, Localist or an iCal feed", "site": me.site})
                return 5
            if platform == "ics":
                events = platforms.ics(base, start, end, student_tz=tz)
            else:
                events = platforms.READERS[platform](base, start, end)
    except OSError:
        emit({"error": "the event site is not reachable right now"})
        return 3
    except (ValueError, KeyError, TypeError) as e:
        emit({"error": "the event site's format changed: " + e.__class__.__name__})
        return 4

    events = [e for e in events if e["end"] >= start and e["start"] <= end]
    found = report(events, me, busy)
    out = {
        "platform": platform,
        "window": f"{start:%a %b %-d %-I:%M %p} to {end:%a %b %-d %-I:%M %p} ({me.tz})",
        "events_checked": len(events),
        "food_events_found": len(found),
        "schedule_checked": bool(me.busy),
        "events": found[: me.limit],
    }
    text = json.dumps(out, ensure_ascii=False)
    while len(text) > 7500 and out["events"]:  # Cubbie reads the first 8,000 characters
        out["events"].pop()
        out["truncated"] = True
        text = json.dumps(out, ensure_ascii=False)
    print(text)
    return 0


if __name__ == "__main__":
    sys.exit(main())
