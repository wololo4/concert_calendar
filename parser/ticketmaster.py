from icalendar import Calendar
from utils.ics import ICSEventBuilder
from utils.normalize import normalize_artist
from datetime import datetime

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

        venue_data = ev.get("_embedded", {}).get("venues", [{}])[0]
        venue = venue_data.get("name", "")
        city = venue_data.get("city", {}).get("name", "")
        state = venue_data.get("state", {}).get("name", "")

        url = ev.get("url", "")
        event_id = ev.get("id", "")

        event = (
            ICSEventBuilder()
            .uid(f"tm-{event_id}")
            .start(start_dt)
            .end(start_dt)
            .summary(f"🎵 | {title}")
            .location(f"{venue}, {city}, {state}")
            .description(f"Tickets: {url}")
            .build()
        )

        cal.add_component(event)

    return cal
