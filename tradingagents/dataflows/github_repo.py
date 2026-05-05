import re
import requests
from datetime import datetime, timezone

from .rate_limiter import TokenBucket
from .api_cache import cached

GITHUB_BUCKET = TokenBucket(rate=10, per=60, name="github")

API_BASE = "https://api.github.com"


def _parse_repo_url(url: str):
    """Extract owner/name from a GitHub URL like https://github.com/owner/name."""
    m = re.search(r"github\.com[:/]([^/]+)/([^/\s#?]+)", url)
    if m:
        return m.group(1), m.group(2).replace(".git", "")
    return None, None


@cached("github")
def get_github_activity(repo_url: str, curr_date: str = None, look_back_days: int = 14) -> str:
    """Fetch recent GitHub activity (commits, open issues, open PRs) for a repo."""
    owner, name = _parse_repo_url(repo_url)
    if not owner or not name:
        return f"Could not parse GitHub repo URL: {repo_url}"

    GITHUB_BUCKET.acquire()

    # Recent commits (default branch)
    commits = _fetch_commits(owner, name)
    # Open issues
    open_issues = _fetch_issues(owner, name, "issue")
    # Open PRs
    open_prs = _fetch_issues(owner, name, "pull")

    lines = [
        f"## GitHub Activity: {owner}/{name}",
        f"**Repo**: https://github.com/{owner}/{name}",
        "",
    ]

    if commits is not None:
        lines.append(f"### Recent Commits (last {look_back_days}d)")
        lines.append(f"Total commits returned: {len(commits)}")
        for c in commits[:10]:
            sha = c.get("sha", "")[:7]
            msg = c.get("commit", {}).get("message", "").split("\n")[0]
            author = c.get("commit", {}).get("author", {}).get("name", "unknown")
            date = c.get("commit", {}).get("author", {}).get("date", "")
            if date:
                try:
                    date = datetime.fromisoformat(date.replace("Z", "+00:00")).strftime("%Y-%m-%d")
                except Exception:
                    pass
            lines.append(f"- {date} | {author}: {msg} ({sha})")
    else:
        lines.append("### Recent Commits: Could not fetch")

    if open_issues is not None:
        lines.append(f"\n### Open Issues: {len(open_issues)} total")
        for issue in open_issues[:5]:
            lines.append(f"- #{issue['number']} {issue['title']} (opened {issue['created_at'][:10]})")
        if len(open_issues) > 5:
            lines.append(f"- ... and {len(open_issues) - 5} more")
    else:
        lines.append("\n### Open Issues: Could not fetch")

    if open_prs is not None:
        lines.append(f"\n### Open Pull Requests: {len(open_prs)} total")
        for pr in open_prs[:5]:
            lines.append(f"- #{pr['number']} {pr['title']} (opened {pr['created_at'][:10]})")
        if len(open_prs) > 5:
            lines.append(f"- ... and {len(open_prs) - 5} more")
    else:
        lines.append("\n### Open Pull Requests: Could not fetch")

    return "\n".join(lines)


def _fetch_commits(owner: str, name: str, per_page: int = 15):
    try:
        resp = requests.get(
            f"{API_BASE}/repos/{owner}/{name}/commits",
            params={"per_page": per_page, "sort": "committer-date"},
            headers={"Accept": "application/vnd.github.v3+json"},
            timeout=10,
        )
        if resp.status_code == 200:
            return resp.json()
        return None
    except Exception:
        return None


def _fetch_issues(owner: str, name: str, issue_type: str, per_page: int = 10):
    try:
        resp = requests.get(
            f"{API_BASE}/repos/{owner}/{name}/issues",
            params={"state": "open", "per_page": per_page, "type": issue_type},
            headers={"Accept": "application/vnd.github.v3+json"},
            timeout=10,
        )
        if resp.status_code == 200:
            items = resp.json()
            if issue_type == "pull":
                return [i for i in items if "pull_request" in i]
            else:
                return [i for i in items if "pull_request" not in i]
        return None
    except Exception:
        return None
