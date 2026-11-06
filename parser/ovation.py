from bs4 import BeautifulSoup
from datetime import date, datetime, timedelta
from icalendar import Calendar
from urllib.parse import urljoin
from utils.ics import ICSEventBuilder
import re
import unicodedata
from zoneinfo import ZoneInfo

LOCAL_TZ = ZoneInfo("America/Toronto")
UTC_TZ = ZoneInfo("UTC")
BASE = "https://m.ovation.ca"

MONTHS = ["jan", "feb", "mar", "apr", "may", "jun",
          "jul", "aug", "sep", "oct", "nov", "dec"]
WEEKDAYS = ["mon", "tue", "wed", "thu", "fri", "sat", "sun"]

# "Thu, Jan 28, 8:00 p.m."  or  "Tue, Oct 26, 27, 8:00 p.m."
DATE_RE = re.compile(
    r"^([A-Za-z]{3})\.?,\s+([A-Za-z]{3,9})\.?\s+([\d,\s]+?),\s+"
    r"(\d{1,2}):(\d{2})\s*([ap])\.?\s*m\.?",
    re.I,
)

# first match wins, checked against the card's venue text
VENUES = {
    "salle odyssée": "Salle Odyssée, 855 boul. de la Gappe, Gatineau",
    "scène png": "Scène PNG, École polyvalente Nicolas-Gatineau, Gatineau",
    "art-image": "Centre d'exposition Art-image, Gatineau",
}


def _norm(text):
  s = unicodedata.normalize("NFKD", str(text).lower())
  return "".join(c for c in s if not unicodedata.combining(c))


def _clean(text):
  return re.sub(r"\s+", " ", text).strip()


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
  names = sorted({_norm(a) for a in artists if len(a) > 3}, key=len, reverse=True)
  pattern = (
      re.compile(r"\b(?:" + "|".join(re.escape(a) for a in names) + r")\b")
      if names
      else None
  )

  shows = soup.select("div.show[data-event-id]")
  if not shows:
    print("⚠️ Ovation: no event cards found (layout change or blocked page)")
    return []

  events, n_dates = [], 0
  for show in shows:
    event_id = show["data-event-id"]

    title_el = show.select_one(".title")
    date_el = show.select_one(".long-date")
    if not title_el or not date_el:
      continue

    title = _clean(title_el.get_text(" ", strip=True))
    date_text = _clean(date_el.get_text(" ", strip=True))
    m = DATE_RE.match(date_text)
    if m:
      n_dates += 1

    if not pattern or not pattern.search(_norm(title)):
      continue

    # from here on the show is one of your artists, so report any drop
    if not m:
      print(f"⚠️ Ovation: skipped '{title}' (unreadable date '{date_text}')")
      continue

    wd_s, mon_s, days_s, hh, mm, ap = m.groups()
    try:
      month = MONTHS.index(mon_s[:3].lower()) + 1
    except ValueError:
      print(f"⚠️ Ovation: skipped '{title}' (unknown month '{mon_s}')")
      continue
    weekday = WEEKDAYS.index(wd_s[:3].lower()) if wd_s[:3].lower() in WEEKDAYS else None
    days = [int(d) for d in re.findall(r"\d+", days_s)]
    year = _infer_year(weekday, month, days[0])
    if not year:
      print(f"⚠️ Ovation: skipped '{title}' (no matching year for '{date_text}')")
      continue
    hour = int(hh) % 12 + (12 if ap.lower() == "p" else 0)

    info_el = show.select_one(".info-show")
    info_text = _norm(_clean(info_el.get_text(" ", strip=True))) if info_el else ""
    venue = next((v for k, v in VENUES.items() if _norm(k) in info_text), None)
    if venue is None:
      print(
          f"⚠️ Ovation: unknown venue for '{title}' "
          f"(card text: '{info_text}'). Add it to VENUES."
      )
      venue = "Gatineau"

    link = show.find("a", href=re.compile(r"/Event/Tickets/")) or show.find(
        "a", href=re.compile(r"/Event/\?eventId=")
    )
    url = urljoin(BASE, link["href"]) if link else BASE

    for day in days:
      events.append({
          "title": title,
          "start": datetime(year, month, day, hour, int(mm)),
          "url": url,
          "venue": venue,
          "uid": f"ovation{event_id}{year}{month:02d}{day:02d}",
      })

  if n_dates == 0:
    print(
        f"⚠️ Ovation: {len(shows)} cards but no readable dates "
        "(date format changed?)"
    )
  return events


def build_event_ovation(events):
  cal = Calendar()
  for ev in events:
    utc_dt = ev["start"].replace(tzinfo=LOCAL_TZ).astimezone(UTC_TZ)
    title_uni = (
        ev["title"].split("@")[0].replace("\\", "").replace(" +", ",").strip()
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
