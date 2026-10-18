#!/usr/bin/env python3
"""Keep the project sections of README.md in sync with GitHub.

Pure standard library, no dependencies. Run by .github/workflows/update-pinned.yml
(hourly, on push, or by hand). It rewrites only the text between marker comments:

    <!--STATS:START--> ... <!--STATS:END-->
    <!--PINNED:START--> ... <!--PINNED:END-->
    <!--POPULAR:START--> ... <!--POPULAR:END-->
    <!--RECENT:START--> ... <!--RECENT:END-->

Output contains no timestamps, so the README only changes (and only gets a new
commit) when something about your repos really changed.
"""
import json
import os
import re
import sys
import urllib.error
import urllib.request

USER = os.environ.get("GH_USER", "RuHRabin")
TOKEN = os.environ.get("GITHUB_TOKEN", "")
README = os.environ.get(
    "README_PATH",
    os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "README.md"),
)
PINNED_LIMIT = 6
RECENT_LIMIT = 3
POPULAR_LIMIT = 3
API = "https://api.github.com"


# ───────────────────────────── GitHub access ─────────────────────────────
def _request(url, payload=None):
    headers = {
        "Accept": "application/vnd.github+json",
        "User-Agent": f"{USER}-profile-readme-sync",
        "X-GitHub-Api-Version": "2022-11-28",
    }
    if TOKEN:
        headers["Authorization"] = f"Bearer {TOKEN}"
    data = json.dumps(payload).encode() if payload is not None else None
    req = urllib.request.Request(url, data=data, headers=headers)
    with urllib.request.urlopen(req, timeout=30) as resp:
        return json.load(resp)


def fetch_repos():
    """All public, non-fork, non-archived repos you own, newest push first."""
    repos, page = [], 1
    while True:
        batch = _request(f"{API}/users/{USER}/repos?per_page=100&type=owner&sort=pushed&page={page}")
        repos += batch
        if len(batch) < 100:
            break
        page += 1
    keep = [
        r for r in repos
        if not r.get("fork") and not r.get("archived") and r["name"].lower() != USER.lower()
    ]
    keep.sort(key=lambda r: r.get("pushed_at") or "", reverse=True)
    for r in keep:
        # The list endpoint reports stars as "watchers_count". Real watchers are
        # "subscribers_count", which only the single-repo endpoint returns.
        try:
            r["watchers"] = _request(f"{API}/repos/{r['full_name']}").get("subscribers_count", 0)
        except urllib.error.URLError:
            r["watchers"] = 0
    return keep


def fetch_pinned():
    """Your pinned repos in pinned order (needs a token; returns [] without one)."""
    if not TOKEN:
        return []
    query = """
    query($login: String!, $n: Int!) {
      user(login: $login) {
        pinnedItems(first: $n, types: REPOSITORY) {
          nodes { ... on Repository { name } }
        }
      }
    }"""
    data = _request(f"{API}/graphql", {"query": query, "variables": {"login": USER, "n": PINNED_LIMIT}})
    if data.get("errors"):
        raise RuntimeError(f"GraphQL error: {data['errors']}")
    return [n["name"] for n in data["data"]["user"]["pinnedItems"]["nodes"] if n]


# ───────────────────────────── rendering ─────────────────────────────
def clean(text, limit=80):
    text = re.sub(r"\s+", " ", (text or "").strip()).replace("|", "\\|")
    if not text:
        return "<sub>no description yet</sub>"
    return text if len(text) <= limit else text[: limit - 1].rstrip() + "…"


def day(iso):
    return (iso or "")[:10] or "–"


def render_stats(repos):
    total_stars = sum(stars(r) for r in repos)
    langs = sorted({r["language"] for r in repos if r.get("language")})
    lang_txt = ", ".join(langs) if langs else "–"
    return (
        f"**{len(repos)}** repos &nbsp;·&nbsp; "
        f"**{total_stars}** ★ &nbsp;·&nbsp; "
        f"{lang_txt}"
    )


def render_pinned(repos, pinned_names):
    by_name = {r["name"]: r for r in repos}
    chosen = [by_name[n] for n in pinned_names if n in by_name]
    if not chosen:  # no token / nothing pinned → fall back to most recently pushed
        chosen = repos[:PINNED_LIMIT]
    if not chosen:
        return "_Nothing here yet. The first public repo I publish will show up automatically._"
    rows = ["| project | what it does | language | ★ | updated |", "| :-- | :-- | :-- | --: | :-- |"]
    for r in chosen:
        rows.append(
            f"| [**{r['name']}**]({r['html_url']}) | {clean(r.get('description'))} "
            f"| {('`' + r['language'] + '`') if r.get('language') else '–'} "
            f"| {r.get('stargazers_count', 0)} | {day(r.get('pushed_at'))} |"
        )
    return "\n".join(rows)


def render_recent(repos):
    if not repos:
        return "_Nothing here yet._"
    lines = []
    for r in repos[:RECENT_LIMIT]:
        lang = f" · `{r['language']}`" if r.get("language") else ""
        lines.append(f"- `{day(r.get('pushed_at'))}` &nbsp;[{r['name']}]({r['html_url']}){lang}")
    return "\n".join(lines)


def stars(r):
    return r.get("stargazers_count", 0)


def forks(r):
    return r.get("forks_count", 0)


def watchers(r):
    return r.get("watchers", 0)


def popularity(r):
    """One number for 'most popular': stars + forks + watchers."""
    return stars(r) + forks(r) + watchers(r)


def render_popular(repos):
    """Top repos by stars, forks, watchers and overall popularity.

    Ties break on stars, then on the most recent push, so the order is stable.
    A repo with a zero count is shown as a dash, never ranked.
    """
    if not repos:
        return "_Nothing here yet._"
    cols = [
        ("★ Most starred", stars),
        ("⑂ Most forked", forks),
        ("◉ Most watched", watchers),
        ("✦ Most popular", popularity),
    ]
    ranked = []
    for _, key in cols:
        order = sorted(
            repos,
            key=lambda r: (key(r), stars(r), r.get("pushed_at") or ""),
            reverse=True,
        )
        ranked.append([r for r in order if key(r) > 0][:POPULAR_LIMIT])
    rows = ["| " + " | ".join(c[0] for c in cols) + " |", "| " + " | ".join([":--"] * len(cols)) + " |"]
    for i in range(POPULAR_LIMIT):
        cells = []
        for (_, key), col in zip(cols, ranked):
            cells.append(f"[**{col[i]['name']}**]({col[i]['html_url']}) · `{key(col[i])}`" if i < len(col) else "–")
        rows.append("| " + " | ".join(cells) + " |")
    return "\n".join(rows)


def replace_block(text, name, body):
    pattern = re.compile(rf"(<!--{name}:START-->)(.*?)(<!--{name}:END-->)", re.S)
    if not pattern.search(text):
        raise RuntimeError(f"Marker <!--{name}:START--> ... <!--{name}:END--> not found in README.md")
    return pattern.sub(lambda m: f"{m.group(1)}\n{body}\n{m.group(3)}", text, count=1)


def main():
    repos = fetch_repos()
    pinned = fetch_pinned()
    with open(README, encoding="utf-8") as f:
        original = f.read()
    text = original
    text = replace_block(text, "STATS", render_stats(repos))
    text = replace_block(text, "PINNED", render_pinned(repos, pinned))
    text = replace_block(text, "POPULAR", render_popular(repos))
    text = replace_block(text, "RECENT", render_recent(repos))
    if text == original:
        print("README already up to date.")
        return
    with open(README, "w", encoding="utf-8") as f:
        f.write(text)
    print(f"README updated: {len(repos)} repos, {len(pinned)} pinned.")


if __name__ == "__main__":
    try:
        main()
    except (urllib.error.URLError, RuntimeError) as exc:
        print(f"sync failed: {exc}", file=sys.stderr)
        sys.exit(1)
