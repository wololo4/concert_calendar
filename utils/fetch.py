import json
import re
import time

import requests

SESSION = requests.Session()

DEFAULT_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/127.0.0.0 Safari/537.36"
    ),
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,*/*;q=0.8",
    "Accept-Language": "en-US,en;q=0.9",
    "Accept-Encoding": "gzip, deflate, br",
    "Referer": "https://www.google.com/",
    "Connection": "keep-alive",
    "Upgrade-Insecure-Requests": "1",
    "Sec-Fetch-Dest": "document",
    "Sec-Fetch-Mode": "navigate",
    "Sec-Fetch-Site": "none",
    "Sec-Fetch-User": "?1",
}

def fetch_json(url, params=None, headers=None, retries=3, delay=1):
    req_headers = DEFAULT_HEADERS.copy()
    if headers:
        req_headers.update(headers)

    for attempt in range(retries):
        try:
            resp = SESSION.get(url, headers=req_headers, params=params, timeout=4)
            resp.raise_for_status()
            return resp.json()
        except Exception as e:
            print(f"⚠️ JSON retry {attempt+1}/{retries}: {e}")
            if attempt < retries - 1:
                time.sleep(delay)

    print(f"❌ JSON fetch failed: {url}")
    return None


def fetch_html(url, headers=None, retries=3, delay=1):
    req_headers = DEFAULT_HEADERS.copy()
    if headers:
        req_headers.update(headers)

    for attempt in range(retries):
        try:
            resp = SESSION.get(url, headers=req_headers, timeout=4)
            resp.raise_for_status()
            return resp.text
        except Exception as e:
            print(f"⚠️ HTML retry {attempt+1}/{retries}: {e}")
            if attempt < retries - 1:
                time.sleep(delay)

    print(f"❌ HTML fetch failed: {url}")
    return None


# --- feeds that need more than a plain GET (used by merge.py) ---

BROWSER_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36"
    ),
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Accept-Language": "en-CA,en;q=0.9",
}

NEXT_DATA_RE = re.compile(
    r'(<script[^>]*id="__NEXT_DATA__"[^>]*>)(.*?)(</script>)', re.DOTALL
)

FETCH_JSON_JS = """async (u) => {
  const r = await fetch(u, {headers: {accept: 'application/json'}});
  return {status: r.status, body: await r.text()};
}"""


def _collect_events(obj, out):
    """Walk any JSON and keep dicts that look like Eventbrite events."""
    if isinstance(obj, dict):
        if (
                obj.get("id")
                and obj.get("name")
                and obj.get("start_date")
                and obj.get("start_time")
        ):
            out[str(obj["id"])] = obj
        for v in obj.values():
            _collect_events(v, out)
    elif isinstance(obj, list):
        for v in obj:
            _collect_events(v, out)


def fetch_eventbrite_html(url):
    """Organizer page with all of its upcoming events.

    The parser reads upcomingEvents from __NEXT_DATA__, which only holds the
    first page. The rest comes from the page's own events API (what "Show
    more" calls), fetched from inside the browser and merged in here.
    """
    from playwright.sync_api import sync_playwright

    org = re.search(r"(\d+)/?$", url).group(1)
    api = f"/api/organizer-profile/organizers/{org}/events?page={{}}&pageSize=12"
    found, last = {}, {}

    with sync_playwright() as p:
        browser = p.chromium.launch(
                headless=False,  # runs under xvfb-run
                args=["--disable-blink-features=AutomationControlled"],
        )
        try:
            ctx = browser.new_context(
                    user_agent=BROWSER_HEADERS["User-Agent"], locale="en-CA"
            )
            ctx.add_init_script(
                    "Object.defineProperty(navigator, 'webdriver', {get: () => undefined})"
            )
            page = ctx.new_page()
            page.goto(url, wait_until="domcontentloaded", timeout=30000)
            try:
                # event links rendered = the page's JS has run and cookies are set
                page.wait_for_selector('a[href*="/e/"]', state="attached", timeout=30000)
            except Exception:
                pass  # organizer with nothing coming up: nothing to page through

            for n in range(1, 31):
                last = page.evaluate(FETCH_JSON_JS, api.format(n))
                before = len(found)
                try:
                    _collect_events(json.loads(last["body"]), found)
                except ValueError:
                    pass
                if last["status"] != 200 or len(found) == before:
                    break
            raw = page.content()
        finally:
            browser.close()

    m = NEXT_DATA_RE.search(raw)
    try:
        data = json.loads(m.group(2))
        page_props = data["props"]["pageProps"]
    except Exception:
        return raw  # the parser reports the missing data block

    existing = page_props.get("upcomingEvents") or []
    have = {str(e.get("id")) for e in existing}
    added = [e for i, e in found.items() if i not in have]
    page_props["upcomingEvents"] = existing + added
    print(f"Eventbrite {org}: {len(existing)} events on page, {len(added)} from API")
    if not found and last:
        print(f"Eventbrite {org}: API HTTP {last['status']} {last['body'][:300]!r}")

    new_json = json.dumps(data, ensure_ascii=False).replace("</", "<\\/")
    return raw[: m.start(2)] + new_json + raw[m.end(2) :]


def fetch_ticketweb_html(session, url, headers):
    """Ticketweb answers plain requests with a 530 challenge now and then."""
    for attempt in range(4):
        if attempt:
            time.sleep(5)
        resp = session.get(url, headers=headers, timeout=15)
        if resp.ok:
            if attempt:
                print(f"ticketweb: worked on retry {attempt}")
            return resp.content.decode("utf-8")
    resp.raise_for_status()
