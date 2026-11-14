#!/usr/bin/env python3
"""
Fetch BPI's USD/PHP indicative rate and send it out (Mon-Fri).

Delivery (all optional, use any combination):
  - Microsoft Teams: set TEAMS_WEBHOOK_URL (Power Automate / Workflows HTTP URL)
  - Email:           set SMTP_HOST, SMTP_USER, SMTP_PASSWORD, EMAIL_TO
                     (optional: SMTP_PORT=587, EMAIL_FROM)
  - GitHub run log:  always printed, and shown in the run's Summary page

Flags:
  --dry-run  fetch and print only, send nothing
  --force    run even on Saturday/Sunday
"""

import argparse
import os
import re
import smtplib
import sys
import time
from datetime import datetime
from email.message import EmailMessage
from zoneinfo import ZoneInfo

import requests

BPI_URL = "https://www.bpi.com.ph/personal/bank/forex/rates"
TZ = ZoneInfo("Asia/Manila")
HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/124.0 Safari/537.36"
    ),
    "Accept-Language": "en-PH,en;q=0.9",
}


def fetch_bpi_usd(retries=3):
    """Return (as_of_text, buying, selling) for USD from BPI's rates page."""
    last_err = None
    for attempt in range(1, retries + 1):
        try:
            resp = requests.get(BPI_URL, headers=HEADERS, timeout=30)
            resp.raise_for_status()
            return parse_usd(resp.text)
        except Exception as exc:  # network error, 403, layout change...
            last_err = exc
            print(f"Attempt {attempt}/{retries} failed: {exc}", file=sys.stderr)
            if attempt < retries:
                time.sleep(10 * attempt)
    raise RuntimeError(f"Could not get BPI rate: {last_err}")


def parse_usd(html):
    # Flatten HTML to plain text so we don't depend on exact table markup.
    text = re.sub(r"<script.*?</script>|<style.*?</style>", " ", html, flags=re.S)
    text = re.sub(r"<[^>]+>", " ", text)
    text = re.sub(r"\s+", " ", text)

    row = re.search(
        r"\(USD\)\s*US Dollar\s*\|?\s*([\d,]+\.\d+)\s*\|?\s*([\d,]+\.\d+)", text
    )
    if not row:
        raise RuntimeError(
            "USD row not found. BPI may have changed the page or blocked the request."
        )
    buying = float(row.group(1).replace(",", ""))
    selling = float(row.group(2).replace(",", ""))
    as_of = re.search(
        r"As of\s+\d{1,2}:\d{2}\s*[AP]M,\s*[A-Za-z]+\s+\d{1,2},\s*\d{4}", text
    )
    return (as_of.group(0) if as_of else "time not shown on page"), buying, selling


def plain_message(as_of, buying, selling):
    today = datetime.now(TZ).strftime("%A, %B %d, %Y")
    return (
        f"BPI USD Rate - {today}\n"
        f"Bank buying:  PHP {buying:,.2f}\n"
        f"Bank selling: PHP {selling:,.2f}\n"
        f"{as_of} (indicative, may change without notice)"
    )


def send_teams(webhook, as_of, buying, selling):
    today = datetime.now(TZ).strftime("%A, %B %d, %Y")
    card = {
        "type": "AdaptiveCard",
        "$schema": "http://adaptivecards.io/schemas/adaptive-card.json",
        "version": "1.4",
        "body": [
            {"type": "TextBlock", "text": f"BPI USD Rate - {today}",
             "weight": "Bolder", "size": "Medium", "wrap": True},
            {"type": "FactSet", "facts": [
                {"title": "Bank buying", "value": f"PHP {buying:,.2f}"},
                {"title": "Bank selling", "value": f"PHP {selling:,.2f}"},
            ]},
            {"type": "TextBlock",
             "text": f"{as_of} (indicative rates, may change without notice)",
             "isSubtle": True, "size": "Small", "wrap": True},
        ],
    }
    # The Teams workflow's "Adaptive card" field is set to the request Body,
    # so the card itself is sent as the whole request body.
    r = requests.post(webhook, json=card, timeout=30)
    r.raise_for_status()
    print("Sent to Teams.")


def send_email(as_of, buying, selling):
    host = os.environ["SMTP_HOST"]
    port = int(os.environ.get("SMTP_PORT", "587"))
    user = os.environ["SMTP_USER"]
    password = os.environ["SMTP_PASSWORD"]
    to = [a.strip() for a in os.environ["EMAIL_TO"].split(",") if a.strip()]

    msg = EmailMessage()
    msg["Subject"] = f"BPI USD rate: buy {buying:,.2f} / sell {selling:,.2f}"
    msg["From"] = os.environ.get("EMAIL_FROM", user)
    msg["To"] = ", ".join(to)
    msg.set_content(plain_message(as_of, buying, selling))

    if port == 465:
        with smtplib.SMTP_SSL(host, port, timeout=30) as s:
            s.login(user, password)
            s.send_message(msg)
    else:
        with smtplib.SMTP(host, port, timeout=30) as s:
            s.starttls()
            s.login(user, password)
            s.send_message(msg)
    print(f"Emailed {len(to)} recipient(s).")


def write_github_summary(text):
    path = os.environ.get("GITHUB_STEP_SUMMARY")
    if path:
        with open(path, "a", encoding="utf-8") as f:
            f.write("### BPI USD rate\n\n```\n" + text + "\n```\n")


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--force", action="store_true")
    args = parser.parse_args()

    if datetime.now(TZ).weekday() >= 5 and not (args.force or args.dry_run):
        print("Weekend - skipping.")
        return 0

    as_of, buying, selling = fetch_bpi_usd()
    message = plain_message(as_of, buying, selling)
    print(message)
    write_github_summary(message)

    if args.dry_run:
        return 0

    failures = 0
    sent_any = False

    webhook = os.environ.get("TEAMS_WEBHOOK_URL")
    if webhook:
        sent_any = True
        try:
            send_teams(webhook, as_of, buying, selling)
        except Exception as exc:
            failures += 1
            print(f"Teams failed: {exc}", file=sys.stderr)

    if os.environ.get("SMTP_HOST") and os.environ.get("EMAIL_TO"):
        sent_any = True
        try:
            send_email(as_of, buying, selling)
        except Exception as exc:
            failures += 1
            print(f"Email failed: {exc}", file=sys.stderr)

    if not sent_any:
        print("No delivery configured (TEAMS_WEBHOOK_URL / SMTP_*). "
              "Rate was only printed to the log.")
    return 1 if failures else 0


if __name__ == "__main__":
    sys.exit(main())
