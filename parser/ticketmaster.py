from datetime import datetime, timedelta
from icalendar import Calendar
from utils.ics import ICSEventBuilder


def parse_ticketmaster_json(raw_json, artists):
  cal = Calendar()
  artists_lower = {a.lower().strip() for a in artists}

  for ev in raw_json.get("_embedded", {}).get("events", []):
    attractions = ev.get("_embedded", {}).get("attractions", [])
    names = [a.get("name", "").strip() for a in attractions if a.get("name")]

    matched = any(a.lower() in artists_lower for a in names) or ev.get(
        "name", ""
    ).lower() in artists_lower
    if not matched:
      continue

    start_raw = ev.get("dates", {}).get("start", {}).get("dateTime")
    if not start_raw:
      continue

    start_dt = datetime.fromisoformat(start_raw.replace("Z", "+00:00"))
    venue = ev.get("_embedded", {}).get("venues", [{}])[0]
    loc = f"{venue.get('name', '')}, {venue.get('address', {}).get('line1', '')}"

    desc = f"Tickets: {ev.get('url', '')}"
    if names:
      desc += "\nArtists: " + ", ".join(names)

    vevent = (
        ICSEventBuilder()
        .uid(f"tm-{ev.get('id', '')}")
        .start(start_dt)
        .end(start_dt + timedelta(hours=3))
        .summary(f"🎵 | {ev.get('name', '')}")
        .location(loc)
        .description(desc)
        .build()
    )
    cal.add_component(vevent)
  return cal
