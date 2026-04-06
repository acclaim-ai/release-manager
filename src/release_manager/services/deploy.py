"""Fetch deployed versions from platform-deploy GitHub repo."""

import base64
import json
import re
import urllib.request

GITHUB_API = "https://api.github.com"
IMAGE_TAG_RE = re.compile(r"image:\s*\n(?:\s+\w+:\s*\S*\n)*?\s+tag:\s*(\S+)")


def _github_get(url: str, token: str) -> dict | list:
    """GET request to GitHub API."""
    req = urllib.request.Request(
        url,
        headers={
            "Accept": "application/vnd.github.v3+json",
            "Authorization": f"Bearer {token}",
            "User-Agent": "release-manager",
        },
    )
    with urllib.request.urlopen(req, timeout=30) as resp:
        return json.loads(resp.read())


def fetch_deployed_versions(
    owner: str,
    repo: str,
    cluster_path: str,
    token: str,
    until: str | None = None,
) -> dict:
    """Fetch component → tag mapping from a cluster directory.

    Args:
        until: ISO date string (e.g. '2026-03-15'). If set, fetches state
               as of the latest commit on or before that date.

    Returns {"components": [{name, tag, file}], "commit": {sha, ...}}.
    """
    base = f"{GITHUB_API}/repos/{owner}/{repo}"

    # 1. Find the commit (latest, or latest before `until`)
    commits_url = f"{base}/commits?path={cluster_path}&per_page=1"
    if until:
        # GitHub API expects ISO 8601: append end-of-day time
        commits_url += f"&until={until}T23:59:59Z"

    commits = _github_get(commits_url, token)
    if not commits:
        return {"components": [], "commit": None}

    commit = commits[0]
    ref = commit["sha"]
    commit_info = {
        "sha": ref[:7],
        "full_sha": ref,
        "message": commit["commit"]["message"].split("\n")[0],
        "date": commit["commit"]["committer"]["date"],
        "url": commit["html_url"],
    }

    # 2. List directories at that ref
    contents = _github_get(f"{base}/contents/{cluster_path}?ref={ref}", token)
    dirs = [item for item in contents if item["type"] == "dir"]

    # 3. For each component dir, scan files for image.tag
    components: list[dict] = []
    for d in sorted(dirs, key=lambda x: x["name"]):
        tag, source_file = _find_image_tag(base, f"{cluster_path}/{d['name']}", token, ref)
        components.append({
            "name": d["name"],
            "tag": tag,
            "file": source_file,
        })

    return {"components": components, "commit": commit_info}


def _find_image_tag(
    base_url: str, dir_path: str, token: str, ref: str | None = None
) -> tuple[str | None, str | None]:
    """Scan all files in a directory for image.tag pattern."""
    url = f"{base_url}/contents/{dir_path}"
    if ref:
        url += f"?ref={ref}"
    try:
        files = _github_get(url, token)
    except Exception:
        return None, None

    for f in files:
        if f["type"] != "file":
            continue
        name = f["name"]
        if not (name.endswith(".yaml") or name.endswith(".yml")):
            continue
        try:
            file_url = f["url"]
            file_data = _github_get(file_url, token)
            content = base64.b64decode(file_data["content"]).decode("utf-8")
            match = IMAGE_TAG_RE.search(content)
            if match:
                return match.group(1), name
        except Exception:
            continue

    return None, None
