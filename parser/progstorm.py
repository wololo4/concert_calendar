from bs4 import BeautifulSoup
from datetime import datetime, timedelta
from icalendar import Calendar
from utils.ics import ICSEventBuilder
from zoneinfo import ZoneInfo

MONTREAL_TZ = ZoneInfo("America/Toronto")
UTC_TZ = ZoneInfo("UTC")


def determine_festival_year():
  today = datetime.now(MONTREAL_TZ)
  return today.year + 1 if today.month >= 10 else today.year

def parse_progstorm_html(html, times_cfg):
  soup = BeautifulSoup(html, "html.parser")
  container = soup.select_one(".sqs-html-content")
  if not container or not container.select_one("h3"):
    return []

  day_name = container.select_one("h2").get_text(strip=True).lower()
  try:
    parsed_date = datetime.strptime(
        container.select_one("h3").get_text(strip=True), "%B %d, %Y"
    )
  except Exception:
    return []

  # bands live in separate blocks, so search the whole page
  h4s = soup.select(".sqs-html-content h4") or soup.select("h4")
  bands = [
      h4.get_text(" ", strip=True) for h4 in h4s if h4.get_text(strip=True)
  ] or ["TO BE ANNOUNCED"]
  times = times_cfg.get(day_name, [])
  if len(times) < len(bands):
    return []

  events, date_str = [], parsed_date.strftime("%Y-%m-%d")
  for i, band in enumerate(bands):
    start_dt = datetime.strptime(f"{date_str} {times[i]}", "%Y-%m-%d %H:%M").replace(
        tzinfo=MONTREAL_TZ
    )
    end_dt = (
        start_dt + timedelta(hours=1)
        if i == 0
        else datetime.strptime(
            f"{date_str} {times[i-1]}", "%Y-%m-%d %H:%M"
        ).replace(tzinfo=MONTREAL_TZ)
    )

    events.append({
        "band": band,
        "venue": container.select_one("p").get_text(strip=True),
        "day_name": day_name,
        "start_dt": start_dt,
        "end_dt": end_dt,
        "index": i,
    })
  return events

def build_progstorm_calendar(events):
  cal = Calendar()
  year = determine_festival_year()
  for ev in events:
    vevent = (
        ICSEventBuilder()
        .uid(f"progstorm-{year}-{ev['day_name']}-{ev['index']}")
        .start(ev["start_dt"].astimezone(UTC_TZ))
        .end(ev["end_dt"].astimezone(UTC_TZ))
        .summary(f"🎵 | {ev['band']}")
        .location(ev["venue"])
        .description(f"Concert: {ev['band']}\nJour: {ev['day_name'].capitalize()}")
        .build()
    )
    cal.add_component(vevent)
  return cal
