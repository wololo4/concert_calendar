import re
from datetime import datetime, timedelta
from icalendar import Calendar
from utils.ics import ICSEventBuilder
from bs4 import BeautifulSoup
from zoneinfo import ZoneInfo

QUEBEC_TZ = ZoneInfo("America/Toronto")
UTC_TZ = ZoneInfo("UTC")

# Reuse your existing date parser
def parse_date_any(date_str):
    date_str = date_str.strip()
    date_str = re.sub(r'(\d+)(st|nd|rd|th)', r'\1', date_str)

    fr_months = {
        "janvier": 1, "février": 2, "mars": 3, "avril": 4,
        "mai": 5, "juin": 6, "juillet": 7, "août": 8,
        "septembre": 9, "octobre": 10, "novembre": 11, "décembre": 12
    }

    parts = date_str.split(",")
    if len(parts) != 2:
        raise ValueError(f"Invalid date format: {date_str}")

    date_part = parts[0].strip()
    time_part = parts[1].strip()

    tokens = [t for t in date_part.lower().split(" ") if t.strip()]
    if len(tokens) < 3:
        raise ValueError(f"Invalid date tokens: {tokens}")
    day = int(tokens[0])
    month = fr_months[tokens[1]]
    year = int(tokens[2])

    hour, minute = map(int, time_part.replace("h", ":").split(":"))

    return datetime(year, month, day, hour, minute)

def parse_imperialbell_html(html, artists):
    soup = BeautifulSoup(html, "html.parser")
    events = []

    venue_name = "L'Impérial"
    venue_address = "Quebec"
    artists_lower = [a.lower() for a in artists]

    for item in soup.select("div#divShow"):
        article = item.find("article", class_="article-card")
        if not article:
            continue

        title_tag = article.find("strong", class_="article-card__title")
        if not title_tag:
            continue

        title = title_tag.get_text(strip=True)
        title_clean = title.lower()
        if not any(a in title_clean for a in artists_lower if len(a) > 3):
            continue

        date_tag = article.find("p", class_="article-card__date")
        time_tag = article.find("p", class_="article-card__time")
        if not date_tag or not time_tag:
            continue
        date_str = date_tag.get_text(strip=True)
        spans = time_tag.find_all("span")
        hour_str = spans[1].get_text(strip=True) if len(spans) > 1 else "20h00"
        date_full = f"{date_str}, {hour_str}"

        link = article.find("a", id="lnkTitle")
        if not link:
            continue

        event_url = "https://www.imperialbell.com" + link["href"]

        events.append({
            "title": title,
            "date_str": date_full,
            "url": event_url,
            "venue": f"{venue_name}, {venue_address}"
        })

    return events

def build_event_imperialbell(events):
    cal = Calendar()

    for ev in events:
        local_dt = parse_date_any(ev["date_str"]).replace(tzinfo=QUEBEC_TZ)
        utc_dt = local_dt.astimezone(UTC_TZ)
        utc_end = utc_dt + timedelta(hours=3)

        title = ev['title'].split('@')[0].split('-')[0]
        title_uni = title.replace('\\', '').replace(' +', ',')
        url_id = ev['url'].split('/')[-1]

        description = f"Tickets: {ev['url']}\nArtists: {title_uni}"

        vevent = (
            ICSEventBuilder()
            .uid(f"imperialbell{url_id}")
            .start(utc_dt)
            .end(utc_end)
            .summary(f"🎵 | {title_uni}")
            .location(ev["venue"])
            .description(description)
            .build()
        )

        cal.add_component(vevent)

    return cal
