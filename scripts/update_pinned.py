"""
Pulls live data from GitHub (pinned repos, recently pushed-to repos, and
contribution streaks) and renders three custom, self-contained SVG boards —
no third-party widget service involved, so nothing here can go down the way
the old activity graph did. Each board has its own hand-built reveal
animation.

Runs inside .github/workflows/update-pinned.yml — nothing here needs to be
edited by hand.
"""

import json
import os
import re
import sys
import urllib.request
from datetime import date, datetime, timedelta, timezone

TOKEN = os.environ["GH_TOKEN"]
USERNAME = os.environ.get("GH_USERNAME", "RuHRabin")
README_PATH = "README.md"
ASSETS_DIR = "assets"

PINNED_START, PINNED_END = "<!--START_SECTION:pinned-->", "<!--END_SECTION:pinned-->"
RECENT_START, RECENT_END = "<!--START_SECTION:recent-->", "<!--END_SECTION:recent-->"
STREAK_START, STREAK_END = "<!--START_SECTION:streak-->", "<!--END_SECTION:streak-->"

# ---- palette (matches README) -------------------------------------------
CARD_BG = "#262c31"
CARD_STROKE = "#333a40"
ACCENT_BLUE = "#3B82F6"
ACCENT_CYAN = "#22D3EE"
ACCENT_GREEN = "#34D399"
GRADIENT_DEF = (
    '<linearGradient id="accentGrad" x1="0%" y1="0%" x2="100%" y2="100%">'
    '<stop offset="0%" stop-color="#3B82F6"/>'
    '<stop offset="50%" stop-color="#22D3EE"/>'
    '<stop offset="100%" stop-color="#34D399"/>'
    "</linearGradient>"
)
TITLE_COLOR = "#f0ece4"
DESC_COLOR = "#9aa4ad"
META_COLOR = "#22D3EE"
FONT_STACK = "-apple-system,BlinkMacSystemFont,Segoe UI,Helvetica,Arial,sans-serif"

CARD_W, CARD_H, GAP, COLS = 336, 108, 16, 2

MAIN_QUERY = """
query($login: String!) {
  user(login: $login) {
    createdAt
    pinnedItems(first: 6, types: REPOSITORY) {
      nodes {
        ... on Repository {
          name
          description
          url
          primaryLanguage { name }
          stargazerCount
        }
      }
    }
    repositories(first: 8, ownerAffiliations: OWNER, isFork: false, orderBy: {field: PUSHED_AT, direction: DESC}) {
      nodes {
        name
        description
        url
        pushedAt
        primaryLanguage { name }
      }
    }
  }
}
"""

CONTRIB_QUERY = """
query($login: String!, $from: DateTime!, $to: DateTime!) {
  user(login: $login) {
    contributionsCollection(from: $from, to: $to) {
      contributionCalendar {
        weeks {
          contributionDays {
            date
            contributionCount
          }
        }
      }
    }
  }
}
"""


def graphql(query, variables):
    payload = json.dumps({"query": query, "variables": variables}).encode()
    req = urllib.request.Request(
        "https://api.github.com/graphql",
        data=payload,
        headers={
            "Authorization": f"bearer {TOKEN}",
            "Content-Type": "application/json",
            "User-Agent": USERNAME,
        },
    )
    with urllib.request.urlopen(req) as resp:
        data = json.load(resp)
    if "errors" in data:
        sys.exit(f"GraphQL error: {data['errors']}")
    return data["data"]


def humanize(iso_ts):
    then = datetime.strptime(iso_ts, "%Y-%m-%dT%H:%M:%SZ").replace(tzinfo=timezone.utc)
    days = (datetime.now(timezone.utc) - then).days
    if days < 1:
        return "today"
    if days == 1:
        return "yesterday"
    if days < 30:
        return f"{days} days ago"
    months = days // 30
    return f"{months} month{'s' if months != 1 else ''} ago"


# ---- contribution streaks --------------------------------------------------

def fetch_all_contribution_days(created_at_iso):
    """Walks year by year from account creation to now and returns a
    {'YYYY-MM-DD': contributionCount} map covering the full account history."""
    created_year = int(created_at_iso[:4])
    now = datetime.now(timezone.utc)

    days = {}
    for year in range(created_year, now.year + 1):
        year_start = datetime(year, 1, 1, tzinfo=timezone.utc)
        year_end = datetime(year + 1, 1, 1, tzinfo=timezone.utc)
        to_dt = min(year_end, now)
        if to_dt <= year_start:
            continue
        data = graphql(
            CONTRIB_QUERY,
            {
                "login": USERNAME,
                "from": year_start.strftime("%Y-%m-%dT%H:%M:%SZ"),
                "to": to_dt.strftime("%Y-%m-%dT%H:%M:%SZ"),
            },
        )
        weeks = data["user"]["contributionsCollection"]["contributionCalendar"]["weeks"]
        for week in weeks:
            for day in week["contributionDays"]:
                days[day["date"]] = day["contributionCount"]

    return days


def compute_streaks(day_counts):
    if not day_counts:
        return 0, 0, 0

    sorted_dates = sorted(day_counts.keys())
    total = sum(day_counts.values())

    cursor = date.fromisoformat(sorted_dates[-1])
    # Today may simply not be over yet -- don't count a zero "today" as a
    # broken streak, just start counting from yesterday instead.
    if day_counts.get(cursor.isoformat(), 0) == 0:
        cursor -= timedelta(days=1)

    current = 0
    while day_counts.get(cursor.isoformat(), 0) > 0:
        current += 1
        cursor -= timedelta(days=1)

    longest, run, prev_date = 0, 0, None
    for d_str in sorted_dates:
        d = date.fromisoformat(d_str)
        if day_counts[d_str] > 0:
            run = run + 1 if prev_date and d == prev_date + timedelta(days=1) and day_counts.get(prev_date.isoformat(), 0) > 0 else 1
            longest = max(longest, run)
        else:
            run = 0
        prev_date = d

    return current, longest, total


# ---- SVG rendering ----------------------------------------------------------

def esc(s):
    return (
        (s or "")
        .replace("&", "&amp;")
        .replace("<", "&lt;")
        .replace(">", "&gt;")
        .replace('"', "&quot;")
    )


def wrap_text(text, max_chars):
    words = (text or "").split()
    lines, current = [], ""
    for w in words:
        trial = f"{current} {w}".strip()
        if len(trial) <= max_chars:
            current = trial
        else:
            if current:
                lines.append(current)
            current = w
    if current:
        lines.append(current)
    return lines


def truncate_lines(lines, max_lines, max_chars):
    if len(lines) <= max_lines:
        return lines
    kept = lines[:max_lines]
    last = kept[-1]
    if len(last) > max_chars - 1:
        last = last[: max_chars - 1].rstrip()
    kept[-1] = last + "…"
    return kept


def render_empty_board(message, width=None, height=64):
    width = width or (2 * CARD_W + GAP)
    return f'''<svg xmlns="http://www.w3.org/2000/svg" width="{width}" height="{height}" viewBox="0 0 {width} {height}" font-family="{FONT_STACK}">
<rect width="{width}" height="{height}" rx="10" fill="{CARD_BG}" stroke="{CARD_STROKE}"/>
<text x="{width/2}" y="{height/2+5}" font-size="13" fill="{DESC_COLOR}" text-anchor="middle">{esc(message)}</text>
</svg>'''


def render_board(items):
    if not items:
        return render_empty_board("Nothing to show yet.")

    n = len(items)
    cols = COLS if n > 1 else 1
    rows = -(-n // cols)
    width = cols * CARD_W + (cols - 1) * GAP
    height = rows * CARD_H + (rows - 1) * GAP

    parts = [
        f'<svg xmlns="http://www.w3.org/2000/svg" width="{width}" height="{height}" '
        f'viewBox="0 0 {width} {height}" font-family="{FONT_STACK}">',
        f'<defs>{GRADIENT_DEF}</defs>',
    ]

    for i, item in enumerate(items):
        col, row = i % cols, i // cols
        x = col * (CARD_W + GAP)
        y = row * (CARD_H + GAP)
        delay = round(i * 0.12, 2)

        title = item["name"]
        if len(title) > 34:
            title = title[:33] + "…"

        desc_lines = truncate_lines(wrap_text(item.get("description"), 46), 2, 46)
        meta = item.get("meta", "")

        parts.append(f'<g transform="translate({x},{y})" opacity="0">')
        parts.append(
            f'<animate attributeName="opacity" from="0" to="1" begin="{delay}s" '
            f'dur="0.45s" fill="freeze" calcMode="spline" keySplines="0.25 0.1 0.25 1"/>'
        )
        parts.append(
            f'<animateTransform attributeName="transform" type="translate" '
            f'from="{x} {y+10}" to="{x} {y}" begin="{delay}s" dur="0.45s" fill="freeze" '
            f'calcMode="spline" keySplines="0.25 0.1 0.25 1"/>'
        )
        parts.append(
            f'<rect x="0" y="0" width="{CARD_W}" height="{CARD_H}" rx="10" '
            f'fill="{CARD_BG}" stroke="{CARD_STROKE}" stroke-width="1"/>'
        )
        parts.append(
            f'<line x1="0" y1="10" x2="0" y2="{CARD_H-10}" stroke="url(#accentGrad)" '
            f'stroke-width="3" stroke-linecap="round" '
            f'stroke-dasharray="{CARD_H-20}" stroke-dashoffset="{CARD_H-20}">'
            f'<animate attributeName="stroke-dashoffset" from="{CARD_H-20}" to="0" '
            f'begin="{delay+0.15}s" dur="0.35s" fill="freeze"/></line>'
        )
        parts.append(
            f'<text x="18" y="28" font-size="15" font-weight="600" '
            f'fill="{TITLE_COLOR}">{esc(title)}</text>'
        )
        for li, line in enumerate(desc_lines):
            parts.append(
                f'<text x="18" y="{48 + li*16}" font-size="12" '
                f'fill="{DESC_COLOR}">{esc(line)}</text>'
            )
        if meta:
            parts.append(
                f'<text x="18" y="{CARD_H-14}" font-size="11" '
                f'fill="{META_COLOR}">{esc(meta)}</text>'
            )
        parts.append("</g>")

    parts.append("</svg>")
    return "\n".join(parts)


def render_stat_strip(current_streak, longest_streak, total_contributions):
    cols = [
        (str(current_streak), "current streak"),
        (str(longest_streak), "longest streak"),
        (str(total_contributions), "all-time contributions"),
    ]
    width, height = 688, 128
    col_w = width / 3

    parts = [
        f'<svg xmlns="http://www.w3.org/2000/svg" width="{width}" height="{height}" '
        f'viewBox="0 0 {width} {height}" font-family="{FONT_STACK}">',
        f'<defs>{GRADIENT_DEF}</defs>',
        f'<rect x="0" y="0" width="{width}" height="{height}" rx="10" '
        f'fill="{CARD_BG}" stroke="{CARD_STROKE}" stroke-width="1"/>',
    ]

    for i, (value, label) in enumerate(cols):
        cx = col_w * i + col_w / 2
        cy = height / 2 + 8
        delay = round(i * 0.15, 2)

        if i > 0:
            parts.append(
                f'<line x1="{col_w*i}" y1="24" x2="{col_w*i}" y2="{height-24}" '
                f'stroke="{CARD_STROKE}" stroke-width="1"/>'
            )

        parts.append(f'<g opacity="0" transform="translate({cx},{cy})">')
        parts.append(
            f'<animate attributeName="opacity" from="0" to="1" begin="{delay}s" '
            f'dur="0.5s" fill="freeze" calcMode="spline" keySplines="0.25 0.1 0.25 1"/>'
        )
        parts.append(
            f'<animateTransform attributeName="transform" type="translate" '
            f'from="{cx} {cy+12}" to="{cx} {cy}" begin="{delay}s" dur="0.5s" fill="freeze" '
            f'calcMode="spline" keySplines="0.25 0.1 0.25 1"/>'
        )
        parts.append(
            f'<text x="0" y="0" font-size="34" font-weight="700" '
            f'fill="url(#accentGrad)" text-anchor="middle">{esc(value)}</text>'
        )
        parts.append(
            f'<text x="0" y="24" font-size="11" fill="{DESC_COLOR}" '
            f'text-anchor="middle" letter-spacing="0.5">{esc(label)}</text>'
        )
        parts.append("</g>")

    parts.append("</svg>")
    return "\n".join(parts)


def pinned_meta(node):
    bits = []
    if node.get("primaryLanguage"):
        bits.append(node["primaryLanguage"]["name"])
    bits.append(f'★ {node.get("stargazerCount", 0)}')
    return "  ·  ".join(bits)


def recent_meta(node):
    bits = []
    if node.get("primaryLanguage"):
        bits.append(node["primaryLanguage"]["name"])
    bits.append(f'updated {humanize(node["pushedAt"])}')
    return "  ·  ".join(bits)


def replace_section(content, start, end, new_block):
    pattern = re.compile(re.escape(start) + r".*?" + re.escape(end), re.S)
    if not pattern.search(content):
        sys.exit(f"Could not find {start} ... {end} markers in {README_PATH}.")
    return pattern.sub(new_block, content)


def main():
    os.makedirs(ASSETS_DIR, exist_ok=True)
    main_data = graphql(MAIN_QUERY, {"login": USERNAME})["user"]

    pinned_nodes = main_data["pinnedItems"]["nodes"]
    recent_nodes = [
        n for n in main_data["repositories"]["nodes"]
        if n["name"].lower() != USERNAME.lower()
    ][:5]

    pinned_items = [
        {"name": n["name"], "description": n["description"], "meta": pinned_meta(n)}
        for n in pinned_nodes
    ]
    recent_items = [
        {"name": n["name"], "description": n["description"], "meta": recent_meta(n)}
        for n in recent_nodes
    ]

    with open(f"{ASSETS_DIR}/pinned.svg", "w", encoding="utf-8") as f:
        f.write(render_board(pinned_items))
    with open(f"{ASSETS_DIR}/recent.svg", "w", encoding="utf-8") as f:
        f.write(render_board(recent_items))

    day_counts = fetch_all_contribution_days(main_data["createdAt"])
    current_streak, longest_streak, total_contributions = compute_streaks(day_counts)
    with open(f"{ASSETS_DIR}/streak.svg", "w", encoding="utf-8") as f:
        f.write(render_stat_strip(current_streak, longest_streak, total_contributions))

    with open(README_PATH, "r", encoding="utf-8") as f:
        content = f.read()

    content = replace_section(
        content, PINNED_START, PINNED_END,
        f'{PINNED_START}\n<img src="assets/pinned.svg" width="100%" alt="Pinned projects" />\n{PINNED_END}',
    )
    content = replace_section(
        content, RECENT_START, RECENT_END,
        f'{RECENT_START}\n<img src="assets/recent.svg" width="100%" alt="Recently active repos" />\n{RECENT_END}',
    )
    content = replace_section(
        content, STREAK_START, STREAK_END,
        f'{STREAK_START}\n<img src="assets/streak.svg" width="100%" alt="Contribution streak" />\n{STREAK_END}',
    )

    with open(README_PATH, "w", encoding="utf-8") as f:
        f.write(content)

    print(f"Pinned: {[n['name'] for n in pinned_nodes]}")
    print(f"Recent: {[n['name'] for n in recent_nodes]}")
    print(f"Streak: current={current_streak} longest={longest_streak} total={total_contributions}")


if __name__ == "__main__":
    main()
