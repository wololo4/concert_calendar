import requests
import re
from icalendar import Calendar
from feeds import load_feeds

from parser.ticketmaster import parse_ticketmaster_json
from parser.progstorm import parse_progstorm_html, build_progstorm_calendar
from parser.eventbrite import parse_eventbrite_html, build_eventbrite_calendar
from parser.lepointdevente import parse_lpdv_html, build_event_lpdv

def main():
    feeds = load_feeds()
    all_events = []

    eventbrite_matched = set()
    lpdv_matched = set()
    progstorm_matched = False

    for parser_name, label, url, params, parser_key in feeds:
        if parser_key == "ticketmaster":
            raw = requests.get(url, params=params, headers={"User-Agent": "Mozilla/5.0"}).json()
        else:
            raw = requests.get(url, headers={"User-Agent": "Mozilla/5.0"}).text

        if parser_key == "eventbrite":
            artists = [a.lower() for a in params["artists"]]
            events = parse_eventbrite_html(raw, artists)
            for ev in events:
                parts = [p.strip() for p in re.split(r"[,+]", ev["name"].lower())]
                for p in parts:
                    if p in artists:
                        eventbrite_matched.add(p.capitalize())
            cal = build_eventbrite_calendar(events)
            all_events.extend(cal.walk("VEVENT"))
        if parser_key == "lepointdevente":
            artists = [a.lower() for a in params["artists"]]
            events = parse_lpdv_html(raw, artists)
            for ev in events:
                parts = [p.strip() for p in re.split(r"[,+]", ev["title"].lower())]
                for p in parts:
                    if p.lower() in artists:
                        lpdv_matched.add(p.capitalize())
            cal = build_event_lpdv(events)
            all_events.extend(cal.walk("VEVENT"))
        if parser_key == "progstorm":
            times_cfg = params["times"]
            events = parse_progstorm_html(raw, times_cfg)
            if events and not progstorm_matched:
                print("Found Progstorm events")
                progstorm_matched = True
            cal = build_progstorm_calendar(events)
            all_events.extend(cal.walk("VEVENT"))
        if parser_key == "ticketmaster":
            artists = [label.lower()]
            cal = parse_ticketmaster_json(raw, artists)
            vevents = list(cal.walk("VEVENT"))
            if vevents:
                print(f"Found Ticketmaster events for: {label}")
            all_events.extend(vevents)

    if eventbrite_matched:
        print("Found Eventbrite events for: " + ", ".join(sorted(eventbrite_matched)))
    if lpdv_matched:
        print("Found LPDV events for: " + ", ".join(sorted(lpdv_matched)))  

    unique = {str(ev.get("UID")): ev for ev in all_events}
    final_cal = Calendar()
    for ev in unique.values():
        final_cal.add_component(ev)

    event_count = len(unique)
    print(f"concerts.ics file created with {event_count} events.")

    with open("calendars/concerts.ics", "wb") as f:
        f.write(final_cal.to_ical())

if __name__ == "__main__":
    main()
