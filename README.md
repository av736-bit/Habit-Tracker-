# Momentum — personal productivity and reminders (v2)

A **personal programming project**, not a production-grade planner. A local Streamlit dashboard that combines your habits, tasks, productivity reviews, iCloud Calendar and (where your university permits) Outlook Calendar. **No Anthropic/OpenAI API is used.**

## Features

- Cleaner Streamlit interface with Dark/Light switch, overview and daily planner.
- Combined per-day checklist of local tasks plus events from iCloud and Outlook. Marking an external calendar event complete affects **Momentum only**, not the original calendar.
- Create events **in iCloud**, in classic Outlook (if available), or as Momentum-local events.
- Windows toast alerts before timed tasks and calendar events. The **background agent** can check for notifications even after you close the dashboard, provided your PC remains on and the agent is running.
- Habit targets (minutes per day), logged deep-work sessions, subjective productivity rating (1–10) and charts across 7–90 days.
- Text file `tracker_data.txt` contains JSON (human readable, local, persistent). Uses an atomic writer and file lock. If a pre-v2 file exists, the first save creates `tracker_data_before_v2.backup.txt`. Old formats may need manual migration for some advanced habit-history fields.
- Secrets only in `.env` (excluded by `.gitignore`).

## Windows install (Python 3.10+)

1. Extract the ZIP into a normal local folder (not a temporary ZIP view).
2. Double-click `setup_windows.bat` once. This creates a `.venv` and installs requirements.
3. Double-click `run_windows.bat` to open the dashboard (usually http://localhost:8501).
4. Your first task/review/habit creates `tracker_data.txt` automatically. Copy your old `tracker_data.txt` into the project folder **before launching** if you want to keep using it; back it up yourself too.

Alternatively, in PowerShell:

```powershell
py -3 -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
.\.venv\Scripts\python.exe -m streamlit run app.py
```

## iCloud Calendar (syncs with iPhone)

1. Make sure the events you want are saved under **iCloud** on the iPhone and appear at <https://www.icloud.com/calendar/>. iPhone calendars from Outlook are not mirrored into iCloud merely because Apple Calendar shows them.
2. Go to <https://account.apple.com/> → **Sign-In and Security** → **App-Specific Passwords** and generate a password. Two-factor authentication must be enabled.
3. Open the `.env` file in the project folder with Notepad:

```ini
ICLOUD_EMAIL=you@example.com
ICLOUD_APP_PASSWORD=your-generated-app-password
```

4. Restart the Streamlit app and click **Settings → Test / sync connections**. Do not share your real password or commit `.env`.

**iCloud access:** reads all calendars associated with those credentials; creation targets the first available iCloud calendar (not necessarily a calendar you want to use). Check the created event in Calendar. Apple calendar permissions or CalDAV authentication errors will appear in the app. When **Mark as deadline** is used on a remotely created event, Momentum adds the small `[Momentum deadline]` marker to the event description so it stays identifiable after later syncs.

## University-managed Outlook: two alternatives

**Option A — classic Outlook for Windows:** If you have the **classic desktop Outlook** application (not New Outlook), with your university mailbox configured, select **Settings → Connection method → Classic Outlook**. It can then read events from your default Outlook calendar via COM, and the app lets you add events there. Some university restrictions can still prevent access. The calendar stays stored in the university account.

**Option B — Outlook ICS calendar publication (read-only):** In Outlook on the web, explore **Settings → Calendar → Shared calendars → Publish a calendar** (wording varies) and copy the generated **ICS** URL. Your university may disable this feature. Put the URL in `.env` as `OUTLOOK_ICS_URL=...`, restart and select **ICS link** in Settings. This allows automatic re-fetching but **not** writing changes back. ICS URLs can expose personal schedules to anyone with the link: do not publish/commit/share it and follow university sharing rules.

**If neither works**, Momentum can still use iCloud and local tasks; to use the university calendar programmatically would require an authorised Microsoft Graph app approved by Cambridge IT. No attempt is made to bypass organisational restrictions.

## Windows deadline notifications

While your **Streamlit dashboard/browser session is active**, it checks every ~60 seconds and fires Windows toast notifications at your selected lead times (15 and 60 minutes by default), including calendar events and task deadlines. Calendar syncing refreshes at configurable intervals (15 minutes by default). **Timing is approximate**, especially if the PC sleeps, the event changes remotely, the calendar source is stale, or Windows notifications are disabled. All-day events have no clock time and do not trigger timed alerts. Events are displayed in the calendar even if not marked as deadlines.

To have alerts **when the browser is closed**, double-click `start_reminders_windows.bat`. It starts a Python process in the background, checking every minute. Your PC must be awake and on. You can check it in Task Manager; close that specific Python process to stop it. Avoid launching multiple reminder agents; notification IDs are de-duplicated regardless. You can make a Windows shortcut to `start_reminders_windows.bat` and place it in the folder opened by `Win + R` → `shell:startup` if you want the agent started at Windows sign-in. It will **not** run if Windows is shut down.

## File structure

```text
Momentum/
  app.py                       Streamlit interface
  tracker_core.py              data, habits, tasks, summaries, alerts
  calendar_sync.py             iCloud / classic Outlook / ICS connectors
  reminder_agent.py            optional reminder background process
  ui_styles.py                 dark/light style
  tracker_data.txt             user data (created on first save; ignored by Git)
  .env                         calendar credentials (ignored by Git)
  .env.example                 safe credential template
  .streamlit/config.toml       theme defaults
  tests/test_core.py           local automated tests
  setup_windows.bat
  run_windows.bat
  start_reminders_windows.bat
  requirements.txt
  .gitignore
```

## Notes and limitations

- **Calendar synchronisation is one-way into the agenda**; iCloud event creation pushes events to Apple Calendar, but checking off an existing calendar event is an app-only state. Reordering or editing external events must be done in their original calendar.
- University ICS access is read-only, and classic Outlook COM won't work with New Outlook.
- Notifications work only when the UI session or background agent is running; no push service is included, so this is **not a guaranteed safety-critical deadline alert system**. Keep normal iPhone reminders for important deadlines.
- Local text data includes event titles, meeting descriptions and dates in the calendar cache; keep it private. `tracker_data.txt` should not be committed to GitHub.
- Your historical v1 data schema wasn't supplied with this edition. A backup is made automatically before converting from v1; some legacy metrics may need adapted import logic.

Sources: [caldav documentation](https://caldav.readthedocs.io/stable/tutorial.html), [Apple app-specific password](https://support.apple.com/en-gb/102654), [Microsoft calendar publishing](https://support.microsoft.com/en-gb/outlook/share-your-calendar-in-outlook-on-the-web).
