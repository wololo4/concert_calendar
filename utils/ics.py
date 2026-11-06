from datetime import timezone
from icalendar import Event


def to_rfc5545(dt):
    # Aware datetimes are converted to UTC before the "Z" is added.
    # Naive datetimes are written as-is (treated as UTC), as before.
    if dt.tzinfo is not None:
        dt = dt.astimezone(timezone.utc)
    return dt.strftime("%Y%m%dT%H%M%SZ")


class ICSEventBuilder:
    def __init__(self):
        self.event = Event()

    def uid(self, value):
        self.event["UID"] = value
        return self

    def start(self, dt):
        self.event["DTSTART"] = to_rfc5545(dt)
        return self

    def end(self, dt):
        self.event["DTEND"] = to_rfc5545(dt)
        return self

    def summary(self, text):
        self.event["SUMMARY"] = text
        return self

    def location(self, text):
        self.event["LOCATION"] = text
        return self

    def description(self, text):
        self.event["DESCRIPTION"] = text
        return self

    def build(self):
        # DTSTAMP is required by RFC 5545. Reusing DTSTART keeps it
        # deterministic, so the files don't change between runs.
        if "DTSTAMP" not in self.event and "DTSTART" in self.event:
            self.event["DTSTAMP"] = self.event["DTSTART"]
        return self.event
