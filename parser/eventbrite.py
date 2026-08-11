from icalendar import Calendar
from utils.ics import ICSEventBuilder
from datetime import datetime, timedelta
from bs4 import BeautifulSoup
from utils.fetch import fetch_html
from playwright.sync_api import sync_playwright
import yaml

def load_eventbrite_config():
    with open("concerts.yaml", "r", encoding="utf-8") as f:
        data = yaml.safe_load(f)
    for src in data.get("sources", []):
        if src.get("parser") == "eventbrite":
            return src
    return {}

def build_search_url(url, city, artist):
    artist_slug = artist.lower().replace(" ", "-")
    return f"{url}/d/canada--{city}/{artist_slug}/"

def extract_events(soup):
    bands = []
    for h3 in soup.select("h3.event-card__clamp-line--two"):
        text = h3.get_text(strip=True)
        if text:
            for part in text.split(","):
                name = part.strip()
                if name:
                    bands.append(name)

    return bands

def fetch_eventbrite_html(url):
    with sync_playwirght() as p:
        browser = p.chromium.launch(headless=True)
        page = browser.new_page()
        page.goto(url, timeout=60000)
        page.wait_for_timeout(3000)
        html = page.content()
        browser.close()
        return html

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
        html = fetch_eventbrite_html(url)

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
