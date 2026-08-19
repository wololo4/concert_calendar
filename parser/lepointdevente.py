import re
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

def parse_lpdv_html(html, artists):
    soup = BeautifulSoup(html, "html.parser")
    events = []

    h1_tags = soup.find_all("h1")
    venue_name = h1_tags[1].get_text(strip=True) if len(h1_tags) > 1 else "Unknown Venue"
    addr_block = soup.find("div", class_="profile-header-address")
    venue_address = addr_block.find("div").get_text(strip=True) if addr_block else ""
    artists_lower = [a.lower() for a in artists]
    
    for article in soup.select("article.feature-canvas"):
        link = article.find("a", class_="feature-link")
        if not link:
            continue

        event_url = "https://lepointdevente.com" + link["href"]
        title = article.find("h3", class_="feature-title").get_text(strip=True)
        date_str = article.find("div", class_="feature-date").get_text(strip=True)

        title_clean = title.lower().strip()
        if not any(a in title_clean for a in artists_lower if len(a) > 3):
            continue

        events.append({
            "title": title,
            "date_str": date_str,
            "url": event_url,
            "venue": f"{venue_name}, {venue_address}"
        })

    return events

def build_event_lpdv(events):
    cal = Calendar()
    for ev in events:
        local_dt = parse_date_any(ev["date_str"]).replace(tzinfo=MONTREAL_TZ)
        utc_dt = local_dt.astimezone(UTC_TZ)
        utc_end = utc_dt + timedelta(hours=3)
        title = ev['title'].split('@')[0].split('-')[0]
        title_uni = title.replace('\\', '').replace(' +', ',')
        url_id = ev['url'].split('/')[-1]

        description = f"Tickets: {ev['url']}\nArtists: {title_uni}"

        vevent = (
            ICSEventBuilder()
            .uid(f"lpdv{url_id}")
            .start(utc_dt)
            .end(utc_end)
            .summary(f"🎵 | {title_uni}")
            .location(ev["venue"])
            .description(description)
            .build()
        )

        cal.add_component(vevent)

    return cal