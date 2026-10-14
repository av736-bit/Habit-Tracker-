"""Windows notifications + periodic calendar refresh. Run via pythonw on login."""
from __future__ import annotations
import argparse
import logging
import platform
import time

from calendar_sync import sync_calendars
from tracker_core import load_data, pending_alerts, reserve_alert


def send_toast(title: str, message: str) -> bool:
    if platform.system() != "Windows":
        return False
    try:
        from winotify import Notification
        Notification(app_id="Momentum Reminders", title=title[:100], msg=message).show()
        return True
    except Exception as exc:
        logging.warning("Windows notification could not be displayed: %s", exc)
        return False


def check_once(show_toasts=True, refresh=True) -> list[dict]:
    if refresh:
        try:
            sync_calendars(force=False)
        except Exception as exc:
            logging.warning("Calendar refresh failed: %s", exc)
    alerts = pending_alerts(load_data())
    dispatched = []
    for alert in alerts:
        if show_toasts and reserve_alert(alert["key"]):
            send_toast(alert["title"], alert["message"])
            dispatched.append(alert)
    return dispatched if show_toasts else alerts


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--once", action="store_true", help="Check once rather than running continuously")
    args = parser.parse_args()
    logging.basicConfig(level=logging.WARNING, filename="reminder_agent.log", filemode="a")
    if args.once:
        check_once()
        return
    while True:
        try:
            check_once()
        except Exception as exc:
            logging.exception("Reminder check failed: %s", exc)
        time.sleep(60)


if __name__ == "__main__":
    main()
