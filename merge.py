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
    api_key = feeds["apikey"]

    all_events = []

    for src in sources:
        parser = src["parser"]
        url = src["url"]

        if parser == "ticketmaster":
            params = {
                "apikey": api_key,
                "keyword": ",".join(artists),
                "city": src.get("city", "Montreal"),
                "countryCode": src.get("country", "CA"),
                "classificationName": "music",
                "size": 200
            }

            raw_json = fetch_json(url, params=params)
            if raw_json:
                cal = parse_ticketmaster_json(raw_json, artists)
                all_events.extend(cal.walk("VEVENT"))

    final_cal = Calendar()
    for ev in all_events:
        final_cal.add_component(ev)

    with open("calendars/concerts.ics", "wb") as f:
        f.write(final_cal.to_ical())

if __name__ == "__main__":
    main()
