from icalendar import Calendar
from utils.ics import ICSEventBuilder
from utils.normalize import normalize_artist
from datetime import datetime, timedelta

def add_duration(dt, hours=3):
    return dt +timedelta(hours=hours)

def parse_ticketmaster_json(raw_json, artists):
    cal = Calendar()

    events = raw_json.get("_embedded", {}).get("events", [])

    for ev in events:
        title = ev.get("name", "")

        if not normalize_artist(title, artists):
            continue

        start_raw = ev.get("dates", {}).get("start", {}).get("dateTime")
        if not start_raw:
            continue

        start_dt = datetime.fromisoformat(start_raw.replace("Z", "+00:00"))
        end_dt = add_duration(start_dt, hours=3)

        venue_data = ev.get("_embedded", {}).get("venues", [{}])[0]
        venue = venue_data.get("name", "")
        address = venue_data.get("address", {}).get("line1": "")

        url = ev.get("url", "")
        event_id = ev.get("id", "")

        event = (
            ICSEventBuilder()
            .uid(f"tm-{event_id}")
            .start(start_dt)
            .end(end_dt)
            .summary(f"🎵 | {title}")
            .location(f"{venue}, {address}")
            .description(f"Tickets: {url}")
            .build()
        )

        cal.add_component(event)

    return cal
