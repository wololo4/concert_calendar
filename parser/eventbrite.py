import json
import re
import yaml
import cloudscraper
from datetime import datetime, timedelta
from icalendar import Calendar
from utils.ics import ICSEventBuilder


def load_eventbrite_config():
    with open("concerts.yaml", "r", encoding="utf-8") as f:
        data = yaml.safe_load(f)

    for src in data.get("sources", []):
        if src.get("parser") == "eventbrite":
            return src

    return {}


def scrape_organizer_page(url):
    scraper = cloudscraper.create_scraper()
    html = scraper.get(url).text

    # NEW: Next.js JSON
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


def extract_artists_from_name(name):
    parts = [p.strip() for p in name.split(",")]
    return parts


def build_event(ev):
    artists = extract_artists_from_name(ev["name"])
    description = f"Tickets: {ev['url']}\Artists: " + ", ".join(artists)
    start_dt = datetime.fromisoformat(f"{ev["start_date"]}T{ev['start_time']}")
    end_dt = start_dt + timedelta(hours=3)
    location = ev["primary_venue"]

    return (
        ICSEventBuilder()
        .uid(f"eventbrite{ev['id']}")
        .start(start_dt)
        .end(end_dt)
        .summary(f"🎵 | {ev['name']}")
        .location(f"{location['name']}, {location['address']['address_1']}")
        .description(description)
        .build()
    )


def parse_eventbrite():
    config = load_eventbrite_config()
    if not config:
        return Calendar()

    organizer_url = config.get("organizer_url")
    if not organizer_url:
        print("⚠️ No organizer_url in YAML")
        return Calendar()

    with open("concerts.yaml", "r", encoding="utf-8") as f:
        data = yaml.safe_load(f)
    artists = data["artists"]

    print(f"Scraping Eventbrite organizer: {organizer_url}")

    events = scrape_organizer_page(organizer_url)
    cal = Calendar()

    for artist in artists:
        artist_lower = artist.lower()

        for ev in events:
            title = ev.get("name", "").lower()

            if artist_lower in title:
                print(f"Found Eventbrite event for {artist}: {ev['url']}")
                cal.add_component(build_event(ev))

    return cal
