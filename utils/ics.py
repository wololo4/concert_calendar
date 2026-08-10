from icalendar import Calendar, Event
from datetime import datetime

def to_rfc5545(dt):
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
        return self.event
