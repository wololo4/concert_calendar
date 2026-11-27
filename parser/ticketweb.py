from bs4 import BeautifulSoup
from datetime import datetime, timedelta
from icalendar import Calendar
from utils.ics import ICSEventBuilder
import html as htmllib
import json
import re
import unicodedata
from zoneinfo import ZoneInfo

MONTREAL_TZ = ZoneInfo("America/Toronto")
UTC_TZ = ZoneInfo("UTC")

# startDate has no timezone: it is venue-local, and the venue only gives its province
REGION_TZ = {
    "BC": ZoneInfo("America/Vancouver"),
    "AB": ZoneInfo("America/Edmonton"),
    "SK": ZoneInfo("America/Regina"),
    "MB": ZoneInfo("America/Winnipeg"),
    "ON": ZoneInfo("America/Toronto"),
    "QC": ZoneInfo("America/Toronto"),
    "NB": ZoneInfo("America/Halifax"),
    "NS": ZoneInfo("America/Halifax"),
    "PE": ZoneInfo("America/Halifax"),
    "NL": ZoneInfo("America/St_Johns"),
}


def _strip_accents(s):
  s = unicodedata.normalize("NFKD", s)
  return "".join(c for c in s if not unicodedata.combining(c))


def _norm(s):
  return _strip_accents(str(s).lower())


def parse_date_any(date_str):
  # ISO, venue-local, no tz: "2026-12-01T19:30"
  return datetime.fromisoformat(date_str.strip())


def clean_title(title):
  # cut at "@" or at a spaced dash, keep hyphenated words like "Forty-Year"
  t = re.split(r"\s+[-–—]\s+", title.split("@")[0])[0]
  return t.replace("\\", "").replace(" +", ",").strip()


def parse_ticketweb_html(html, artists):
  soup = BeautifulSoup(html, "html.parser")

  # embedded JSON-LD: each script holds an object or a list of objects
  items = []
  for script in soup.find_all("script", type="application/ld+json"):
    try:
      data = json.loads(script.string or "", strict=False)
    except json.JSONDecodeError:
      continue
    items.extend(data if isinstance(data, list) else [data])

  # the EventVenue block is skipped, only MusicEvent entries are events
  items = [i for i in items if i.get("@type") == "MusicEvent"]
  if not items:
    return []  # empty venue page, nothing to add

  names = sorted({_norm(a) for a in artists if len(a) >= 3}, key=len, reverse=True)
  pattern = (
      re.compile(r"\b(?:" + "|".join(re.escape(a) for a in names) + r")\b")
      if names
      else None
  )

  events = []
  for item in items:
    title = htmllib.unescape(item.get("name", "")).strip()
    start = item.get("startDate", "")
    url = item.get("url") or item.get("offers", {}).get("url")
    if not title or not start or not url:
      continue

    # support acts only appear in the performer list on multi-act bills
    performers = [p.get("name", "") for p in item.get("performer", [])]
    haystack = _norm(" ".join([title, *map(htmllib.unescape, performers)]))
    if not pattern or not pattern.search(haystack):
      continue

    location = item.get("location", {})
    venue_name = location.get("name", "").strip()
    address = location.get("address", {})
    street = address.get("streetAddress", "").strip()
    venue = ", ".join(p for p in (venue_name, street) if p) or "Unknown Venue"

    events.append({
        "title": title,
        "date_str": start,
        "url": url,
        "venue": venue,
        "region": address.get("addressRegion", ""),
    })
  return events


def build_event_ticketweb(events):
  cal = Calendar()
  for ev in events:
    try:
      tz = REGION_TZ.get(ev.get("region", ""), MONTREAL_TZ)
      local_dt = parse_date_any(ev["date_str"]).replace(tzinfo=tz)
    except Exception as e:
      print(
          f"⚠️ ticketweb: skipped '{ev['title']}' "
          f"(unreadable date '{ev['date_str']}': {e})"
      )
      continue
    utc_dt = local_dt.astimezone(UTC_TZ)
    title_uni = clean_title(ev["title"])

    vevent = (
        ICSEventBuilder()
        .uid(f"tw{ev['url'].rstrip('/').split('/')[-1]}")
        .start(utc_dt)
        .end(utc_dt + timedelta(hours=3))
        .summary(f"🎵 | {title_uni}")
        .location(ev["venue"])
        .description(f"Tickets: {ev['url']}\nArtists: {title_uni}")
        .build()
    )
    cal.add_component(vevent)
  return cal
