"""
Fetches pinned repos and recently pushed-to repos from GitHub and writes them
into README.md as plain text, between the repos section markers.

Runs inside .github/workflows/update-repos.yml, nothing here needs to be
edited by hand.
"""

import json
import os
import re
import sys
import textwrap
import urllib.request
from datetime import datetime, timezone

TOKEN = os.environ["GH_TOKEN"]
USERNAME = os.environ.get("GH_USERNAME", "RuHRabin")
README_PATH = "README.md"

START = "<!--START_SECTION:repos-->"
END = "<!--END_SECTION:repos-->"
PROMPT = "rabin@kernel:~$"
WIDTH = 72

QUERY = """
query($login: String!) {
  user(login: $login) {
    pinnedItems(first: 6, types: REPOSITORY) {
      nodes {
        ... on Repository {
          name
          description
          primaryLanguage { name }
          stargazerCount
        }
      }
    }
    repositories(first: 8, ownerAffiliations: OWNER, isFork: false, orderBy: {field: PUSHED_AT, direction: DESC}) {
      nodes {
        name
        pushedAt
        primaryLanguage { name }
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


def clean(text):
    return " ".join((text or "").replace("```", "").split())


def render_pinned(nodes):
    lines = [f"{PROMPT} ls -l ~/pinned"]
    if not nodes:
        lines.append("(nothing pinned)")
        return lines
    name_w = max(len(n["name"]) for n in nodes) + 2
    for n in nodes:
        lang = (n.get("primaryLanguage") or {}).get("name", "-")
        stars = n.get("stargazerCount", 0)
        lines.append(f'{n["name"].ljust(name_w)}{lang.ljust(12)}{stars} stars')
        desc = clean(n.get("description"))
        if desc:
            wrapped = textwrap.wrap(desc, WIDTH - 2)
            if len(wrapped) > 2:
                wrapped = wrapped[:2]
                wrapped[1] = wrapped[1][: WIDTH - 5].rstrip() + "..."
            lines.extend("  " + w for w in wrapped)
    return lines


def render_recent(nodes):
    lines = [f"{PROMPT} ls -lt ~/recent"]
    if not nodes:
        lines.append("(no recent activity)")
        return lines
    name_w = max(len(n["name"]) for n in nodes) + 2
    for n in nodes:
        lang = (n.get("primaryLanguage") or {}).get("name", "-")
        lines.append(f'{n["name"].ljust(name_w)}{lang.ljust(12)}{humanize(n["pushedAt"])}')
    return lines


def build_block(pinned_nodes, recent_nodes):
    body = render_pinned(pinned_nodes) + [""] + render_recent(recent_nodes)
    return f"{START}\n```\n" + "\n".join(body) + f"\n```\n{END}"


def replace_section(content, new_block):
    pattern = re.compile(re.escape(START) + r".*?" + re.escape(END), re.S)
    if not pattern.search(content):
        sys.exit(f"Could not find {START} ... {END} markers in {README_PATH}.")
    return pattern.sub(lambda _m: new_block, content)


def main():
    user = graphql(QUERY, {"login": USERNAME})["user"]
    pinned = [n for n in user["pinnedItems"]["nodes"] if n]
    recent = [
        n for n in user["repositories"]["nodes"]
        if n["name"].lower() != USERNAME.lower()
    ][:5]

    with open(README_PATH, "r", encoding="utf-8") as f:
        content = f.read()
    content = replace_section(content, build_block(pinned, recent))
    with open(README_PATH, "w", encoding="utf-8") as f:
        f.write(content)

    print(f"Pinned: {[n['name'] for n in pinned]}")
    print(f"Recent: {[n['name'] for n in recent]}")


if __name__ == "__main__":
    main()
