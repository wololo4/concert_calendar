from datetime import datetime, timedelta
from icalendar import Calendar
import json
import re
from utils.ics import ICSEventBuilder
from zoneinfo import ZoneInfo

MONTREAL_TZ = ZoneInfo("America/Toronto")
UTC_TZ = ZoneInfo("UTC")


def parse_eventbrite_html(html, artists):
  match = re.search(
      r'<script[^>]*id="__NEXT_DATA__"[^>]*>(.*?)</script>', html, re.DOTALL
  )
  if not match:
    return []

  try:
    events = json.loads(match.group(1))["props"]["pageProps"]["upcomingEvents"]
  except Exception:
    return []

  artists_lower = {a.lower().strip() for a in artists}
  filtered = []

  for ev in events:
    title = ev.get("name", "").lower()
    parts = {p.strip() for p in re.split(r"[,+]", title) if p.strip()}
    if parts & artists_lower:
      filtered.append(ev)

  return filtered


def build_eventbrite_calendar(events):
  cal = Calendar()
  for ev in events:
    artists = [p.strip() for p in ev["name"].split(",") if p.strip()]
    start_dt = datetime.fromisoformat(
        f"{ev['start_date']}T{ev['start_time']}"
    ).replace(tzinfo=MONTREAL_TZ)
    utc_start = start_dt.astimezone(UTC_TZ)
    loc = ev["primary_venue"]

    vevent = (
        ICSEventBuilder()
        .uid(f"eventbrite{ev['id']}")
        .start(utc_start)
        .end(utc_start + timedelta(hours=3))
        .summary(f"🎵 | {ev['name']}")
        .location(f"{loc['name']}, {loc['address']['address_1']}")
        .description(f"Tickets: {ev['url']}\nArtists: {', '.join(artists)}")
        .build()
    )
    cal.add_component(vevent)
  return cal
