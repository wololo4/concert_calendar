from icalendar import Calendar
from utils.ics import ICSEventBuilder
from datetime import datetime, timedelta
from bs4 import BeautifulSoup
from utils.fetch import fetch_html
from playwright.sync_api import sync_playwright
from multiprocessing import Pool
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

def extract_events(html):
    soup = BeautifulSoup(html, "html.parser")
    bands = []
    for h3 in soup.select("h3.event-card__clamp-line--two"):
        text = h3.get_text(strip=True)
        if text:
            for part in text.split(","):
                name = part.strip()
                if name:
                    bands.append(name)

    return bands

def scrape_artist(args):
    base_url, city, artist = args
    url = build_search_url(base_url, city, artist)

    try:
        with sync_playwright() as p:
            browser = p.chromium.launch(headless=True)
            context = browser.new_context()
            page = context.new_page()

            # block heavy resources
            page.route("**/*", lambda route: (
                route.abort()
                if route.request.resource_type in ["image", "media", "font", "stylesheet"]
                else route.continue_()
            ))

            page.goto(url, timeout=60000)
            page.wait_for_selector("h3.event-card__clamp-line--two", timeout=8000)

            html = page.content()
            browser.close()

            bands = extract_events(html)
            return artist, bands

    except Exception as e:
        return artist, []

def parse_eventbrite():
    config = load_eventbrite_config()
    if not config:
        print("⚠️ No eventbrite block in concerts.yaml")
        return Calendar()

    base_url = config.get("url")
    city = config.get("city")

    # Load artists from YAML
    with open("concerts.yaml", "r", encoding="utf-8") as f:
        data = yaml.safe_load(f)
    artists = data.get("artists", [])

    cal = Calendar()

    worker_count = 2

    with Pool(worker_count) as pool:
        results = pool.map(scrape_artist, [(base_url, city, artist) for artist in artists])

    for artist, band in results:
        for i, band in enumerate(bands):
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
