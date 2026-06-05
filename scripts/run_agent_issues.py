#!/usr/bin/env python3
"""
Fetch all open GitHub issues labelled ready-for-agent and run Claude Code
against each one with a static prompt that injects the issue number.
"""

import argparse
import json
import subprocess
import sys

DEFAULT_MODEL = "claude-sonnet-4-6"

# Static prompt template — {number} is replaced with the issue number.
PROMPT_TEMPLATE = (
    "Work on GitHub issue #{number}. "
    "Read the issue with `gh issue view {number} --comments`, understand the "
    "requirements, implement the changes, test test changes you made, then close the loop by commiting the changes than commenting on "
    "the issue and updating its labels as appropriate."
)


def fetch_issues(label: str) -> list[dict]:
    result = subprocess.run(
        [
            "gh", "issue", "list",
            "--label", label,
            "--state", "open",
            "--json", "number,title",
        ],
        capture_output=True,
        text=True,
        check=True,
    )
    issues = json.loads(result.stdout)
    return sorted(issues, key=lambda i: i["number"])


def run_claude(issue_number: int, issue_title: str, model: str, abort_on_failure: bool = False) -> None:
    prompt = PROMPT_TEMPLATE.format(number=issue_number)
    print(f"\n{'='*60}")
    print(f"Issue #{issue_number}: {issue_title}")
    print(f"{'='*60}")
    subprocess.run(
        ["claude", "--model", model, "-p", prompt],
        check=abort_on_failure,
    )


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--label",
        default="ready-for-agent",
        help="GitHub issue label to filter on (default: ready-for-agent).",
    )
    parser.add_argument(
        "--model",
        default=DEFAULT_MODEL,
        help=f"Claude model to use (default: {DEFAULT_MODEL}).",
    )
    parser.add_argument(
        "--abort-on-failure",
        action="store_true",
        default=False,
        help="Stop processing further issues if one fails (default: continue).",
    )
    args = parser.parse_args()

    try:
        issues = fetch_issues(args.label)
    except subprocess.CalledProcessError as exc:
        print(f"Failed to fetch issues: {exc.stderr}", file=sys.stderr)
        sys.exit(1)

    if not issues:
        print(f"No open issues with label '{args.label}' found.")
        return

    print(f"Found {len(issues)} issue(s) with label '{args.label}'.")

    for issue in issues:
        run_claude(issue["number"], issue["title"], model=args.model, abort_on_failure=args.abort_on_failure)

    print("\nAll issues processed.")


if __name__ == "__main__":
    main()
