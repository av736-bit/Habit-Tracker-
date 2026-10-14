"""Momentum v3 — calendar as read-only schedule, separate to-do and habit tracker.

Replace your existing app.py and tracker_core.py with the v3 files.
All user data remains in the existing tracker_data.txt. Run: streamlit run app.py
"""
from __future__ import annotations

import html
import os
from datetime import date, datetime, time, timedelta

import pandas as pd
import streamlit as st

import calendar_sync as calendars
import tracker_core as core
from reminder_agent import check_once
from ui_styles import apply_styles

st.set_page_config(page_title="Momentum · Planner", page_icon="📅", layout="wide", initial_sidebar_state="expanded")

CATEGORIES = ["Study", "Coding", "Career", "Exercise", "Personal", "General"]
PRIORITIES = ["Low", "Medium", "High"]
NAV = ["Overview", "Daily planner", "To-do list", "Calendar", "Habits & focus", "Insights", "Settings"]


def header(title: str, subtitle: str):
    st.markdown('<div class="momentum-eyebrow">PERSONAL PRODUCTIVITY</div>', unsafe_allow_html=True)
    st.title(title)
    st.markdown(f'<div class="momentum-subtitle">{html.escape(subtitle)}</div>', unsafe_allow_html=True)


def small_card(title: str, meta: str):
    st.markdown(f'<div class="momentum-card"><div class="title">{html.escape(str(title))}</div>'
                f'<div class="meta">{html.escape(str(meta))}</div></div>', unsafe_allow_html=True)


def format_event_time(value: str) -> str:
    try:
        d = datetime.fromisoformat(value)
        d = d if d.tzinfo else d.replace(tzinfo=core.LONDON)
        return d.astimezone(core.LONDON).strftime("%a %d %b · %H:%M")
    except (TypeError, ValueError):
        return "Date unavailable"


def near_deadlines(data: dict, limit=8) -> list[tuple[datetime, str, str]]:
    values = []
    for task in data["tasks"]:
        if not task.get("done"):
            when = core._due_datetime(task)
            if when:
                values.append((when, task["title"], "To-do deadline"))
    for event in data["calendar_cache"] + data["local_events"]:
        if not event.get("deadline"):
            continue
        try:
            when = datetime.fromisoformat(event["start"])
            when = (when if when.tzinfo else when.replace(tzinfo=core.LONDON)).astimezone(core.LONDON)
            values.append((when, event["title"], f"{event.get('source', 'Calendar')} deadline"))
        except (KeyError, ValueError, TypeError):
            continue
    values.sort(key=lambda item: item[0])
    now = core.now_local()
    return [item for item in values if item[0] >= now - timedelta(days=1)][:limit]


def task_meta(task: dict, habits: dict[str, str]) -> str:
    bits = [task.get("priority", "Medium"), task.get("category", "General")]
    if task.get("minutes"):
        bits.append(f"{task['minutes']} min")
    if task.get("habit_id") in habits:
        bits.append(f"Habit: {habits[task['habit_id']]}")
    if task.get("due_date"):
        bits.append(f"Due {task['due_date']} {task.get('due_time') or ''}".strip())
    if task.get("planned_date"):
        bits.append(f"Planned {task['planned_date']}")
    return " · ".join(bits)


def task_row(task: dict, data: dict, prefix: str, *, selected_day: date | None = None):
    habits = {h["id"]: h["title"] for h in data["habits"]}
    a, b, c = st.columns([0.74, 0.15, 0.11], vertical_alignment="center")
    with a:
        current = bool(task.get("done"))
        checked = st.checkbox(task["title"], value=current, key=f"{prefix}-done-{task['id']}")
        if checked != current:
            core.set_task_done(task["id"], checked)
            st.rerun()
        st.caption(task_meta(task, habits))
    with b:
        if selected_day and not task.get("done"):
            is_planned = task.get("planned_date") == selected_day.isoformat()
            label = "Unplan" if is_planned else "Plan"
            if st.button(label, key=f"{prefix}-plan-{task['id']}", help="Place this to-do in the selected day's planner"):
                core.set_task_plan(task["id"], None if is_planned else selected_day.isoformat())
                st.rerun()
    with c:
        if st.button("×", key=f"{prefix}-delete-{task['id']}", help="Delete to-do"):
            core.delete_task(task["id"])
            st.rerun()


def event_card(event: dict):
    """Events reflect time passing; unlike to-dos, they have no checkbox."""
    try:
        now = core.now_local()
        start = datetime.fromisoformat(event["start"])
        end = datetime.fromisoformat(event["end"])
        start = (start if start.tzinfo else start.replace(tzinfo=core.LONDON)).astimezone(core.LONDON)
        end = (end if end.tzinfo else end.replace(tzinfo=core.LONDON)).astimezone(core.LONDON)
        state = "Finished" if end <= now else "In progress" if start <= now else "Upcoming"
        time_label = "All day" if event.get("all_day") else f"{start:%H:%M}–{end:%H:%M}"
        details = f"{time_label} · {event.get('source', 'Calendar')} · {state}"
        if event.get("deadline"):
            details += " · Deadline"
        small_card(event.get("title", "Untitled"), details)
    except (KeyError, ValueError, TypeError):
        small_card(event.get("title", "Untitled"), "Calendar event")


def events_on_day(data: dict, day: date) -> list[dict]:
    """Lookup full event records associated with the read-only daily agenda."""
    ids = {e["id"] for e in core.daily_agenda(data, day) if e["kind"] == "event"}
    events = [e for e in data["calendar_cache"] + data["local_events"] if e.get("id") in ids]
    return sorted(events, key=lambda e: (not e.get("all_day"), e.get("start", "")))


def calendar_day_section(data: dict, day: date):
    events = events_on_day(data, day)
    if not events:
        st.caption("No calendar events for this day.")
    for event in events:
        event_card(event)


def add_todo_form(data: dict, key: str, *, default_planned: date | None = None):
    """Creating a to-do never creates a calendar event."""
    habits = data["habits"]
    labels = ["No habit"] + [f"{h['title']} [{h['id'][:6]}]" for h in habits]
    with st.form(f"add-todo-{key}", clear_on_submit=True):
        title = st.text_input("To-do", placeholder="e.g. Complete structures problem sheet", key=f"{key}-title")
        c1, c2 = st.columns(2)
        with c1:
            priority = st.selectbox("Priority", PRIORITIES, index=1, key=f"{key}-priority")
            duration = st.number_input("Minutes to credit when completed", min_value=0, max_value=1440,
                                       value=30, step=5, key=f"{key}-duration")
            set_plan = st.checkbox("Show in daily planner", value=default_planned is not None, key=f"{key}-set-plan")
            plan_date = st.date_input("Planner day (only used if ticked)", value=default_planned or core.now_local().date(),
                                      key=f"{key}-plan-date")
        with c2:
            category = st.selectbox("Category", CATEGORIES, key=f"{key}-category")
            link = st.selectbox("Credit time to habit", labels, key=f"{key}-habit")
            set_deadline = st.checkbox("Has a deadline / reminder", value=False, key=f"{key}-has-deadline")
            due_day = st.date_input("Deadline date (only used if ticked)", value=core.now_local().date(), key=f"{key}-due-day")
            due_time = st.time_input("Deadline time", value=time(17), step=900, key=f"{key}-due-time")
        new_habit = st.text_input("Or create and link a new habit (optional)",
                                  placeholder="e.g. Revision", key=f"{key}-new-habit")
        new_habit_goal = st.number_input("New habit daily goal (minutes)", min_value=5, max_value=1440,
                                         value=60, step=5, key=f"{key}-new-goal")
        notes = st.text_input("Notes (optional)", key=f"{key}-notes")
        submitted = st.form_submit_button("Add to-do", type="primary", use_container_width=True)
    if submitted:
        if not title.strip():
            st.error("Enter a to-do title.")
            return
        selected = labels.index(link)
        habit_id = habits[selected - 1]["id"] if selected else None
        try:
            core.add_task(title, due_date=due_day.isoformat() if set_deadline else None,
                          due_time=due_time.strftime("%H:%M") if set_deadline else None,
                          priority=priority, category=category, notes=notes,
                          minutes=int(duration), habit_id=habit_id,
                          planned_date=plan_date.isoformat() if set_plan else None,
                          new_habit=new_habit, new_habit_goal=int(new_habit_goal))
            st.rerun()
        except ValueError as exc:
            st.error(str(exc))


def overview(data: dict):
    today = core.now_local().date()
    header("Overview", today.strftime("%A, %d %B %Y"))
    stats = core.productivity_for_day(data, today)
    remaining = sum(not t.get("done") for t in data["tasks"])
    a, b, c, d = st.columns(4)
    a.metric("Completed today", stats["done"])
    b.metric("Open to-dos", remaining)
    c.metric("Focus time", f"{stats['focus']} min")
    d.metric("Habit time", f"{stats['habit_minutes']} min")

    left, right = st.columns([1.5, 1], gap="large")
    with left:
        st.subheader("Today's calendar")
        calendar_day_section(data, today)
        st.subheader("Today's to-dos")
        todos = [t for t in data["tasks"] if t.get("planned_date") == today.isoformat()]
        if not todos:
            st.caption("No to-dos assigned to today. Use Daily planner to choose from your backlog.")
        for task in sorted(todos, key=lambda t: (t.get("done", False), t.get("priority") != "High")):
            task_row(task, data, "overview", selected_day=today)
    with right:
        st.subheader("Upcoming deadlines")
        upcoming = near_deadlines(data, 6)
        if not upcoming:
            st.caption("No approaching deadlines.")
        for when, name, source in upcoming:
            prefix = "Overdue · " if when < core.now_local() else ""
            small_card(name, prefix + f"{when:%a %d %b at %H:%M} · {source}")
        with st.expander("+ Quick add to-do"):
            add_todo_form(data, "quick")
    st.divider()
    st.subheader("Last 7 days")
    days = [today - timedelta(days=i) for i in range(6, -1, -1)]
    stats7 = [core.productivity_for_day(data, day) for day in days]
    chart = pd.DataFrame({"Date": [day.strftime("%a %d") for day in days],
                          "Focus (min)": [s["focus"] for s in stats7],
                          "Habits (min)": [s["habit_minutes"] for s in stats7]}).set_index("Date")
    st.bar_chart(chart, height=220)


def planner(data: dict):
    header("Daily planner", "Your calendar is a schedule; to-dos are things you can complete.")
    day = st.date_input("Select day", value=core.now_local().date(), key="planner-day")
    c1, c2 = st.columns([1.4, 1], gap="large")
    with c1:
        st.subheader("Calendar · " + day.strftime("%a %d %b"))
        calendar_day_section(data, day)
        st.divider()
        st.subheader("Planned to-dos")
        today_tasks = [t for t in data["tasks"] if t.get("planned_date") == day.isoformat()]
        if not today_tasks:
            st.caption("Nothing planned yet. Use Plan on a backlog item below.")
        for task in sorted(today_tasks, key=lambda t: (t.get("done", False), t.get("priority") != "High")):
            task_row(task, data, "planner", selected_day=day)
    with c2:
        st.subheader("Add a to-do")
        add_todo_form(data, "planner-add", default_planned=day)
    st.divider()
    st.subheader("Unscheduled to-dos")
    backlog = [t for t in data["tasks"] if not t.get("done") and not t.get("planned_date")]
    if not backlog:
        st.caption("Your backlog is clear.")
    for task in backlog:
        task_row(task, data, "planner-backlog", selected_day=day)


def todo_page(data: dict):
    header("To-do list", "An independent backlog: tasks never appear on your Apple Calendar.")
    left, right = st.columns([1.5, 1], gap="large")
    with left:
        open_tasks = [t for t in data["tasks"] if not t.get("done")]
        planned = [t for t in open_tasks if t.get("planned_date")]
        backlog = [t for t in open_tasks if not t.get("planned_date")]
        st.metric("Outstanding", len(open_tasks))
        st.subheader(f"Unscheduled · {len(backlog)}")
        if not backlog:
            st.caption("Your backlog is empty.")
        for task in sorted(backlog, key=lambda t: (t.get("priority") != "High", t.get("title", "").casefold())):
            task_row(task, data, "todo-backlog", selected_day=core.now_local().date())
        st.divider()
        st.subheader(f"Planned · {len(planned)}")
        for task in sorted(planned, key=lambda t: t.get("planned_date") or ""):
            task_row(task, data, "todo-planned", selected_day=core.now_local().date())
        completed = [t for t in data["tasks"] if t.get("done")]
        with st.expander(f"Completed · {len(completed)}"):
            for task in sorted(completed, key=lambda t: t.get("completed_at") or "", reverse=True)[:100]:
                task_row(task, data, "todo-completed")
    with right:
        st.subheader("New to-do")
        add_todo_form(data, "todo-page")
        st.caption("Minutes are credited to a linked habit when the to-do is ticked off, not when it is created.")


def calendar_page(data: dict):
    header("Calendar", "Read-only view of your iCloud and university Outlook schedule.")
    st.caption("Add or edit appointments on your phone. Momentum synchronises the calendar here.")
    if st.button("↻ Sync calendars"):
        with st.spinner("Syncing calendars…"):
            result = calendars.sync_calendars(force=True)
        if result.get("errors"):
            for source, error in result["errors"].items():
                st.warning(f"{source}: {error}")
        st.rerun()
    info = data.get("calendar_sync", {})
    if info.get("last_attempt"):
        st.caption("Last sync attempt: " + format_event_time(info["last_attempt"]))
    for source, error in info.get("errors", {}).items():
        st.warning(f"{source}: {error}")
    days = st.selectbox("View", [7, 14, 30, 60], index=1, format_func=lambda n: f"Next {n} days")
    start = core.now_local().date()
    events = []
    for event in data["calendar_cache"] + data["local_events"]:
        try:
            when = datetime.fromisoformat(event["start"])
            when = (when if when.tzinfo else when.replace(tzinfo=core.LONDON)).astimezone(core.LONDON)
            if start <= when.date() < start + timedelta(days=days):
                events.append((when, event))
        except (KeyError, ValueError, TypeError):
            continue
    if not events:
        st.info("No calendar events found. Use Settings to test your iCloud connection.")
    for _, event in sorted(events, key=lambda x: x[0])[:150]:
        event_card(event)


def habits_focus(data: dict):
    header("Habits & focus", "Completed to-dos count automatically toward linked habits.")
    day = st.date_input("View day", value=core.now_local().date(), key="habit-day")
    ds = day.isoformat()
    totals = core.habit_minutes_for_day(data, ds)
    left, right = st.columns(2, gap="large")
    with left:
        st.subheader("Habit progress")
        for habit in data["habits"]:
            duration = totals.get(habit["id"], 0)
            target = int(habit["target_minutes"])
            st.markdown(f"**{html.escape(habit['title'])}** · {duration}/{target} min")
            st.progress(min(duration / target, 1.0))
            with st.expander("Manage · " + habit["title"]):
                inc = st.number_input("Extra minutes", min_value=0, max_value=720, value=15,
                                      step=5, key=f"habit-add-{habit['id']}")
                if st.button("Log extra time", key=f"habit-log-{habit['id']}"):
                    core.log_habit(habit["id"], int(inc), ds)
                    st.rerun()
                if st.button("Delete habit", key=f"habit-del-{habit['id']}"):
                    core.delete_habit(habit["id"])
                    st.rerun()
        with st.expander("+ New habit"):
            with st.form("new-habit", clear_on_submit=True):
                name = st.text_input("Name", placeholder="e.g. Reading")
                goal = st.number_input("Daily target (min)", min_value=5, max_value=1440, value=30, step=5)
                category = st.selectbox("Category", CATEGORIES, key="new-habit-category")
                if st.form_submit_button("Create habit"):
                    if name.strip():
                        core.add_habit(name, int(goal), category)
                        st.rerun()
                    else:
                        st.error("Enter a habit name.")
    with right:
        st.subheader("Focus sessions")
        with st.form("focus-session", clear_on_submit=True):
            minutes = st.number_input("Focused minutes", min_value=1, max_value=720, value=45, step=5)
            category = st.selectbox("Type", CATEGORIES, key="focus-category")
            notes = st.text_input("What did you work on? (optional)")
            if st.form_submit_button("Log focus session"):
                core.add_focus(int(minutes), category, ds, notes)
                st.rerun()
        sessions = [f for f in data["focus_logs"] if f.get("date") == ds]
        st.caption(f"{sum(int(f.get('minutes', 0)) for f in sessions)} focused minutes · {len(sessions)} sessions")
        for session in sessions[-6:]:
            small_card(session.get("category", "Focus"), f"{session.get('minutes', 0)} min · {session.get('notes', '')}")
        st.divider()
        st.subheader("iPhone Screen Time (manual)")
        st.caption("Apple does not provide a direct Windows/Python Screen Time sync. Enter the daily totals from iPhone Settings → Screen Time.")
        previous = data.get("screen_time_logs", {}).get(ds) or {}
        with st.form(f"screen-time-form-{ds}"):
            total = st.number_input("Total screen time (minutes)", min_value=0, max_value=1440,
                                    value=int(previous.get("total_minutes", 0)), step=5)
            distracting = st.number_input("Social / entertainment minutes (optional)", min_value=0, max_value=1440,
                                          value=int(previous.get("distracting_minutes", 0)), step=5)
            if st.form_submit_button("Save Screen Time"):
                try:
                    core.save_screen_time(ds, int(total), int(distracting))
                    st.rerun()
                except ValueError as exc:
                    st.error(str(exc))
    st.divider()
    with st.expander("Daily notes (optional)"):
        current = data["daily_reviews"].get(ds) or {}
        with st.form(f"day-note-{ds}"):
            note = st.text_area("Reflection", value=current.get("note", ""),
                                placeholder="What did you accomplish? What should change tomorrow?")
            if st.form_submit_button("Save notes"):
                core.save_day_note(ds, note)
                st.rerun()


def insights(data: dict):
    header("Insights", "Activity you actually recorded, without a subjective productivity score.")
    period = st.select_slider("Timeframe", options=[7, 14, 30, 60, 90], value=30,
                              format_func=lambda n: f"{n} days")
    today = core.now_local().date()
    dates = [today - timedelta(days=i) for i in range(period - 1, -1, -1)]
    stats = [core.productivity_for_day(data, day) for day in dates]
    df = pd.DataFrame({"Date": dates,
                       "Focus minutes": [s["focus"] for s in stats],
                       "Habit minutes": [s["habit_minutes"] for s in stats],
                       "Completed to-dos": [s["done"] for s in stats],
                       "iPhone Screen Time (manual min)": [s["screen_time"] for s in stats]})
    a, b, c = st.columns(3)
    a.metric("To-dos completed", int(df["Completed to-dos"].sum()))
    b.metric("Focus hours", f"{df['Focus minutes'].sum()/60:.1f}")
    c.metric("Habit hours", f"{df['Habit minutes'].sum()/60:.1f}")
    st.subheader("Time invested")
    st.bar_chart(df.set_index("Date")[["Focus minutes", "Habit minutes"]], height=280)
    st.subheader("Completed to-dos")
    st.bar_chart(df.set_index("Date")["Completed to-dos"], height=210)
    if df["iPhone Screen Time (manual min)"].notna().any():
        st.subheader("iPhone Screen Time")
        st.line_chart(df.set_index("Date")["iPhone Screen Time (manual min)"], height=210)
    with st.expander("See daily data"):
        st.dataframe(df.sort_values("Date", ascending=False), hide_index=True, use_container_width=True)
    st.caption("Focus and habit minutes may overlap. Completing a linked to-do adds its stated duration to habit progress, not automatically to focus time.")


def settings(data: dict):
    header("Settings", "Appearance, calendar connections, alerts and local data.")
    st.subheader("Appearance")
    selected = st.radio("Colour theme", ["Dark", "Light"],
                        index=["Dark", "Light"].index(data["settings"].get("appearance", "Dark")), horizontal=True)
    if selected != data["settings"].get("appearance"):
        core.change(lambda d: d["settings"].update({"appearance": selected}))
        st.rerun()
    st.divider()
    st.subheader("Calendar connections")
    icloud_ok = bool(os.getenv("ICLOUD_EMAIL") and os.getenv("ICLOUD_APP_PASSWORD"))
    st.write("**iCloud:** " + ("credentials configured" if icloud_ok else "not configured"))
    st.caption("Store credentials only in the .env file; never include .env in GitHub or screenshots.")
    modes = ["Off", "Classic Outlook", "ICS link"]
    current = data["settings"].get("outlook_mode", "Off")
    mode = st.selectbox("University Outlook method", modes, index=modes.index(current) if current in modes else 0)
    if mode != current:
        core.change(lambda d: d["settings"].update({"outlook_mode": mode}))
        st.rerun()
    if mode == "Classic Outlook":
        st.caption("Only classic Outlook on Windows supports this method. New Outlook is not supported.")
    elif mode == "ICS link":
        st.caption("The university must permit an ICS feed. Set OUTLOOK_ICS_URL in .env; the feed is read-only.")
    if st.button("Test / sync connections", type="primary"):
        with st.spinner("Contacting calendars…"):
            result = calendars.sync_calendars(force=True)
        if result.get("counts"):
            st.success("Synced: " + ", ".join(f"{k}: {v} events" for k, v in result["counts"].items()))
        for source, error in result.get("errors", {}).items():
            st.error(f"{source}: {error}")
        if not result.get("counts") and not result.get("errors"):
            st.info("No calendar connection configured.")
    st.divider()
    st.subheader("Deadline alerts")
    enabled = st.toggle("Enable Windows reminders", value=data["settings"].get("alerts_enabled", True))
    options = [5, 10, 15, 30, 60, 120, 1440]
    chosen = st.multiselect("Notify before an event or to-do deadline (minutes)", options,
                            default=[v for v in data["settings"].get("alert_minutes", [60, 15]) if v in options])
    intervals = [5, 10, 15, 30, 60]
    current_interval = data["settings"].get("sync_interval_minutes", 15)
    interval = st.selectbox("Sync interval (minutes)", intervals,
                            index=intervals.index(current_interval) if current_interval in intervals else 2)
    if st.button("Save alert settings"):
        core.change(lambda d: d["settings"].update({"alerts_enabled": enabled,
                                                     "alert_minutes": chosen,
                                                     "sync_interval_minutes": interval}))
        st.success("Saved.")
    st.caption("Reminders work while Momentum is running. For background alerts, launch start_reminders_windows.bat.")
    st.divider()
    st.subheader("Your data")
    st.caption("All task/habit data and cached event details remain local in tracker_data.txt.")
    if core.DATA_PATH.exists():
        st.download_button("Export data", core.DATA_PATH.read_bytes(), file_name="momentum_backup.txt", mime="text/plain")


try:
    data = core.load_data()
except ValueError as exc:
    st.error(str(exc))
    st.stop()

apply_styles(st, data["settings"].get("appearance", "Dark"))
with st.sidebar:
    st.markdown('<div class="momentum-brand">◈ momentum</div>', unsafe_allow_html=True)
    st.caption("Plan less. Do more.")
    st.divider()
    page = st.radio("Navigate", NAV, label_visibility="collapsed")
    st.divider()
    st.caption("LOCAL · PRIVATE · NO AI API")
    if st.button("↻ Refresh data", use_container_width=True):
        st.rerun()


@st.fragment(run_every="60s")
def background_refresh():
    try:
        before = st.session_state.get("last_calendar_refresh_in_ui")
        check_once(show_toasts=True, refresh=True)
        after = core.load_data().get("calendar_sync", {}).get("last_attempt")
        st.session_state["last_calendar_refresh_in_ui"] = after
        if before is not None and after != before:
            st.rerun()
    except Exception:
        pass  # Errors appear in Settings or Calendar.


background_refresh()
data = core.load_data()
if page == "Overview":
    overview(data)
elif page == "Daily planner":
    planner(data)
elif page == "To-do list":
    todo_page(data)
elif page == "Calendar":
    calendar_page(data)
elif page == "Habits & focus":
    habits_focus(data)
elif page == "Insights":
    insights(data)
else:
    settings(data)
