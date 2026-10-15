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

# addresses for venues that only appear as card text (cafecampusshows page)
KNOWN_ADDRESSES = {
    "petit campus": "57-B Rue Prince-Arthur Est",
    "café campus": "57 Rue Prince-Arthur Est",
    "cafe campus": "57 Rue Prince-Arthur Est",
}


def venue_from_card(text):
  name = text.split(",")[0].strip()
  addr = KNOWN_ADDRESSES.get(name.lower())
  return f"{name}, {addr}" if addr else name


def slug_from_image(article):
  img = article.find("img")
  if not img or not img.get("src"):
    return None
  name = img["src"].split("/")[-1]
  return re.sub(r"-\d+x\d+-[a-z]{2}-[0-9a-f]+\.\w+$", "", name) or None


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
    title_el = article.find("h3", class_="feature-title")
    date_el = article.find("div", class_="feature-date")
    if not title_el or not date_el:
      continue

    title = title_el.get_text(strip=True)
    if not any(
        re.search(rf"\b{re.escape(a)}\b", title.lower()) for a in artists_lower
    ):
      continue

    if link := article.find("a", class_="feature-link"):
      # regular venue page
      url = urljoin("https://lepointdevente.com", link["href"])
      venue = page_venue or "Unknown Venue"
    else:
      # cafecampusshows page: no link, venue is on the card
      slug = slug_from_image(article)
      if not slug:
        parent = article.find_parent(attrs={"data-tpos-event": True})
        slug = parent["data-tpos-event"] if parent else None
      if not slug:
        continue
      url = f"https://lepointdevente.com/tickets/{slug}"
      city = article.find("div", class_="feature-city")
      venue = venue_from_card(city.get_text(strip=True)) if city else "Unknown Venue"

    events.append({
        "title": title,
        "date_str": date_el.get_text(strip=True),
        "url": url,
        "venue": venue,
    })
  return events


def build_event_lpdv(events):
  cal = Calendar()
  for ev in events:
    try:
      local_dt = parse_date_any(ev["date_str"]).replace(tzinfo=MONTREAL_TZ)
    except Exception:
      continue
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
