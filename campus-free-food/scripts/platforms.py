"""Readers for the event platforms universities use. Each returns events in one shape.

Every reader takes (base, start, end, fetch) and returns a list of dicts:

    id, name, host, tags, audience, start, end, location, price, description,
    restricted, sold_out, closed, register_by, spots_left, food_flag, campus, url

`start`/`end` are timezone-aware. `description` is plain text. `audience` is a set drawn from
{"undergrad", "grad", "students", "faculty", "alumni", "everyone"}; empty means not stated.
`restricted` means the platform itself limits who can attend. `food_flag` is the platform's own
free-food label when it has one (Engage's "Free Food" perk), else None.

Verified 2026-10-24 against: ASU Sun Devil Central (CampusGroups), Georgia Tech and Iowa
(Engage), Stanford and CU Boulder (Localist), UW Seattle via Trumba and CU Boulder (iCal).
"""

from __future__ import annotations

import concurrent.futures as cf
import html
import json
import re
import shutil
import ssl
import subprocess
import urllib.error
import urllib.parse
import urllib.request
from datetime import date, datetime, time, timedelta, timezone
from typing import Callable, Optional

try:
    from zoneinfo import ZoneInfo
except ImportError:  # Python < 3.9
    ZoneInfo = None  # type: ignore[assignment]

UA = {"User-Agent": "Mozilla/5.0 (campus-free-food Cubbie Skill)"}
Fetch = Callable[[str], str]


def _cert_error(e: Exception) -> bool:
    return isinstance(getattr(e, "reason", e), ssl.SSLCertVerificationError)


def _curl(url: str, timeout: int) -> tuple[str, str, str]:
    """Some campus servers leave out an intermediate certificate. Python can't fill the gap; curl
    often can, and it still verifies the certificate. Never falls back to an unverified request."""
    if not shutil.which("curl"):
        raise OSError("certificate could not be verified")
    p = subprocess.run(["curl", "-sSL", "--max-time", str(timeout), "-A", UA["User-Agent"],
                        "-w", "\n%{url_effective}\n%{content_type}", url], capture_output=True, timeout=timeout + 5)
    if p.returncode != 0:
        raise OSError("curl failed: " + p.stderr.decode("utf-8", "replace")[:200])
    body, final, ctype = p.stdout.decode("utf-8", "replace").rsplit("\n", 2)
    return final, ctype, body


def fetch(url: str, timeout: int = 60) -> str:
    req = urllib.request.Request(url, headers=UA)
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            return r.read().decode("utf-8", "replace")
    except urllib.error.URLError as e:
        if _cert_error(e):
            return _curl(url, timeout)[2]
        raise


def fetch_final(url: str, timeout: int = 30) -> tuple[str, str, str]:
    """(final url after redirects, content type, first 200 KB of body)."""
    req = urllib.request.Request(url, headers=UA)
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            return r.geturl(), r.headers.get("Content-Type", ""), r.read(200_000).decode("utf-8", "replace")
    except urllib.error.URLError as e:
        if _cert_error(e):
            final, ctype, body = _curl(url, timeout)
            return final, ctype, body[:200_000]
        raise


def text_of(fragment: str) -> str:
    """HTML to plain text, keeping paragraph breaks so sentences stay apart."""
    s = re.sub(r"(?i)<br\s*/?>|</p>|</div>|</li>|</h\d>", "\n", fragment or "")
    s = html.unescape(re.sub(r"<[^>]+>", " ", s))
    return "\n".join(" ".join(line.split()) for line in s.splitlines() if line.strip())


def zone(name: Optional[str]):
    if name and ZoneInfo is not None:
        try:
            return ZoneInfo(name)
        except Exception:
            return None
    return None


AUDIENCE_WORDS = [
    (re.compile(r"\bundergrad", re.I), "undergrad"),
    (re.compile(r"\bgrad(uate)?\b(?! school fair)", re.I), "grad"),
    (re.compile(r"\bstudents?\b", re.I), "students"),
    (re.compile(r"\bfaculty|staff\b", re.I), "faculty"),
    (re.compile(r"\balumni\b", re.I), "alumni"),
    (re.compile(r"\b(everyone|public|all)\b", re.I), "everyone"),
]


def audience_from(labels: list[str]) -> set[str]:
    out: set[str] = set()
    for label in labels:
        if re.search(r"\bundergrad", label, re.I):
            out.add("undergrad")
            continue
        for rx, aud in AUDIENCE_WORDS[1:]:
            if rx.search(label):
                out.add(aud)
    return out


def blank(**kw) -> dict:
    ev = dict(id="", name="", host="", tags=[], audience=set(), start=None, end=None, location="",
              price="", description="", restricted=False, sold_out=False, closed=False,
              register_by=None, spots_left=None, food_flag=None, campus=None, url="")
    ev.update(kw)
    return ev


# ---------------------------------------------------------------- CampusGroups (Ready Education)

CG_LIST = "/mobile_ws/v17/mobile_events_list?range={offset}&limit=100"
CG_EVENT = "/rsvp_boot?id={id}"
CG_RESTRICTED = "This event is open to specific members only"
CG_DATE = re.compile(r"(\d{1,2}) (\w+) (\d{4}) At (\d{1,2})(?::(\d{2}))? (AM|PM)")
CG_CAMPUS = {"Tempe Campus": "tempe", "Downtown Phoenix Campus": "downtown",
             "Polytechnic Campus": "poly", "West Valley Campus": "west"}


def cg_offset(row: dict) -> timezone:
    m = re.search(r"GMT([+-]\d{1,2})(?::?(\d{2}))?", row.get("p28") or "")
    if not m:
        return timezone.utc
    h = int(m.group(1))
    return timezone(timedelta(hours=h, minutes=(int(m.group(2) or 0) * (1 if h >= 0 else -1))))


def cg_row_start(row: dict) -> Optional[datetime]:
    m = CG_DATE.search(row.get("p29") or "")
    if not m:
        return None
    day, month, year, hour, minute, ampm = m.groups()
    try:
        d = datetime.strptime(f"{day} {month} {year}", "%d %B %Y")
    except ValueError:
        return None
    h = int(hour) % 12 + (12 if ampm == "PM" else 0)
    return d.replace(hour=h, minute=int(minute or 0), tzinfo=cg_offset(row))


def cg_tags(row: dict) -> list[str]:
    return [html.unescape(t).strip() for t in re.findall(r'aria-label="([^"]+)"', row.get("p22") or "")]


def cg_multiday(row: dict) -> bool:
    """Rows like "Mon, Aug 24 – Mon, Nov 30" are standing meetings, not one event with a time."""
    days = re.findall(r"\w{3}, \w{3} \d{1,2}, \d{4}", re.sub(r"<[^>]+>", " ", row.get("p4") or ""))
    return len(set(days)) > 1


def cg_jsonld(page: str) -> Optional[dict]:
    m = re.search(r'<script type="application/ld\+json">(.*?)</script>', page, re.S)
    if not m:
        return None
    raw = re.sub(r'\\(?!["\\/bfnrtu])', r"\\\\", m.group(1))  # the feed writes stray backslashes
    try:
        return json.loads(raw, strict=False)
    except ValueError:
        return None


def cg_availability(page: str, tz) -> dict:
    text = re.sub(r"\s+", " ", html.unescape(re.sub(r"<[^>]+>", " ", page)))
    out: dict = {}
    if re.search(r"Availability\s+Sold-?Out", text, re.I):
        out["sold_out"] = True
    m = re.search(r"Availability\s+(\d+) Spots? Left", text, re.I)
    if m:
        out["spots_left"] = int(m.group(1))
    m = re.search(r"Sales End\s+(\w{3} \d{1,2}, \d{4} at \d{1,2}(?::\d{2})? [AP]M)", text)
    if m:
        for fmt in ("%b %d, %Y at %I:%M %p", "%b %d, %Y at %I %p"):
            try:
                out["register_by"] = datetime.strptime(m.group(1), fmt).replace(tzinfo=tz)
                break
            except ValueError:
                pass
    if "Registration is closed" in text:
        out["closed"] = True
    return out


def cg_rows(base: str, end: datetime, get: Fetch, max_pages: int = 15) -> list[dict]:
    """Every event row up to the window's end, de-duplicated by id (pages overlap)."""
    rows: dict[str, dict] = {}
    for page in range(max_pages):
        data = json.loads(get(base + CG_LIST.format(offset=page * 100)))
        events = [r for r in data if str(r.get("fields", "")).startswith("date_separator,eventId")]
        if not events:
            break
        for r in events:
            rows.setdefault(r["p1"], r)
        last = cg_row_start(events[-1])
        if last and last > end:
            break
    return list(rows.values())


def cg_event(base: str, row: dict, page: Optional[str]) -> Optional[dict]:
    tz = cg_offset(row)
    ld = cg_jsonld(page) if page else None
    start, end = cg_row_start(row), None
    description, location = "", html.unescape(row.get("p6") or "")
    if ld:
        description = html.unescape(ld.get("description") or "")
        try:
            start = datetime.fromisoformat(ld["startDate"])
            end = datetime.fromisoformat(ld["endDate"])
        except (KeyError, ValueError):
            pass
        loc = ld.get("location") or {}
        if isinstance(loc, dict) and loc.get("name"):
            location = html.unescape(loc["name"]).strip()
    if start is None:
        return None
    tags = cg_tags(row)
    ev = blank(
        id=row["p1"], name=html.unescape(row.get("p3") or (ld or {}).get("name", "")).strip(),
        host=html.unescape(row.get("p9") or "").strip(), tags=tags, audience=audience_from(
            [t for t in tags if t in ("Undergraduate", "Graduate")]),
        start=start, end=end or start + timedelta(hours=1), location=location,
        price=(row.get("p12") or "").strip(), description=description,
        restricted=bool(page and CG_RESTRICTED in page),
        campus=next((CG_CAMPUS[t] for t in tags if t in CG_CAMPUS), None),
        url=base + CG_EVENT.format(id=row["p1"]),
    )
    if page:
        ev.update(cg_availability(page, tz))
    return ev


def campusgroups(base: str, start: datetime, end: datetime, get: Fetch = fetch) -> list[dict]:
    rows = cg_rows(base, end, get)
    rows = [r for r in rows if not cg_multiday(r)
            and start - timedelta(hours=3) <= (cg_row_start(r) or start) <= end]

    def detail(r):
        try:
            return r, get(base + CG_EVENT.format(id=r["p1"]))
        except OSError:
            return r, None

    with cf.ThreadPoolExecutor(max_workers=6) as pool:
        pairs = list(pool.map(detail, rows))
    if rows and not any(p for _, p in pairs):
        raise OSError("no event page could be read")
    return [e for e in (cg_event(base, r, p) for r, p in pairs) if e]


# ---------------------------------------------------------------- Campus Labs Engage (Anthology)

def engage(base: str, start: datetime, end: datetime, get: Fetch = fetch) -> list[dict]:
    def iso(d: datetime) -> str:
        return d.astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")

    out, skip = [], 0
    while True:
        q = urllib.parse.urlencode({"endsAfter": iso(start), "startsBefore": iso(end), "orderByField": "startsOn",
                                    "orderByDirection": "ascending", "status": "Approved", "take": 100, "skip": skip})
        data = json.loads(get(f"{base}/api/discovery/event/search?{q}"))
        batch = data.get("value") or []
        for e in batch:
            s, f = datetime.fromisoformat(e["startsOn"]), datetime.fromisoformat(e["endsOn"])
            if f - s > timedelta(days=2):
                continue  # standing, term-long listings
            tags = [t for t in (e.get("categoryNames") or []) + [e.get("theme") or ""] if t]
            benefits = e.get("benefitNames") or []
            out.append(blank(
                id=str(e["id"]), name=(e.get("name") or "").strip(), host=e.get("organizationName") or "",
                tags=tags + benefits, audience=audience_from(tags), start=s, end=f,
                location=e.get("location") or "", description=text_of(e.get("description") or ""),
                restricted=(e.get("visibility") or "Public") != "Public",
                food_flag="Listed with the Free Food perk" if "Free Food" in benefits else None,
                url=f"{base}/event/{e['id']}",
            ))
        skip += len(batch)
        if not batch or skip >= int(data.get("@odata.count") or 0) or skip >= 1500:
            return out


# ---------------------------------------------------------------- Localist

def localist(base: str, start: datetime, end: datetime, get: Fetch = fetch) -> list[dict]:
    days = max(1, (end.date() - start.date()).days + 1)
    out, page = [], 1
    while True:
        q = urllib.parse.urlencode({"start": start.date().isoformat(), "days": days, "pp": 100, "page": page})
        data = json.loads(get(f"{base}/api/2/events?{q}"))
        for wrap in data.get("events") or []:
            e = wrap.get("event") or {}
            filters = e.get("filters") or {}
            aud_labels = [a.get("name", "") for a in filters.get("event_audience") or []]
            types = [t.get("name", "") for t in filters.get("event_types") or []]
            tags = types + list(e.get("tags") or []) + list(e.get("keywords") or [])
            host = ", ".join(d.get("name", "") for d in e.get("departments") or [] if d.get("name"))
            place = " ".join(x for x in [e.get("location_name") or "", e.get("room_number") or ""] if x).strip()
            price = "FREE" if e.get("free") else (e.get("ticket_cost") or "")
            for inst in e.get("event_instances") or []:
                i = inst.get("event_instance") or {}
                if i.get("all_day"):
                    continue  # all-day listings are exhibits and deadlines, not gatherings with a time
                try:
                    s = datetime.fromisoformat(i["start"])
                except (KeyError, TypeError, ValueError):
                    continue
                f = datetime.fromisoformat(i["end"]) if i.get("end") else s + timedelta(hours=1)
                out.append(blank(
                    id=f"{e.get('id')}-{i.get('id')}", name=(e.get("title") or "").strip(), host=host,
                    tags=tags + aud_labels, audience=audience_from(aud_labels), start=s, end=f,
                    location=place or e.get("address") or "", price=price,
                    description=e.get("description_text") or text_of(e.get("description") or ""),
                    restricted=bool(e.get("private")), url=e.get("localist_url") or "",
                ))
        info = data.get("page") or {}
        if not info.get("next_page") or page >= 20:
            return out
        page += 1


# ---------------------------------------------------------------- iCalendar (.ics) feeds

def ics_unescape(v: str) -> str:
    return re.sub(r"\\([nN,;\\])", lambda m: "\n" if m.group(1) in "nN" else m.group(1), v)


def ics_time(value: str, params: str, default_tz) -> tuple[Optional[datetime], bool]:
    """(datetime, all_day)."""
    value = value.strip()
    if "VALUE=DATE" in params.upper() and "VALUE=DATE-TIME" not in params.upper():
        try:
            d = datetime.strptime(value[:8], "%Y%m%d")
            return d.replace(tzinfo=default_tz), True
        except ValueError:
            return None, True
    try:
        d = datetime.strptime(value[:15], "%Y%m%dT%H%M%S")
    except ValueError:
        return None, False
    if value.endswith("Z"):
        return d.replace(tzinfo=timezone.utc), False
    m = re.search(r"TZID=([^;:]+)", params)
    tz = (zone(m.group(1).strip('"')) if m else None) or default_tz
    return d.replace(tzinfo=tz), False


def ics(url: str, start: datetime, end: datetime, get: Fetch = fetch, student_tz=None) -> list[dict]:
    raw = get(url)
    if "BEGIN:VCALENDAR" not in raw[:2000]:
        raise ValueError("not an iCalendar feed")
    text = re.sub(r"\r?\n[ \t]", "", raw)  # unfold continuation lines
    m = re.search(r"^X-WR-TIMEZONE:(.+)$", text, re.M)
    default_tz = zone(m.group(1).strip()) if m else None
    default_tz = default_tz or student_tz or start.tzinfo
    out = []
    for block in re.findall(r"BEGIN:VEVENT(.*?)END:VEVENT", text, re.S):
        props: dict[str, tuple[str, str]] = {}
        for line in block.strip().splitlines():
            km = re.match(r"([A-Z][A-Z0-9-]*)((?:;[^:]*)?):(.*)", line)
            if km and km.group(1) not in props:
                props[km.group(1)] = (km.group(2), km.group(3))
        if "DTSTART" not in props:
            continue
        s, all_day = ics_time(props["DTSTART"][1], props["DTSTART"][0], default_tz)
        if s is None or all_day:
            continue
        f = ics_time(props["DTEND"][1], props["DTEND"][0], default_tz)[0] if "DTEND" in props else None
        if f is None or f <= s:
            f = s + timedelta(hours=1)
        if not (f >= start and s <= end):
            continue  # recurrences (RRULE) are not expanded; only each event's own start counts
        get_v = lambda k: ics_unescape(props.get(k, ("", ""))[1]).strip()
        cats = [c.strip() for c in get_v("CATEGORIES").split(",") if c.strip()]
        org = re.search(r'CN="?([^";:]+)', props.get("ORGANIZER", ("", ""))[0])
        out.append(blank(
            id=get_v("UID") or f"{s.isoformat()}-{get_v('SUMMARY')}", name=get_v("SUMMARY"),
            host=org.group(1) if org else "", tags=cats, audience=audience_from(cats), start=s, end=f,
            location=get_v("LOCATION"), description=text_of(get_v("DESCRIPTION")) if "<" in get_v("DESCRIPTION") else get_v("DESCRIPTION"),
            restricted=get_v("CLASS").upper() in ("PRIVATE", "CONFIDENTIAL"), url=get_v("URL"),
        ))
    return out


# ---------------------------------------------------------------- the student's own list

def events_file(path: str, start: datetime, end: datetime, student_tz) -> list[dict]:
    """Events Cubbie read from any other site and wrote down: a JSON list of
    {name, start, end?, location?, description?, url?, host?, tags?, audience?, price?}."""
    with open(path) as fh:
        data = json.load(fh)
    out = []
    for i, e in enumerate(data):
        s = datetime.fromisoformat(e["start"])
        s = s if s.tzinfo else s.replace(tzinfo=student_tz)
        f = datetime.fromisoformat(e["end"]) if e.get("end") else s + timedelta(hours=1)
        f = f if f.tzinfo else f.replace(tzinfo=student_tz)
        if not (f >= start and s <= end):
            continue
        tags = list(e.get("tags") or [])
        out.append(blank(
            id=str(e.get("id") or i), name=e.get("name", ""), host=e.get("host", ""), tags=tags,
            audience=audience_from(list(e.get("audience") or [])), start=s, end=f,
            location=e.get("location", ""), price=e.get("price", ""), description=e.get("description", ""),
            restricted=bool(e.get("restricted")), url=e.get("url", ""),
        ))
    return out


# ---------------------------------------------------------------- recognising a site

def origin(url: str) -> str:
    p = urllib.parse.urlsplit(url if "://" in url else "https://" + url)
    return f"{p.scheme}://{p.netloc}"


def detect(site: str, get: Fetch = fetch, peek=fetch_final) -> tuple[str, str]:
    """(platform, base) for a school's event site, or ("unknown", site)."""
    url = site if "://" in site else "https://" + site
    path = urllib.parse.urlsplit(url).path
    if path.lower().endswith((".ics", ".ical")) or "/ical" in path.lower():
        return "ics", url
    candidates = [url]
    try:
        final, ctype, body = peek(url)
        if "text/calendar" in ctype or body.lstrip().startswith("BEGIN:VCALENDAR"):
            return "ics", final
        candidates.append(final)
        m = re.search(r'https://[\w.-]+\.campuslabs\.com/engage', body)
        if m:
            candidates.append(m.group(0))
    except OSError:
        pass
    for u in candidates:
        o = origin(u)
        if "/engage" in u or o.endswith("campuslabs.com"):
            if _json_has(get, o + "/engage/api/discovery/event/search?take=1", "@odata.count"):
                return "engage", o + "/engage"
        if _json_has(get, o + "/mobile_ws/v18/mobile_school", "school_code"):
            return "campusgroups", o
        if _json_has(get, o + "/api/2/events?pp=1", "events"):
            return "localist", o
        if _json_has(get, o + "/engage/api/discovery/event/search?take=1", "@odata.count"):
            return "engage", o + "/engage"
    return "unknown", url


def _json_has(get: Fetch, url: str, key: str) -> bool:
    try:
        return key in json.loads(get(url))
    except (OSError, ValueError, TypeError):
        return False


READERS = {"campusgroups": campusgroups, "engage": engage, "localist": localist}
