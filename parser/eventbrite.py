from datetime import datetime, timedelta
from icalendar import Calendar
import json
import re
import unicodedata
from utils.ics import ICSEventBuilder
from zoneinfo import ZoneInfo

MONTREAL_TZ = ZoneInfo("America/Toronto")
UTC_TZ = ZoneInfo("UTC")

# original split, then a wider one for titles like "Haken - Tour" or "A avec B"
_SPLIT_BASIC = re.compile(r"[,+]")
_SPLIT_MORE = re.compile(
    r"[,+&/|:]|\s[-–—]\s|\s(?:avec|with|feat\.?|ft\.?|w/)\s", re.I
)
_DISPLAY_SPLIT = re.compile(r"\s*[,+]\s*")


def _norm(text):
  s = unicodedata.normalize("NFKD", str(text).lower())
  return "".join(c for c in s if not unicodedata.combining(c)).strip()


def _title_parts(title):
  n = _norm(title)
  parts = set()
  for rx in (_SPLIT_BASIC, _SPLIT_MORE):
    parts |= {p.strip() for p in rx.split(n) if p.strip()}
  return parts


def parse_eventbrite_html(html, artists):
  match = re.search(
      r'<script[^>]*id="__NEXT_DATA__"[^>]*>(.*?)</script>', html, re.DOTALL
  )
  if not match:
    print("⚠️ Eventbrite: page data block not found (layout change or blocked page)")
    return []

  try:
    data = json.loads(match.group(1))
  except Exception as e:
    print(f"⚠️ Eventbrite: page data is not readable ({e})")
    return []

  # an organizer with nothing coming up is normal, so no message here
  events = (data.get("props", {}).get("pageProps", {}) or {}).get(
      "upcomingEvents"
  ) or []

  artists_norm = {_norm(a) for a in artists if str(a).strip()}
  filtered = []
  for ev in events:
    if _title_parts(ev.get("name") or "") & artists_norm:
      filtered.append(ev)
  return filtered


def _build_event(ev):
  name = ev["name"]
  artists = [p for p in _DISPLAY_SPLIT.split(name) if p.strip()]

  start_dt = datetime.fromisoformat(
      f"{ev['start_date']}T{ev['start_time']}"
  ).replace(tzinfo=MONTREAL_TZ)
  utc_start = start_dt.astimezone(UTC_TZ)

  # real end time when the page provides a sane one, else 3 hours
  utc_end = utc_start + timedelta(hours=3)
  if ev.get("end_date") and ev.get("end_time"):
    try:
      end_dt = (
          datetime.fromisoformat(f"{ev['end_date']}T{ev['end_time']}")
          .replace(tzinfo=MONTREAL_TZ)
          .astimezone(UTC_TZ)
      )
      if timedelta(0) < end_dt - utc_start <= timedelta(hours=12):
        utc_end = end_dt
    except ValueError:
      pass

  loc = ev.get("primary_venue") or {}
  venue_name = (loc.get("name") or "").strip()
  address = ((loc.get("address") or {}).get("address_1") or "").strip()
  location = ", ".join(p for p in (venue_name, address) if p)

  return (
      ICSEventBuilder()
      .uid(f"eventbrite{ev['id']}")
      .start(utc_start)
      .end(utc_end)
      .summary(f"🎵 | {name}")
      .location(location)
      .description(f"Tickets: {ev.get('url', '')}\nArtists: {', '.join(artists)}")
      .build()
  )


def build_eventbrite_calendar(events):
  cal = Calendar()
  for ev in events:
    try:
      vevent = _build_event(ev)
    except Exception as e:
      print(
          f"⚠️ Eventbrite: skipped '{ev.get('name')}' "
          f"({type(e).__name__}: {e})"
      )
      continue
    cal.add_component(vevent)
  return cal
