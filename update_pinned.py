"""
Fetches the repos currently pinned on a GitHub profile and rewrites the
section of README.md between <!--START_SECTION:pinned--> and
<!--END_SECTION:pinned--> to match.

Runs inside .github/workflows/update-pinned.yml — no manual editing needed.
"""

import json
import os
import re
import sys
import urllib.request

TOKEN = os.environ["GH_TOKEN"]
USERNAME = os.environ.get("GH_USERNAME", "RuHRabin")
README_PATH = "README.md"
START = "<!--START_SECTION:pinned-->"
END = "<!--END_SECTION:pinned-->"

QUERY = """
query($login: String!) {
  user(login: $login) {
    pinnedItems(first: 6, types: REPOSITORY) {
      nodes {
        ... on Repository {
          name
        }
      }
    }
  }
}
"""


def fetch_pinned_repo_names():
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

    nodes = data["data"]["user"]["pinnedItems"]["nodes"]
    return [n["name"] for n in nodes]


def build_section(repo_names):
    cards = []
    for repo in repo_names:
        pin_url = (
            "https://github-stats-extended.vercel.app/api/pin/"
            f"?username={USERNAME}&repo={repo}"
            "&theme=dark&hide_border=true&bg_color=1e2327"
            "&title_color=4FD6FF&text_color=ffffff&icon_color=4FD6FF"
        )
        cards.append(
            f'<a href="https://github.com/{USERNAME}/{repo}">'
            f'<img src="{pin_url}" /></a>'
        )
    cards_block = "\n".join(cards)
    return f'{START}\n<div align="center">\n\n{cards_block}\n\n</div>\n{END}'


def main():
    repo_names = fetch_pinned_repo_names()
    if not repo_names:
        print("No pinned repos found — leaving README.md unchanged.")
        return

    with open(README_PATH, "r", encoding="utf-8") as f:
        content = f.read()

    pattern = re.compile(re.escape(START) + r".*?" + re.escape(END), re.S)
    if not pattern.search(content):
        sys.exit(
            f"Could not find {START} ... {END} markers in {README_PATH}. "
            "Add them once and re-run."
        )

    content = pattern.sub(build_section(repo_names), content)

    with open(README_PATH, "w", encoding="utf-8") as f:
        f.write(content)

    print(f"Updated pinned section with: {', '.join(repo_names)}")


if __name__ == "__main__":
    main()
