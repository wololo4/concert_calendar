from bs4 import BeautifulSoup
from datetime import date, datetime, timedelta
from icalendar import Calendar
from urllib.parse import urljoin
from utils.ics import ICSEventBuilder
import re
from zoneinfo import ZoneInfo

LOCAL_TZ = ZoneInfo("America/Toronto")
UTC_TZ = ZoneInfo("UTC")
BASE = "https://m.ovation.ca"

MONTHS = ["jan", "feb", "mar", "apr", "may", "jun",
          "jul", "aug", "sep", "oct", "nov", "dec"]
WEEKDAYS = ["mon", "tue", "wed", "thu", "fri", "sat", "sun"]

EVENT_ID_RE = re.compile(r"eventId=([A-Za-z0-9]+)")
# "Thu, Jan 28, 8:00 p.m."  or  "Tue, Oct 26, 27, 8:00 p.m."
DATE_RE = re.compile(
    r"^([A-Za-z]{3})\.?,\s+([A-Za-z]{3,9})\.?\s+([\d,\s]+?),\s+"
    r"(\d{1,2}):(\d{2})\s*([ap])\.?\s*m\.?",
    re.I,
)

# first match wins, checked against the card's lines
VENUES = {
    "salle odyssée": "Salle Odyssée, 855 boul. de la Gappe, Gatineau",
    "scène png": "Scène PNG, École polyvalente Nicolas-Gatineau, Gatineau",
    "art-image": "Centre d'exposition Art-image, Gatineau",
}


def _card_for(link):
  """Largest ancestor of this link that contains only one event id."""
  card = link
  while card.parent is not None and card.parent.name not in ("body", "html"):
    ids = {
        EVENT_ID_RE.search(a["href"]).group(1)
        for a in card.parent.find_all("a", href=EVENT_ID_RE)
    }
    if len(ids) > 1:
      break
    card = card.parent
  return card


def _infer_year(weekday, month, day):
  today = datetime.now(LOCAL_TZ).date()
  for year in range(today.year, today.year + 3):
    try:
      d = date(year, month, day)
    except ValueError:
      continue
    if d < today - timedelta(days=1):
      continue
    if weekday is None or d.weekday() == weekday:
      return year
  return None


def parse_ovation_html(html, artists):
  soup = BeautifulSoup(html, "html.parser")
  artists_lower = [a.lower() for a in artists if len(a) > 3]
  seen, events = set(), []

  for link in soup.find_all("a", href=EVENT_ID_RE):
    event_id = EVENT_ID_RE.search(link["href"]).group(1)
    if event_id in seen:
      continue
    seen.add(event_id)

    card = _card_for(link)
    lines = list(card.stripped_strings)
    date_idx = next((i for i, l in enumerate(lines) if DATE_RE.match(l)), None)
    if not date_idx:  # None, or 0 (no title before the date)
      continue

    title = lines[date_idx - 1]
    if not any(
        re.search(rf"\b{re.escape(a)}\b", title.lower()) for a in artists_lower
    ):
      continue

    wd_s, mon_s, days_s, hh, mm, ap = DATE_RE.match(lines[date_idx]).groups()
    try:
      month = MONTHS.index(mon_s[:3].lower()) + 1
    except ValueError:
      continue
    weekday = WEEKDAYS.index(wd_s[:3].lower()) if wd_s[:3].lower() in WEEKDAYS else None
    days = [int(d) for d in re.findall(r"\d+", days_s)]
    year = _infer_year(weekday, month, days[0])
    if not year:
      continue
    hour = int(hh) % 12 + (12 if ap.lower() == "p" else 0)

    venue = None
    for line in lines[date_idx + 1:]:
      if key := next((k for k in VENUES if k in line.lower()), None):
        venue = VENUES[key]
        break

    if venue is None:
      print(
          f"⚠️ Ovation: unknown venue for '{title}' "
          f"(card lines: {lines[date_idx + 1:]}). Add it to VENUES."
      )
      venue = "Gatineau"

    tickets = card.find("a", href=re.compile(r"/Event/Tickets/"))
    url = urljoin(BASE, (tickets or link)["href"])

    for day in days:
      events.append({
          "title": title,
          "start": datetime(year, month, day, hour, int(mm)),
          "url": url,
          "venue": venue,
          "uid": f"ovation{event_id}{year}{month:02d}{day:02d}",
      })
  return events


def build_event_ovation(events):
  cal = Calendar()
  for ev in events:
    utc_dt = ev["start"].replace(tzinfo=LOCAL_TZ).astimezone(UTC_TZ)
    title_uni = (
        ev["title"].split("@")[0].replace("\\", "").replace(" +", ",")
    )

    vevent = (
        ICSEventBuilder()
        .uid(ev["uid"])
        .start(utc_dt)
        .end(utc_dt + timedelta(hours=3))
        .summary(f"🎵 | {title_uni}")
        .location(ev["venue"])
        .description(f"Tickets: {ev['url']}\nArtists: {title_uni}")
        .build()
    )
    cal.add_component(vevent)
  return cal
