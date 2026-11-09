"""Ticketmaster search with far fewer requests.

Each artist's Ticketmaster attraction ID is looked up once and cached in
ticketmaster_ids.json, then many attractions are requested per call.
Artists with no attraction yet are re-checked every NEGATIVE_TTL_DAYS days and
known IDs are refreshed every POSITIVE_TTL_DAYS days. Both are spread out so
that only about ceil(n / TTL) artists are looked up per day.
"""
from datetime import datetime, timezone
import json
import os
import re
import threading
import time
import unicodedata

from parser.ticketmaster import parse_ticketmaster_json

CACHE_FILE = "ticketmaster_ids.json"
NEGATIVE_TTL_DAYS = 30    # re-check artists with no attraction this often
POSITIVE_TTL_DAYS = 180   # refresh known attraction IDs this often
FORCE_RECHECK = os.environ.get("TM_FORCE_RECHECK") == "1"
BATCH_SIZE = 40           # attraction IDs per request
PAGE_SIZE = 200
MAX_PAGES = 5             # 200 x 5 stays under the API's 1000-result limit
MIN_INTERVAL = 0.25       # seconds between requests (API limit is 5 per second)

# Artists with no attraction are NOT keyword-searched; the periodic re-check
# above picks them up once Ticketmaster creates an attraction for them.
# Set True to also keyword-search them on every run.
KEYWORD_FALLBACK_UNRESOLVED = False
# These artists always get a keyword search, even with an attraction ID.
KEYWORD_FALLBACK_ARTISTS = {
    "elder",
}

_lock = threading.Lock()
_last = 0.0
_requests = 0


def _redact(e):
  return re.sub(r"apikey=[^&\s]+", "apikey=***", str(e))


def _norm(s):
  s = unicodedata.normalize("NFKD", str(s).casefold())
  s = "".join(c for c in s if not unicodedata.combining(c))
  return re.sub(r"[^a-z0-9]+", " ", s).strip()


def _get(session, url, params):
  global _last, _requests
  with _lock:
    wait = _last + MIN_INTERVAL - time.monotonic()
    if wait > 0:
      time.sleep(wait)
    _last = time.monotonic()
    _requests += 1
  resp = session.get(
      url, params=params, headers={"User-Agent": "Mozilla/5.0"}, timeout=15
  )
  resp.raise_for_status()
  return resp.json()


def _paged(session, url, params):
  out, page = [], 0
  while page < MAX_PAGES:
    data = _get(session, url, {**params, "page": page})
    out.extend((data.get("_embedded") or {}).get("events") or [])
    total = (data.get("page") or {}).get("totalPages", 1)
    page += 1
    if page >= total:
      break
  return out


def _chunks(items, n):
  for i in range(0, len(items), n):
    yield items[i : i + n]


# --- attraction ID cache ----------------------------------------------------

def _load_cache():
  try:
    with open(CACHE_FILE, encoding="utf-8") as f:
      data = json.load(f)
    return data if isinstance(data, dict) else {}
  except (OSError, ValueError):
    return {}


def _save_cache(artists_cache):
  tmp = f"{CACHE_FILE}.tmp"
  try:
    with open(tmp, "w", encoding="utf-8") as f:
      json.dump(
          {"artists": artists_cache},
          f,
          ensure_ascii=False,
          indent=1,
          sort_keys=True,
      )
    os.replace(tmp, CACHE_FILE)
  except OSError as e:
    print(f"⚠️ Ticketmaster: could not save {CACHE_FILE}: {e}")


def _age_days(stamp):
  try:
    d = datetime.strptime(stamp, "%Y-%m-%d").date()
    return (datetime.now(timezone.utc).date() - d).days
  except Exception:
    return 10**6


def _lookup(session, attractions_url, apikey, artist):
  data = _get(
      session,
      attractions_url,
      {"apikey": apikey, "keyword": artist, "size": 30},
  )
  want = artist.casefold().strip()
  found = []
  for a in (data.get("_embedded") or {}).get("attractions") or []:
    # same exact-name rule your Ticketmaster parser uses
    if str(a.get("name", "")).casefold().strip() == want and a.get("id"):
      found.append(a["id"])
  return sorted(set(found))


def resolve_ids(session, events_url, apikey, artists, errors):
  """Returns (attraction_ids, artists_without_attraction, stats)."""
  attractions_url = events_url.rsplit("/", 1)[0] + "/attractions.json"
  stored = _load_cache().get("artists", {})
  today = datetime.now(timezone.utc).date().isoformat()
  keys = [a.casefold().strip() for a in artists]

  def known(key):
    e = stored.get(key)
    return e if isinstance(e, dict) else None

  def pick_due(group, ttl):
    """Due artists, most overdue first, at most ceil(n / ttl) per day."""
    cap = max(1, -(-len(group) // ttl))
    done_today = sum(1 for k in group if stored[k].get("checked") == today)
    due = sorted(
        (k for k in group if _age_days(stored[k].get("checked")) >= ttl),
        key=lambda k: (stored[k].get("checked") or "", k),
    )
    return set(due[: max(0, cap - done_today)]), cap

  unique = set(keys)
  waiting = [k for k in unique if known(k) and not known(k).get("ids")]
  have = [k for k in unique if known(k) and known(k).get("ids")]

  if FORCE_RECHECK:
    recheck, neg_cap = set(waiting) | set(have), len(waiting)
  else:
    neg_due, neg_cap = pick_due(waiting, NEGATIVE_TTL_DAYS)
    pos_due, _ = pick_due(have, POSITIVE_TTL_DAYS)
    recheck = neg_due | pos_due

  cache, ids, unresolved = {}, [], []
  lookups, changed = 0, False
  for artist, key in zip(artists, keys):
    entry = known(key)
    # new artists are looked up right away
    if entry is None or key in recheck:
      try:
        found = _lookup(session, attractions_url, apikey, artist)
        old = (entry or {}).get("ids") or []
        # an empty result never wipes an ID that worked before
        entry = {"ids": found or old, "checked": today}
        lookups += 1
        changed = True
      except Exception as e:
        errors.append(f"attraction lookup '{artist}': {_redact(e)}")
        # an old entry stays as it was and is retried on the next run
    if entry:
      cache[key] = entry
      if entry.get("ids"):
        ids.extend(entry["ids"])
        continue
    unresolved.append(artist)

  if changed or set(cache) != set(stored) or not os.path.exists(CACHE_FILE):
    _save_cache(cache)
  return sorted(set(ids)), unresolved, {"lookups": lookups, "cap": neg_cap}


# --- events -----------------------------------------------------------------

def _in_cities(ev, cities_norm):
  venues = (ev.get("_embedded") or {}).get("venues") or []
  city = _norm(((venues[0] if venues else {}).get("city") or {}).get("name") or "")
  if not city:
    return True
  return any(c == city or c in city for c in cities_norm)


def _start(ev):
  return ((ev.get("dates") or {}).get("start") or {}).get("dateTime") or ""


def _parse(events, artists):
  lowered = [a.lower() for a in artists]
  for ev in events:  # an empty venue list would crash the parser
    emb = ev.get("_embedded")
    if isinstance(emb, dict) and emb.get("venues") == []:
      emb["venues"] = [{}]
  try:
    cal = parse_ticketmaster_json({"_embedded": {"events": events}}, lowered)
    return list(cal.walk("VEVENT"))
  except Exception as e:
    print(
        f"⚠️ Ticketmaster: parser failed ({type(e).__name__}: {e}), "
        "retrying event by event"
    )
    out = []
    for ev in events:
      try:
        cal = parse_ticketmaster_json({"_embedded": {"events": [ev]}}, lowered)
        out.extend(cal.walk("VEVENT"))
      except Exception as e2:
        print(f"⚠️ Ticketmaster: skipped '{ev.get('name')}' ({type(e2).__name__}: {e2})")
    return out


def fetch_events(session, url, params):
  """Returns (vevents, errors). errors lists requests that failed."""
  apikey = params["apikey"]
  cities = params.get("cities") or []
  country = params.get("country") or ""
  artists = params.get("artists") or []
  errors = []
  if not cities or not artists:
    return [], errors

  start_requests = _requests
  cities_norm = [_norm(c) for c in cities]
  collected = {}

  def add(events, city_filter=False):
    for ev in events:
      ev_id = ev.get("id")
      if not ev_id or ev_id in collected:
        continue
      if city_filter and not _in_cities(ev, cities_norm):
        continue
      collected[ev_id] = ev

  ids, unresolved, stats = resolve_ids(session, url, apikey, artists, errors)

  base = {"apikey": apikey, "size": PAGE_SIZE}
  if country:
    base["countryCode"] = country

  for city in cities:
    for batch in _chunks(ids, BATCH_SIZE):
      try:
        add(_paged(session, url, {**base, "city": city, "attractionId": ",".join(batch)}))
      except Exception as e:
        errors.append(f"{city} batch: {_redact(e)}")

  # Keyword searches: configured exceptions (artists that have an attraction
  # ID but are still searched by name), plus the unresolved artists only if
  # KEYWORD_FALLBACK_UNRESOLVED is on.
  fallback = {}
  if KEYWORD_FALLBACK_UNRESOLVED:
    fallback.update({a.casefold().strip(): a for a in unresolved})
  for artist in artists:
    key = artist.casefold().strip()
    if key in KEYWORD_FALLBACK_ARTISTS:
      fallback[key] = artist

  for artist in fallback.values():
    try:
      add(_paged(session, url, {**base, "keyword": artist}), city_filter=True)
    except Exception as e:
      errors.append(f"keyword '{artist}': {_redact(e)}")

  events = sorted(collected.values(), key=lambda e: (_start(e), e.get("id", "")))
  vevents = _parse(events, artists)

  print(
      f"Ticketmaster: {len(vevents)} events from {_requests - start_requests} "
      f"requests ({len(artists) - len(unresolved)} artists matched to "
      f"attractions, {len(unresolved)} without), "
      f"{stats['lookups']} attraction lookup(s) this run"
  )
  if unresolved:
    print(
        f"Ticketmaster: artists without an attraction are re-checked every "
        f"{NEGATIVE_TTL_DAYS} days, at most {stats['cap']} per day: "
        + ", ".join(unresolved)
    )
  return vevents, errors
