import json
import re
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo
from icalendar import Calendar
from utils.ics import ICSEventBuilder

MONTREAL_TZ = ZoneInfo("America/Toronto")
UTC_TZ = ZoneInfo("UTC")

def extract_nextjs_events(html):
    match = re.search(
        r'<script[^>]*id="__NEXT_DATA__"[^>]*>(.*?)</script>',
        html,
        re.DOTALL
    )

    if not match:
        print("⚠️ Could not find __NEXT_DATA__ JSON")
        return []

    data = json.loads(match.group(1))

    try:
        return data["props"]["pageProps"]["upcomingEvents"]
    except Exception as e:
        print("⚠️ organizer.events missing:", e)
        return []

def extract_artists(name):
    if not name:
        return []
    return [p.strip() for p in name.split(",") if p.strip()]

def build_event(ev):
    artists = extract_artists(ev["name"])
    description = (
        f"Tickets: {ev['url']}\n"
        f"Artists: {', '.join(artists)}"
    )
    start_dt = datetime.fromisoformat(
        f"{ev['start_date']}T{ev['start_time']}"
    ).replace(tzinfo=MONTREAL_TZ)
    utc_start = start_dt.astimezone(UTC_TZ)
    utc_end = utc_start + timedelta(hours=3)

    location = ev["primary_venue"]

    return (
        ICSEventBuilder()
        .uid(f"eventbrite{ev['id']}")
        .start(utc_start)
        .end(utc_end)
        .summary(f"🎵 | {ev['name']}")
        .location(f"{location['name']}, {location['address']['address_1']}")
        .description(description)
        .build()
    )

def parse_eventbrite_html(html, artists):
    events = extract_nextjs_events(html)
    filtered = []
    artists_lower = [a.lower() for a in artists]

    for ev in events:
        title = ev.get("name", "").lower()
        parts = [p.strip() for p in re.split(f"[,+]", title) if p.strip()]
        if any(part in artists_lower for part in parts):
            filtered.append(ev)
    return filtered

def build_eventbrite_calendar(events):
    cal = Calendar()
    for ev in events:
        cal.add_component(build_event(ev))
    return cal