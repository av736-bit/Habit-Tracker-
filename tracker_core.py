"""Data persistence and input interpretation for the Momentum habit tracker."""

from __future__ import annotations

from copy import deepcopy
from datetime import date, datetime, timedelta
from pathlib import Path
import json
import os
import re
import tempfile
import uuid

DATA_FILE = Path(__file__).resolve().parent / "tracker_data.txt"
DEFAULT_HABITS = ["studying", "exercise", "reading"]


def fresh_data() -> dict:
    return {"version": 1, "habits": DEFAULT_HABITS.copy(), "days": {}, "todos": [], "events": []}


def load_data(path: Path = DATA_FILE) -> dict:
    """Load the .txt file; create it on first use, never silently erase corrupt data."""
    path = Path(path)
    if not path.exists():
        data = fresh_data()
        save_data(data, path)
        return data
    try:
        with path.open("r", encoding="utf-8") as handle:
            data = json.load(handle)
        if not isinstance(data, dict) or not all(
            isinstance(data.get(field), kind)
            for field, kind in (("habits", list), ("days", dict), ("todos", list), ("events", list))
        ):
            raise ValueError("Invalid tracker file format")
        return data
    except (ValueError, OSError) as exc:
        raise ValueError(
            f"Could not read {path.name}. Your existing file has NOT been overwritten: {exc}"
        ) from exc


def save_data(data: dict, path: Path = DATA_FILE) -> None:
    """Write human-readable JSON to a .txt file, replacing it atomically."""
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp_name = None
    try:
        with tempfile.NamedTemporaryFile(
            mode="w", encoding="utf-8", dir=path.parent,
            prefix=".tracker_", suffix=".tmp", delete=False
        ) as handle:
            tmp_name = handle.name
            json.dump(data, handle, indent=2, ensure_ascii=False)
            handle.write("\n")
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(tmp_name, path)
    finally:
        if tmp_name and os.path.exists(tmp_name):
            os.unlink(tmp_name)


def duration(minutes: int) -> str:
    hours, mins = divmod(minutes, 60)
    if hours and mins:
        return f"{hours}h {mins}m"
    return f"{hours}h" if hours else f"{mins}m"


def _find_todo(todos: list, phrase: str):
    needle = phrase.strip().casefold()
    exact = [t for t in todos if t["text"].casefold() == needle]
    if len(exact) == 1:
        return exact[0], None
    partial = [t for t in todos if needle and needle in t["text"].casefold()]
    if len(partial) == 1:
        return partial[0], None
    return None, "Multiple tasks match; please use the checkbox instead." if partial else "Task not found."


def apply_actions(data: dict, actions: list, *, today: date | None = None) -> tuple[dict, list[str], list[str]]:
    """Validate and apply user/AI-proposed actions; returns (new_data, messages, errors)."""
    now = datetime.now().astimezone()
    today = today or now.date()
    updated = deepcopy(data)
    messages, errors = [], []

    if not isinstance(actions, list):
        return updated, messages, ["Expected a list of actions."]

    for action in actions[:25]:
        if not isinstance(action, dict):
            errors.append("Skipped an invalid action.")
            continue
        kind = action.get("type")
        summary = None

        if kind == "log_habit":
            habit = str(action.get("habit", "")).strip().lower()
            raw_mins = action.get("minutes")
            try:
                mins = float(raw_mins)
                if not mins.is_integer() or not 1 <= mins <= 1440:
                    raise ValueError
                mins = int(mins)
            except (ValueError, TypeError, OverflowError):
                errors.append(f"Invalid duration for '{habit or 'habit'}' (use 1–1440 minutes).")
                continue
            if not habit or len(habit) > 50:
                errors.append("Habit name must be 1–50 characters.")
                continue
            day_value = str(action.get("date", today.isoformat()))
            try:
                day = date.fromisoformat(day_value)
                if day > today or day.year < 2000:
                    raise ValueError
            except ValueError:
                errors.append(f"Invalid date: {day_value}. Entries must be from 2000 through today.")
                continue
            if habit not in updated["habits"]:
                updated["habits"].append(habit)
            record = updated["days"].setdefault(day.isoformat(), {})
            record[habit] = record.get(habit, 0) + mins
            summary = f"Logged {duration(mins)} of {habit} for {day.isoformat()}."

        elif kind == "add_todo":
            task = str(action.get("text", "")).strip()
            if not task or len(task) > 250:
                errors.append("To-do must contain 1–250 characters.")
                continue
            if any(t["text"].casefold() == task.casefold() and not t["done"] for t in updated["todos"]):
                errors.append(f"Already on your list: {task}")
                continue
            updated["todos"].append({
                "id": uuid.uuid4().hex, "text": task, "done": False,
                "created_on": today.isoformat(), "completed_on": None
            })
            summary = f"Added to-do: {task}"

        elif kind in ("complete_todo", "reopen_todo", "delete_todo"):
            selected = next((t for t in updated["todos"] if t["id"] == action.get("id")), None)
            reason = None
            if selected is None:
                selected, reason = _find_todo(updated["todos"], str(action.get("text", "")))
            if selected is None:
                errors.append(reason or "Task not found.")
                continue
            if kind == "delete_todo":
                updated["todos"].remove(selected)
                summary = f"Deleted to-do: {selected['text']}"
            else:
                done = kind == "complete_todo"
                if selected["done"] == done:
                    errors.append(f"Task already {'complete' if done else 'open'}: {selected['text']}")
                    continue
                selected["done"] = done
                selected["completed_on"] = today.isoformat() if done else None
                summary = ("Completed" if done else "Reopened") + f" to-do: {selected['text']}"

        elif kind == "add_habit":
            habit = str(action.get("habit", "")).strip().lower()
            if not 1 <= len(habit) <= 50:
                errors.append("Habit name must be 1–50 characters.")
                continue
            if habit in updated["habits"]:
                errors.append("Habit already exists.")
                continue
            updated["habits"].append(habit)
            summary = f"Added habit: {habit}"

        else:
            errors.append(f"Unsupported action: {kind}")
            continue

        if summary:
            messages.append(summary)
            updated["events"].append({"time": now.isoformat(timespec="seconds"), "summary": summary})

    return updated, messages, errors


VERBS = {
    "study": "studying", "studied": "studying", "studying": "studying",
    "read": "reading", "reading": "reading",
    "exercise": "exercise", "exercised": "exercise", "exercising": "exercise",
    "worked out": "exercise", "working out": "exercise",
    "code": "coding", "coded": "coding", "coding": "coding",
}
UNIT = r"hours?|hrs?|h|minutes?|mins?|m"
VERB = "|".join(sorted((re.escape(v) for v in VERBS), key=len, reverse=True))


def _minutes(amount: str, unit: str) -> int:
    return round(float(amount) * (60 if unit.lower().startswith(("h",)) else 1))


def parse_locally(message: str, *, today: date | None = None) -> list[dict]:
    """Offline parser for common log/to-do commands; AI covers more varied sentences."""
    today = today or date.today()
    parts = re.split(
        r"\s*(?:;|,|(?<=[.!?])\s+|\band\b(?=\s+(?:i\s+)?(?:studied|study|reading|read|exercised|exercise|coded|coding|add|complete|mark|remove|delete|remind)\b))\s*",
        message, flags=re.I
    )
    actions = []
    for clause in parts:
        clause = clause.strip().rstrip(".!")
        if not clause:
            continue
        low = clause.lower()
        day = (today - timedelta(days=1)).isoformat() if re.search(r"\byesterday\b", low) else today.isoformat()

        task_patterns = (
            ("add_todo", r"^(?:please\s+)?(?:add|remind me to)\s+(.+)$"),
            ("complete_todo", r"^(?:please\s+)?(?:complete|finish|mark)\s+(.+)$"),
            ("delete_todo", r"^(?:please\s+)?(?:remove|delete)\s+(.+)$"),
        )
        matched_task = False
        for kind, pattern in task_patterns:
            match = re.search(pattern, clause, re.I)
            if match:
                task = re.sub(r"\s+(?:to|from)\s+(?:my\s+)?(?:to[- ]?do\s+)?list\s*$", "", match.group(1), flags=re.I)
                task = re.sub(r"\s+as\s+done\s*$", "", task, flags=re.I).strip()
                if task:
                    actions.append({"type": kind, "text": task})
                matched_task = True
                break
        if matched_task:
            continue

        # An intention to do something later is not time already completed.
        if re.search(r"\b(?:will|plan to|going to|want to|would like to|need to|have to|intend to)\s+", low):
            continue

        # Example: "I studied maths for 1.5 hours" or "read 30 mins"
        match = re.search(
            rf"\b(?P<verb>{VERB})\b(?:\s+\w+){{0,4}}?\s+(?:for\s+)?(?P<qty>\d+(?:\.\d+)?)\s*(?P<unit>{UNIT})\b",
            low, re.I
        )
        if not match:
            # Example: "2 hours of studying"
            match = re.search(
                rf"\b(?P<qty>\d+(?:\.\d+)?)\s*(?P<unit>{UNIT})\s+(?:of\s+)?(?P<verb>{VERB})\b",
                low, re.I
            )
        if match:
            mins = _minutes(match.group("qty"), match.group("unit"))
            trailing = low[match.end():]
            if match.group("unit").startswith(("h",)):
                extra = re.match(rf"\s*(?:and\s+)?(\d+)\s*(minutes?|mins?|m)\b", trailing)
                if extra:
                    mins += int(extra.group(1))
            if mins:
                actions.append({
                    "type": "log_habit", "habit": VERBS[match.group("verb")],
                    "minutes": mins, "date": day
                })
    return actions


def interpret_message(message: str, data: dict, *, today: date | None = None):
    """Return (actions, source, note). AI is optional and uses ANTHROPIC_API_KEY."""
    key = os.getenv("ANTHROPIC_API_KEY", "").strip()
    today = today or date.today()
    if not key:
        return parse_locally(message, today=today), "offline", "Offline parser (AI key not configured)."

    system = (
        "You interpret habit tracker updates. Return ONE JSON object only, containing "
        "an 'actions' array, never explanatory text. Use only these action types: "
        "log_habit {type, habit, minutes, date}, add_todo {type, text}, "
        "complete_todo {type, text}, reopen_todo {type, text}, delete_todo {type, text}, "
        "add_habit {type, habit}. 'minutes' must be a positive integer (convert hours "
        "to minutes). For logging use ISO date YYYY-MM-DD, default to today. "
        "If the user describes a plan or intent (e.g. 'I will study'), do not log "
        "completed time: add a to-do only if requested. 'I studied' means completed. "
        "Never infer hours that weren't stated. Keep to-do text concise. "
        "Do not invent actions, and return an empty actions array for questions. "
        "When uncertain, return no action rather than guess. "
    )
    content = json.dumps({
        "today": today.isoformat(), "habits": data["habits"],
        "open_todos": [t["text"] for t in data["todos"] if not t["done"]],
        "message": message
    })
    try:
        import anthropic
        client = anthropic.Anthropic(api_key=key, timeout=15.0, max_retries=1)
        response = client.messages.create(
            model=os.getenv("ANTHROPIC_MODEL", "claude-sonnet-4-6"),
            max_tokens=600,
            temperature=0,
            system=system,
            messages=[{"role": "user", "content": content}]
        )
        raw = "".join(block.text for block in response.content if block.type == "text").strip()
        parsed = json.loads(raw)
        if not isinstance(parsed, dict) or not isinstance(parsed.get("actions"), list):
            raise ValueError("AI returned an unexpected format")
        return parsed["actions"], "AI", "Interpreted with Claude."
    except Exception as exc:
        # Failure cannot corrupt saved data; show a minimal error and try locally.
        actions = parse_locally(message, today=today)
        return actions, "offline fallback", f"AI unavailable ({type(exc).__name__}); used offline parser."
