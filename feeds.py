from parser.progstorm import determine_festival_year
from urllib.parse import urljoin
import os
from dotenv import load_dotenv
import yaml

load_dotenv()

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
  artists, sources = config.get("artists", []), config.get("sources", [])
  for src in sources:
    if handler := FEED_HANDLERS.get(src.get("parser")):
      handler(feeds, src, artists)
    else:
      print(f"Warning: Unknown parser '{src.get('parser')}'")
  return feeds


@register_feed("ticketmaster")
def handle_ticketmaster(feeds, src, artists):
  for city in src.get("city", []):
    for artist in artists:
      feeds.append((
          "ticketmaster",
          f"{artist} ({city})",
          src["url"],
          {
              "apikey": os.environ["TICKETMASTER_API_KEY"],
              "keyword": artist,
              "city": city,
              "countryCode": src.get("country", ""),
              "size": 200,
          },
          "ticketmaster",
      ))


@register_feed("eventbrite")
def handle_eventbrite(feeds, src, artists):
  for org in src.get("organizer", []):
    feeds.append((
        "eventbrite",
        "eventbrite",
        src["base_url"] + org,
        {"artists": artists},
        "eventbrite",
    ))


@register_feed("imperialbell")
def handle_imperialbell(feeds, src, artists):
  if url := src.get("base_url"):
    feeds.append(
        ("imperialbell", "imperialbell", url, {"artists": artists}, "imperialbell")
    )
  else:
    print("Missing url for Imperial Bell")

@register_feed("lepointdevente")
def handle_lpvd(feeds, src, artists):
  base = src["base_url"]
  pages = [urljoin(base, slug) for slug in src.get("venues", [])]
  pages += [urljoin(base, f"../tickets/{slug}") for slug in src.get("tickets", [])]

  for url in pages:
    feeds.append((
        "lepointdevente",
        url.rstrip("/").split("/")[-1],
        url,
        {"artists": artists},
        "lepointdevente",
    ))

@register_feed("ovation")
def handle_ovation(feeds, src, artists):
  if url := src.get("base_url"):
    feeds.append(("ovation", "ovation", url, {"artists": artists}, "ovation"))
  else:
    print("Missing url for Ovation")

@register_feed("progstorm")
def handle_progstorm(feeds, src, artists):
  year = determine_festival_year()
  for day in ["friday", "saturday", "sunday"]:
    feeds.append((
        "progstorm",
        day,
        f"{src.get('url')}/lineup{year}-{day}",
        {"times": src.get("times", {})},
        "progstorm",
    ))
