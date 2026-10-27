
from datetime import datetime, timedelta
from icalendar import Calendar
from utils.ics import ICSEventBuilder


def parse_ticketmaster_json(raw_json, artists):
    cal = Calendar()
    artists_lower = {a.lower().strip() for a in artists}
    seen_events = set()

    for ev in raw_json.get("_embedded", {}).get("events", []):
        name = ev.get("name", "").strip()
        name_lower = name.casefold()

        # Ignore Ticketmaster official platinum ticket listings.
        if "sièges platine officiels" in name_lower or "official platinum" in name_lower:
            continue

        ticket_lines = ev.get("ticketTextLines", {}).get("en-us", {})
        ticket_text = " ".join(ticket_lines.values()).casefold()

        # Identify Ticketmaster redirect listings.
        is_redirect = (
            "redirect listing" in ticket_text
            or "tm1 created" in ticket_text
        )

        attractions = ev.get("_embedded", {}).get("attractions", [])
        names = [
            a.get("name", "").strip()
            for a in attractions
            if a.get("name")
        ]

        matched = (
            any(a.casefold() in artists_lower for a in names)
            or name_lower in artists_lower
        )
        if not matched:
            continue

        start_raw = ev.get("dates", {}).get("start", {}).get("dateTime")
        if not start_raw:
            continue

        start_dt = datetime.fromisoformat(
            start_raw.replace("Z", "+00:00")
        )

        venue = ev.get("_embedded", {}).get("venues", [{}])[0]
        venue_name = venue.get("name", "").strip()
        venue_address = venue.get("address", {}).get("line1", "").strip()
        loc = f"{venue_name}, {venue_address}".strip(", ")

        # Prevent multiple listings for the same performance.
        attraction_key = tuple(sorted(a.casefold() for a in names))
        event_key = (
            attraction_key,
            start_dt.date(),
            venue.get("id", venue_name.casefold()),
        )
        if event_key in seen_events:
            continue
        seen_events.add(event_key)

        desc = f"Tickets: {ev.get('url', '')}"
        if names:
            desc += "\nArtists: " + ", ".join(names)

        # Prefer the redirect entry's UID, which represents the performance.
        vevent = (
            ICSEventBuilder()
            .uid(f"tm-{ev.get('id', '')}")
            .start(start_dt)
            .end(start_dt + timedelta(hours=3))
            .summary(f"🎵 | {name}")
            .location(loc)
            .description(desc)
            .build()
        )
        cal.add_component(vevent)

    return cal
