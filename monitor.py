#!/usr/bin/env python3
"""Fetch public GitHub repository activity and build a static dashboard."""

from __future__ import annotations

import argparse
import base64
import datetime as dt
import json
import os
import pathlib
import subprocess
import sys
import time
import urllib.error
import urllib.parse
import urllib.request

API = "https://api.github.com"
ROOT = pathlib.Path(__file__).resolve().parent


class GitHub:
    def __init__(self) -> None:
        self.token = os.environ.get("MONITOR_TOKEN")
        if self.token:
            return
        # Prefer a valid GitHub CLI login for local work. In some environments
        # a stale GITHUB_TOKEN is exported globally and would otherwise shadow
        # the token stored by `gh auth login`. Automation can still use its
        # token when gh is unavailable or has no logged-in account.
        env = os.environ.copy()
        env.pop("GITHUB_TOKEN", None)
        env.pop("GH_TOKEN", None)
        try:
            result = subprocess.run(
                ["gh", "auth", "token"],
                check=True,
                capture_output=True,
                text=True,
                env=env,
            )
            self.token = result.stdout.strip() or None
        except (FileNotFoundError, subprocess.CalledProcessError):
            self.token = os.environ.get("GITHUB_TOKEN") or os.environ.get("GH_TOKEN")

    def get(self, path: str):
        headers = {
            "Accept": "application/vnd.github+json",
            "X-GitHub-Api-Version": "2022-11-28",
            "User-Agent": "hackathon-repo-monitor",
        }
        if self.token:
            headers["Authorization"] = f"Bearer {self.token}"
        req = urllib.request.Request(API + path, headers=headers)
        for attempt in range(4):
            try:
                with urllib.request.urlopen(req, timeout=25) as response:
                    return json.load(response)
            except urllib.error.HTTPError as exc:
                if exc.code == 404:
                    raise RuntimeError("not found or not public") from exc
                if exc.code in (403, 429) and exc.headers.get("X-RateLimit-Remaining") == "0":
                    reset = int(exc.headers.get("X-RateLimit-Reset", "0"))
                    wait = max(1, min(reset - int(time.time()), 60))
                    if attempt < 3:
                        time.sleep(wait)
                        continue
                if exc.code == 409:
                    detail = exc.read().decode("utf-8", "replace")
                    if '"message":"Git Repository is empty."' in detail:
                        # GitHub returns 409 rather than an empty array for
                        # commit listings on repositories with no commits.
                        return []
                if exc.code >= 500 and attempt < 3:
                    time.sleep(2**attempt)
                    continue
                detail = exc.read().decode("utf-8", "replace")[:300]
                raise RuntimeError(f"GitHub API returned {exc.code}: {detail}") from exc
            except (urllib.error.URLError, TimeoutError) as exc:
                if attempt < 3:
                    time.sleep(2**attempt)
                    continue
                raise RuntimeError(f"GitHub API request failed: {exc}") from exc


def get_commit_stats(api: GitHub, full_name: str, sha: str) -> dict:
    try:
        commit = api.get(f"/repos/{full_name}/commits/{urllib.parse.quote(sha, safe='')}")
        stats = commit.get("stats") or {}
        files = commit.get("files") or []
        return {
            "additions": stats.get("additions", 0),
            "deletions": stats.get("deletions", 0),
            "changed_files": len(files),
        }
    except RuntimeError:
        return {"additions": None, "deletions": None, "changed_files": None}


def get_commit_date(api: GitHub, full_name: str, sha: str) -> str | None:
    try:
        commit = api.get(f"/repos/{full_name}/commits/{urllib.parse.quote(sha, safe='')}")
        details = commit.get("commit") or {}
        committer = details.get("committer") or {}
        author = details.get("author") or {}
        return committer.get("date") or author.get("date")
    except RuntimeError:
        return None


def collect_repo(api: GitHub, full_name: str) -> tuple[dict, dict]:
    try:
        repo = api.get(f"/repos/{full_name}")
        languages = {}
        try:
            languages = api.get(f"/repos/{full_name}/languages") or {}
        except RuntimeError:
            pass
        readme_text = None
        try:
            readme = api.get(f"/repos/{full_name}/readme")
            if readme.get("encoding") == "base64":
                raw = base64.b64decode(readme.get("content", ""))
                readme_text = raw.decode("utf-8", "replace")[:12000]
        except (RuntimeError, ValueError):
            pass
        root_files = []
        if repo.get("default_branch"):
            try:
                listing = api.get(
                    f"/repos/{full_name}/contents?ref={urllib.parse.quote(repo['default_branch'], safe='')}"
                )
                if isinstance(listing, list):
                    root_files = [
                        {"name": entry.get("name", ""), "type": entry.get("type", "")}
                        for entry in listing[:100]
                    ]
            except RuntimeError:
                pass
        branches = api.get(f"/repos/{full_name}/branches?per_page=100")
        commits = api.get(f"/repos/{full_name}/commits?per_page=10")
        history = []
        for commit in commits:
            item = commit.get("commit", {})
            author = item.get("author") or {}
            stats = get_commit_stats(api, full_name, commit.get("sha", ""))
            history.append({
                "sha": commit.get("sha", "")[:7],
                "url": commit.get("html_url", ""),
                "message": (item.get("message") or "").splitlines()[0][:180],
                "author": (author.get("name") or "Unknown")[:80],
                "date": author.get("date"),
                **stats,
            })
        branch_rows = []
        for branch in branches:
            branch_commit = branch.get("commit") or {}
            sha = branch_commit.get("sha", "")
            commit_details = branch_commit.get("commit") or {}
            committer = commit_details.get("committer") or {}
            author = commit_details.get("author") or {}
            branch_date = committer.get("date") or author.get("date")
            if not branch_date and sha:
                branch_date = get_commit_date(api, full_name, sha)
            branch_rows.append({
                "name": branch.get("name", ""), "sha": sha[:7],
                "date": branch_date,
                "protected": branch.get("protected", False),
            })
        totals = {
            key: sum(c[key] or 0 for c in history)
            for key in ("additions", "deletions", "changed_files")
        }
        row = {
            "name": full_name.split("/")[-1], "full_name": full_name,
            "url": repo.get("html_url", f"https://github.com/{full_name}"),
            "description": repo.get("description") or "",
            "private": repo.get("private", False), "archived": repo.get("archived", False),
            "fork": repo.get("fork", False),
            "parent": (repo.get("parent") or {}).get("full_name"),
            "default_branch": repo.get("default_branch"),
            "forks_count": repo.get("forks_count", 0),
            "open_issues_count": repo.get("open_issues_count", 0),
            "created_at": repo.get("created_at"), "pushed_at": repo.get("pushed_at"),
            "branches": branch_rows, "commits": history, "recent_totals": totals,
            "has_code": bool(languages),
            "error": None,
        }
        context = {
            "full_name": full_name,
            "description": repo.get("description") or "",
            "topics": repo.get("topics") or [],
            "languages_bytes": languages,
            "readme_excerpt": readme_text,
            "root_files": root_files,
            "recent_commits": [
                {"date": c.get("date"), "message": c.get("message", "")}
                for c in history
            ],
        }
        return row, context
    except RuntimeError as exc:
        row = {
            "name": full_name.split("/")[-1], "full_name": full_name,
            "url": f"https://github.com/{full_name}", "branches": [], "commits": [],
            "recent_totals": {"additions": 0, "deletions": 0, "changed_files": 0},
            "has_code": False, "error": str(exc),
        }
        return row, {"full_name": full_name, "error": str(exc)}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output-dir", default="site", help="Directory for dashboard files")
    parser.add_argument("--context-output", help="Optional JSON path for project research context (kept outside the Pages site)")
    parser.add_argument("--config", default=str(ROOT / "repositories.json"))
    args = parser.parse_args()
    repositories = json.loads(pathlib.Path(args.config).read_text())
    api = GitHub()
    results = [collect_repo(api, name) for name in repositories]
    rows = [row for row, _ in results]
    contexts = [context for _, context in results]
    generated = dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds")
    output = pathlib.Path(args.output_dir)
    output.mkdir(parents=True, exist_ok=True)
    (output / "data.json").write_text(json.dumps({"generated_at": generated, "repositories": rows}, indent=2) + "\n")
    (output / "index.html").write_text((ROOT / "index.html").read_text())
    if args.context_output:
        context_path = pathlib.Path(args.context_output)
        context_path.parent.mkdir(parents=True, exist_ok=True)
        context_path.write_text(json.dumps({"generated_at": generated, "repositories": contexts}, indent=2) + "\n")
    failed = sum(bool(row.get("error")) for row in rows)
    print(f"Wrote {len(rows)} repositories to {output} ({failed} unavailable)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
