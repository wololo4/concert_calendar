import re
import yaml
import cloudscraper
from datetime import datetime, timedelta
from icalendar import Calendar
from utils.ics import ICSEventBuilder
from bs4 import BeautifulSoup
from zoneinfo import ZoneInfo

MONTREAL_TZ = ZoneInfo("America/Toronto")
UTC_TZ = ZoneInfo("UTC")

def parse_date_any(date_str):
    date_str = date_str.strip()
    date_str = re.sub(r'(\d+)(st|nd|rd|th)', r'\1', date_str)

    fr_months = {
        "janvier": 1, "février": 2, "mars": 3, "avril": 4,
        "mai": 5, "juin": 6, "juillet": 7, "août": 8,
        "septembre": 9, "octobre": 10, "novembre": 11, "décembre": 12
    }
    en_months = {
        "january": 1, "february": 2, "march": 3, "april": 4,
        "may": 5, "june": 6, "july": 7, "august": 8,
        "september": 9, "october": 10, "november": 11, "december": 12
    }

    parts = date_str.split(",")
    if len(parts) != 2:
        raise ValueError(f"Invalid date format: {date_str}")

    date_part = parts[0].strip()
    time_part = parts[1].strip()
    tokens = date_part.lower().split(" ")

    if tokens[1] in fr_months:
        day = int(tokens[0])
        month = fr_months[tokens[1]]
        year = int(tokens[2])
    elif tokens[0] in en_months:
        month = en_months[tokens[0]]
        day = int(tokens[1])
        year = int(tokens[2])
    else:
        raise ValueError(f"Unknown month: {date_str}")

    if "h" in time_part:
        hour, minute = map(int, time_part.replace("h", ":").split(":"))
    else:
        dt = datetime.strptime(time_part, "%I:%M %p")
        hour = dt.hour
        minute = dt.minute

    return datetime(year, month, day, hour, minute)

def scrape_lpdv_html(url, venue_name):
    scraper = cloudscraper.create_scraper()
    html = scraper.get(url).text

    soup = BeautifulSoup(html, "html.parser")
    events = []

    for article in soup.select("article.feature-canvas"):
        link = article.find("a", class_="feature-link")
        if not link:
            continue

        event_url = "https://lepointdevente.com" + link["href"]
        title = article.find("h3", class_="feature-title").get_text(strip=True)
        date_str = article.find("div", class_="feature-date").get_text(strip=True)

        events.append({
            "title": title,
            "date_str": date_str,
            "url": event_url,
            "venue": venue_name
        })

    return events

def build_event_lpdv(ev):
    local_dt = parse_date_any(ev["date_str"])
    local_dt = local_dt.replace(tzinfo=MONTREAL_TZ)
    utc_dt = local_dt.astimezone(UTC_TZ)
    utc_end = utc_dt + timedelta(hours=3)

    description = f"Tickets: {ev['url']}\nArtists: {ev['title']}"

    return (
        ICSEventBuilder()
        .uid(f"lpdv-{ev['title']}-{ev['venue']}")
        .start(utc_dt)
        .end(utc_end)
        .summary(f"🎵 | {ev['title']}")
        .location(ev["venue"])
        .description(description)
        .build()
    )

def parse_lpdv(venues):
    if not venues:
        print("⚠️ No venues configured for LPDV")
        return Calendar()

    # Load artists
    with open("concerts.yaml", "r", encoding="utf-8") as f:
        data = yaml.safe_load(f)
    artists = [a.lower() for a in data["artists"]]

    all_events = []

    # Scrape each venue
    for v in venues:
        url = v["url"]
        name = v["name"]

        print(f"Scraping LPDV venue: {name} ({url})")
        all_events.extend(scrape_lpdv_html(url, name))

    # Build calendar
    cal = Calendar()

    for ev in all_events:
        title = ev["title"].lower()
        if any(a in title for a in artists):
            print(f"Found LPDV event: {ev['title']} @ {ev['venue']}")
            cal.add_component(build_event_lpdv(ev))

    return cal
    
