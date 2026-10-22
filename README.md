# Hackathon repository monitor

A small GitHub Actions job that samples 25 public team repositories and publishes a static status dashboard to GitHub Pages.

## What it tracks

- Repository fork status and upstream, if the team repo itself is a fork
- Branch names and their most recent commit dates
- Recent commits, including additions, deletions, and changed-file counts
- Repository push time and a simple recent-activity summary

The monitor treats the listed team repositories as the source of truth. A team repository being a fork is shown separately from a team creating branches inside its repository. The commit statistics describe only the most recent 10 commits per repository; GitHub's commit stats can take time to calculate, so the workflow tolerates missing stats.

## Run locally

```sh
GITHUB_TOKEN=github_pat_... python3 monitor.py --output-dir site
python3 -m http.server --directory site 8000
```

Then open <http://localhost:8000>. The script uses Python's standard library. A token is recommended because collecting recent commit statistics across 25 repositories can exceed GitHub's unauthenticated API limit. Use a fine-grained token with public repository read access:

```sh
GITHUB_TOKEN=github_pat_... python3 monitor.py --output-dir site
```

## Publish with GitHub Pages

1. Create a new public repository for this monitor and push these files to its default branch.
2. In the repository settings, enable **Pages** with **GitHub Actions** as the build and deployment source.
3. The workflow runs every 30 minutes, on pushes, and when manually dispatched. It fetches the team data, then deploys `site/` to Pages.
4. The published URL will be `https://OWNER.github.io/REPOSITORY/` (or the custom domain configured in Pages).

The workflow uses the repository's built-in `GITHUB_TOKEN`; grant it the listed Pages and Actions permissions if GitHub prompts for them. No team repository secrets or write access are needed. Scheduled runs can start late during busy periods, so the page shows the time of its last successful data refresh.

## Scope and limits

- Only public repository data is read. Private repos would require token access and should not be placed on a public Pages site.
- GitHub API limits apply. The workflow requests up to 10 recent commits and their stats per repository.
- “Major activity” is presented as transparent counts (commits, lines added/deleted, files changed), not as an automatic quality score.
- A branch is considered active when its latest commit is within the last 14 days. This is a configurable display heuristic, not an evaluation of team quality.
