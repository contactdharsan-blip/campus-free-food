"""Offline tests for campus-free-food. Fixtures are real responses saved 2026-10-24 from ASU
Sun Devil Central (CampusGroups), Georgia Tech (Engage), Stanford (Localist) and UW (Trumba iCal).

    python3 -m unittest discover -s tests
"""

import argparse
import io
import json
import os
import sys
import unittest
from contextlib import redirect_stdout
from datetime import datetime, timedelta, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SKILL = ROOT / "campus-free-food"
sys.path.insert(0, str(SKILL / "scripts"))
import free_food as ff  # noqa: E402
import platforms as pf  # noqa: E402

FIX = Path(__file__).resolve().parent / "fixtures"
CG = FIX / "campusgroups"
ROWS = {r["p1"]: r for r in json.loads((CG / "list.json").read_text())}
AZ = pf.zone("America/Phoenix")
UTC = timezone.utc


def cg(eid):
    return pf.cg_event("https://sundevilcentral.eoss.asu.edu", ROWS[eid], (CG / f"{eid}.html").read_text())


def me(**kw):
    base = dict(now=datetime(2026, 10, 24, 13, 0, tzinfo=AZ), tz=AZ, level="undergrad", campus="tempe",
                honors=False, hall="", orgs=[], international=False, veteran=False, show_ineligible=False)
    base.update(kw)
    return argparse.Namespace(**base)


def run(*args):
    buf = io.StringIO()
    with redirect_stdout(buf):
        code = ff.main(list(args))
    return code, json.loads(buf.getvalue())


def ev(**kw):
    return pf.blank(**dict(dict(name="Social", host="Some Club", tags=["Social"], location="MU 202", price="FREE",
                                start=datetime(2026, 10, 26, 12, tzinfo=AZ), end=datetime(2026, 10, 26, 13, tzinfo=AZ)), **kw))


# ---------------------------------------------------------------- platforms

class CampusGroups(unittest.TestCase):
    def test_jsonld_with_stray_backslashes_is_repaired(self):
        self.assertIsNotNone(pf.cg_jsonld((CG / "414317.html").read_text()))

    def test_registration_form_page_falls_back_to_the_list_row(self):
        e = cg("416012")
        self.assertIsNone(pf.cg_jsonld((CG / "416012.html").read_text()))
        self.assertEqual(e["name"], "Pumpkins, Pies & Pals")
        self.assertIsNotNone(e["start"])

    def test_restricted_banner(self):
        self.assertTrue(cg("415056")["restricted"])
        self.assertFalse(cg("414636")["restricted"])

    def test_times_are_arizona_time(self):
        e = cg("418132")
        self.assertEqual(e["start"].utcoffset(), timedelta(hours=-7))
        self.assertEqual(pf.cg_row_start(ROWS["418132"]).utcoffset(), timedelta(hours=-7))

    def test_campus_and_audience_from_tags(self):
        e = cg("414636")
        self.assertEqual(e["campus"], "tempe")
        self.assertIn("grad", cg("414317")["audience"])

    def test_pages_overlap_are_deduplicated_and_an_empty_page_ends_paging(self):
        rows = list(ROWS.values())
        pages = {0: rows, 100: rows[-2:], 200: []}
        calls = []

        def fake(url):
            off = int(url.split("range=")[1].split("&")[0])
            calls.append(off)
            return json.dumps(pages[off])

        got = pf.cg_rows("https://x", datetime(2027, 1, 1, tzinfo=AZ), fake)
        self.assertEqual(sorted(r["p1"] for r in got), sorted(ROWS))
        self.assertEqual(calls, [0, 100, 200])

    def test_paging_stops_once_a_page_ends_past_the_window(self):
        rows = sorted(ROWS.values(), key=pf.cg_row_start)
        calls = []
        pf.cg_rows("https://x", pf.cg_row_start(rows[-1]).replace(day=1), lambda u: calls.append(u) or json.dumps(rows))
        self.assertEqual(len(calls), 1)

    def test_multiday_standing_meetings_are_recognised(self):
        self.assertTrue(pf.cg_multiday({"p4": "<p>Mon, Aug 24, 2026 7:00 PM &ndash; </p><p>Mon, Nov 30, 2026 8:00 PM</p>"}))
        self.assertFalse(pf.cg_multiday({"p4": "<p>Sat, Oct 24, 2026</p>9 AM &ndash; 11 AM"}))


class Engage(unittest.TestCase):
    def setUp(self):
        data = json.loads((FIX / "engage.json").read_text())
        self.calls = []

        def fake(url):
            self.calls.append(url)
            batch = data["value"] if "skip=0" in url else []
            return json.dumps({"value": batch, "@odata.count": len(data["value"])})

        self.events = pf.engage("https://gatech.campuslabs.com/engage", datetime(2026, 10, 1, tzinfo=UTC),
                                datetime(2026, 12, 1, tzinfo=UTC), fake)

    def test_window_is_filtered_on_the_server(self):
        self.assertIn("startsBefore=2026-12-01T00%3A00%3A00Z", self.calls[0])
        self.assertIn("endsAfter=2026-10-01T00%3A00%3A00Z", self.calls[0])
        self.assertEqual(len(self.calls), 1)  # all 40 fit the reported count, so no second page

    def test_descriptions_are_plain_text(self):
        self.assertTrue(all("<p" not in e["description"] and "&amp;" not in e["description"] for e in self.events))

    def test_free_food_perk_is_a_certain_food_signal(self):
        e = next(e for e in self.events if e["name"] == "GT D&D Club Halloween Game Night")
        self.assertEqual(e["food_flag"], "Listed with the Free Food perk")
        self.assertTrue(ff.food_evidence(e["name"], e["description"], e["food_flag"])["certain"])

    def test_times_are_utc_and_convert_to_the_students_zone(self):
        e = next(e for e in self.events if e["name"] == "Homecoming Football Tailgate")
        self.assertEqual(e["start"], datetime(2026, 10, 24, 16, tzinfo=UTC))
        self.assertEqual(e["start"].astimezone(pf.zone("America/New_York")).hour, 12)


class Localist(unittest.TestCase):
    def setUp(self):
        data = json.loads((FIX / "localist.json").read_text())
        self.raw = data
        self.events = pf.localist("https://events.stanford.edu", datetime(2026, 10, 24, tzinfo=UTC),
                                  datetime(2026, 10, 28, tzinfo=UTC),
                                  lambda u: json.dumps({"events": data["events"], "page": {"next_page": None}}))

    def test_one_event_per_timed_instance_and_all_day_listings_skipped(self):
        timed = sum(1 for w in self.raw["events"] for i in w["event"]["event_instances"] if not i["event_instance"]["all_day"])
        self.assertEqual(len(self.events), timed)

    def test_audience_comes_from_the_event_audience_filter(self):
        self.assertTrue(any("everyone" in e["audience"] or "students" in e["audience"] for e in self.events))

    def test_times_keep_their_offset(self):
        self.assertTrue(all(e["start"].utcoffset() is not None for e in self.events))

    def test_paging_follows_next_page(self):
        pages = []

        def fake(url):
            pages.append(url)
            n = int(url.split("page=")[1])
            return json.dumps({"events": [], "page": {"next_page": n + 1 if n < 3 else None}})

        pf.localist("https://x", datetime(2026, 10, 24, tzinfo=UTC), datetime(2026, 10, 25, tzinfo=UTC), fake)
        self.assertEqual(len(pages), 3)


class ICal(unittest.TestCase):
    def setUp(self):
        raw = (FIX / "uw.ics").read_text(newline="")
        self.events = pf.ics("https://www.trumba.com/x.ics", datetime(2026, 10, 20, tzinfo=UTC),
                             datetime(2026, 11, 5, tzinfo=UTC), lambda u: raw)

    def test_tzid_times_and_folded_lines(self):
        e = next(e for e in self.events if e["name"] == "Wind Ensemble Chamber Winds")
        self.assertEqual(e["start"], datetime(2026, 10, 25, 13, 30, tzinfo=pf.zone("America/Los_Angeles")))
        self.assertEqual(e["url"], "https://music.washington.edu/events/2026-10-25/wind-ensemble-chamber-winds")
        self.assertEqual(e["end"] - e["start"], timedelta(hours=1))  # DTEND equal to DTSTART gets an hour

    def test_escapes_utc_and_all_day(self):
        raw = ("BEGIN:VCALENDAR\r\nBEGIN:VEVENT\r\nSUMMARY:Pizza\\, pop\\; and talk\r\nDTSTART:20261026T190000Z\r\n"
               "DESCRIPTION:Free pizza provided.\\nAll welcome.\r\nEND:VEVENT\r\nBEGIN:VEVENT\r\nSUMMARY:Holiday\r\n"
               "DTSTART;VALUE=DATE:20261026\r\nEND:VEVENT\r\nEND:VCALENDAR\r\n")
        got = pf.ics("u", datetime(2026, 10, 26, tzinfo=UTC), datetime(2026, 10, 27, tzinfo=UTC), lambda u: raw)
        self.assertEqual([e["name"] for e in got], ["Pizza, pop; and talk"])
        self.assertEqual(got[0]["start"], datetime(2026, 10, 26, 19, tzinfo=UTC))
        self.assertEqual(got[0]["description"], "Free pizza provided.\nAll welcome.")

    def test_tzid_wins_over_the_calendars_default_zone(self):
        raw = ("BEGIN:VCALENDAR\r\nX-WR-TIMEZONE:America/Los_Angeles\r\nBEGIN:VEVENT\r\nSUMMARY:Bagels\r\n"
               "DTSTART;TZID=America/New_York:20261026T090000\r\nEND:VEVENT\r\nEND:VCALENDAR\r\n")
        got = pf.ics("u", datetime(2026, 10, 26, tzinfo=UTC), datetime(2026, 10, 27, tzinfo=UTC), lambda u: raw)
        self.assertEqual(got[0]["start"].astimezone(UTC), datetime(2026, 10, 26, 13, tzinfo=UTC))

    def test_not_a_calendar_is_a_format_error(self):
        with self.assertRaises(ValueError):
            pf.ics("u", datetime(2026, 1, 1, tzinfo=UTC), datetime(2026, 1, 2, tzinfo=UTC), lambda u: "<html>")


class Detect(unittest.TestCase):
    def fake(self, answers):
        def get(url):
            for key, body in answers.items():
                if key in url:
                    return body
            raise OSError("404")
        return get

    def test_each_platform_is_recognised_by_its_own_probe(self):
        peek = lambda u: (u, "text/html", "<html></html>")
        cases = {
            "campusgroups": ({"/mobile_ws/v18/mobile_school": '{"school_code": "x"}'}, "https://events.example.edu"),
            "engage": ({"/engage/api/discovery/event/search": '{"@odata.count": 3}'}, "https://x.campuslabs.com/engage"),
            "localist": ({"/api/2/events": '{"events": []}'}, "https://calendar.example.edu"),
        }
        for want, (answers, site) in cases.items():
            self.assertEqual(pf.detect(site, self.fake(answers), peek)[0], want, want)

    def test_ics_by_extension_or_content_type(self):
        self.assertEqual(pf.detect("https://x.edu/cal.ics", self.fake({}), None)[0], "ics")
        peek = lambda u: (u, "text/calendar", "BEGIN:VCALENDAR")
        self.assertEqual(pf.detect("https://x.edu/feed", self.fake({}), peek)[0], "ics")

    def test_custom_domain_that_links_to_engage(self):
        peek = lambda u: (u, "text/html", '<a href="https://school.campuslabs.com/engage/events">Events</a>')
        got = pf.detect("https://getinvolved.school.edu", self.fake({"school.campuslabs.com/engage/api": '{"@odata.count": 1}'}), peek)
        self.assertEqual(got, ("engage", "https://school.campuslabs.com/engage"))

    def test_unknown_site(self):
        self.assertEqual(pf.detect("https://example.com", self.fake({}), lambda u: (u, "text/html", ""))[0], "unknown")


class Certificates(unittest.TestCase):
    def test_a_certificate_error_retries_with_curl_and_nothing_else_does(self):
        import ssl
        import urllib.error
        calls = []
        orig_open, orig_curl = pf.urllib.request.urlopen, pf._curl
        try:
            pf._curl = lambda url, t: calls.append(url) or ("u", "application/json", "{}")
            pf.urllib.request.urlopen = lambda *a, **k: (_ for _ in ()).throw(
                urllib.error.URLError(ssl.SSLCertVerificationError("bad chain")))
            self.assertEqual(pf.fetch("https://x"), "{}")
            pf.urllib.request.urlopen = lambda *a, **k: (_ for _ in ()).throw(urllib.error.URLError("refused"))
            with self.assertRaises(OSError):
                pf.fetch("https://y")
        finally:
            pf.urllib.request.urlopen, pf._curl = orig_open, orig_curl
        self.assertEqual(calls, ["https://x"])


# ---------------------------------------------------------------- the shared core

class Food(unittest.TestCase):
    def test_quotes_the_sentence_that_promises_food(self):
        f = ff.food_evidence("Barrett Study Night", cg("418132")["description"])
        self.assertEqual(f["quote"], "Snacks provided.")
        self.assertTrue(f["certain"])

    def test_title_alone_counts_when_there_is_no_description(self):
        self.assertIsNotNone(ff.food_evidence("Pumpkins, Pies & Pals", ""))

    def test_event_without_food_is_not_reported(self):
        e = cg("413603")
        self.assertIsNone(ff.food_evidence(e["name"], e["description"]))

    def test_food_that_is_not_free_food(self):
        for s in ["Donate canned food for local families.", "Bake sale: cookies for purchase.",
                  "Pack meals for families in need.", "They work with global food distribution partners.",
                  "Bring a snack to share!", "Food is not allowed on the trails.", "Snacks will not be provided.",
                  "A musical full of eye candy."]:
            self.assertIsNone(ff.food_evidence("Event", s), s)

    def test_long_sentence_quote_keeps_the_food_word(self):
        self.assertIn("snacks", ff.food_evidence("Event", "x " * 150 + "and eat snacks with us!")["quote"])


class Eligibility(unittest.TestCase):
    def test_open_event_is_yes(self):
        self.assertEqual(ff.eligibility(ev(description="Open to all students."), me())[0], "yes")

    def test_members_of_the_community_is_not_members_only(self):
        e = ev(description="Alumni, students, and other members of the community welcome.")
        self.assertEqual(ff.eligibility(e, me())[0], "yes")

    def test_members_of_a_named_club(self):
        e = ev(description="General meeting for members of TAMID.", host="TAMID Group")
        self.assertEqual(ff.eligibility(e, me())[0], "check")
        self.assertEqual(ff.eligibility(e, me(orgs=["TAMID"]))[0], "yes")

    def test_audience(self):
        self.assertEqual(ff.eligibility(ev(audience={"grad"}), me())[0], "no")
        self.assertEqual(ff.eligibility(ev(audience={"grad"}), me(level="grad"))[0], "yes")
        self.assertEqual(ff.eligibility(ev(audience={"faculty"}), me())[0], "no")
        self.assertEqual(ff.eligibility(ev(audience={"grad", "everyone"}), me())[0], "yes")

    def test_honors_event_needs_honors(self):
        e = ev(host="Barrett Residential Life")
        self.assertEqual(ff.eligibility(e, me())[0], "check")
        e = ev(description="A night for Honors College students.")
        self.assertEqual(ff.eligibility(e, me(honors=True))[0], "yes")

    def test_hall_event_is_yes_for_that_halls_residents(self):
        e = ev(host="Palo Blanco Hall", description="Meet your neighbors, free snacks.")
        self.assertEqual(ff.eligibility(e, me())[0], "check")
        self.assertEqual(ff.eligibility(e, me(hall="Palo Blanco"))[0], "yes")

    def test_faculty_named_event_is_a_check(self):
        self.assertEqual(ff.eligibility(ev(name="Faculty SPACE Fall Lunch"), me())[0], "check")

    def test_platform_restriction_sold_out_closed_price(self):
        self.assertEqual(ff.eligibility(ev(restricted=True), me())[0], "check")
        self.assertEqual(ff.eligibility(ev(sold_out=True), me())[0], "no")
        self.assertEqual(ff.eligibility(ev(register_by=datetime(2026, 10, 23, tzinfo=AZ)), me())[0], "no")
        self.assertEqual(ff.eligibility(ev(price="$19-$62"), me())[0], "check")


class Schedule(unittest.TestCase):
    def test_overlap_is_a_conflict_and_back_to_back_is_not(self):
        e = ev()
        clash = [{"start": e["start"] + timedelta(minutes=30), "end": e["end"] + timedelta(minutes=30), "title": "Lab"}]
        after = [{"start": e["end"], "end": e["end"] + timedelta(hours=1), "title": "Class"}]
        self.assertEqual(ff.conflicts(e, clash), ["Lab"])
        self.assertEqual(ff.conflicts(e, after), [])

    def test_busy_times_in_another_zone_still_clash(self):
        e = ev()  # 12:00-13:00 Arizona = 19:00-20:00 UTC
        busy = [{"start": datetime(2026, 10, 26, 19, 30, tzinfo=UTC), "end": datetime(2026, 10, 26, 20, 30, tzinfo=UTC), "title": "Call"}]
        self.assertEqual(ff.conflicts(e, busy), ["Call"])


class Command(unittest.TestCase):
    BUSY = str(SKILL / "assets/sample_busy.json")

    def test_sample_run(self):
        code, out = run("--sample", "--busy", self.BUSY)
        self.assertEqual(code, 0)
        by = {e["name"]: e for e in out["events"]}
        self.assertNotIn("Canned Food Drive", by)  # donating food is not free food
        self.assertNotIn("Grad Mixer", by)          # graduate-only; the student is an undergrad
        self.assertEqual(by["Pizza and Pitches"]["conflicts_with"], ["CHM 113 lecture (example)"])
        self.assertEqual(by["Honors Halloween Social"]["eligible"], "check")
        self.assertEqual(by["Taco Tuesday Study Hall"]["conflicts_with"], ["BIO 181 lab (example)"])
        self.assertTrue(out["schedule_checked"])
        self.assertEqual(out["events"][0]["name"], "Downtown Donut Day")

    def test_same_campus_ranks_before_another_campus(self):
        _, out = run("--sample", "--campus", "tempe", "--days", "3")
        names = [e["name"] for e in out["events"]]
        self.assertLess(names.index("Pizza and Pitches"), names.index("Downtown Donut Day"))
        donut = next(e for e in out["events"] if e["name"] == "Downtown Donut Day")
        self.assertIn("on the downtown campus", donut["why"])

    def test_times_print_in_the_students_zone(self):
        _, out = run("--sample", "--tz", "America/New_York", "--now", "2026-10-26T13:00", "--days", "3")
        donut = next(e for e in out["events"] if e["name"] == "Downtown Donut Day")
        self.assertTrue(donut["when"].startswith("Wed Oct 28, 12:00 PM"))  # 9 AM Arizona is noon Eastern

    def test_events_file_path(self):
        p = FIX / "tmp_events.json"
        p.write_text(json.dumps([
            {"name": "Club Fair", "start": "2026-10-26T11:00", "end": "2026-10-26T13:00",
             "description": "Free tacos while they last.", "url": "https://school.edu/fair"},
            {"name": "Lecture", "start": "2026-10-26T15:00", "description": "A talk."}]))
        try:
            code, out = run("--events-file", str(p), "--now", "2026-10-26T09:00", "--tz", "America/Chicago")
        finally:
            p.unlink()
        self.assertEqual(code, 0)
        self.assertEqual(out["platform"], "events-file")
        self.assertEqual([e["name"] for e in out["events"]], ["Club Fair"])
        self.assertEqual(out["events"][0]["start"], "2026-10-26T11:00:00-05:00")

    def test_argument_errors_are_exit_2(self):
        self.assertEqual(run("--days", "1", "--sample", "--now", "x")[0], 2)
        self.assertEqual(run("--site", "https://x.edu")[0], 2)                      # no --now
        self.assertEqual(run("--site", "https://x.edu", "--now", "2026-10-26T09:00")[0], 2)  # no zone
        self.assertEqual(run("--sample", "--busy", str(CG / "list.json"))[0], 2)
        self.assertEqual(run("--events-file", "/nonexistent.json", "--now", "2026-10-26T09:00-07:00")[0], 2)

    def test_unreachable_site_is_exit_3_and_unknown_site_is_exit_5(self):
        orig = pf.detect
        try:
            pf.detect = lambda s: (_ for _ in ()).throw(OSError("down"))
            self.assertEqual(run("--site", "https://x.edu", "--now", "2026-10-26T09:00-07:00")[0], 3)
            pf.detect = lambda s: ("unknown", s)
            self.assertEqual(run("--site", "https://x.edu", "--now", "2026-10-26T09:00-07:00")[0], 5)
        finally:
            pf.detect = orig

    def test_output_fits_what_cubbie_reads_and_nothing_is_saved(self):
        before = set(os.listdir(Path.home()))
        _, out = run("--sample")
        self.assertLess(len(json.dumps(out)), 8000)
        self.assertEqual(before, set(os.listdir(Path.home())))


if __name__ == "__main__":
    unittest.main()
