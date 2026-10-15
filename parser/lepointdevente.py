from bs4 import BeautifulSoup
from datetime import datetime, timedelta
from icalendar import Calendar
from utils.ics import ICSEventBuilder
from urllib.parse import urljoin
import re
from zoneinfo import ZoneInfo

MONTREAL_TZ = ZoneInfo("America/Toronto")
UTC_TZ = ZoneInfo("UTC")

MONTHS = {
    **{
        m: i
        for i, m in enumerate(
            [
                "janvier",
                "février",
                "mars",
                "avril",
                "mai",
                "juin",
                "juillet",
                "août",
                "septembre",
                "octobre",
                "novembre",
                "décembre",
            ],
            1,
        )
    },
    **{
        m: i
        for i, m in enumerate(
            [
                "january",
                "february",
                "march",
                "april",
                "may",
                "june",
                "july",
                "august",
                "september",
                "october",
                "november",
                "december",
            ],
            1,
        )
    },
}


def parse_date_any(date_str):
  date_str = re.sub(r"(\d+)(st|nd|rd|th)", r"\1", date_str.strip())
  date_part, time_part = map(str.strip, date_str.split(","))
  tokens = date_part.lower().split()

  if tokens[1] in MONTHS:
    day, month, year = int(tokens[0]), MONTHS[tokens[1]], int(tokens[2])
  elif tokens[0] in MONTHS:
    month, day, year = MONTHS[tokens[0]], int(tokens[1]), int(tokens[2])
  else:
    raise ValueError(f"Unknown date: {date_str}")

  if "h" in time_part:
    hour, minute = map(int, time_part.replace("h", ":").split(":"))
  else:
    dt = datetime.strptime(time_part, "%I:%M %p")
    hour, minute = dt.hour, dt.minute

  return datetime(year, month, day, hour, minute)


def parse_lpdv_html(html, artists):
  soup = BeautifulSoup(html, "html.parser")
  h1s = soup.find_all("h1")
  venue_name = h1s[1].get_text(strip=True) if len(h1s) > 1 else ""
  addr_block = soup.find("div", class_="profile-header-address")
  venue_address = addr_block.find("div").get_text(strip=True) if addr_block else ""
  page_venue = ", ".join(p for p in (venue_name, venue_address) if p)
  artists_lower = [a.lower() for a in artists if len(a) > 3]

  events = []
  for article in soup.select("article.feature-canvas"):
    if not (link := article.find("a", class_="feature-link")):
      continue
    title = article.find("h3", class_="feature-title").get_text(strip=True)
    if not any(
        re.search(rf"\b{re.escape(a)}\b", title.lower()) for a in artists_lower
    ):
      continue

    date_el = article.find("div", class_="feature-date")
    if not date_el:
      continue

    card_venue = next(
       (s for s in article.stripped_strings if ", QC" in s), None
    )

    events.append({
        "title": title,
        "date_str": date_el.get_text(strip=True),
        "url": urljoin("https://lepointdevente.com", link["href"]),
        "venue": card_venue or page_venue or "Unknown Venue",
    })
  return events


def build_event_lpdv(events):
  cal = Calendar()
  for ev in events:
    local_dt = parse_date_any(ev["date_str"]).replace(tzinfo=MONTREAL_TZ)
    utc_dt = local_dt.astimezone(UTC_TZ)
    title_uni = (
        ev["title"].split("@")[0].split("-")[0].replace("\\", "").replace(" +", ",")
    )

    vevent = (
        ICSEventBuilder()
        .uid(f"lpdv{ev['url'].split('/')[-1]}")
        .start(utc_dt)
        .end(utc_dt + timedelta(hours=3))
        .summary(f"🎵 | {title_uni}")
        .location(ev["venue"])
        .description(f"Tickets: {ev['url']}\nArtists: {title_uni}")
        .build()
    )
    cal.add_component(vevent)
  return cal
