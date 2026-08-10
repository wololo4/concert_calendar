import yaml
from utils.fetch import fetch_json
from parser.ticketmaster import parse_ticketmaster_json
from icalendar import Calendar

def load_feeds():
    with open("concerts.yaml", "r") as f:
        return yaml.safe_load(f)

def main():
    feeds = load_feeds()
    artists = feeds["artists"]
    sources = feeds["sources"]

    all_events = []

    for src in sources:
        api_key = src.get("apikey")
        parser = src["parser"]
        url = src["url"]

        if parser == "ticketmaster":
            for artist in artists:
                params = {
                    "apikey": api_key,
                    "keyword": artist,
                    "city": src.get("city", ""),
                    "countryCode": src.get("country", ""),
                    "classificationName": "music",
                    "size": 200
                }

                raw_json = fetch_json(url, params=params)
                if raw_json:
                    cal = parse_ticketmaster_json(raw_json, artists)
                    all_events.extend(cal.walk("VEVENT"))

    unique_events = {}
    for ev in all_events:
        uid = str(ev.get("UID"))
        unique_Events[uid] = ev
    final_cal = Calendar()
    for ev in unique_events.values():
        final_cal.add_component(ev)

    with open("calendars/concerts.ics", "wb") as f:
        f.write(final_cal.to_ical())

if __name__ == "__main__":
    main()
