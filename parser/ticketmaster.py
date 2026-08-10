from icalendar import Calendar
from utils.ics import ICSEventBuilder
from datetime import datetime, timedelta

def add_duration(dt, hours=3):
    return dt +timedelta(hours=hours)

def event_has_artist(event, artists):
    attractions = event.get("_embedded", {}).get("attractions", [])
    for a in attractions:
        name = p.get("name", "").lower()
        for artist in artists:
            if artist.lower() in name:
                return True
    return False

def extract_artists(ev):
    attractions = ev.get("_embedded", {}).get("attractions", [])
    names = []
    for a in attractions:
        name = a.get("name", "").strip()
        if name and name not in names:
            names.append(name)
    return names

def parse_ticketmaster_json(raw_json, artists):
    cal = Calendar()

    events = raw_json.get("_embedded", {}).get("events", [])

    for ev in events:
        title = ev.get("name", "")
        if not event_has_artist(ev, artists):
            continue

        start_raw = ev.get("dates", {}).get("start", {}).get("dateTime")
        if not start_raw:
            continue

        start_dt = datetime.fromisoformat(start_raw.replace("Z", "+00:00"))
        end_dt = add_duration(start_dt, hours=3)

        venue_data = ev.get("_embedded", {}).get("venues", [{}])[0]
        venue = venue_data.get("name", "")
        address = venue_data.get("address", {}).get("line1", "")

        url = ev.get("url", "")
        event_id = ev.get("id", "")

        artist_names = extract_artists(ev)
        description_text = f"Tickets: {url}"
        if artist_names:
            description_text += "\nArtists: " + ", ".join(artist_names)

        event = (
            ICSEventBuilder()
            .uid(f"tm-{event_id}")
            .start(start_dt)
            .end(end_dt)
            .summary(f"🎵 | {title}")
            .location(f"{venue}, {address}")
            .description(description_text)
            .build()
        )

        cal.add_component(event)

    return cal
