#!/usr/bin/env python3
"""
Fetch all open GitHub issues labelled ready-for-agent and run Claude Code
against each one with a static prompt that injects the issue number.
"""

import json
import subprocess
import sys

#LABEL = "ready-for-agent"
LABEL = "Sandcastle"

# Static prompt template — {number} is replaced with the issue number.
PROMPT_TEMPLATE = (
    "Work on GitHub issue #{number}. "
    "Read the issue with `gh issue view {number} --comments`, understand the "
    "requirements, implement the changes, test test changes you made,then close the loop by commiting the changes than commenting on "
    "the issue and updating its labels as appropriate."
)


def fetch_issues() -> list[dict]:
    result = subprocess.run(
        [
            "gh", "issue", "list",
            "--label", LABEL,
            "--state", "open",
            "--json", "number,title",
        ],
        capture_output=True,
        text=True,
        check=True,
    )
    issues = json.loads(result.stdout)
    return sorted(issues, key=lambda i: i["number"])


def run_claude(issue_number: int, issue_title: str) -> None:
    prompt = PROMPT_TEMPLATE.format(number=issue_number)
    print(f"\n{'='*60}")
    print(f"Issue #{issue_number}: {issue_title}")
    print(f"{'='*60}")
    subprocess.run(
        ["claude", "-p", prompt],
        check=False,  # don't abort the loop if one issue fails
    )


def main() -> None:
    try:
        issues = fetch_issues()
    except subprocess.CalledProcessError as exc:
        print(f"Failed to fetch issues: {exc.stderr}", file=sys.stderr)
        sys.exit(1)

    if not issues:
        print(f"No open issues with label '{LABEL}' found.")
        return

    print(f"Found {len(issues)} issue(s) with label '{LABEL}'.")

    for issue in issues:
        run_claude(issue["number"], issue["title"])

    print("\nAll issues processed.")


if __name__ == "__main__":
    main()
