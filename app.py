"""Run using: python -m streamlit run app.py"""

from datetime import date, timedelta
import json
import os

import pandas as pd
import streamlit as st

from tracker_core import (
    DATA_FILE, apply_actions, duration, interpret_message, load_data, save_data
)

st.set_page_config(page_title="Momentum | Habit Tracker", page_icon="📈", layout="wide")

st.markdown("""
<style>
  .block-container {max-width: 1180px; padding-top: 2.0rem; padding-bottom: 4rem;}
  [data-testid="stMetric"] {background: #17243A; padding: 1.1rem 1.25rem;
                            border-radius: 14px; border: 1px solid #2A3A50;}
  [data-testid="stMetricLabel"] {color: #A9B9CC;}
  .hero {padding: 1.5rem 1.7rem; border: 1px solid #2A3A50;
          border-radius: 20px; margin-bottom: 1.4rem;
          background: linear-gradient(115deg, #172A3B 0%, #142031 60%, #1C2637 100%);}
  .eyebrow {color: #B7EB6D; letter-spacing: .16em; font-size: .72rem;
             font-weight: 700; text-transform: uppercase;}
  .hero h1 {font-size: 2.4rem; margin: .3rem 0 .35rem; color: #F8FBFF;}
  .hero p {color: #BBCADC; margin: 0; font-size: 1rem;}
  .hint {color: #A9B9CC; font-size: .86rem;}
  div.stButton > button[kind="primary"], div.stFormSubmitButton > button[kind="primary"]
  {border-radius: 10px; font-weight: 700;}
  [data-testid="stTabs"] button {font-size: 1rem;}
</style>
""", unsafe_allow_html=True)

try:
    data = load_data()
except ValueError as error:
    st.error(str(error))
    st.stop()


def commit(actions: list, *, source: str = "manual", note: str = ""):
    new_data, messages, errors = apply_actions(data, actions)
    if messages:
        try:
            save_data(new_data)
        except OSError as exc:
            st.session_state.feedback = ("error", f"Could not save data: {exc}")
            st.rerun()
    if messages:
        result = " ".join(messages)
        st.session_state.feedback = ("success", f"{result}  ({source})")
    elif errors:
        st.session_state.feedback = ("error", " ".join(errors))
    else:
        st.session_state.feedback = (
            "warning", "I didn't find an actionable update. Try 'studied for 90 minutes' "
            "or use the manual entry form."
        )
    if errors and messages:
        st.session_state.feedback = ("warning", " ".join(messages + errors))
    if note and source == "offline fallback":
        level, info = st.session_state.feedback
        st.session_state.feedback = (level, info + "  " + note)
    st.rerun()


with st.sidebar:
    st.markdown("### ◈ Momentum")
    st.caption("A local-first habit tracker")
    st.divider()
    st.markdown("**YOUR HABITS**")
    for habit in data["habits"]:
        st.write("• " + habit.title())
    with st.form("new_habit", clear_on_submit=True):
        name = st.text_input("New habit", placeholder="e.g. coding")
        if st.form_submit_button("Add habit", use_container_width=True):
            commit([{"type": "add_habit", "habit": name}])
    st.divider()
    st.caption("Your data is saved automatically in:")
    st.code(DATA_FILE.name, language=None)
    st.download_button(
        "Download backup (.txt)",
        data=json.dumps(data, indent=2, ensure_ascii=False),
        file_name="momentum_backup.txt", mime="text/plain",
        use_container_width=True
    )
    if not os.environ.get("ANTHROPIC_API_KEY"):
        st.caption("AI is off. Common English commands work offline. Set ANTHROPIC_API_KEY for full interpretation.")
    else:
        st.caption("◉ Claude interpretation enabled")

st.markdown(
    '<div class="hero"><div class="eyebrow">Personal dashboard · ' +
    date.today().strftime("%A, %d %B %Y") +
    '</div><h1>Build momentum.</h1><p>Log your time, clear your to-dos, and see your progress over time.</p></div>',
    unsafe_allow_html=True
)

feedback = st.session_state.pop("feedback", None)
if feedback:
    level, text = feedback
    {"success": st.success, "warning": st.warning, "error": st.error}[level](text)

today = date.today().isoformat()
today_values = data["days"].get(today, {})
total_today = sum(today_values.values())
completed = sum(t["done"] for t in data["todos"])
open_count = len(data["todos"]) - completed
active_days = sum(bool(day and sum(day.values()) > 0) for day in data["days"].values())

m1, m2, m3, m4 = st.columns(4)
m1.metric("Hours today", f"{total_today / 60:.1f} h")
m2.metric("Tasks remaining", open_count)
m3.metric("Tasks completed", completed)
m4.metric("Days with activity", active_days)

overview, trends, todo_tab, history = st.tabs(["◈ Overview", "↗ Trends", "✓ To-do", "◷ History"])

with overview:
    st.markdown("#### Quick capture")
    st.caption("Write what you've done naturally. AI can interpret complex updates, or you can use the offline parser.")
    with st.form("capture", clear_on_submit=True):
        message = st.text_area(
            "What have you done today?",
            placeholder="Studied for 2 hours and read for 30 minutes; add finish lab report to my list",
            height=105,
        )
        submitted = st.form_submit_button("Interpret & save →", type="primary", use_container_width=True)
    if submitted:
        if message.strip():
            with st.spinner("Interpreting entry..."):
                actions, source, note = interpret_message(message.strip(), data)
            commit(actions, source=source, note=note)
        else:
            st.warning("Enter something first.")

    st.markdown("#### Today's habits")
    if any(today_values.values()):
        for habit in data["habits"]:
            minutes = today_values.get(habit, 0)
            if minutes:
                left, right = st.columns([4, 1])
                left.write(habit.title())
                right.markdown(f"**{duration(minutes)}**")
                st.progress(min(minutes / 120, 1.0), text=f"{min(round(100 * minutes / 120), 100)}% of a 2-hour reference")
    else:
        st.info("No time logged today yet. Start with a quick capture or manual entry.")

    with st.expander("Manual entry — no AI needed", expanded=False):
        with st.form("manual_entry", clear_on_submit=True):
            col_a, col_b, col_c = st.columns(3)
            habit = col_a.selectbox("Habit", data["habits"])
            mins = col_b.number_input("Minutes completed", min_value=1, max_value=1440, value=30, step=5)
            when = col_c.date_input("Date", value=date.today(), max_value=date.today())
            if st.form_submit_button("Log this time", type="primary"):
                commit([{"type": "log_habit", "habit": habit, "minutes": int(mins), "date": when.isoformat()}])

with trends:
    st.markdown("#### See your progress")
    days_back = st.segmented_control("Timeframe", options=["7 days", "30 days", "90 days"], default="30 days")
    count = int(days_back.split()[0])
    range_days = [date.today() - timedelta(days=i) for i in reversed(range(count))]
    rows = []
    for current_date in range_days:
        logged = data["days"].get(current_date.isoformat(), {})
        rows.append({"Date": pd.Timestamp(current_date), **{
            habit.title(): round(logged.get(habit, 0) / 60, 3) for habit in data["habits"]
        }})
    df = pd.DataFrame(rows).set_index("Date")
    st.markdown("**Daily time by habit**")
    st.bar_chart(df, height=320, y_label="Hours")
    habit_to_plot = st.selectbox("Inspect one habit", options=data["habits"], format_func=str.title)
    st.markdown(f"**{habit_to_plot.title()} over time**")
    st.line_chart(df[[habit_to_plot.title()]], height=230, y_label="Hours")
    aggregate = df.sum().sort_values(ascending=False)
    if aggregate.sum() > 0:
        st.caption("Total hours during this period")
        st.dataframe(aggregate.rename("Hours").to_frame(), use_container_width=True)
    else:
        st.info("Start logging habits to see graphs fill up.")

with todo_tab:
    st.markdown("#### Tasks")
    with st.form("add_task", clear_on_submit=True):
        new_task = st.text_input("New to-do", placeholder="Finish engineering lab report")
        if st.form_submit_button("Add task", type="primary"):
            commit([{"type": "add_todo", "text": new_task}])
    ordered = sorted(data["todos"], key=lambda t: t["done"])
    if not ordered:
        st.info("Your to-do list is empty.")
    for item in ordered:
        col_check, col_delete = st.columns([8, 1], vertical_alignment="center")
        is_checked = col_check.checkbox(
            item["text"], value=item["done"], key="todo_" + item["id"]
        )
        if is_checked != item["done"]:
            commit([{"type": "complete_todo" if is_checked else "reopen_todo", "id": item["id"]}])
        if col_delete.button("✕", key="delete_" + item["id"], help="Delete task"):
            commit([{"type": "delete_todo", "id": item["id"]}])
    if ordered:
        st.progress(completed / len(ordered), text=f"{completed}/{len(ordered)} complete")

with history:
    st.markdown("#### Activity history")
    if not data["events"]:
        st.info("Your activity history will appear here.")
    for event in reversed(data["events"][-60:]):
        timestamp = event.get("time", "")
        st.caption(timestamp[:16].replace("T", " "))
        st.write(event.get("summary", ""))
        st.divider()
    st.caption("All information stays in the local tracker_data.txt file unless you choose to use the AI integration or upload the app elsewhere.")
