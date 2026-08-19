import yaml
from parser.progstorm import determine_festival_year

FEED_HANDLERS = {}

def register_feed(name):
    def decorator(func):
        FEED_HANDLERS[name] = func
        return func
    return decorator

def load_feeds():
    with open("concerts.yaml", "r", encoding="utf-8") as f:
        config = yaml.safe_load(f)
    
    feeds = []
    artists = config.get("artists", [])
    sources = config.get("sources", [])
    for src in sources:
        parser = src.get("parser")
        handler = FEED_HANDLERS.get(parser)
        if handler:
            handler(feeds, src, artists)
        else:
            print(f"Warning: Unknown parser '{parser}'")
    return feeds

@register_feed("ticketmaster")
def handle_ticketmaster(feeds, src, artists):
    base_url = src["url"]
    api_key = src.get("apikey")
    city = src.get("city", "")
    country = src.get("country", "")
    for artist in artists:
        params = {
            "apikey": api_key,
            "keyword": artist,
            "city": city,
            "countryCode": country,
            "size": 200
        }

        feeds.append((
            "ticketmaster",
            artist,
            base_url,
            params,
            "ticketmaster"
        ))

@register_feed("eventbrite")
def handle_eventbrite(feeds, src, artists):
    organizer_url = src.get("organizer_url")
    if not organizer_url:
        print("Missing organizer_url for Eventbrite")
        return
    
    feeds.append((
        "eventbrite", 
        "eventbrite",
        organizer_url,
        {"artists": artists},
        "eventbrite"
    ))

@register_feed("lepointdevente")
def handle_lpvd(feeds, src, artists):
    base_url =src["base_url"]
    slugs = src.get("venues", [])
    for slug in slugs:
        url = base_url + slug
        feeds.append((
            "lepointdevente",
            slug,
            url,
            {"artists": artists},
            "lepointdevente"
        ))

@register_feed("progstorm")
def handle_progstorm(feeds, src, artists):
    base_url = src.get("url")
    times = src.get("times", {})
    year = determine_festival_year()

    for day in ["friday", "saturday", "sunday"]:
        url = f"{base_url}/lineup{year}-{day}"
        feeds.append((
            "progstorm",
            day,
            url,
            {"times": times},
            "progstorm"
        ))