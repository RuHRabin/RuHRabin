#!/usr/bin/env python3
"""Generate self-hosted GitHub profile SVG cards using GitHub GraphQL."""
import json
import os
import re
import sys
import urllib.request
import urllib.error
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from xml.sax.saxutils import escape

USERNAME = os.environ.get("GITHUB_USERNAME", "RuHRabin")
TOKEN = os.environ.get("GITHUB_TOKEN")
OUT = Path("assets")
OUT.mkdir(exist_ok=True)

THEMES = {
    "dark": dict(bg="#1a1b27", panel="#24283b", text="#c0caf5", muted="#a9b1d6",
                 accent="#7aa2f7", green="#9ece6a", purple="#bb9af7",
                 orange="#e0af68", grid="#414868"),
    "light": dict(bg="#ffffff", panel="#f3f5fb", text="#24283b", muted="#565f89",
                  accent="#3451a3", green="#387a36", purple="#7545a5",
                  orange="#986515", grid="#d8deef"),
}
QUERY = """
query($login: String!, $from: DateTime!, $to: DateTime!) {
  user(login: $login) {
    login
    status { emoji emojiHTML message }
    followers { totalCount }
    repositories(ownerAffiliations: OWNER, first: 100, privacy: PUBLIC,
      isFork: false, orderBy: {field: UPDATED_AT, direction: DESC}) {
      totalCount
      nodes {
        stargazerCount
        forkCount
        languages(first: 10, orderBy: {field: SIZE, direction: DESC}) {
          edges { size node { name } }
        }
      }
    }
    contributionsCollection(from: $from, to: $to) {
      totalCommitContributions
      totalPullRequestContributions
      totalIssueContributions
      contributionCalendar {
        totalContributions
        weeks { contributionDays { date contributionCount } }
      }
    }
  }
}
"""

def fetch():
    if not TOKEN:
        raise RuntimeError("GITHUB_TOKEN is missing.")
    today = datetime.now(timezone.utc).date()
    start = today - timedelta(days=364)
    variables = {"login": USERNAME, "from": start.isoformat()+"T00:00:00Z",
                 "to": today.isoformat()+"T23:59:59Z"}
    payload = json.dumps({"query": QUERY, "variables": variables}).encode()
    req = urllib.request.Request("https://api.github.com/graphql", data=payload,
        headers={"Authorization": "Bearer " + TOKEN,
                 "Content-Type": "application/json",
                 "User-Agent": "RuHRabin-profile-stats"}, method="POST")
    try:
        with urllib.request.urlopen(req, timeout=30) as response:
            result = json.loads(response.read().decode())
    except urllib.error.HTTPError as exc:
        raise RuntimeError("GitHub API HTTP %s: %s" %
                           (exc.code, exc.read().decode(errors="replace"))) from exc
    if result.get("errors"):
        raise RuntimeError("GitHub GraphQL error: " + json.dumps(result["errors"]))
    user = result.get("data", {}).get("user")
    if not user:
        raise RuntimeError("GitHub user %r was not found." % USERNAME)
    return user

def svg(name, title, width, height, body_fn):
    for theme, t in THEMES.items():
        body = body_fn(t)
        doc = f"""<svg xmlns="http://www.w3.org/2000/svg" width="{width}" height="{height}" viewBox="0 0 {width} {height}" role="img" aria-label="{escape(title)}">
<title>{escape(title)}</title>
<rect width="100%" height="100%" rx="16" fill="{t['bg']}"/>
<style>
text {{ font-family: Inter, -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif; }}
.title {{ fill: {t['text']}; font-size: 20px; font-weight: 700; }}
.label {{ fill: {t['muted']}; font-size: 12px; }}
.value {{ fill: {t['text']}; font-size: 25px; font-weight: 700; }}
.small {{ fill: {t['muted']}; font-size: 11px; }}
</style>
{body}
</svg>"""
        (OUT / f"{name}.{theme}.svg").write_text(doc, encoding="utf-8")

def metric_card(x, y, label, value, accent, t):
    return (f'<rect x="{x}" y="{y}" width="250" height="108" rx="12" fill="{t["panel"]}"/>'
            f'<rect x="{x}" y="{y}" width="4" height="108" rx="2" fill="{accent}"/>'
            f'<text x="{x+18}" y="{y+30}" class="label">{escape(label)}</text>'
            f'<text x="{x+18}" y="{y+70}" class="value">{escape(str(value))}</text>')

def status_badge(user):
    """Write assets/status.svg from the live GitHub profile status."""
    st = user.get("status") or {}
    message = (st.get("message") or "").strip() or "Focusing"
    emoji = re.sub(r"<[^>]+>", "", st.get("emojiHTML") or "").strip()
    if not st and not emoji:
        emoji = "\U0001F3AF"          # default when no profile status is set
    message = message[:40]
    text = (emoji + " " + message).strip()
    label = "Status"
    lw = 12 + 7 * len(label)
    rw = 14 + int(6.6 * (len(message) + (2 if emoji else 0)))
    w = lw + rw
    doc = (
        f'<svg xmlns="http://www.w3.org/2000/svg" width="{w}" height="20" role="img" '
        f'aria-label="{escape(label)}: {escape(text)}">'
        f'<title>{escape(label)}: {escape(text)}</title>'
        f'<rect width="{lw}" height="20" fill="#1a1b27"/>'
        f'<rect x="{lw}" width="{rw}" height="20" fill="#bb9af7"/>'
        '<g font-family="Verdana,Geneva,DejaVu Sans,sans-serif" font-size="11" text-anchor="middle">'
        f'<text x="{lw/2:.1f}" y="14" fill="#ffffff">{escape(label)}</text>'
        f'<text x="{lw+rw/2:.1f}" y="14" fill="#1a1b27" font-weight="bold">{escape(text)}</text>'
        '</g></svg>'
    )
    (OUT / "status.svg").write_text(doc, encoding="utf-8")

def main():
    user = fetch()
    status_badge(user)
    repos = user["repositories"]["nodes"]
    cc = user["contributionsCollection"]
    calendar = cc["contributionCalendar"]
    days = [d for w in calendar["weeks"] for d in w["contributionDays"]]
    total_stars = sum(r["stargazerCount"] for r in repos)
    total_forks = sum(r["forkCount"] for r in repos)

    def overview(t):
        metrics = [
            ("PUBLIC REPOSITORIES", user["repositories"]["totalCount"], t["accent"]),
            ("FOLLOWERS", user["followers"]["totalCount"], t["purple"]),
            ("TOTAL STARS", total_stars, t["green"]),
            ("TOTAL FORKS", total_forks, t["orange"]),
            ("COMMITS · 12 MONTHS", cc["totalCommitContributions"], t["accent"]),
            ("PULL REQUESTS", cc["totalPullRequestContributions"], t["purple"]),
            ("ISSUES", cc["totalIssueContributions"], t["green"]),
            ("CONTRIBUTIONS", calendar["totalContributions"], t["orange"]),
        ]
        out = f'<text x="28" y="36" class="title">GitHub Overview · {escape(USERNAME)}</text>'
        for i, (label, val, color) in enumerate(metrics):
            out += metric_card(28+(i%4)*270, 52+(i//4)*124, label, f"{val:,}", color, t)
        return out
    svg("overview", "GitHub Overview", 1108, 310, overview)

    language_totals = {}
    for repo in repos:
        for edge in repo["languages"]["edges"]:
            lang = edge["node"]["name"]
            language_totals[lang] = language_totals.get(lang, 0) + edge["size"]
    ranked = sorted(language_totals.items(), key=lambda x: x[1], reverse=True)[:8]
    palette = ["#7aa2f7", "#9ece6a", "#bb9af7", "#e0af68",
               "#f7768e", "#7dcfff", "#2ac3de", "#c0caf5"]
    def languages(t):
        out = '<text x="28" y="36" class="title">Top Programming Languages · Public Repositories</text>'
        total = sum(v for _, v in ranked) or 1
        if not ranked:
            return out + '<text x="28" y="90" class="label">No public language data found.</text>'
        offset = 0
        for i, (name, size) in enumerate(ranked):
            w = 1052 * size / total
            out += f'<rect x="{28+offset:.1f}" y="58" width="{max(w,1):.1f}" height="14" fill="{palette[i]}"/>'
            offset += w
        for i, (name, size) in enumerate(ranked):
            x = 32 + (i%2)*530
            y = 112 + (i//2)*43
            out += f'<circle cx="{x+5}" cy="{y-4}" r="5" fill="{palette[i]}"/>'
            out += f'<text x="{x+19}" y="{y}" class="label">{escape(name)}</text>'
            out += f'<text x="{x+490}" y="{y}" text-anchor="end" class="label">{size/total*100:.1f}%</text>'
        return out
    svg("languages", "Top Programming Languages", 1108, 300, languages)

    counts = {date.fromisoformat(d["date"]): d["contributionCount"] for d in days}
    today = date.today()
    current = 0
    cursor = today
    while cursor in counts and counts[cursor] > 0:
        current += 1
        cursor -= timedelta(days=1)
    if current == 0:
        cursor = today - timedelta(days=1)
        while cursor in counts and counts[cursor] > 0:
            current += 1
            cursor -= timedelta(days=1)
    best = run = 0
    previous = None
    for day in sorted(counts):
        if counts[day] > 0 and (previous is None or day == previous + timedelta(days=1)):
            run += 1
        elif counts[day] > 0:
            run = 1
        else:
            run = 0
        best = max(best, run)
        previous = day

    def contributions(t):
        out = '<text x="28" y="36" class="title">Contribution Activity · Last 12 Months</text>'
        out += metric_card(28, 50, "CONTRIBUTIONS", f'{calendar["totalContributions"]:,}', t["accent"], t)
        out += metric_card(298, 50, "CURRENT STREAK", f"{current} days", t["green"], t)
        out += metric_card(568, 50, "LONGEST STREAK", f"{best} days", t["purple"], t)
        out += metric_card(838, 50, "COMMITS", f'{cc["totalCommitContributions"]:,}', t["orange"], t)
        max_count = max((d["contributionCount"] for d in days), default=1) or 1
        palette_heat = [t["panel"], "#263b5b" if t["bg"] == THEMES["dark"]["bg"] else "#dce7f8",
                        "#345b83" if t["bg"] == THEMES["dark"]["bg"] else "#a9c4eb",
                        "#477db0" if t["bg"] == THEMES["dark"]["bg"] else "#7099d2", t["accent"]]
        out += '<text x="30" y="183" class="small">Daily contribution calendar</text>'
        for i, d in enumerate(days):
            week, dow = divmod(i, 7)
            x, y = 30+week*14, 196+dow*14
            if x <= 1060:
                count = d["contributionCount"]
                level = 0 if count == 0 else min(4, 1+int(count/max_count*3))
                out += f'<rect x="{x}" y="{y}" width="11" height="11" rx="2" fill="{palette_heat[level]}"><title>{escape(d["date"])}: {count} contributions</title></rect>'
        return out
    svg("contributions", "Contribution Calendar and Streak", 1108, 310, contributions)

    weekly = [sum(d["contributionCount"] for d in w["contributionDays"])
              for w in calendar["weeks"]][-52:]
    def momentum(t):
        out = '<text x="28" y="36" class="title">Contribution Momentum · Weekly Activity</text>'
        if not weekly:
            return out + '<text x="28" y="90" class="label">No contribution data available.</text>'
        left, top, width, height = 42, 65, 1020, 185
        peak = max(weekly) or 1
        for j in range(5):
            yy = top+j*height/4
            out += f'<line x1="{left}" y1="{yy:.1f}" x2="{left+width}" y2="{yy:.1f}" stroke="{t["grid"]}"/>'
        points = []
        for i, val in enumerate(weekly):
            x = left+i*width/max(len(weekly)-1, 1)
            y = top+height-(val/peak)*height
            points.append((x,y))
        poly = " ".join(f"{x:.1f},{y:.1f}" for x,y in points)
        area = f"{left},{top+height} "+poly+f" {left+width},{top+height}"
        out += f'<polygon points="{area}" fill="{t["accent"]}" opacity="0.16"/>'
        out += f'<polyline points="{poly}" fill="none" stroke="{t["accent"]}" stroke-width="3" stroke-linecap="round" stroke-linejoin="round"/>'
        out += f'<text x="42" y="285" class="small">52 weeks · weekly contributions</text>'
        out += f'<text x="1062" y="285" text-anchor="end" class="small">Peak: {peak}</text>'
        return out
    svg("momentum", "GitHub Contribution Momentum", 1108, 310, momentum)

    print("Generated 9 SVG files in assets/.")

if __name__ == "__main__":
    try:
        main()
    except Exception as error:
        print(f"ERROR: {error}", file=sys.stderr)
        sys.exit(1)
