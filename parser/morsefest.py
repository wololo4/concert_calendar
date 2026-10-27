
from bs4 import BeautifulSoup
from datetime import date, datetime, timedelta
from icalendar import Calendar
from urllib.parse import urljoin, urlparse
from utils.ics import ICSEventBuilder
from zoneinfo import ZoneInfo
import re

MONTREAL_TZ = ZoneInfo("America/Toronto")
UTC_TZ = ZoneInfo("UTC")

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
MONTHS.update({name[:3]: number for name, number in MONTHS.copy().items()})


def parse_morsefest_dates(date_text, year):
    """Parse date ranges such as 'Jun 21–22' or 'Jun 30–Jul 1'."""
    text = date_text.strip().replace("\u2013", "-").replace("\u2014", "-")

    match = re.fullmatch(
        r"([A-Za-z]+)\s+(\d{1,2})\s*-\s*"
        r"(?:([A-Za-z]+)\s+)?(\d{1,2})",
        text,
    )

    if match:
        start_month_text, start_day, end_month_text, end_day = match.groups()
        start_month = MONTHS.get(start_month_text.lower())
        end_month = MONTHS.get((end_month_text or start_month_text).lower())

        if not start_month or not end_month:
            return []

        try:
            start = date(year, start_month, int(start_day))
            end_year = year + (1 if end_month < start_month else 0)
            end = date(end_year, end_month, int(end_day))
        except ValueError:
            return []

        if end < start or (end - start).days > 14:
            return []

        return [
            start + timedelta(days=offset)
            for offset in range((end - start).days + 1)
        ]

    single = re.fullmatch(r"([A-Za-z]+)\s+(\d{1,2})", text)
    if single:
        month = MONTHS.get(single.group(1).lower())
        if month:
            try:
                return [date(year, month, int(single.group(2)))]
            except ValueError:
                return []

    return []


def year_from_listing(event_url, date_text):
    """Use the event slug's year, or find the next upcoming occurrence."""
    slug = urlparse(event_url).path.rstrip("/").split("/")[-1]
    match = re.search(r"((?:19|20)\d{2})$", slug)

    if match:
        return int(match.group(1))

    today = datetime.now(MONTREAL_TZ).date()

    for year in range(today.year, today.year + 6):
        dates = parse_morsefest_dates(date_text, year)
        if dates and dates[-1] >= today:
            return year

    return today.year


def parse_morsefest_html(html, listing_url):
    soup = BeautifulSoup(html, "html.parser")
    events = []

    for card in soup.select('a[data-attr="event-link"]'):
        heading = card.find(["h1", "h2", "h3"])
        if not heading or heading.get_text(" ", strip=True).casefold() != "montreal":
            continue

        href = card.get("href")
        date_el = card.find("span")
        if not href or not date_el:
            continue

        event_url = urljoin(listing_url, href)
        date_text = date_el.get_text(" ", strip=True)
        year = year_from_listing(event_url, date_text)
        dates = parse_morsefest_dates(date_text, year)

        if not dates:
            print(f"⚠️ Could not parse Morsefest dates: {date_text!r}")
            continue

        detail = card.find("p")
        detail_text = detail.get_text(" ", strip=True) if detail else ""

        venue = (
            re.split(r"\s*[·•]\s*", detail_text, maxsplit=1)[0].strip()
            if detail_text
            else "Théâtre Paradoxe, Montreal, QC"
        )

        slug = urlparse(event_url).path.rstrip("/").split("/")[-1]

        events.append({
            "slug": slug,
            "url": event_url,
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

            uid = (
                f"morsefest-{event['slug']}-"
                f"{event_date.isoformat()}"
            )

            vevent = (
                ICSEventBuilder()
                .uid(uid)
                .start(local_start.astimezone(UTC_TZ))
                .end(local_end.astimezone(UTC_TZ))
                .summary("🎵 | Morsefest Montreal")
                .location(event["venue"])
                .description(
                    f"Morsefest Montreal\nTickets: {event['url']}"
                )
                .build()
            )
            cal.add_component(vevent)

    return cal
