from icalendar import Calendar
from utils.ics import ICSEventBuilder
from datetime import datetime, timedelta
from bs4 import BeautifulSoup
from utils.fetch import fetch_html
import yaml

def load_eventbrite_config():
    with open("concerts.yaml", "r", encoding="utf-8") as f:
        data = yaml.safe_load(f)
    for src in data.get("sources", []):
        if src.get("parser") == "eventbrite":
            return src
    return {}

def build_search_url(base_url, city, artist):
    artist_slug = artist.lower().replace(" ", "-")
    return f"{url}/d/canada--{city}/{artist_slug}/"

def extract_events(soup):
    bands = []

    for title in soup.select(".eds-event-card-content__title"):
        text = title.get_text(strip=True)
        if text:
            for part in text.split(","):
                name = part.strip()
                if name:
                    bands.append(name)

    return bands

def parse_eventbrite():
    config = load_eventbrite_config()
    if not config:
        print("⚠️ No eventbrite block in concerts.yaml")
        return Calendar()

    base_url = config.get("url")
    city = config.get("city")

    if not base_url or not city:
        print("⚠️ eventbrite.base_url or eventbrite.city missing")
        return Calendar()

    # Load artists from YAML
    with open("concerts.yaml", "r", encoding="utf-8") as f:
        data = yaml.safe_load(f)
    artists = data.get("artists", [])

    cal = Calendar()

    for artist in artists:
        url = build_search_url(base_url, city, artist)
        html = fetch_html(url)

        if not html:
            print(f"⚠️ Failed to load Eventbrite page for {artist}")
            continue

        soup = BeautifulSoup(html, "html.parser")
        bands = extract_events(soup)

        if not bands:
            continue

        # Create ICS events (no dates available → use placeholder)
        for i, band in enumerate(bands):
            # Placeholder date: today + i days
            start_dt = datetime.now() + timedelta(days=i)
            end_dt = start_dt + timedelta(hours=3)

            uid = f"eventbrite-{artist}-{i}"

            event = (
                ICSEventBuilder()
                .uid(uid)
                .start(start_dt)
                .end(end_dt)
                .summary(f"🎵 | {band}")
                .location("Eventbrite Event")
                .description(f"Eventbrite listing for: {band}")
                .build()
            )

            cal.add_component(event)

    return cal
