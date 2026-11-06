from bs4 import BeautifulSoup
from datetime import datetime, timedelta
from icalendar import Calendar
from utils.ics import ICSEventBuilder
import re
import unicodedata
from zoneinfo import ZoneInfo

QUEBEC_TZ = ZoneInfo("America/Toronto")
UTC_TZ = ZoneInfo("UTC")


def _strip_accents(s):
  s = unicodedata.normalize("NFKD", str(s))
  return "".join(c for c in s if not unicodedata.combining(c))


def _norm(s):
  return _strip_accents(str(s).lower())


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
# also accept month names written without accents (fevrier, aout, decembre)
FR_MONTHS.update({_strip_accents(k): v for k, v in list(FR_MONTHS.items())})

# "6 novembre 2026", "1er novembre 2026", "vendredi 6 novembre 2026"
DATE_RE = re.compile(
    r"(\d{1,2})(?:er|st|nd|rd|th)?\s+([^\W\d_]+)\.?\s+(\d{4})", re.I
)
# "20h00", "20h", "20 h 30"
TIME_RE = re.compile(r"(\d{1,2})\s*h\s*(\d{2})?", re.I)

DEFAULT_TIME = "20h00"


def parse_date_french(date_str):
  date_part, _, time_part = date_str.partition(",")
  m = DATE_RE.search(date_part)
  if not m:
    raise ValueError(f"unreadable date '{date_part.strip()}'")
  day, month_name, year = m.groups()
  month = FR_MONTHS.get(_norm(month_name))
  if not month:
    raise ValueError(f"unknown month '{month_name}'")
  t = TIME_RE.search(time_part)
  if not t:
    raise ValueError(f"unreadable time '{time_part.strip()}'")
  hour, minute = int(t.group(1)), int(t.group(2) or 0)
  return datetime(int(year), month, int(day), hour, minute)


def clean_title(title):
  # cut at "@" or at a spaced dash, keep hyphenated words like "Forty-Year"
  t = re.split(r"\s+[-–—]\s+", title.split("@")[0])[0]
  return t.replace("\\", "").replace(" +", ",").strip()


def parse_imperialbell_html(html, artists):
  soup = BeautifulSoup(html, "html.parser")
  names = sorted({_norm(a) for a in artists if len(a) > 3}, key=len, reverse=True)
  pattern = (
      re.compile(r"\b(?:" + "|".join(re.escape(a) for a in names) + r")\b")
      if names
      else None
  )
  events = []

  for item in soup.select("div#divShow"):
    if not (article := item.find("article", class_="article-card")):
      continue
    if not (title_tag := article.find("strong", class_="article-card__title")):
      continue

    title = title_tag.get_text(strip=True)
    if not pattern or not pattern.search(_norm(title)):
      continue

    date_tag = article.find("p", class_="article-card__date")
    time_tag = article.find("p", class_="article-card__time")
    link = article.find("a", id="lnkTitle")
    if not date_tag or not time_tag or not link:
      print(f"⚠️ Imperial Bell: skipped '{title}' (date, time or link missing)")
      continue

    spans = time_tag.find_all("span")
    hour_str = spans[1].get_text(strip=True) if len(spans) > 1 else None

    events.append({
        "title": title,
        "date_str": f"{date_tag.get_text(strip=True)}, {hour_str or DEFAULT_TIME}",
        "time_assumed": hour_str is None,
        "url": "https://www.imperialbell.com" + link["href"],
        "venue": "L'Impérial, Quebec",
    })
  return events


def build_event_imperialbell(events):
  cal = Calendar()
  for ev in events:
    try:
      local_dt = parse_date_french(ev["date_str"]).replace(tzinfo=QUEBEC_TZ)
    except Exception as e:
      print(f"⚠️ Imperial Bell: skipped '{ev['title']}' ({e})")
      continue
    utc_dt = local_dt.astimezone(UTC_TZ)
    title_uni = clean_title(ev["title"])

    desc = f"Tickets: {ev['url']}\nArtists: {title_uni}"
    if ev.get("time_assumed"):
      desc += f"\nStart time assumed {DEFAULT_TIME} (not listed on the page)."

    vevent = (
        ICSEventBuilder()
        .uid(f"imperialbell{ev['url'].rstrip('/').split('/')[-1]}")
        .start(utc_dt)
        .end(utc_dt + timedelta(hours=3))
        .summary(f"🎵 | {title_uni}")
        .location(ev["venue"])
        .description(desc)
        .build()
    )
    cal.add_component(vevent)
  return cal
