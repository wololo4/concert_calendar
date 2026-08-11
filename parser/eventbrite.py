import json
import re
from icalendar import Calendar
from utils.ics import ICSEventBuilder
from datetime import datetime, timedelta
from bs4 import BeautifulSoup
from playwright.sync_api import sync_playwright
from playwright_stealth import Stealth
import yaml
import time

def load_eventbrite_config():
    print("DEBUG1: Loading Eventbrite config...")
    with open("concerts.yaml", "r", encoding="utf-8") as f:
        data = yaml.safe_load(f)
    for src in data.get("sources", []):
        if src.get("parser") == "eventbrite":
            print("DEBUG2: Eventbrite config found:", src)
            return src
    print("DEBUG3: No eventbrite config found")
    return {}

def build_search_url(url, city, artist):
    artist_slug = artist.lower().replace(" ", "-")
    final_url = f"{url}/d/canada--{city}/{artist_slug}/"
    print(f"DEBUG4: Build URL for {artist}: {final_url}")
    return final_url

def extract_events_from_json(html):
    print("DEBUG5: Extracting events from JSON blob...")
    print("DEBUG6: HTML length:", len(html))

    # Extract window.__SERVER_DATA__ JSON
    match = re.search(r"window.__SERVER_DATA__\s*=\s*(\{.*?\});", html, re.DOTALL)
    if not match:
        print("DEBUG7: No SERVER_DATA JSON found")
        return []

    json_blob = match.group(1)
    data = json.loads(json_blob)

    # Navigate to events list
    try:
        events = data["search_data"]["events"]["results"]
    except Exception as e:
        print("DEBUG8: JSON structure error:", e)
        return []

    bands = []
    print("DEBUG9: Found", len(events), "events in JSON")

    for ev in events:
        title = ev.get("name", "")
        print("DEBUG10: Raw event title:", title)

        for part in title.split(","):
            name = part.strip()
            print("DEBUG11: Parsed band:", name)
            if name:
                bands.append(name)

    print("DEBUG12: Total bands extracted:", bands)
    return bands

def parse_eventbrite():
    config = load_eventbrite_config()
    if not config:
        print("⚠️ No eventbrite block in concerts.yaml")
        return Calendar()

    base_url = config.get("url")
    city = config.get("city")

    print("DEBUG11: Base URL:", base_url)
    print("DEBUG12: City:", city)

    # Load artists from YAML
    with open("concerts.yaml", "r", encoding="utf-8") as f:
        data = yaml.safe_load(f)
    artists = data.get("artists", [])
    print("DEBUG13: Artists to scrape:", artists)

    cal = Calendar()

    print("DEBUG14: Launching Playwright browser")
    with Stealth().use_sync(sync_playwright()) as p:
        browser = p.chromium.launch(
            headless=False,
            args=[
                "--disable-blink-features=AutomationControlled",
                "--disable-web-security",
                "--disable-features=IsolateOrigins,site-per-process",
                "--disable-dev-shm-usage",
            ]
        )

        context = browser.new_context(
            user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/123.0.0.0 Safari/537.36",
            locale="en-US",
            viewport={"width": 1280, "height": 800},
            timezone_id="America/New_York",
            java_script_enabled=True,
            permissions=["geolocation"],
        )

        page = context.new_page()

        for artist in artists:
            print("\n==============================")
            print(f"DEBUG15: SCRAPING ARTIST: {artist}")
            print("==============================")

            url = build_search_url(base_url, city, artist)
            print("DEBUG: Navigating to:", url)

            start_time = time.time()

            try:
                page.goto(url, timeout=60000)
                page.wait_for_timeout(1500)

                html = page.content()
                print("DEBUG20: HTML fetched")

                # Extract events from JSON instead of DOM
                bands = extract_events_from_json(html)

                if not bands:
                    print(f"⚠️ No bands found for {artist}")
                    continue

                print("DEBUG21: Creating ICS events…")

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

                print(f"DEBUG22: Finished artist {artist} in {time.time() - start_time:.2f}s")

            except Exception as e:
                print(f"⚠️ Eventbrite failed for {artist}: {e}")
                continue

        print("DEBUG23: Closing browser…")
        browser.close()

    print("DEBUG24: Finished Eventbrite scraping")
    return cal
