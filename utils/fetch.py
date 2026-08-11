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
