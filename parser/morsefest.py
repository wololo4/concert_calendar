
from bs4 import BeautifulSoup
from datetime import date, datetime, timedelta
from icalendar import Calendar
from urllib.parse import urljoin, urlparse
from utils.ics import ICSEventBuilder
from zoneinfo import ZoneInfo
import re

MONTREAL_TZ = ZoneInfo("America/Toronto")
UTC_TZ = ZoneInfo("UTC")
BASE_URL = "https://morsefest.com"

MONTHS = {
    month.lower(): i
    for i, month in enumerate(
        [
            "January", "February", "March", "April",
            "May", "June", "July", "August",
            "September", "October", "November", "December",
        ],
        1,
    )
}

MONTHS.update({
    month[:3].lower(): number
    for month, number in list(MONTHS.items())
    if len(month) > 3
})


def parse_morsefest_dates(date_text, year):
    """
    Parse a listing date such as:
        Jun 21–22
        Jun 21 - 22
        June 21-22
        Jun 30–Jul 1

    Returns a list of date objects, one per festival day.
    """
    text = date_text.strip().replace("\u2013", "-").replace("\u2014", "-")

    pattern = (
        r"([A-Za-z]+)\s+(\d{1,2})"
        r"\s*-\s*"
        r"(?:([A-Za-z]+)\s+)?(\d{1,2})"
    )
    match = re.search(pattern, text)

    if match:
        start_month_text, start_day, end_month_text, end_day = match.groups()

        start_month = MONTHS.get(start_month_text.lower())
        end_month = MONTHS.get(
            (end_month_text or start_month_text).lower()
        )

        if not start_month or not end_month:
            return []

        start = date(year, start_month, int(start_day))
        end_year = year

        if end_month < start_month:
            end_year += 1

        end = date(end_year, end_month, int(end_day))

        if end < start or (end - start).days > 14:
            return []

        result = []
        current = start
        while current <= end:
            result.append(current)
            current += timedelta(days=1)

        return result

    # Also support a single-day listing, e.g. "Jun 21".
    single = re.fullmatch(
        r"([A-Za-z]+)\s+(\d{1,2})",
        text,
    )
    if single:
        month = MONTHS.get(single.group(1).lower())
        if month:
            return [date(year, month, int(single.group(2)))]

    return []


def year_from_listing(link, date_text):
    """
    Prefer the year in the event slug, such as montreal-2027.
    If the slug has no year, infer the next occurrence from the
    displayed month/day range.
    """
    slug = urlparse(link).path.rstrip("/").split("/")[-1]
    match = re.search(r"((?:19|20)\d{2})$", slug)

    if match:
        return int(match.group(1))

    today = datetime.now(MONTREAL_TZ).date()

    for year in (today.year, today.year + 1, today.year + 2):
        dates = parse_morsefest_dates(date_text, year)
        if dates and dates[-1] >= today:
            return year

    return today.year


def parse_morsefest_html(html):
    soup = BeautifulSoup(html, "html.parser")
    events = []

    # Restrict parsing to event links on the listing page.
    for card in soup.select('a[data-attr="event-link"]'):
        heading = card.find(["h1", "h2", "h3"])
        if not heading:
            continue

        city = heading.get_text(" ", strip=True).casefold()
        if city != "montreal":
            continue

        href = card.get("href")
        if not href:
            continue

        url = urljoin(BASE_URL, href)

        # The date is displayed in the first span in the card.
        date_el = card.find("span")
        if not date_el:
            continue

        date_text = date_el.get_text(" ", strip=True)
        year = year_from_listing(url, date_text)
        dates = parse_morsefest_dates(date_text, year)

        if not dates:
            print(f"Could not parse Morsefest dates: {date_text!r}")
            continue

        # Example:
        # Théâtre Paradoxe, Montreal, QC · 7:00 PM EDT
        detail = card.find("p")
        detail_text = detail.get_text(" ", strip=True) if detail else ""

        venue = (
            re.split(r"\s*[·•]\s*", detail_text, maxsplit=1)[0].strip()
            if detail_text
            else "Théâtre Paradoxe, Montreal, QC"
        )

        events.append({
            "slug": urlparse(url).path.rstrip("/").split("/")[-1],
            "url": url,
            "venue": venue,
            "dates": dates,
        })

    return events


def build_event_morsefest(events):
    cal = Calendar()

    for event in events:
        for event_date in event["dates"]:
            local_start = datetime(
                event_date.year,
                event_date.month,
                event_date.day,
                19,
                0,
                tzinfo=MONTREAL_TZ,
            )
            local_end = local_start + timedelta(hours=3)

            utc_start = local_start.astimezone(UTC_TZ)
            utc_end = local_end.astimezone(UTC_TZ)

            uid = f"morsefest-{event['slug']}-{event_date.isoformat()}"

            vevent = (
                ICSEventBuilder()
                .uid(uid)
                .start(utc_start)
                .end(utc_end)
                .summary(f"🎵 | Morsefest Montreal")
                .location(event["venue"])
                .description(
                    f"Morsefest Montreal\n"
                    f"Tickets: {event['url']}"
                )
                .build()
            )

            cal.add_component(vevent)

    return cal
