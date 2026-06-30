#!/usr/bin/env python3
"""
Pioneer Valley Events — weekly email digest.

Reads docs/data/events.json, selects events in the next N days, and emails a
grouped, mobile-friendly HTML summary via Gmail SMTP.

Environment variables:
  GMAIL_ADDRESS       sender Gmail address; also the default recipient.
  GMAIL_APP_PASSWORD  a Gmail App Password (NOT your normal password — create
                      one at https://myaccount.google.com/apppasswords).
  MAIL_TO             optional recipient override (defaults to GMAIL_ADDRESS).

Usage:
  python3 email_digest.py                 # build + send (next 14 days)
  python3 email_digest.py --days 7        # change the window
  python3 email_digest.py --preview out.html   # build + write HTML, do NOT send
"""

import argparse
import html
import json
import os
import smtplib
import ssl
import sys
from datetime import date, datetime, timedelta
from email.mime.text import MIMEText

OUTPUT_PATH = os.path.join(os.path.dirname(__file__), "docs", "data", "events.json")
SITE_URL = "https://mhotard.github.io/pioneer-valley-events"

CATEGORY_EMOJI = {
    "music": "🎵", "arts": "🎨", "film": "🎬", "comedy": "😂",
    "community": "🤝", "academia": "🎓", "family": "👨‍👩‍👧", "food": "🍽️",
    "outdoor": "🌳", "festival": "🎪",
}


def load_events(path: str) -> list:
    with open(path) as f:
        return json.load(f).get("events", [])


def time_sort_key(ev: dict):
    """Sort all-day events (no time) first, then chronologically."""
    raw = (ev.get("time") or "").strip()
    for fmt in ("%I:%M %p", "%I %p"):
        try:
            t = datetime.strptime(raw, fmt)
            return (1, t.hour * 60 + t.minute)
        except ValueError:
            continue
    return (0, 0)


def select_upcoming(events: list, days: int) -> list:
    today = date.today()
    horizon = (today + timedelta(days=days)).isoformat()
    today_str = today.isoformat()
    upcoming = [e for e in events if today_str <= e.get("date", "") <= horizon]
    upcoming.sort(key=lambda e: (e["date"], time_sort_key(e)))
    return upcoming


def pretty_day(date_str: str) -> str:
    try:
        return datetime.strptime(date_str, "%Y-%m-%d").strftime("%A, %B %-d")
    except ValueError:
        return date_str


def build_html(upcoming: list, total: int, days: int) -> str:
    esc = html.escape
    today = date.today()
    end = today + timedelta(days=days)
    window = f"{today.strftime('%B %-d')} – {end.strftime('%B %-d')}"

    parts = [
        '<div style="font-family:-apple-system,Segoe UI,Roboto,Helvetica,Arial,'
        'sans-serif;max-width:640px;margin:0 auto;color:#1a1a1a;">',
        '<h1 style="font-size:22px;margin:0 0 4px;">Pioneer Valley Events</h1>',
        f'<p style="color:#666;margin:0 0 20px;font-size:14px;">{window} · '
        f'{len(upcoming)} events coming up · {total} on the site</p>',
    ]

    if not upcoming:
        parts.append(
            '<p style="font-size:15px;">No events scheduled in this window yet — '
            f'check <a href="{SITE_URL}">the site</a> later in the week.</p>'
        )
    else:
        current_day = None
        for ev in upcoming:
            if ev["date"] != current_day:
                if current_day is not None:
                    parts.append("</div>")
                current_day = ev["date"]
                parts.append(
                    f'<h2 style="font-size:16px;border-bottom:1px solid #e2e2e2;'
                    f'padding-bottom:4px;margin:24px 0 10px;">{esc(pretty_day(current_day))}</h2>'
                    '<div>'
                )

            emoji = CATEGORY_EMOJI.get(ev.get("category", ""), "•")
            time_str = esc(ev.get("time", "").strip()) or "All day"
            title = esc(ev.get("title", "Untitled"))
            url = ev.get("url", "")
            if url:
                link_style = "color:#0b5cad;text-decoration:none;"
                title = f'<a href="{esc(url)}" style="{link_style}">{title}</a>'
            where = " · ".join(
                p for p in [esc(ev.get("venue", "")), esc(ev.get("town", ""))] if p
            )
            parts.append(
                '<div style="margin:0 0 10px;font-size:15px;line-height:1.4;">'
                f'<span style="color:#888;">{time_str}</span> &nbsp;{emoji} '
                f'<strong>{title}</strong>'
                + (f'<br><span style="color:#666;font-size:13px;">{where}</span>' if where else "")
                + "</div>"
            )
        parts.append("</div>")

    parts.append(
        f'<p style="margin:28px 0 0;font-size:13px;color:#999;">'
        f'<a href="{SITE_URL}" style="color:#999;">Browse all events →</a></p></div>'
    )
    return "\n".join(parts)


def send_email(html_body: str, subject: str, sender: str, recipient: str, password: str):
    msg = MIMEText(html_body, "html", "utf-8")
    msg["Subject"] = subject
    msg["From"] = sender
    msg["To"] = recipient

    context = ssl.create_default_context()
    with smtplib.SMTP_SSL("smtp.gmail.com", 465, context=context) as server:
        server.login(sender, password)
        server.sendmail(sender, [recipient], msg.as_string())


def main():
    parser = argparse.ArgumentParser(description="Email the weekly events digest")
    parser.add_argument("--days", type=int, default=14, help="Window length (default 14)")
    parser.add_argument("--preview", metavar="FILE", help="Write HTML to FILE instead of sending")
    args = parser.parse_args()

    events = load_events(OUTPUT_PATH)
    upcoming = select_upcoming(events, args.days)
    html_body = build_html(upcoming, total=len(events), days=args.days)

    end = date.today() + timedelta(days=args.days)
    subject = f"Pioneer Valley Events — {len(upcoming)} events through {end.strftime('%b %-d')}"

    if args.preview:
        with open(args.preview, "w", encoding="utf-8") as f:
            f.write(html_body)
        print(f"Wrote preview to {args.preview} ({len(upcoming)} events, subject: {subject!r})")
        return

    sender = os.environ.get("GMAIL_ADDRESS")
    password = os.environ.get("GMAIL_APP_PASSWORD")
    recipient = os.environ.get("MAIL_TO") or sender
    if not sender or not password:
        print(
            "ERROR: GMAIL_ADDRESS and GMAIL_APP_PASSWORD must be set to send. "
            "(Use --preview to build the email without sending.)",
            file=sys.stderr,
        )
        sys.exit(1)

    send_email(html_body, subject, sender, recipient, password)
    print(f"Sent digest to {recipient}: {len(upcoming)} events, subject {subject!r}")


if __name__ == "__main__":
    main()
