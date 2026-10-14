"""Calendar connectors for iCloud CalDAV, classic Outlook COM, and Outlook ICS.

Credentials are loaded from local environment/.env and never written to the
tracker database. Outlook ICS is read-only; classic Outlook requires Windows.
"""
from __future__ import annotations

import hashlib
import os
import platform
from datetime import date, datetime, time, timedelta
from typing import Any
from zoneinfo import ZoneInfo

from dotenv import load_dotenv

from tracker_core import BASE_DIR, LONDON, change, load_data, now_local

load_dotenv(BASE_DIR / ".env")


def _dt(value: Any, all_day=False) -> datetime:
    if isinstance(value, datetime):
        if value.tzinfo is None:
            return value.replace(tzinfo=LONDON)
        return value.astimezone(LONDON)
    if isinstance(value, date):
        return datetime.combine(value, time.min, tzinfo=LONDON)
    raise ValueError(f"Unknown calendar date: {value!r}")


def _key(source: str, calendar: str, uid: str, start: datetime) -> str:
    seed = f"{source}|{calendar}|{uid}|{start.isoformat()}"
    return source.lower() + "-" + hashlib.sha256(seed.encode()).hexdigest()[:24]


def make_event(source: str, calendar: str, uid: str, title: str,
               start, end, location="", notes="", deadline=False) -> dict:
    all_day = isinstance(start, date) and not isinstance(start, datetime)
    a = _dt(start)
    b = _dt(end) if end else (a + timedelta(days=1 if all_day else 0, hours=0 if all_day else 1))
    return {"id": _key(source, calendar, uid, a), "source": source,
            "calendar_name": calendar, "title": str(title or "Untitled event"),
            "start": a.isoformat(), "end": b.isoformat(),
            "all_day": all_day, "location": str(location or ""),
            "notes": str(notes or ""), "deadline": bool(deadline) or
            "[Momentum deadline]" in str(notes or "") or any(
                word in str(title).lower() for word in ["deadline", "submission due", "assignment due"])}


def _get_icloud_client():
    from caldav import DAVClient
    username = os.getenv("ICLOUD_EMAIL", "").strip()
    password = os.getenv("ICLOUD_APP_PASSWORD", "").strip()
    if not username or not password:
        raise RuntimeError("Set ICLOUD_EMAIL and ICLOUD_APP_PASSWORD in your .env file")
    return DAVClient(url="https://caldav.icloud.com/", username=username, password=password)


def fetch_icloud(start_day: date, end_day: date) -> list[dict]:
    result = []
    with _get_icloud_client() as client:
        calendars = client.principal().calendars()
        for calendar in calendars:
            calendar_name = str(calendar.name or "iCloud")
            for event in calendar.search(start=start_day, end=end_day, event=True, expand=True):
                component = event.get_icalendar_component()
                if component is None:
                    continue
                begin = component.decoded("DTSTART")
                finish = component.decoded("DTEND") if component.get("DTEND") else None
                uid = str(component.get("UID") or getattr(event, "url", "unknown"))
                if component.get("RECURRENCE-ID"):
                    uid += "|" + str(component.get("RECURRENCE-ID"))
                result.append(make_event("iCloud", calendar_name, uid, component.get("SUMMARY"),
                                         begin, finish, component.get("LOCATION", ""),
                                         component.get("DESCRIPTION", "")))
    return result


def fetch_outlook_ics(start_day: date, end_day: date) -> list[dict]:
    import requests
    import icalendar
    import recurring_ical_events
    url = os.getenv("OUTLOOK_ICS_URL", "").strip()
    if not url:
        raise RuntimeError("Set OUTLOOK_ICS_URL in .env, or switch Outlook mode to Off")
    if not url.lower().startswith("https://"):
        raise RuntimeError("Outlook ICS URL must be HTTPS")
    response = requests.get(url, timeout=25)
    response.raise_for_status()
    cal = icalendar.Calendar.from_ical(response.content)
    expanded = recurring_ical_events.of(cal).between(start_day, end_day)
    events = []
    for component in expanded:
        if component.name != "VEVENT" or component.get("STATUS") == "CANCELLED":
            continue
        start = component.decoded("DTSTART")
        end = component.decoded("DTEND") if component.get("DTEND") else None
        uid = str(component.get("UID", "unknown"))
        if component.get("RECURRENCE-ID"):
            uid += "|" + str(component.get("RECURRENCE-ID"))
        events.append(make_event("Outlook", "University Outlook", uid,
                                 component.get("SUMMARY"), start, end,
                                 component.get("LOCATION", ""), component.get("DESCRIPTION", "")))
    return events


def fetch_outlook_classic(start_day: date, end_day: date) -> list[dict]:
    if platform.system() != "Windows":
        raise RuntimeError("Classic Outlook integration runs only on Windows")
    import pythoncom
    import win32com.client
    pythoncom.CoInitialize()
    try:
        outlook = win32com.client.Dispatch("Outlook.Application")
        folder = outlook.GetNamespace("MAPI").GetDefaultFolder(9)
        items = folder.Items
        items.Sort("[Start]")
        items.IncludeRecurrences = True
        start = datetime.combine(start_day, time.min)
        end = datetime.combine(end_day, time.min)
        date_fmt = "%m/%d/%Y %I:%M %p"
        filtered = items.Restrict(f"[Start] < '{end.strftime(date_fmt)}' AND [End] > '{start.strftime(date_fmt)}'")
        events = []
        for item in filtered:
            try:
                begin = _dt(item.Start)
                finish = _dt(item.End)
                events.append(make_event("Outlook", str(folder.Name),
                                         str(getattr(item, "GlobalAppointmentID", None) or item.EntryID),
                                         str(item.Subject or "Untitled event"), begin, finish,
                                         str(item.Location or ""), str(item.Body or "")))
            except Exception:
                continue  # Some Outlook items are not appointments.
        return events
    finally:
        pythoncom.CoUninitialize()


def create_icloud_event(title: str, start: datetime, end: datetime,
                         notes="", location="", calendar_name="") -> None:
    with _get_icloud_client() as client:
        calendars = client.principal().calendars()
        if not calendars:
            raise RuntimeError("No iCloud calendars found")
        cal = next((c for c in calendars if str(c.name) == calendar_name), calendars[0])
        # Let CalDAV generate a UID. A timezone-aware datetime handles DST.
        cal.add_event(dtstart=start, dtend=end, summary=title,
                      description=notes, location=location)


def create_outlook_classic_event(title: str, start: datetime, end: datetime,
                                 notes="", location="") -> None:
    if platform.system() != "Windows":
        raise RuntimeError("Classic Outlook integration runs only on Windows")
    import pythoncom
    import win32com.client
    pythoncom.CoInitialize()
    try:
        outlook = win32com.client.Dispatch("Outlook.Application")
        item = outlook.CreateItem(1)  # Outlook appointment
        item.Subject = title
        item.Start = start.astimezone(LONDON).replace(tzinfo=None)
        item.End = end.astimezone(LONDON).replace(tzinfo=None)
        item.Location = location
        item.Body = notes
        item.ReminderSet = True
        item.ReminderMinutesBeforeStart = 15
        item.Save()
    finally:
        pythoncom.CoUninitialize()


def sync_calendars(force=False) -> dict:
    """Refresh configured sources; retain last-known events on source errors."""
    current = load_data()
    mode = current["settings"].get("outlook_mode", "Off")
    last = current["calendar_sync"].get("last_attempt")
    interval = max(2, int(current["settings"].get("sync_interval_minutes", 15)))
    if not force and last:
        try:
            if (now_local() - datetime.fromisoformat(last)).total_seconds() < interval * 60:
                return current["calendar_sync"]
        except (ValueError, TypeError):
            pass
    end = date.today() + timedelta(days=60)
    begin = date.today() - timedelta(days=2)
    results = {}
    errors = {}
    if os.getenv("ICLOUD_EMAIL") and os.getenv("ICLOUD_APP_PASSWORD"):
        try:
            results["iCloud"] = fetch_icloud(begin, end)
        except Exception as exc:
            errors["iCloud"] = str(exc)
    if mode in ("Classic Outlook", "ICS link"):
        try:
            results["Outlook"] = (fetch_outlook_classic(begin, end) if mode == "Classic Outlook"
                                  else fetch_outlook_ics(begin, end))
        except Exception as exc:
            errors["Outlook"] = str(exc)
    stamp = now_local().isoformat()
    def update(data):
        # For disabled sources remove stale events; for failures retain the cache.
        configured = set(results) | set(errors)
        if not (os.getenv("ICLOUD_EMAIL") and os.getenv("ICLOUD_APP_PASSWORD")):
            data["calendar_cache"] = [e for e in data["calendar_cache"] if e.get("source") != "iCloud"]
        if mode == "Off":
            data["calendar_cache"] = [e for e in data["calendar_cache"] if e.get("source") != "Outlook"]
        for source, events in results.items():
            data["calendar_cache"] = [e for e in data["calendar_cache"] if e.get("source") != source] + events
        data["calendar_sync"] = {"last_attempt": stamp, "last_success": stamp if results else data["calendar_sync"].get("last_success"),
                                 "counts": {s: len(ev) for s, ev in results.items()}, "errors": errors}
    change(update)
    return {"last_attempt": stamp, "counts": {s: len(ev) for s, ev in results.items()}, "errors": errors}
