from concurrent.futures import ThreadPoolExecutor, as_completed
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
from parser.progstorm import build_progstorm_calendar, parse_progstorm_html
from parser.ticketmaster import parse_ticketmaster_json


def get_robust_session():
  session = requests.Session()
  retries = Retry(
      total=3, backoff_factor=1, status_forcelist=[500, 502, 503, 504, 429]
  )
  adapter = HTTPAdapter(max_retries=retries)
  session.mount("https://", adapter)
  session.mount("http://", adapter)
  return session


def extract_city_from_event(ev):
  loc = ev.get("LOCATION")
  if not loc:
    return None

  venue_raw = loc.split(",")[0].strip()
  venue = venue_raw
  for canonical, aliases in VENUE_ALIASE.items():
    if venue_raw in aliases:
      venue = canonical
      break

  if venue not in VENUE_CITY:
    return None
  return VENUE_CITY[venue]


def fetch_and_parse_feed(feed, session):
  parser_name, label, url, params, parser_key = feed
  headers = {"User-Agent": "Mozilla/5.0"}
  vevents = []

  try:
    if parser_key == "ticketmaster":
      response = session.get(url, params=params, headers=headers, timeout=15)
      response.raise_for_status()
      raw = response.json()

      artist_part, city_part = label.rsplit("(", 1)
      artist = artist_part.strip()
      city = city_part.strip(") ").strip()
      cal = parse_ticketmaster_json(raw, [artist.lower()])
      vevents = list(cal.walk("VEVENT"))
      if vevents:
        print(f"Found Ticketmaster events for: {artist} in {city}")

    else:
      response = session.get(url, headers=headers, timeout=15)
      response.raise_for_status()
      raw = response.text

      if parser_key == "eventbrite":
        artists = [a.lower() for a in params["artists"]]
        events = parse_eventbrite_html(raw, artists)
        cal = build_eventbrite_calendar(events)
        vevents = list(cal.walk("VEVENT"))

      elif parser_key == "imperialbell":
        artists = [a.lower() for a in params["artists"]]
        events = parse_imperialbell_html(raw, artists)
        cal = build_event_imperialbell(events)
        vevents = list(cal.walk("VEVENT"))

      elif parser_key == "lepointdevente":
        artists = [a.lower() for a in params["artists"]]
        events = parse_lpdv_html(raw, artists)
        cal = build_event_lpdv(events)
        vevents = list(cal.walk("VEVENT"))

      elif parser_key == "progstorm":
        times_cfg = params["times"]
        events = parse_progstorm_html(raw, times_cfg)
        cal = build_progstorm_calendar(events)
        vevents = list(cal.walk("VEVENT"))
        if vevents:
          print("Found Progstorm events")

  except Exception as e:
    print(f"⚠️ Error fetching/parsing {parser_name} ({label}): {e}")

  return vevents


def main():
  feeds = load_feeds()
  all_events = []
  city_events = {}
  session = get_robust_session()

  print(f"Fetching {len(feeds)} feeds safely...")
  # max_workers=2 prevents hammering remote servers and getting blocked/rate-limited
  with ThreadPoolExecutor(max_workers=2) as executor:
    futures = {
        executor.submit(fetch_and_press_feed_wrapper, feed, session): feed
        for feed in feeds
    }
    # (Using a helper wrapper below for clean execution)
    for future in as_completed(futures):
      vevents = future.result()
      if vevents:
        all_events.extend(vevents)

  unique = {str(ev.get("UID")): ev for ev in all_events}

  for ev in unique.values():
    city = extract_city_from_event(ev)
    if city is not None:
      city_events.setdefault(city, []).append(ev)

  for city, events in city_events.items():
    cal = Calendar()
    for ev in events:
      cal.add_component(ev)

    filename = f"calendars/{city.lower()}.ics"
    with open(filename, "wb") as f:
      f.write(cal.to_ical())

    print(f"{city}.ics file created with {len(events)} events.")


def fetch_and_press_feed_wrapper(feed, session):
  return fetch_and_parse_feed(feed, session)


if __name__ == "__main__":
  main()
