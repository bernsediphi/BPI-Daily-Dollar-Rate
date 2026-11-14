#!/usr/bin/env python3
"""
Fetch BPI's USD/PHP selling rate, add our markup, keep a history, and rebuild
the web page that shows our daily rate.

  Our daily rate = BPI selling rate + MARKUP

Writes (served by GitHub Pages from the /docs folder):
  docs/rates.json   history, one row per rate date
  docs/index.html   the page people open

Usage:
  python update_rate.py                  fetch from BPI and update the files
  python update_rate.py --html-file F    read BPI's HTML from a local file (testing)
"""

import argparse
import html
import json
import re
import sys
import time
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

# Amount added to BPI's selling rate. Change it here if the markup changes;
# rows already saved in the history keep the markup they were recorded with.
MARKUP = 0.50

BPI_URL = "https://www.bpi.com.ph/personal/bank/forex/rates"
TZ = ZoneInfo("Asia/Manila")
DOCS = Path(__file__).resolve().parent / "docs"
HISTORY_FILE = DOCS / "rates.json"
PAGE_FILE = DOCS / "index.html"
MAX_ROWS = 365
TABLE_ROWS = 30
HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/124.0 Safari/537.36"
    ),
    "Accept-Language": "en-PH,en;q=0.9",
}


# ---------------------------------------------------------------- fetching
def fetch_html(retries=3):
    import requests  # imported here so --html-file works without it

    last_err = None
    for attempt in range(1, retries + 1):
        try:
            resp = requests.get(BPI_URL, headers=HEADERS, timeout=30)
            resp.raise_for_status()
            return resp.text
        except Exception as exc:
            last_err = exc
            print(f"Attempt {attempt}/{retries} failed: {exc}", file=sys.stderr)
            if attempt < retries:
                time.sleep(10 * attempt)
    raise RuntimeError(f"Could not get BPI page: {last_err}")


def parse_usd(page_html):
    """Return (as_of_time_text, rate_date 'YYYY-MM-DD', buying, selling)."""
    text = re.sub(r"<script.*?</script>|<style.*?</style>", " ", page_html, flags=re.S)
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

    as_of_text = None
    rate_date = datetime.now(TZ).strftime("%Y-%m-%d")
    m = re.search(
        r"As of\s+(\d{1,2}:\d{2})\s*([AP]M),\s*([A-Za-z]+)\s+(\d{1,2}),\s*(\d{4})", text
    )
    if m:
        hm, ampm, month, day, year = m.groups()
        as_of_text = f"{hm} {ampm}, {month} {day}, {year}"
        for fmt in ("%I:%M %p %B %d %Y", "%I:%M %p %b %d %Y"):
            try:
                parsed = datetime.strptime(f"{hm} {ampm} {month} {day} {year}", fmt)
                rate_date = parsed.strftime("%Y-%m-%d")
                break
            except ValueError:
                continue
    return as_of_text, rate_date, buying, selling


# ----------------------------------------------------------------- history
def load_history():
    if HISTORY_FILE.exists():
        return json.loads(HISTORY_FILE.read_text(encoding="utf-8"))
    return []


def update_history(history, entry):
    history = [h for h in history if h["date"] != entry["date"]]
    history.append(entry)
    history.sort(key=lambda h: h["date"])
    return history[-MAX_ROWS:]


def our_rate(row):
    """Our rate for a history row (older rows without it use the current markup)."""
    return row.get("our_rate", round(row["selling"] + MARKUP, 2))


def markup_of(row):
    return row.get("markup", MARKUP)


# --------------------------------------------------------------- rendering
def nice_date(iso):
    return datetime.strptime(iso, "%Y-%m-%d").strftime("%a, %b %d, %Y")


def change_html(latest, prev):
    if not prev:
        return '<span class="muted">first day recorded</span>'
    diff = round(our_rate(latest) - our_rate(prev), 2)
    if diff == 0:
        return f'<span class="muted">no change vs {nice_date(prev["date"])}</span>'
    arrow, cls = ("&#9650;", "up") if diff > 0 else ("&#9660;", "down")
    return (
        f'<span class="{cls}">{arrow} {abs(diff):.2f}</span> '
        f'<span class="muted">vs {nice_date(prev["date"])}</span>'
    )


def chart_svg(rows):
    rows = rows[-TABLE_ROWS:]
    if len(rows) < 2:
        return '<p class="muted">The chart appears once there are two or more days of data.</p>'
    W, H, PL, PR, PT, PB = 640, 210, 52, 14, 14, 30
    vals = [our_rate(r) for r in rows]
    lo, hi = min(vals), max(vals)
    if hi - lo < 0.5:
        mid = (hi + lo) / 2
        lo, hi = mid - 0.25, mid + 0.25
    pad = (hi - lo) * 0.1
    lo, hi = lo - pad, hi + pad
    n = len(rows)

    def x(i):
        return PL + (W - PL - PR) * i / (n - 1)

    def y(v):
        return PT + (H - PT - PB) * (hi - v) / (hi - lo)

    pts = " ".join(f"{x(i):.1f},{y(v):.1f}" for i, v in enumerate(vals))

    return f"""<svg viewBox="0 0 {W} {H}" role="img"
  aria-label="Line chart of our daily USD rate, last {n} days">
  <line class="grid" x1="{PL}" y1="{y(hi):.1f}" x2="{W-PR}" y2="{y(hi):.1f}"/>
  <line class="grid" x1="{PL}" y1="{y(lo):.1f}" x2="{W-PR}" y2="{y(lo):.1f}"/>
  <text class="axis" x="{PL-6}" y="{y(hi)+4:.1f}" text-anchor="end">{hi:.2f}</text>
  <text class="axis" x="{PL-6}" y="{y(lo)+4:.1f}" text-anchor="end">{lo:.2f}</text>
  <text class="axis" x="{PL}" y="{H-8}" text-anchor="start">{rows[0]["date"]}</text>
  <text class="axis" x="{W-PR}" y="{H-8}" text-anchor="end">{rows[-1]["date"]}</text>
  <polyline class="line" points="{pts}"/>
</svg>"""


CSS = """
:root{--bg:#f7f7f5;--card:#fff;--text:#1c1c1a;--muted:#6b6b66;--line:#e3e3de;
--accent:#2563eb;--up:#0f9d6b;--down:#d1342f}
@media (prefers-color-scheme:dark){:root{--bg:#161615;--card:#1f1f1d;--text:#ecece8;
--muted:#9a9a93;--line:#34342f;--accent:#6ea0ff;--up:#3ccf94;--down:#ff7a74}}
*{box-sizing:border-box}
body{margin:0;background:var(--bg);color:var(--text);
font:16px/1.5 system-ui,-apple-system,"Segoe UI",Roboto,sans-serif}
main{max-width:720px;margin:0 auto;padding:24px 16px 48px}
h1{font-size:1.5rem;margin:0 0 4px}
h2{font-size:1.05rem;margin:32px 0 10px}
.sub,.muted{color:var(--muted)}
.sub{margin:0 0 20px}
.hero{background:var(--card);border:1px solid var(--line);border-radius:12px;padding:20px}
.hero .label{color:var(--muted);font-size:.9rem}
.hero .value{font-size:2.6rem;font-weight:700;line-height:1.15;margin:4px 0;
font-variant-numeric:tabular-nums}
.hero .chg{font-size:.9rem}
.hero .calc{margin-top:12px;padding-top:12px;border-top:1px solid var(--line);
font-size:.95rem;font-variant-numeric:tabular-nums}
.up{color:var(--up)}.down{color:var(--down)}
.card{background:var(--card);border:1px solid var(--line);border-radius:12px;padding:12px}
svg{width:100%;height:auto;display:block}
.grid{stroke:var(--line);stroke-width:1}
.axis{fill:var(--muted);font-size:11px}
.line{fill:none;stroke:var(--accent);stroke-width:2.4;stroke-linejoin:round;stroke-linecap:round}
table{width:100%;border-collapse:collapse;font-variant-numeric:tabular-nums}
th,td{text-align:right;padding:8px 6px;border-bottom:1px solid var(--line)}
th:first-child,td:first-child{text-align:left}
th{font-size:.8rem;color:var(--muted);font-weight:600}
td.rate{font-weight:650}
tr:last-child td{border-bottom:0}
footer{margin-top:28px;font-size:.8rem;color:var(--muted)}
a{color:var(--accent)}
@media (max-width:420px){.hero .value{font-size:2.1rem}}
"""


def render_page(history):
    latest = history[-1]
    prev = history[-2] if len(history) > 1 else None
    checked = datetime.fromisoformat(latest["checked"]).strftime("%a, %b %d, %Y %I:%M %p")
    as_of = html.escape(latest.get("as_of") or latest["date"])

    body_rows = "\n".join(
        f'<tr><td>{nice_date(h["date"])}</td><td>{h["selling"]:.2f}</td>'
        f'<td class="rate">{our_rate(h):.2f}</td></tr>'
        for h in reversed(history[-TABLE_ROWS:])
    )

    return f"""<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Daily USD Rate</title>
<style>{CSS}</style>
</head>
<body>
<main>
  <h1>Daily USD rate</h1>
  <p class="sub">Reference rate for student fees: BPI selling rate + PHP {markup_of(latest):.2f}</p>

  <div class="hero">
    <div class="label">Our rate (PHP per USD)</div>
    <div class="value">PHP {our_rate(latest):.2f}</div>
    <div class="chg">{change_html(latest, prev)}</div>
    <div class="calc">BPI selling PHP {latest["selling"]:.2f} + PHP {markup_of(latest):.2f}
      = <strong>PHP {our_rate(latest):.2f}</strong></div>
  </div>
  <p class="muted" style="margin:10px 2px 0">Based on the BPI rate as of {as_of}</p>

  <h2>Last {min(len(history), TABLE_ROWS)} days</h2>
  <div class="card">{chart_svg(history)}</div>

  <h2>History</h2>
  <div class="card">
    <table>
      <thead><tr><th>Date</th><th>BPI selling</th><th>Our rate</th></tr></thead>
      <tbody>
{body_rows}
      </tbody>
    </table>
  </div>

  <footer>
    Page last updated {checked} (Manila time). BPI rates are indicative and may
    change without notice. Source:
    <a href="{BPI_URL}">BPI foreign exchange rates</a>.
  </footer>
</main>
</body>
</html>
"""


# -------------------------------------------------------------------- main
def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--html-file", help="read BPI HTML from this file instead of fetching")
    args = parser.parse_args()

    if args.html_file:
        page_html = Path(args.html_file).read_text(encoding="utf-8")
    else:
        page_html = fetch_html()

    as_of, rate_date, buying, selling = parse_usd(page_html)
    entry = {
        "date": rate_date,
        "as_of": as_of,
        "buying": buying,
        "selling": selling,
        "markup": MARKUP,
        "our_rate": round(selling + MARKUP, 2),
        "checked": datetime.now(TZ).isoformat(timespec="seconds"),
    }
    history = update_history(load_history(), entry)

    DOCS.mkdir(exist_ok=True)
    HISTORY_FILE.write_text(json.dumps(history, indent=2) + "\n", encoding="utf-8")
    PAGE_FILE.write_text(render_page(history), encoding="utf-8")

    print(
        f"{rate_date}: BPI selling {selling:.2f} + {MARKUP:.2f} = our rate {entry['our_rate']:.2f} "
        f"({as_of or 'time not shown'})"
    )
    print(f"History rows: {len(history)}. Wrote {PAGE_FILE.name} and {HISTORY_FILE.name}.")
    return 0


if __name__ == "__main__":
    sys.exit(main())