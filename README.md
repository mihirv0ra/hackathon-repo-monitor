# Hackathon repository monitor

A small GitHub Actions job that samples team repositories and publishes a static status dashboard to GitHub Pages.

## What it tracks

- Repository fork status and upstream, if the team repo itself is a fork
- Branch names and their most recent commit dates
- Recent commits, including additions, deletions, and changed-file counts
- Repository push time and a simple recent-activity summary
- Whether a repository is a fork and whether GitHub detects source code in it

The monitor treats the listed team repositories as the source of truth. A team repository being a fork is shown separately from a team creating branches inside its repository. The commit statistics describe only the most recent 10 commits per repository; GitHub's commit stats can take time to calculate, so the workflow tolerates missing stats.

## Run locally

```sh
MONITOR_TOKEN=github_pat_... python3 monitor.py --output-dir site
python3 -m http.server --directory site 8000
```

Then open <http://localhost:8000>. The script uses Python's standard library. A token is recommended because collecting recent commit statistics across many repositories can exceed GitHub's unauthenticated API limit. The script uses `MONITOR_TOKEN` first, then a local `gh auth` login, then `GITHUB_TOKEN` or `GH_TOKEN`:

```sh
MONITOR_TOKEN=github_pat_... python3 monitor.py --output-dir site
```

## Publish with GitHub Pages

1. Push these files to the monitor repository's default branch.
2. In the repository settings, enable **Pages** with **GitHub Actions** as the build and deployment source.
3. Add an Actions secret named `MONITOR_TOKEN` containing a fine-grained token with read-only access to the team repositories. The workflow runs every 30 minutes, on pushes, and when manually dispatched. It fetches the team data, then deploys `site/` to Pages. Without that secret, it falls back to the repository's built-in `GITHUB_TOKEN`, which can only access this repository.
4. The published URL will be `https://OWNER.github.io/REPOSITORY/` (or the custom domain configured in Pages).

Each workflow run also saves a `project-context` artifact for 7 days. It contains repository descriptions, topics, language byte counts, root file names, recent commit messages, and a README excerpt to support later high-level synthesis. This artifact is separate from the dashboard. Anyone with access to the repository's Actions runs can download it.

Grant the workflow the listed Pages and Actions permissions if GitHub prompts for them. Revoke `MONITOR_TOKEN` after the event. Scheduled runs can start late during busy periods, so the page shows the time of its last successful data refresh.

## Scope and limits

- The dashboard is public. Only use a token for repositories whose activity data you are authorized and comfortable publishing; private repo activity fetched by the workflow will also appear on the public site.
- A repository counts as recently active only when it is a fork, contains detected source code, and was pushed within the last 14 days. Other repositories are marked yellow and excluded from that count.
- GitHub API limits apply. The workflow requests up to 10 recent commits and their stats per repository.
- “Major activity” is presented as transparent counts (commits, lines added/deleted, files changed), not as an automatic quality score.
- A branch is considered active when its latest commit is within the last 14 days. This is a configurable display heuristic, not an evaluation of team quality.
