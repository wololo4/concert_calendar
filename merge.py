from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timezone
import re
from feeds import load_feeds
from icalendar import Calendar
import requests
from requests.adapters import HTTPAdapter
from urllib3.util import Retry

from dict.dict_venue import VENUE_ALIASE, VENUE_CITY
from parser.imperialbell import build_event_imperialbell, parse_imperialbell_html
from parser.eventbrite import build_eventbrite_calendar, parse_eventbrite_html
from parser.lepointdevente import build_event_lpdv, parse_lpdv_html
from parser.ovation import build_event_ovation, parse_ovation_html
from parser.progstorm import build_progstorm_calendar, parse_progstorm_html
from parser.ticketmaster import parse_ticketmaster_json


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
  parser_name, label, url, params, parser_key = feed
  headers = {"User-Agent": "Mozilla/5.0"}
  try:
    if parser_key == "ticketmaster":
      raw = session.get(
          url, params=params, headers=headers, timeout=15
      ).json()
      artist, city = label.rsplit("(", 1)
      artist, city = artist.strip(), city.strip(") ").strip()
      cal = parse_ticketmaster_json(raw, [artist.lower()])
      if cal.walk("VEVENT"):
        print(f"Found Ticketmaster events for: {artist} in {city}")
      return list(cal.walk("VEVENT"))

    resp = session.get(url, headers=headers, timeout=15)
    raw = resp.text
    artists = [a.lower() for a in params.get("artists", [])]

    if parser_key == "eventbrite":
      cal = build_eventbrite_calendar(parse_eventbrite_html(raw, artists))
    elif parser_key == "imperialbell":
      cal = build_event_imperialbell(parse_imperialbell_html(raw, artists))
    elif parser_key == "lepointdevente":
      cal = build_event_lpdv(parse_lpdv_html(raw, artists))
    elif parser_key == "ovation":
      parsed = parse_ovation_html(raw, artists)
      print("OVATION parsed events:", len(parsed))
      cal = build_event_ovation(parsed)
    elif parser_key == "progstorm":
      cal = build_progstorm_calendar(
          parse_progstorm_html(raw, params["times"])
      )
      print("Found Progstorm events")
    else:
      print(f"⚠️ No handler for parser_key '{parser_key}' ({label})")
      return []

    return list(cal.walk("VEVENT"))
  except Exception as e:
    print(f"⚠️ Error fetching/parsing {parser_name} ({label}): {e}")
    return []


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


def main():
  feeds = load_feeds()
  all_events = []
  session = get_robust_session()

  print(f"Fetching {len(feeds)} feeds safely...")
  with ThreadPoolExecutor(max_workers=5) as executor:
    futures = {
        executor.submit(fetch_and_parse_feed, feed, session): feed
        for feed in feeds
    }
    for f in as_completed(futures):
      if res := f.result():
        all_events.extend(res)

  unique = {str(ev.get("UID")): ev for ev in all_events}
  city_events = {}
  for ev in unique.values():
    city = extract_city_from_event(ev)
    if city is None:
      print(f"⚠️ No city for: {ev.get('SUMMARY')} @ {ev.get('LOCATION')}")
      continue
    city_events.setdefault(city, []).append(ev)

  for city, events in city_events.items():
    events.sort(key=get_event_start)
    cal = Calendar()
    for ev in events:
      cal.add_component(ev)
    with open(f"calendars/{city.lower()}.ics", "wb") as f:
      f.write(cal.to_ical())
    print(f"{city}.ics file created with {len(events)} events.")


if __name__ == "__main__":
  main()
