"""Local, JSON-in-a-.txt-file persistence and calculations for Momentum.

No cloud credentials are stored here. Mutations are locked and written atomically,
so the Streamlit interface and background reminder process can safely share data.
"""
from __future__ import annotations

import copy
import json
import os
import shutil
import tempfile
import uuid
from datetime import date, datetime, time, timedelta
from pathlib import Path
from typing import Callable
from zoneinfo import ZoneInfo

from filelock import FileLock

BASE_DIR = Path(__file__).resolve().parent
DATA_PATH = Path(os.getenv("MOMENTUM_DATA_FILE", str(BASE_DIR / "tracker_data.txt")))
LONDON = ZoneInfo("Europe/London")


def now_local() -> datetime:
    return datetime.now(LONDON)


def default_data() -> dict:
    return {
        "version": 3,
        "tasks": [],
        "habits": [],
        "habit_logs": {},
        "focus_logs": [],
        "daily_reviews": {},
        "screen_time_logs": {},
        "local_events": [],
        "event_checks": {},
        "calendar_cache": [],
        "calendar_sync": {},
        "notified": {},
        "settings": {
            "appearance": "Dark",
            "outlook_mode": "Off",
            "alerts_enabled": True,
            "alert_minutes": [60, 15],
            "sync_interval_minutes": 15,
        },
    }


def _as_task(item, from_older_version: bool = False) -> dict | None:
    if isinstance(item, str):
        item = {"title": item}
    if not isinstance(item, dict):
        return None
    title = item.get("title") or item.get("text") or item.get("task")
    if not title:
        return None
    due = str(item.get("due_date") or item.get("date") or "")[:10] or None
    plan = item.get("planned_date")
    if from_older_version and "planned_date" not in item:
        plan = due  # Preserve where tasks appeared in the old daily checklist.
    plan = str(plan)[:10] if plan else None
    try:
        minutes = max(0, min(1440, int(item.get("minutes", 0 if from_older_version else 30))))
    except (TypeError, ValueError):
        minutes = 0
    return {
        **item,
        "id": str(item.get("id") or uuid.uuid4().hex),
        "title": str(title),
        "due_date": due,  # Optional deadline; not a calendar appointment.
        "due_time": (str(item.get("due_time") or "17:00")[:5] if due else None),
        "planned_date": plan,  # Optional day to display in Daily Planner.
        "minutes": minutes,  # Credited to the linked habit once completed.
        "habit_id": item.get("habit_id") or None,
        "priority": str(item.get("priority") or "Medium"),
        "category": str(item.get("category") or "General"),
        "notes": str(item.get("notes") or ""),
        "done": bool(item.get("done", item.get("completed", False))),
        "created_at": str(item.get("created_at") or now_local().isoformat()),
        "completed_at": item.get("completed_at"),
    }


def normalise(raw: dict) -> dict:
    """Keep all old keys, and make pre-v2 habit/to-do records usable where possible."""
    if not isinstance(raw, dict):
        raise ValueError("tracker_data.txt must contain a JSON object")
    data = default_data()
    data.update(raw)
    data["version"] = 3
    original_tasks = raw.get("tasks") or raw.get("todos") or raw.get("to_dos") or raw.get("to_do_list") or []
    if isinstance(original_tasks, dict):
        original_tasks = list(original_tasks.values())
    if not isinstance(original_tasks, list):
        original_tasks = []
    data["tasks"] = [t for item in original_tasks
                     if (t := _as_task(item, from_older_version=int(raw.get("version", 1)) < 3)) is not None]
    original_habits = raw.get("habits") or []
    if isinstance(original_habits, dict):
        original_habits = [{"title": k, **(v if isinstance(v, dict) else {"target_minutes": v if isinstance(v, int) else 30})}
                           for k, v in original_habits.items()]
    if not isinstance(original_habits, list):
        original_habits = []
    habits = []
    for h in original_habits:
        if isinstance(h, str):
            h = {"title": h}
        if isinstance(h, dict) and (h.get("title") or h.get("name")):
            habits.append({**h, "id": str(h.get("id") or uuid.uuid4().hex),
                           "title": str(h.get("title") or h.get("name")),
                           "target_minutes": max(1, int(h.get("target_minutes") or 30)),
                           "category": h.get("category", "General")})
    data["habits"] = habits
    for key in ["habit_logs", "daily_reviews", "screen_time_logs", "event_checks", "notified", "calendar_sync", "settings"]:
        if not isinstance(data.get(key), dict):
            data[key] = copy.deepcopy(default_data()[key])
    for key in ["focus_logs", "calendar_cache", "local_events"]:
        if not isinstance(data.get(key), list):
            data[key] = []
    data["settings"] = {**default_data()["settings"], **data["settings"]}
    return data


def _read_unlocked() -> dict:
    if not DATA_PATH.exists():
        return default_data()
    try:
        raw = json.loads(DATA_PATH.read_text(encoding="utf-8"))
    except (ValueError, UnicodeError) as exc:
        raise ValueError(f"Could not read {DATA_PATH.name}. Original file is untouched: {exc}") from exc
    return normalise(raw)


def load_data() -> dict:
    # Files are replaced atomically: reading never sees half-written JSON.
    return _read_unlocked()


def _atomic_write(data: dict) -> None:
    DATA_PATH.parent.mkdir(parents=True, exist_ok=True)
    fd, temp_path = tempfile.mkstemp(prefix=".momentum-", suffix=".tmp", dir=DATA_PATH.parent)
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as file:
            json.dump(data, file, ensure_ascii=False, indent=2, default=str)
            file.flush()
            os.fsync(file.fileno())
        os.replace(temp_path, DATA_PATH)
    finally:
        if os.path.exists(temp_path):
            os.remove(temp_path)


def change(mutator: Callable[[dict], None]) -> dict:
    with FileLock(str(DATA_PATH) + ".lock", timeout=15):
        data = _read_unlocked()
        # Keep the exact original data as a safety net before a version upgrade.
        if DATA_PATH.exists():
            try:
                old_raw = json.loads(DATA_PATH.read_text(encoding="utf-8"))
                if int(old_raw.get("version", 1)) < 3:
                    backup = DATA_PATH.with_name("tracker_data_before_v3.backup.txt")
                    if not backup.exists():
                        shutil.copy2(DATA_PATH, backup)
            except (ValueError, AttributeError, TypeError):
                pass
        mutator(data)
        _atomic_write(data)
        return data


def add_task(title: str, due_date: str | None = None, due_time: str | None = None,
             priority="Medium", category="General", notes="", *, minutes=30,
             habit_id: str | None = None, planned_date: str | None = None,
             new_habit: str = "", new_habit_goal: int = 30) -> str:
    """Create an unscheduled to-do (optionally planned or with a deadline).

    New habits and the to-do are created in one atomic transaction.
    """
    if not title.strip():
        raise ValueError("The to-do must have a title")
    minutes = int(minutes)
    if not 0 <= minutes <= 1440:
        raise ValueError("Minutes must be between 0 and 1440")
    task_id = uuid.uuid4().hex

    def update(d):
        nonlocal habit_id
        if new_habit.strip():
            existing = next((h for h in d["habits"] if h["title"].casefold() == new_habit.strip().casefold()), None)
            if existing:
                habit_id = existing["id"]
            else:
                habit_id = uuid.uuid4().hex
                d["habits"].append({"id": habit_id, "title": new_habit.strip(),
                                    "target_minutes": max(1, int(new_habit_goal)), "category": category})
        if habit_id and not any(h["id"] == habit_id for h in d["habits"]):
            raise ValueError("Linked habit no longer exists")
        d["tasks"].append({"id": task_id, "title": title.strip(),
                           "due_date": due_date or None,
                           "due_time": (due_time or "17:00") if due_date else None,
                           "planned_date": planned_date or None,
                           "minutes": minutes, "habit_id": habit_id,
                           "priority": priority, "category": category,
                           "notes": notes.strip(), "done": False,
                           "completed_at": None, "created_at": now_local().isoformat()})
    change(update)
    return task_id


def set_task_done(task_id: str, done: bool) -> None:
    def update(d):
        for task in d["tasks"]:
            if task["id"] == task_id:
                if bool(task.get("done")) != bool(done):
                    task["done"] = bool(done)
                    task["completed_at"] = now_local().isoformat() if done else None
                return
    change(update)


def set_task_plan(task_id: str, planned_date: str | None) -> None:
    def update(d):
        for task in d["tasks"]:
            if task["id"] == task_id:
                task["planned_date"] = planned_date
                return
    change(update)


def delete_task(task_id: str) -> None:
    change(lambda d: d.update(tasks=[t for t in d["tasks"] if t["id"] != task_id]))


def set_event_checked(event_id: str, checked: bool) -> None:
    """Retained for backward compatibility; calendar events are no longer checkable."""
    change(lambda d: d["event_checks"].update({event_id: checked}))


def add_habit(title: str, target_minutes: int, category="General") -> str:
    habit_id = uuid.uuid4().hex
    change(lambda d: d["habits"].append({"id": habit_id, "title": title.strip(),
                                         "target_minutes": int(target_minutes), "category": category}))
    return habit_id


def delete_habit(habit_id: str) -> None:
    def update(d):
        d["habits"] = [h for h in d["habits"] if h["id"] != habit_id]
        for task in d["tasks"]:
            if task.get("habit_id") == habit_id:
                task["habit_id"] = None
    change(update)


def log_habit(habit_id: str, minutes: int, when: str) -> None:
    def update(d):
        day = d["habit_logs"].setdefault(when, {})
        day[habit_id] = max(0, int(day.get(habit_id, 0)) + minutes)
    change(update)


def task_completion_day(task: dict) -> str | None:
    if not task.get("done"):
        return None
    completed_at = task.get("completed_at")
    if completed_at:
        try:
            stamp = datetime.fromisoformat(completed_at)
            return (stamp.astimezone(LONDON) if stamp.tzinfo else stamp).date().isoformat()
        except (TypeError, ValueError):
            pass
    return task.get("due_date") or task.get("planned_date")  # Older completed records.


def habit_minutes_for_day(data: dict, day: date | str) -> dict[str, int]:
    """Manual logs + completed task minutes, derived to avoid double counting.

    Unticking, deleting, or reassigning a to-do updates totals automatically.
    """
    ds = day.isoformat() if isinstance(day, date) else day
    result = {hid: max(0, int(mins)) for hid, mins in data["habit_logs"].get(ds, {}).items()}
    for task in data["tasks"]:
        hid = task.get("habit_id")
        if hid and task_completion_day(task) == ds:
            result[hid] = result.get(hid, 0) + max(0, int(task.get("minutes") or 0))
    return result


def save_screen_time(when: str, total_minutes: int, distracting_minutes: int = 0) -> None:
    """Manual iPhone Screen Time entry; no automatic Apple Screen Time access."""
    total, distracting = int(total_minutes), int(distracting_minutes)
    if not 0 <= distracting <= total <= 1440:
        raise ValueError("Screen Time values must be between 0 and 1440 minutes")
    change(lambda d: d["screen_time_logs"].update({when: {
        "total_minutes": total, "distracting_minutes": distracting}}))


def save_day_note(when: str, note: str) -> None:
    def update(d):
        previous = d["daily_reviews"].get(when, {})
        d["daily_reviews"][when] = {**previous, "note": note.strip()}
    change(update)


def add_focus(minutes: int, category: str, when: str, notes: str = "") -> None:
    change(lambda d: d["focus_logs"].append({"id": uuid.uuid4().hex,
                                              "date": when, "minutes": int(minutes),
                                              "category": category, "notes": notes.strip()}))


def save_review(when: str, rating: int, note: str) -> None:
    change(lambda d: d["daily_reviews"].update({when: {"rating": int(rating), "note": note.strip()}}))


def add_local_event(title: str, start: datetime, end: datetime, location: str = "", deadline: bool = False) -> str:
    event_id = "local-" + uuid.uuid4().hex
    change(lambda d: d["local_events"].append({"id": event_id, "title": title.strip(),
                                               "start": start.isoformat(), "end": end.isoformat(),
                                               "source": "Local", "calendar_name": "Momentum",
                                               "all_day": False, "location": location.strip(),
                                               "deadline": deadline}))
    return event_id


def daily_agenda(data: dict, day: date) -> list[dict]:
    """Schedule and planned to-dos, distinguishable by kind (events never tickable)."""
    ds = day.isoformat()
    entries = []
    for task in data["tasks"]:
        if task.get("planned_date") == ds:
            entries.append({"kind": "task", "id": task["id"], "title": task["title"],
                            "time": "To-do", "source": task.get("category", "Task"),
                            "done": task.get("done", False), "minutes": task.get("minutes", 0),
                            "priority": task.get("priority", "Medium")})
    for event in data["calendar_cache"] + data["local_events"]:
        try:
            start = datetime.fromisoformat(event["start"])
            end = datetime.fromisoformat(event["end"])
            start = (start if start.tzinfo else start.replace(tzinfo=LONDON)).astimezone(LONDON)
            end = (end if end.tzinfo else end.replace(tzinfo=LONDON)).astimezone(LONDON)
            if start.date() > day or end.date() < day or (end.date() == day and end.time() == time.min and start.date() != day):
                continue
        except (KeyError, ValueError, TypeError):
            continue
        entries.append({"kind": "event", "id": event["id"], "title": event["title"],
                        "time": "All day" if event.get("all_day") else start.strftime("%H:%M"),
                        "source": event.get("source", "Calendar"),
                        "priority": "Deadline" if event.get("deadline") else "Event"})
    return sorted(entries, key=lambda x: (x["kind"] != "event", x["time"] == "All day", x["time"], x["title"].lower()))


def productivity_for_day(data: dict, day: date) -> dict:
    ds = day.isoformat()
    planned = [t for t in data["tasks"] if t.get("planned_date") == ds]
    completed = [t for t in data["tasks"] if task_completion_day(t) == ds]
    focus = sum(int(x.get("minutes", 0)) for x in data["focus_logs"] if x.get("date") == ds)
    habit_minutes = sum(habit_minutes_for_day(data, ds).values())
    return {"tasks": len(planned), "done": len(completed),
            "focus": focus, "habit_minutes": habit_minutes,
            "screen_time": (data.get("screen_time_logs", {}).get(ds) or {}).get("total_minutes")}


def _due_datetime(task: dict) -> datetime | None:
    try:
        return datetime.combine(date.fromisoformat(task["due_date"]),
                                time.fromisoformat(task.get("due_time") or "17:00"), tzinfo=LONDON)
    except (KeyError, TypeError, ValueError):
        return None


def pending_alerts(data: dict, now: datetime | None = None) -> list[dict]:
    """Return imminent deadlines/events not yet sent; caller reserves IDs before toast."""
    now = (now or now_local()).astimezone(LONDON)
    thresholds = sorted({int(v) for v in data["settings"].get("alert_minutes", [60, 15]) if int(v) > 0})
    alerts = []
    if not data["settings"].get("alerts_enabled", True):
        return alerts
    def consider(event_id, name, when, category):
        if not when:
            return
        mins = (when.astimezone(LONDON) - now).total_seconds() / 60
        matching = next((m for m in thresholds if 0 <= mins <= m), None)
        if matching is None:
            return
        key = f"{category}:{event_id}:{when.isoformat()}:{matching}"
        if key not in data["notified"]:
            alerts.append({"key": key, "title": name,
                           "message": f"{category} in {round(mins)} minutes · {when:%H:%M}",
                           "when": when})
    for task in data["tasks"]:
        if not task.get("done", False):
            consider(task["id"], task["title"], _due_datetime(task), "Task due")
    for event in data["calendar_cache"] + data["local_events"]:
        if event.get("all_day") and not event.get("deadline"):
            continue  # Ordinary all-day calendar entries aren't timed alerts.
        try:
            when = datetime.fromisoformat(event["start"])
            if when.tzinfo is None:
                when = when.replace(tzinfo=LONDON)
            if event.get("all_day") and event.get("deadline"):
                when = when.astimezone(LONDON).replace(hour=9, minute=0)
        except (KeyError, ValueError, TypeError):
            continue
        consider(event["id"], event["title"], when,
                 "Deadline" if event.get("deadline") else "Event")
    return alerts


def reserve_alert(key: str) -> bool:
    """Atomic de-duplication across the web interface and reminder agent."""
    reserved = False
    def update(d):
        nonlocal reserved
        if key not in d["notified"]:
            d["notified"][key] = now_local().isoformat()
            reserved = True
        # Keep notification history bounded.
        if len(d["notified"]) > 3000:
            old = sorted(d["notified"], key=lambda x: d["notified"][x])[:1000]
            for name in old:
                del d["notified"][name]
    change(update)
    return reserved
