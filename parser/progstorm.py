from icalendar import Calendar
from utils.ics import ICSEventBuilder
from datetime import datetime, timedelta
from bs4 import BeautifulSoup
from utils.fetch import fetch_html
import calendar
import yaml

def load_progstorm_config():
  with open("concerts.yaml", "r", encoding="utf-8") as f:
    data = yaml.safe_load(f)
    for src in data.get("sources", []):
      if src.get("parser") == "progstorm":
        return src
  return {}

def determine_festival_year():
  today = datetime.now()
  if today.month >= 12:
    return today.year + 1
  return today.year

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

def fetch_bands(soup):
    return [
      h3.get_text(strip=True)
      for h3 in soup.select("div.lineup-item h3")
    ]

def parse_progstorm():
    config = load_progstorm_config()
    if not config:
        print("⚠️ Aucun bloc progstorm dans concerts.yaml")
        return Calendar()

    base_url = config.get("base_url")
    times_cfg = config.get("times", {})

    if not base_url or not times_cfg:
        print("⚠️ progstorm.base_url ou progstorm.times manquant")
        return Calendar()
      
    cal = Calendar()

    year = determine_festival_year()

    day_names = ["friday", "saturday", "sunday"]

    for day_name in day_names:
        url = f"{base_url}/lineup{year}-{day_name}"
        html = fetch_html(url)
        if not html:
            print(f" Failed to load {url}")
            continue

        soup = BeautifulSoup(html, "html.parser")
        extracted_day, parsed_date, venue = extract_meta(soup)
        if not parsed_date:
            print(f" No date found in HTML for {day_name}")
            continue
             
        bands = fetch_bands(soup)
        if not bands:
            print(f" No bands found for {day_name}")
            continue

        times = times_cfg.get(day_name, [])
        if len(times) < len(bands):
            print(f" Not enough times for {day_name}: {len(times)} time for {len(bands)} bands")
            continue
      
        for i, band in enumerate(bands):
            start_time = times[i]
            start_dt = datetime.strptime(f"{parsed_date.strftime('%Y-%m-%d')} {start_time}", "%Y-%m-%d %H:%M")
            if i == 0:
                end_dt = start_dt + timedelta(hours=1)
            else:
                prev_time = times[i - 1]
                end_dt = datetime.strptime(f"{parsed_date.strftime('%Y-%m-%d')} {prev_time}", "%Y-%m-%d %H:%M")  

            uid = f"progstorm-{year}-{day_name}-{i}"

            event = (
                ICSEventBuilder()
                .uid(uid)
                .start(start_dt)
                .end(end_dt)
                .summary(f"🎵 | {band}")
                .location(venue)
                .description(f"Concert: {band}\nJour: {day_name.capitalize()}")
                .build()
            )

            cal.add_component(event)

    return cal
