import requests
import re
from icalendar import Calendar
from feeds import load_feeds

from parser.ticketmaster import parse_ticketmaster_json
from parser.progstorm import parse_progstorm_html, build_progstorm_calendar
from parser.eventbrite import parse_eventbrite_html, build_eventbrite_calendar
from parser.lepointdevente import parse_lpdv_html, build_event_lpdv
from parser.imperialbell import parse_imperialbell_html, build_event_imperialbell

VENUE_ALIASE = {
    "L'Anti Bar": [
        "L'Anti Bar",
        "L'Anti Bar & Spectacles"
    ],
    "Club Soda": [
        "Club Soda",
        "CLUB SODA"
    ],
    "Salle Montaigne": [
        "Salle Montaigne",
        "Salle Montaigne - Cégep Limoilou"
    ]
}

VENUE_CITY = {
    "Club Soda": "Montreal",
    "Fairmount Theatre": "Montreal",
    "Le Ministère": "Montreal",
    "MTELUS": "Montreal",
    "L'Olympia": "Montreal", 
    "Piranha Bar": "Montreal",
    "Théâtre Beanfield": "Montreal",

    "The Bronson": "Ottawa",
    "Rainbow Bistro": "Ottawa",

    "L'Anti Bar": "Quebec",
    "L'Impérial": "Quebec",
    "Salle Montaigne" : "Quebec", 
    "La Source de la Martinière": "Quebec",
    "Théâtre Capitole": "Quebec",
}

def extract_city_from_event(ev):
    loc = ev.get("LOCATION")
    if not loc:
        print("⚠️ Event has no LOCATION field")
        return None
    
    venue_raw = loc.split(",")[0].strip()
    venue = venue_raw
    for canonical, aliases in VENUE_ALIASE.items():
        if venue_raw in aliases:
            venue = canonical
            break

    if venue not in VENUE_CITY:
        print(f"⚠️ Unknown venue: {venue_raw}")
        return None
    return VENUE_CITY[venue]

def main():
    feeds = load_feeds()
    all_events = []
    city_events = {}

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
            vevents = list(cal.walk("VEVENT"))
            all_events.extend(vevents)
            for ev_raw, ev_ical in zip(events, vevents):
                city = extract_city_from_event(ev_ical)
                if city is None:
                    continue
                raw_title = ev_raw["name"].lower()
                for a in artists:
                    if a in raw_title:
                        print(f"Found Eventbrite events for: {a.capitalize()} in {city}")
                city_events.setdefault(city, []).append(ev_ical)
        if parser_key == "imperialbell":
            artists = [a.lower() for a in params["artists"]]
            events = parse_imperialbell_html(raw, artists)
            cal = build_event_imperialbell(events)
            vevents = list(cal.walk("VEVENT"))
            all_events.extend(vevents)
            for ev_raw, ev_ical in zip(events, vevents):
                city = extract_city_from_event(ev_ical)
                if city is None:
                    continue
                raw_title = ev_raw["title"].lower()
                for a in artists:
                    if a in raw_title:
                        print(f"Found ImperialBell events for: {a.capitalize()} in {city}")
                city_events.setdefault(city, []).append(ev_ical)
        if parser_key == "lepointdevente":
            artists = [a.lower() for a in params["artists"]]
            events = parse_lpdv_html(raw, artists)
            for ev in events:
                parts = [p.strip() for p in re.split(r"[,+]", ev["title"].lower())]
                for p in parts:
                    if p.lower() in artists:
                        lpdv_matched.add(p.capitalize())
            cal = build_event_lpdv(events)
            vevents = list(cal.walk("VEVENT"))
            all_events.extend(vevents)
            for ev in vevents:
                city = extract_city_from_event(ev)
                if city is None:
                    continue
                title = ev.get("SUMMARY", "").lower()
                matched_artist = None
                for a in artists:
                    if a in title:
                        print(f"Found LPDV events for: {a.capitalize()} in {city}")
                city_events.setdefault(city, []).append(ev)
        if parser_key == "progstorm":
            times_cfg = params["times"]
            events = parse_progstorm_html(raw, times_cfg)
            if events and not progstorm_matched:
                print("Found Progstorm events")
                progstorm_matched = True
            cal = build_progstorm_calendar(events)
            vevents = list(cal.walk("VEVENT"))
            all_events.extend(vevents)
            for ev in vevents:
                city = extract_city_from_event(ev)
                if city is None:
                    continue
                city_events.setdefault(city, []).append(ev)
        if parser_key == "ticketmaster":
            artist_part, city_part = label.rsplit("(",1)
            artist = artist_part.strip()
            city = city_part.strip(") ").strip()

            artists = [artist.lower()]
            cal = parse_ticketmaster_json(raw, artists)
            vevents = list(cal.walk("VEVENT"))
            if vevents:
                print(f"Found Ticketmaster events for: {artist} in {city}")
            all_events.extend(vevents)
            for ev in vevents:
                event_city = extract_city_from_event(ev)
                if event_city is None:
                    continue
                city_events.setdefault(event_city, []).append(ev)

    unique = {str(ev.get("UID")): ev for ev in all_events}

    for city, events in city_events.items():
        city_unique = {}
        for ev in events:
            uid = str(ev.get("UID"))
            if uid in unique:
                city_unique[uid] = unique[uid]

        cal = Calendar()
        for ev in city_unique.values():
            cal.add_component(ev)

        filename = f"calendars/{city.lower()}.ics"
        with open(filename, "wb") as f:
            f.write(cal.to_ical())

        print(f"{city}.ics file created with {len(city_unique)} events.")

if __name__ == "__main__":
    main()
