# Momentum — Habit Tracker

A local-first Python habit tracker with an interactive dashboard, natural-language logging, a to-do list, and historical progress charts.

## Getting started (Windows / PowerShell)

```powershell
cd path\to\momentum_habit_tracker
py -m pip install -r requirements.txt
py -m streamlit run app.py
```

On Windows you can also double-click **`run_windows.bat`** to install dependencies and launch the app.

Your browser opens to a locally running app. All updates are stored in **`tracker_data.txt`** next to the app, using readable JSON text. The file is created automatically and survives restarting the program.

## Features

- Record time spent studying, exercising, reading, coding, or custom habits.
- Enter natural English updates (AI integration optional).
- Track and complete tasks, with a history of changes.
- Visualise the last 7, 30, or 90 days with daily bar and line charts.
- Export a text backup from the sidebar.
- Data written atomically to reduce the chance of partial/corrupt saves.

## Examples

With no API key, the offline parser recognises common commands:

- `I studied for 2 hours`
- `Read for 30 minutes yesterday`
- `I exercised for 45 minutes and studied for 90 minutes`
- `Add finish my lab report to my list`
- `Complete finish my lab report`
- `Remove finish my lab report`

For more varied descriptions (such as multi-action, freeform messages), enable Claude below. If a sentence isn't understood offline, use the manual logging form.

## Optional AI interpretation (Claude)

1. Create a **new** Anthropic API key in your Anthropic account. Never paste it into source code, README files or GitHub.
2. In PowerShell, before starting the app, run:

   ```powershell
   $env:ANTHROPIC_API_KEY="PASTE_YOUR_NEW_KEY_HERE"
   py -m streamlit run app.py
   ```

   Alternatively set `ANTHROPIC_MODEL` if you have access to a different Claude model. The default is `claude-sonnet-4-6`.
3. Habit names and currently open task titles, together with the message you enter, are sent to Anthropic for interpretation when the key is enabled. API usage may cost money. Without the key, nothing is sent to Anthropic.

## Keeping data safe

`tracker_data.txt`, `.env` and `.streamlit/secrets.toml` are ignored by Git. Keep backups of `tracker_data.txt`. This app is designed for **local** use; on a hosted service such as Streamlit Community Cloud, local file storage may be temporary or shared between visitors. Add authentication and a real database before deploying a private tracker publicly.

## Structure

- `app.py` — Streamlit dashboard, forms and charts
- `tracker_core.py` — natural-language interpretation, validation, persistence
- `.streamlit/config.toml` — theme
- `tracker_data.txt` — created at first run; permanent local data
- `tests/test_tracker.py` — offline unit tests
