import os
import re
from datetime import datetime
from zoneinfo import ZoneInfo

import requests

TZ = ZoneInfo("America/Toronto")
ISSUE_TITLE = "Concert tickets"
ISSUE_LABEL = "tickets"
BOUGHT = "TICKET BOUGHT"

LINE_RE = re.compile(
    r"^- \[(?P<box>[ xX])\] .*<!-- (?P<date>\d{4}-\d{2}-\d{2})\|(?P<key>.+?) -->\s*$"
)


def local_date(ev):
  dt = ev.decoded("dtstart")
  if isinstance(dt, datetime):
    return (dt.astimezone(TZ) if dt.tzinfo else dt).date()
  return dt


def key(ev):
  return str(ev.get("UID")).replace("--", "-").strip()


def _api():
  repo, token = os.environ.get("GITHUB_REPOSITORY"), os.environ.get("GITHUB_TOKEN")
  if not (repo and token):
    return None, None
  return (
      f"https://api.github.com/repos/{repo}",
      {"Authorization": f"Bearer {token}", "Accept": "application/vnd.github+json"},
  )


def _find_issue(base, headers):
  r = requests.get(
      f"{base}/issues",
      params={"labels": ISSUE_LABEL, "state": "open", "per_page": 1},
      headers=headers,
      timeout=15,
  )
  r.raise_for_status()
  return r.json()[0] if r.json() else None


def load_state():
  """{key: (date, original_line)} for every ticked box."""
  base, headers = _api()
  if not base:
    return {}
  issue = _find_issue(base, headers)
  state = {}
  for line in ((issue or {}).get("body") or "").splitlines():
    m = LINE_RE.match(line)
    if m and m["box"] in "xX":
      state[m["key"]] = (datetime.strptime(m["date"], "%Y-%m-%d").date(), line)
  return state


def mark_events(events, state):
  """Prepend the BOUGHT marker to the DESCRIPTION of ticked events."""
  for ev in events:
    if key(ev) not in state:
      continue
    desc = str(ev.get("DESCRIPTION", ""))
    if not desc.startswith(BOUGHT):
      ev["DESCRIPTION"] = f"{BOUGHT}\n\n{desc}".strip()


def sync_issue(entries, state):
  """entries: list of (event, city). Rebuilds the checklist, keeping ticks."""
  base, headers = _api()
  if not base:
    return
  today = datetime.now(TZ).date()
  upcoming = sorted(
      ((local_date(ev), ev, city) for ev, city in entries if local_date(ev) >= today),
      key=lambda x: (x[0], str(x[1].get("SUMMARY"))),
  )

  lines = ["Tick a box when you buy a ticket. The calendar updates on the next run.", ""]
  month, seen = None, set()
  for d, ev, city in upcoming:
    if (d.year, d.month) != month:
      month = (d.year, d.month)
      lines += ["", f"### {d:%B %Y}"]
    k = key(ev)
    seen.add(k)
    box = "x" if k in state else " "
    venue = str(ev.get("LOCATION", "")).split(",")[0].strip()
    lines.append(
        f"- [{box}] **{d:%a %b %d}** · {ev.get('SUMMARY')} · {venue} ({city})"
        f" <!-- {d.isoformat()}|{k} -->"
    )

  # Keep ticks for upcoming events that vanished from the feeds (e.g. a failed scrape)
  carried = [line for k, (d, line) in state.items() if k not in seen and d >= today]
  if carried:
    lines += ["", "### Not in the feeds right now (kept)"] + carried

  body = "\n".join(lines)[:65000]
  issue = _find_issue(base, headers)
  if issue:
    if issue["body"] != body:
      requests.patch(f"{base}/issues/{issue['number']}", json={"body": body},
                     headers=headers, timeout=15)
  else:
    requests.post(f"{base}/issues",
                  json={"title": ISSUE_TITLE, "body": body, "labels": [ISSUE_LABEL]},
                  headers=headers, timeout=15)
