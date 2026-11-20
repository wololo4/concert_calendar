from bs4 import BeautifulSoup
from datetime import datetime, timedelta
from icalendar import Calendar
from utils.ics import ICSEventBuilder
from urllib.parse import urljoin
import re
import unicodedata
from zoneinfo import ZoneInfo

UTC_TZ = ZoneInfo("UTC")
DEFAULT_TZ = ZoneInfo("America/Toronto")

# card times are venue-local; the card only gives the city
CITY_TZ = {
    "vancouver": ZoneInfo("America/Vancouver"),
    "victoria": ZoneInfo("America/Vancouver"),
    "calgary": ZoneInfo("America/Edmonton"),
    "edmonton": ZoneInfo("America/Edmonton"),
    "winnipeg": ZoneInfo("America/Winnipeg"),
    "toronto": ZoneInfo("America/Toronto"),
    "ottawa": ZoneInfo("America/Toronto"),
    "montreal": ZoneInfo("America/Toronto"),
    "montréal": ZoneInfo("America/Toronto"),
}

MONTHS = [
    "jan", "feb", "mar", "apr", "may", "jun",
    "jul", "aug", "sep", "oct", "nov", "dec",
]

# "Mon, Nov 30, 2026, 7:30 p.m."  (also "7 p.m.")
DATE_RE = re.compile(
    r"^[A-Za-z]{3}, ([A-Za-z]{3}) (\d{1,2}), (\d{4}), "
    r"(\d{1,2})(?::(\d{2}))? ([ap])\.?m\.?$",
    re.I,
)


def _strip_accents(s):
  s = unicodedata.normalize("NFKD", s)
  return "".join(c for c in s if not unicodedata.combining(c))


def _norm(s):
  return _strip_accents(str(s).lower())


def parse_date_any(date_str):
  m = DATE_RE.match(date_str.strip())
  if not m:
    raise ValueError(f"Unknown date: {date_str}")
  month = MONTHS.index(m[1].lower()) + 1
  hour = int(m[4]) % 12 + (12 if m[6].lower() == "p" else 0)
  return datetime(int(m[3]), month, int(m[2]), hour, int(m[5] or 0))


def clean_title(title):
  # cut at "@" or at a spaced dash, keep hyphenated words like "Forty-Year"
  t = re.split(r"\s+[-–—]\s+", title.split("@")[0])[0]
  return t.replace("\\", "").replace(" +", ",").strip()


def parse_admitone_html(html, artists):
  soup = BeautifulSoup(html, "html.parser")
  for tag in soup(["script", "style"]):
    tag.decompose()

  links = [
      a["href"]
      for a in soup.find_all("a", href=True)
      if "/events/" in a["href"] and a.get_text(strip=True).lower() == "get tickets"
  ]
  if not links:
    return []  # empty venue page, nothing to add

  # the page is a flat list: title, date, "venue, city", then "Get Tickets"
  lines = [l for l in soup.get_text("\n", strip=True).split("\n") if l]
  dates = [i for i, l in enumerate(lines) if DATE_RE.match(l)]
  if len(dates) != len(links):
    print(
        f"⚠️ admitone: {len(dates)} dates but {len(links)} ticket links "
        "(layout change?)"
    )

  address = ""
  if "Venue Information" in lines:
    nxt = lines[lines.index("Venue Information") + 1 :][:1]
    address = nxt[0] if nxt and nxt[0] != "Get Directions" else ""

  names = sorted({_norm(a) for a in artists if len(a) >= 3}, key=len, reverse=True)
  pattern = (
      re.compile(r"\b(?:" + "|".join(re.escape(a) for a in names) + r")\b")
      if names
      else None
  )

  events = []
  for i, link in zip(dates, links):
    title = lines[i - 1]
    if not pattern or not pattern.search(_norm(title)):
      continue

    venue_name, _, city = (lines[i + 1] if i + 1 < len(lines) else "").partition(",")
    venue_name, city = venue_name.strip(), city.strip()
    venue = ", ".join(p for p in (venue_name, address) if p) or "Unknown Venue"

    events.append({
        "title": title,
        "date_str": lines[i],
        "url": urljoin("https://admitone.com", link),
        "venue": venue,
        "city": city,
    })
  return events


def build_event_admitone(events):
  cal = Calendar()
  for ev in events:
    try:
      tz = CITY_TZ.get(ev["city"].lower(), DEFAULT_TZ)
      local_dt = parse_date_any(ev["date_str"]).replace(tzinfo=tz)
    except Exception as e:
      print(
          f"⚠️ admitone: skipped '{ev['title']}' "
          f"(unreadable date '{ev['date_str']}': {e})"
      )
      continue
    utc_dt = local_dt.astimezone(UTC_TZ)
    title_uni = clean_title(ev["title"])

    vevent = (
        ICSEventBuilder()
        .uid(f"ao{ev['url'].rstrip('/').split('/')[-1]}")
        .start(utc_dt)
        .end(utc_dt + timedelta(hours=3))
        .summary(f"🎵 | {title_uni}")
        .location(ev["venue"])
        .description(f"Tickets: {ev['url']}\nArtists: {title_uni}")
        .build()
    )
    cal.add_component(vevent)
  return cal
