import time
import requests

SESSION = requests.Session()

DEFAULT_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/138.0.0.0 Safari/537.36"
    ),
    "Accept": "*/*",
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
