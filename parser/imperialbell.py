from bs4 import BeautifulSoup
from datetime import datetime, timedelta
from icalendar import Calendar
from utils.ics import ICSEventBuilder
import re
from zoneinfo import ZoneInfo

QUEBEC_TZ = ZoneInfo("America/Toronto")
UTC_TZ = ZoneInfo("UTC")

FR_MONTHS = {
    "janvier": 1,
    "février": 2,
    "mars": 3,
    "avril": 4,
    "mai": 5,
    "juin": 6,
    "juillet": 7,
    "août": 8,
    "septembre": 9,
    "octobre": 10,
    "novembre": 11,
    "décembre": 12,
}


def parse_date_french(date_str):
  date_str = re.sub(r"(\d+)(st|nd|rd|th)", r"\1", date_str.strip())
  parts = date_str.split(",")
  tokens = parts[0].strip().lower().split()
  hour, minute = map(int, parts[1].strip().replace("h", ":").split(":"))
  return datetime(
      int(tokens[2]), FR_MONTHS[tokens[1]], int(tokens[0]), hour, minute
  )


def parse_imperialbell_html(html, artists):
  soup = BeautifulSoup(html, "html.parser")
  artists_lower = [a.lower() for a in artists if len(a) > 3]
  events = []

  for item in soup.select("div#divShow"):
    if not (article := item.find("article", class_="article-card")):
      continue
    if not (title_tag := article.find("strong", class_="article-card__title")):
      continue

    title = title_tag.get_text(strip=True)
    if not any(a in title.lower() for a in artists_lower):
      continue

    date_tag = article.find("p", class_="article-card__date")
    time_tag = article.find("p", class_="article-card__time")
    link = article.find("a", id="lnkTitle")
    if not date_tag or not time_tag or not link:
      continue

    spans = time_tag.find_all("span")
    hour_str = spans[1].get_text(strip=True) if len(spans) > 1 else "20h00"

    events.append({
        "title": title,
        "date_str": f"{date_tag.get_text(strip=True)}, {hour_str}",
        "url": "https://www.imperialbell.com" + link["href"],
        "venue": "L'Impérial, Quebec",
    })
  return events


def build_event_imperialbell(events):
  cal = Calendar()
  for ev in events:
    local_dt = parse_date_french(ev["date_str"]).replace(tzinfo=QUEBEC_TZ)
    utc_dt = local_dt.astimezone(UTC_TZ)
    title_uni = (
        ev["title"].split("@")[0].split("-")[0].replace("\\", "").replace(" +", ",")
    )

    vevent = (
        ICSEventBuilder()
        .uid(f"imperialbell{ev['url'].split('/')[-1]}")
        .start(utc_dt)
        .end(utc_dt + timedelta(hours=3))
        .summary(f"🎵 | {title_uni}")
        .location(ev["venue"])
        .description(f"Tickets: {ev['url']}\nArtists: {title_uni}")
        .build()
    )
    cal.add_component(vevent)
  return cal
