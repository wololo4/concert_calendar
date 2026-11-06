from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timezone
import os
import re
import sys
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
from tickets import load_state, mark_events, sync_issue

CITIES = {"Montreal"}  # cities listed in the ticket checklist issue


def get_robust_session():
  s = requests.Session()
  retries = Retry(
      total=3, backoff_factor=1, status_forcelist=[500, 502, 503, 504, 429]
  )
  adapter = HTTPAdapter(
      pool_connections=10, pool_maxsize=10, max_retries=retries
  )
  s.mount("https://", adapter)
  s.mount("http://", adapter)
  return s


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
  headers = {"User-Agent": "Mozilla/5.0"}
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

    resp = session.get(url, headers=headers, timeout=15)
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
