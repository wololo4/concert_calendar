from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timezone
import json
import os
import re
import sys
import time
from feeds import load_feeds
from icalendar import Calendar
import requests
from requests.adapters import HTTPAdapter
from urllib3.util import Retry

import tm_search
from dict.dict_venue import VENUE_ALIASE, VENUE_CITY
from parser.imperialbell import build_event_imperialbell, parse_imperialbell_html
from parser.eventbrite import build_eventbrite_calendar, parse_eventbrite_html
from parser.lepointdevente import build_event_lpdv, parse_lpdv_html
from parser.ovation import build_event_ovation, parse_ovation_html
from parser.morsefest import build_event_morsefest, parse_morsefest_html
from parser.progstorm import build_progstorm_calendar, parse_progstorm_html
from parser.ticketweb import build_event_ticketweb, parse_ticketweb_html
from tickets import load_state, mark_events, sync_issue

CITIES = {"Montreal"}  # cities listed in the ticket checklist issue

DEFAULT_HEADERS = {"User-Agent": "Mozilla/5.0"}
BROWSER_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36"
    ),
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Accept-Language": "en-CA,en;q=0.9",
}
HEADERS_BY_PARSER = {"ticketweb": BROWSER_HEADERS}


def get_robust_session():
  s = requests.Session()
  retries = Retry(
      total=3,
      backoff_factor=1,
      status_forcelist=[500, 502, 503, 504, 429, 530],
      raise_on_status=False,  # keep the last response so its body can be logged
  )
  adapter = HTTPAdapter(
      pool_connections=10, pool_maxsize=10, max_retries=retries
  )
  s.mount("https://", adapter)
  s.mount("http://", adapter)
  return s


LD_JSON = 'script[type="application/ld+json"]'
NEXT_DATA_RE = re.compile(
    r'(<script[^>]*id="__NEXT_DATA__"[^>]*>)(.*?)(</script>)', re.DOTALL
)


def fetch_html_browser(
    url, ready, more=None, collect=None, seen=None, paginate=None
):
  """Real Chromium fetch for pages that need JavaScript.

  ready: CSS selector that must exist before the page counts as loaded.
  more: text of a "load more" control to click until it disappears.
  collect/seen: when given, JSON responses are scanned for events (dict by
  id) and their URLs listed, so data loaded by "load more" is not lost.
  paginate: same-site API path with a {page} placeholder, called from inside
  the page (cookies included) for page 1, 2, ... until no new event shows up.
  """
  from playwright.sync_api import sync_playwright

  with sync_playwright() as p:
    browser = p.chromium.launch(
        headless=False,  # runs under xvfb-run
        args=["--disable-blink-features=AutomationControlled"],
    )
    try:
      ctx = browser.new_context(
          user_agent=BROWSER_HEADERS["User-Agent"], locale="en-CA"
      )
      ctx.add_init_script(
          "Object.defineProperty(navigator, 'webdriver', {get: () => undefined})"
      )
      page = ctx.new_page()
      responses = []
      if collect is not None:
        page.on("response", lambda r: responses.append(r))

      page.goto(url, wait_until="domcontentloaded", timeout=30000)
      try:
        page.wait_for_selector(ready, state="attached", timeout=40000)
      except Exception:
        print(f"⚠️ browser: '{ready}' never appeared on {page.url}")
        print(f"⚠️ browser: title={page.title()!r}")
        print(f"⚠️ browser: html[:1500]={page.content()[:1500]!r}")
        raise

      for _ in range(30 if more else 0):
        btn = page.get_by_text(more, exact=True)
        if not btn.count() or not btn.first.is_visible():
          break
        before = page.locator(ready).count()
        try:
          btn.first.click(timeout=5000)
          page.wait_for_function(
              "([sel, n]) => document.querySelectorAll(sel).length > n",
              arg=[ready, before],
              timeout=8000,
          )
        except Exception:
          break  # click failed or nothing new loaded: keep what we have

      if paginate and collect is not None:
        for n in range(1, 31):
          got = page.evaluate(
              """async (u) => {
                const r = await fetch(u, {headers: {accept: 'application/json'}});
                return {status: r.status, body: await r.text()};
              }""",
              paginate.format(page=n),
          )
          before = len(collect)
          try:
            _collect_events(json.loads(got["body"]), collect)
          except Exception:
            pass
          new = len(collect) - before
          print(f"Eventbrite API page {n}: HTTP {got['status']}, {new} new events")
          if got["status"] != 200 or new == 0:
            if n == 1:
              print(f"Eventbrite API page 1 body[:400]: {got['body'][:400]!r}")
            break

      if collect is not None:
        for r in responses:
          try:
            if "json" not in (r.headers.get("content-type") or ""):
              continue
            if seen is not None:
              seen.append(r.url[:110])
            _collect_events(r.json(), collect)
          except Exception:
            pass
      return page.content()
    finally:
      browser.close()


def _collect_events(obj, out):
  """Walk any JSON and keep dicts that look like Eventbrite events."""
  if isinstance(obj, dict):
    if (
        obj.get("id")
        and obj.get("name")
        and obj.get("start_date")
        and obj.get("start_time")
    ):
      out[str(obj["id"])] = obj
    for v in obj.values():
      _collect_events(v, out)
  elif isinstance(obj, list):
    for v in obj:
      _collect_events(v, out)


def fetch_eventbrite_html(url, label):
  """Organizer page + the events its "Show more" button loads.

  The parser reads upcomingEvents from __NEXT_DATA__, which only holds the
  first page, so events loaded by "Show more" are merged into it here.
  """
  extra, seen = {}, []
  org = re.search(r"(\d+)/?$", url).group(1)
  raw = fetch_html_browser(
      url,
      ready='a[href*="/e/"]',
      collect=extra,
      seen=seen,
      paginate=f"/api/organizer-profile/organizers/{org}/events?page={{page}}&pageSize=12",
  )

  m = NEXT_DATA_RE.search(raw)
  if not m:
    return raw
  try:
    data = json.loads(m.group(2))
    page_props = data["props"]["pageProps"]
  except Exception:
    return raw

  existing = page_props.get("upcomingEvents") or []
  have = {str(e.get("id")) for e in existing}
  added = [e for i, e in extra.items() if i not in have]
  page_props["upcomingEvents"] = existing + added
  print(
      f"Eventbrite {label}: {len(existing)} events on first page, "
      f"{len(added)} more loaded by 'Show more'"
  )
  if not added:
    print(f"Eventbrite {label}: JSON responses seen: {seen[:15]}")

  new_json = json.dumps(data, ensure_ascii=False).replace("</", "<\\/")
  return raw[: m.start(2)] + new_json + raw[m.end(2) :]


def fetch_ticketweb_html(session, url, headers):
  """Plain requests succeed only some of the time, so try again, then browser."""
  for attempt in range(1, 4):
    time.sleep(5)
    resp = session.get(url, headers=headers, timeout=15)
    if resp.ok:
      print(f"ticketweb: plain request worked on retry {attempt}")
      return resp.content.decode("utf-8")
  print("ticketweb: still blocked after retries, trying a browser")
  return fetch_html_browser(url, ready=LD_JSON)


def extract_city_from_event(ev):
  loc = ev.get("LOCATION")
  if not loc:
    return None

  venue_raw = loc.split(",")[0].strip()
  venue = venue_raw
  for canonical, aliases in VENUE_ALIASE.items():
    if venue_raw == canonical or venue_raw in aliases:
      venue = canonical
      break

  return VENUE_CITY.get(venue)


def fetch_and_parse_feed(feed, session):
  """Returns (events, error). error is None when the feed succeeded."""
  parser_name, label, url, params, parser_key = feed
  headers = HEADERS_BY_PARSER.get(parser_key, DEFAULT_HEADERS)
  try:
    if parser_key == "ticketmaster":
      events, errors = tm_search.fetch_events(session, url, params)
      err = None
      if errors:
        err = (
            f"{parser_name}: {len(errors)} request(s) failed, "
            f"first: {errors[0]}"
        )
        print(f"⚠️ {err}")
      return events, err

    if parser_key == "eventbrite":
      raw = fetch_eventbrite_html(url, label)
    else:
      resp = session.get(url, headers=headers, timeout=15)
      if resp.ok:
        raw = resp.content.decode("utf-8")
      elif parser_key == "ticketweb":
        print(
            f"⚠️ {parser_name} ({label}) HTTP {resp.status_code} "
            f"server={resp.headers.get('server')!r}, retrying"
        )
        raw = fetch_ticketweb_html(session, url, headers)
      else:
        print(
            f"⚠️ {parser_name} ({label}) HTTP {resp.status_code} "
            f"server={resp.headers.get('server')!r} body={resp.text[:300]!r}"
        )
        resp.raise_for_status()
        raw = resp.content.decode("utf-8")
    artists = [a.lower() for a in params.get("artists", [])]

    if parser_key == "eventbrite":
      cal = build_eventbrite_calendar(parse_eventbrite_html(raw, artists))
    elif parser_key == "imperialbell":
      cal = build_event_imperialbell(parse_imperialbell_html(raw, artists))
    elif parser_key == "lepointdevente":
      cal = build_event_lpdv(parse_lpdv_html(raw, artists))
    elif parser_key == "morsefest":
      cal = build_event_morsefest(parse_morsefest_html(raw, url))
      print(f"Found {len(list(cal.walk('VEVENT')))} Morsefest events")
    elif parser_key == "ovation":
      parsed = parse_ovation_html(raw, artists)
      cal = build_event_ovation(parsed)
    elif parser_key == "progstorm":
      cal = build_progstorm_calendar(
          parse_progstorm_html(raw, params["times"])
      )
      print("Found Progstorm events")
    elif parser_key == "ticketweb":
      cal = build_event_ticketweb(parse_ticketweb_html(raw, artists))
    else:
      msg = f"No handler for parser_key '{parser_key}' ({label})"
      print(f"⚠️ {msg}")
      return [], msg

    return list(cal.walk("VEVENT")), None
  except Exception as e:
    # never print the Ticketmaster API key
    msg = re.sub(r"apikey=[^&\s]+", "apikey=***", str(e))
    err = f"{parser_name} ({label}): {msg}"
    print(f"⚠️ Error fetching/parsing {err}")
    return [], err


def get_event_start(ev):
  try:
    dt = ev.decoded("dtstart")
    if not isinstance(dt, datetime):
      dt = datetime(dt.year, dt.month, dt.day)
    return (
        dt.astimezone(timezone.utc).replace(tzinfo=None) if dt.tzinfo else dt
    )
  except Exception:
    return datetime.max


def write_calendar(path, events):
  cal = Calendar()
  for ev in events:
    cal.add_component(ev)
  tmp = f"{path}.tmp"
  with open(tmp, "wb") as f:
    f.write(cal.to_ical())
  os.replace(tmp, path)  # a crash can't leave a half-written calendar


def main():
  feeds = load_feeds()
  session = get_robust_session()

  print(f"Fetching {len(feeds)} feeds safely...")
  results = [([], "not run")] * len(feeds)
  with ThreadPoolExecutor(max_workers=5) as executor:
    futures = {
        executor.submit(fetch_and_parse_feed, feed, session): i
        for i, feed in enumerate(feeds)
    }
    for f in as_completed(futures):
      i = futures[f]
      try:
        results[i] = f.result()
      except Exception as e:
        results[i] = ([], f"{feeds[i][0]} ({feeds[i][1]}): {e}")

  # Same as before (unique by UID), but in feed order so the result is
  # the same on every run
  failed = [err for _, err in results if err]
  unique = {}
  for events, _ in results:
    for ev in events:
      unique[str(ev.get("UID"))] = ev

  if not unique:
    print("ABORTING: no events fetched, calendars left untouched.")
    sys.exit(1)

  # Read ticked boxes from the GitHub issue and mark those events.
  # If the checklist can't be read, stop: writing the calendars now would
  # silently remove the TICKET BOUGHT lines.
  try:
    state = load_state()
  except Exception as e:
    print(f"ABORTING: could not read the ticket checklist: {e}")
    sys.exit(1)
  mark_events(unique.values(), state)

  city_events = {}
  for ev in unique.values():
    city = extract_city_from_event(ev)
    if city is None:
      print(f"⚠️ No city for: {ev.get('SUMMARY')} @ {ev.get('LOCATION')}")
      continue
    city_events.setdefault(city, []).append(ev)

  # Every city keeps its own calendar file
  os.makedirs("calendars", exist_ok=True)
  for city, events in city_events.items():
    events.sort(key=get_event_start)
    write_calendar(f"calendars/{city.lower()}.ics", events)
    print(f"{city}.ics file created with {len(events)} events.")

  # Checklist issue: only the cities listed in CITIES
  try:
    sync_issue(
        [
            (ev, city)
            for city, evs in city_events.items()
            if city in CITIES
            for ev in evs
        ],
        state,
    )
  except Exception as e:
    print(f"⚠️ Could not update the checklist: {e}")

  print(f"\nFailed feeds: {len(failed)}")
  for err in failed[:20]:
    print(f"  - {err}")


if __name__ == "__main__":
  main()
