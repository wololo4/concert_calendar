from icalendar import Calendar
from utils.ics import ICSEventBuilder
from datetime import datetime, timedelta

def add_duration(dt, hours=3):
    return dt +timedelta(hours=hours)

def event_has_artist(event, artists):
    attractions = event.get("_embedded", {}).get("attractions", [])
    print("DEBUG1 attractions in event_has_artist:", attractions)
    for a in attractions:
        name = a.get("name", "").lower()
        print("DEBUG2 attraction name:", name)
        for artist in artists:
            if artist.lower() in name:
                print("DEBUG3 MATCH:", artist, "<->", name
                return True
    print("DEBUG4 NO MATCH for event")
    return False

def extract_artists(ev):
    attractions = ev.get("_embedded", {}).get("attractions", [])
    print("DEBUG5 extracted name:", name)
    names = []
    for a in attractions:
        name = a.get("name", "").strip()
        print("DEBUG6 extract artists attractions:", attractions)
        if name and name not in names:
            names.append(name)
    print("DEBUG7 final artist list:", names)
    return names

def parse_ticketmaster_json(raw_json, artists):
    cal = Calendar()
    print("DEBUG8 raw_json keys:", raw_json.keys())
    events = raw_json.get("_embedded", {}).get("events", [])
    print("DEBUG9 event count:", len(events))
    for ev in events:
        print("\n=== DEBUG10 NEW EVENT ===")
        print("DEBUG11 event name:", ev.get("name"))
        title = ev.get("name", "")
        if not event_has_artist(ev, artists):
            print("DEBUG12 event skipped (no artist match)")
            continue

        start_raw = ev.get("dates", {}).get("start", {}).get("dateTime")
        print("DEBUG13 start_raw:", start_raw)
        if not start_raw:
              print("DEBUG14 skipped(no started_raw)")
            continue

        start_dt = datetime.fromisoformat(start_raw.replace("Z", "+00:00"))
        end_dt = add_duration(start_dt, hours=3)

        venue_data = ev.get("_embedded", {}).get("venues", [{}])[0]
        print("DEBUG15 venue_data:", venue_data)
        venue = venue_data.get("name", "")
        address = venue_data.get("address", {}).get("line1", "")

        url = ev.get("url", "")
        event_id = ev.get("id", "")

        artist_names = extract_artists(ev)
        description_text = f"Tickets: {url}"
        if artist_names:
            description_text += "\nArtists: " + ", ".join(artist_names)

        print("DEBUG16 description_text:", description_text)
        
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
        print("DEBUG18 event added to calendar")
        cal.add_component(event)
    print("DEBUG19 returning calendar")
    return cal
