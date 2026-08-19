from icalendar import Calendar
from utils.ics import ICSEventBuilder
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo
from bs4 import BeautifulSoup

MONTREAL_TZ = ZoneInfo("America/Toronto")
UTC_TZ = ZoneInfo("UTC")

def determine_festival_year():
  today = datetime.now(MONTREAL_TZ)
  return today.year + 1 if today.month >= 12 else today.year

def extract_meta(soup):
  container = soup.select_one(".sqs-html-content")
  if not container:
      return None, None, None
  day_el = container.select_one("h2")
  date_el = container.select_one("h3")
  venue_el = container.select_one("p")

  day_name = day_el.get_text(strip=True).lower() if day_el else None
  date_text = date_el.get_text(strip=True) if date_el else None
  venue_text = venue_el.get_text(strip=True) if venue_el else None

  parsed_date = None
  if date_text:
    try:
      parsed_date = datetime.strptime(date_text, "%B %d, %Y")
    except ValueError:
      parsed_date = None
  return day_name, parsed_date, venue_text

def extract_bands(soup):
    return [
      a.get_text(strip=True)
      for a in soup.select(".sqs-html-content h4 a")
    ]

def parse_progstorm_html(html, times_cfg):
    soup = BeautifulSoup(html, "html.parser")

    day_name, parsed_date, venue = extract_meta(soup)
    if not parsed_date:
       print("No date found in HTML")
       return []

    bands = extract_bands(soup)
    if not bands:
        print("No bands found")
        return []

    times = times_cfg.get(day_name, [])
    if len(times) < len(bands):
       print(f"Not enough times for {day_name}: {len(times)} time for {len(bands)} bands")
       return []

    events = []
    for i, band in enumerate(bands):
        start_time = times[i]
        start_dt = datetime.strptime(
            f"{parsed_date.strftime('%Y-%m-%d')} {start_time}",
            "%Y-%m-%d %H:%M"
        ).replace(tzinfo=MONTREAL_TZ)

        if i == 0:
            end_dt = start_dt + timedelta(hours=1)
        else:
           prev_time =times[i-1]
           end_dt = datetime.strptime(
              f"{parsed_date.strftime('%Y-%m-%d')} {prev_time}",
              "%Y-%m-%d %H:%M"
           ).replace(tzinfo=MONTREAL_TZ)

        events.append({
           "band": band,
           "venue": venue,
           "day_name": day_name,
           "start_dt": start_dt,
           "end_dt": end_dt,
           "index": i
        })

    return events

def build_progstorm_calendar(events):
    cal = Calendar()
    year = determine_festival_year()
    for ev in events:
        utc_start = ev["start_dt"].astimezone(UTC_TZ)
        utc_end = ev["end_dt"].astimezone(UTC_TZ)

        uid = f"progstorm-{year}-{ev['day_name']}-{ev['index']}"

        vevent = (
            ICSEventBuilder()
            .uid(uid)
            .start(utc_start)
            .end(utc_end)
            .summary(f"🎵 | {ev['band']}")
            .location(ev["venue"])
            .description(f"Concert: {ev['band']}\nJour: {ev['day_name'].capitalize()}")
            .build()
        )

        cal.add_component(vevent)

    return cal
