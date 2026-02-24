import csv
import io
import json
import re
from dataclasses import dataclass

from release_manager.models import ReleaseReport

BOT_PATTERNS = [
    re.compile(p, re.I)
    for p in [
        r"\[bot\]",
        r"^dependabot",
        r"^renovate",
        r"^github-actions",
        r"^bender-",
        r"^aiphoria-ai$",
    ]
]


def _is_bot(name: str) -> bool:
    return any(p.search(name) for p in BOT_PATTERNS)


@dataclass
class TaskRow:
    key: str
    components: list[str]
    contributors: list[str]


def _build_tasks(report: ReleaseReport) -> list[TaskRow]:
    """Build task rows from a report (same logic as the Jinja2 template)."""
    rows: list[TaskRow] = []
    for key in report.all_linear_keys:
        components: list[str] = []
        contributors: list[str] = []
        seen_authors: set[str] = set()
        for repo in report.repos:
            found = False
            for c in repo.commits:
                if key in c.linear_keys:
                    found = True
                    if c.author not in seen_authors and not _is_bot(c.author):
                        seen_authors.add(c.author)
                        contributors.append(c.author)
            if found:
                components.append(repo.repo_name)
        rows.append(TaskRow(key=key, components=components, contributors=contributors))
    return rows


# ── Tasks export (the main release export) ─────────────────


def to_csv(report: ReleaseReport) -> str:
    """Export tasks table as CSV: Linear Key, Components, Contributors."""
    output = io.StringIO()
    writer = csv.writer(output)
    writer.writerow(["Linear Key", "Components", "Contributors"])
    for task in _build_tasks(report):
        writer.writerow([
            task.key,
            ", ".join(task.components),
            ", ".join(task.contributors),
        ])
    return output.getvalue()


def to_markdown(report: ReleaseReport) -> str:
    """Export tasks table as Markdown."""
    lines: list[str] = []
    lines.append("# Release Tasks")
    lines.append(f"Generated: {report.generated_at.strftime('%Y-%m-%d %H:%M')}")
    lines.append("")
    lines.append("| Linear Key | Components | Contributors |")
    lines.append("|------------|------------|--------------|")
    for task in _build_tasks(report):
        comps = ", ".join(task.components)
        devs = ", ".join(task.contributors)
        lines.append(f"| {task.key} | {comps} | {devs} |")
    lines.append("")
    return "\n".join(lines)


def to_json(report: ReleaseReport) -> str:
    """Export tasks table as JSON array."""
    tasks = [
        {
            "linear_key": t.key,
            "components": t.components,
            "contributors": t.contributors,
        }
        for t in _build_tasks(report)
    ]
    return json.dumps(tasks, indent=2, ensure_ascii=False)


# ── Contributors by Component export ───────────────────────


def contributors_to_csv(report: ReleaseReport) -> str:
    """Export contributors by component as CSV."""
    output = io.StringIO()
    writer = csv.writer(output)
    writer.writerow(["Component", "Version Range", "Developers"])
    for repo in report.repos:
        authors: list[str] = []
        seen: set[str] = set()
        for c in repo.commits:
            if c.author not in seen and not _is_bot(c.author):
                seen.add(c.author)
                authors.append(c.author)
        writer.writerow([
            repo.repo_name,
            f"{repo.from_tag} -> {repo.to_tag}",
            ", ".join(authors),
        ])
    return output.getvalue()


# ── Commits export ─────────────────────────────────────────


def commits_to_csv(report: ReleaseReport) -> str:
    """Export all commits as CSV."""
    output = io.StringIO()
    writer = csv.writer(output)
    writer.writerow(
        ["Repo", "From Tag", "To Tag", "Commit", "Author", "Date", "Message", "Linear Keys"]
    )
    for repo in report.repos:
        for commit in repo.commits:
            writer.writerow([
                repo.repo_name,
                repo.from_tag,
                repo.to_tag,
                commit.short_hash,
                commit.author,
                commit.date.strftime("%Y-%m-%d %H:%M"),
                commit.message.split("\n")[0],
                ", ".join(commit.linear_keys),
            ])
    return output.getvalue()
