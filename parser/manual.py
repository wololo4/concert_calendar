from datetime import datetime, timedelta
from icalendar import Calendar
from utils.ics import ICSEventBuilder
import re
from zoneinfo import ZoneInfo

UTC_TZ = ZoneInfo("UTC")
DEFAULT_TZ = "America/Toronto"
DEFAULT_TIME = "19:00"


def build_event_manual(events):
  cal = Calendar()
  now = datetime.now(UTC_TZ)
  for ev in events:
    try:
      title, day = str(ev["title"]), str(ev["date"])[:10]
      time_str = ev.get("time", DEFAULT_TIME)
      if isinstance(time_str, int):
        # YAML reads an unquoted 19:00 as minutes (1140)
        time_str = f"{time_str // 60}:{time_str % 60:02d}"
      hour, minute = map(int, str(time_str).split(":"))
      local_dt = datetime.fromisoformat(day).replace(
          hour=hour,
          minute=minute,
          tzinfo=ZoneInfo(ev.get("timezone", DEFAULT_TZ)),
      )
    except Exception as e:
      print(f"⚠️ manual: skipped {ev!r} ({type(e).__name__}: {e})")
      continue

    utc_dt = local_dt.astimezone(UTC_TZ)
    utc_end = utc_dt + timedelta(hours=float(ev.get("hours", 3)))
    if utc_end < now:
      continue  # event is over: it leaves the calendar on its own

    slug = re.sub(r"\W+", "", title.lower())
    description = f"Artists: {title}"
    if ev.get("url"):
      description = f"Tickets: {ev['url']}\n{description}"

    vevent = (
        ICSEventBuilder()
        .uid(f"manual{slug}{day.replace('-', '')}")
        .start(utc_dt)
        .end(utc_end)
        .summary(f"🎵 | {title}")
        .location(str(ev.get("venue", "")))
        .description(description)
        .build()
    )
    cal.add_component(vevent)
  return cal
