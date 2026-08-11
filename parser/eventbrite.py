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

def scrape_artist(page, url, artist):
    try:
        page.goto(url, timeout=60000)
        page.wait_for_selector("h3.event-card__clamp-line--two", timeout=8000)
        html = page.content()
        return extract_events(html)
    except Exception as e:
        print(f"⚠️ Eventbrite failed for {artist}: {e}")
        return []

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

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        num_workers = min(8, len(artists))
        context = [browser.new_context() for _ in range(num_workers)]
        pages = [ctx.new_page() for ctx in context]

        for page in pages:
            page.route("**/*", lambda route: (
                route.abort()
                if route.request.resource_type in ["image", "media", "font", "stylesheet"]
                else route.continue_()
            ))

        def worker(args):
            page, artist = args
            url = build_search_url(url, city, artist)
            bands = scrape_artist(page, url, artist)
            return artist, bands

        with ThreadPoolExecutor(max_workers=num_workers) as executor:
            results = executor.map(worker, zip(pages, artists)

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

        browser.close

    return cal
