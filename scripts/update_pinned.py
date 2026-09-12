"""
Pulls live data from GitHub (pinned repos + recently pushed-to repos) and
rewrites the matching marked sections of README.md as plain markdown lists —
no third-party image widgets involved, so nothing here can go down.

Runs inside .github/workflows/update-pinned.yml — nothing here needs to be
edited by hand.
"""

import json
import os
import re
import sys
import urllib.request
from datetime import datetime, timezone

TOKEN = os.environ["GH_TOKEN"]
USERNAME = os.environ.get("GH_USERNAME", "RuHRabin")
README_PATH = "README.md"

PINNED_START, PINNED_END = "<!--START_SECTION:pinned-->", "<!--END_SECTION:pinned-->"
RECENT_START, RECENT_END = "<!--START_SECTION:recent-->", "<!--END_SECTION:recent-->"

QUERY = """
query($login: String!) {
  user(login: $login) {
    pinnedItems(first: 6, types: REPOSITORY) {
      nodes {
        ... on Repository {
          name
          description
          url
        }
      }
    }
    repositories(first: 8, ownerAffiliations: OWNER, isFork: false, orderBy: {field: PUSHED_AT, direction: DESC}) {
      nodes {
        name
        description
        url
        pushedAt
      }
    }
  }
}
"""


def fetch_data():
    payload = json.dumps({"query": QUERY, "variables": {"login": USERNAME}}).encode()
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
    return data["data"]["user"]


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


def bullet(name, description, url, suffix=""):
    desc = f" — {description}" if description else ""
    return f"- **[{name}]({url})**{desc}{suffix}"


def build_pinned_section(nodes):
    if not nodes:
        body = "_No repos currently pinned._"
    else:
        body = "\n".join(bullet(n["name"], n["description"], n["url"]) for n in nodes)
    return f"{PINNED_START}\n{body}\n{PINNED_END}"


def build_recent_section(nodes):
    filtered = [n for n in nodes if n["name"].lower() != USERNAME.lower()][:5]
    if not filtered:
        body = "_Nothing recent to show._"
    else:
        body = "\n".join(
            bullet(n["name"], n["description"], n["url"], f", updated {humanize(n['pushedAt'])}")
            for n in filtered
        )
    return f"{RECENT_START}\n{body}\n{RECENT_END}"


def replace_section(content, start, end, new_block):
    pattern = re.compile(re.escape(start) + r".*?" + re.escape(end), re.S)
    if not pattern.search(content):
        sys.exit(f"Could not find {start} ... {end} markers in {README_PATH}.")
    return pattern.sub(new_block, content)


def main():
    user_data = fetch_data()
    pinned_nodes = user_data["pinnedItems"]["nodes"]
    recent_nodes = user_data["repositories"]["nodes"]

    with open(README_PATH, "r", encoding="utf-8") as f:
        content = f.read()

    content = replace_section(content, PINNED_START, PINNED_END, build_pinned_section(pinned_nodes))
    content = replace_section(content, RECENT_START, RECENT_END, build_recent_section(recent_nodes))

    with open(README_PATH, "w", encoding="utf-8") as f:
        f.write(content)

    print(f"Pinned: {[n['name'] for n in pinned_nodes]}")
    print(f"Recent: {[n['name'] for n in recent_nodes][:5]}")


if __name__ == "__main__":
    main()
