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
    "requirements. "
    "This issue may be one slice of a larger feature: look for a `Parent` "
    "reference in the issue body or comments, usually formatted like "
    "`#554 (PRD: ...)`. If you find one, read the parent PRD issue with "
    "`gh issue view <parent-number> --comments` for the full feature context "
    "and acceptance criteria, and make sure your implementation stays "
    "consistent with it. "
    "Then implement the changes, test the changes you made, and close the "
    "loop by committing the changes, commenting on the issue, and updating "
    "its labels as appropriate."
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


def _fmt_int(n: int) -> str:
    return f"{n:,}"


def summarise_run(result: dict, model: str) -> dict:
    """Extract token/context/cost stats from a Claude Code JSON result.

    Returns a dict of running totals (tokens + cost) so the caller can
    accumulate a grand total across issues.
    """
    usage = result.get("usage", {}) or {}
    iterations = usage.get("iterations") or []

    # Cumulative tokens consumed across every turn of this run.
    input_tokens = usage.get("input_tokens", 0)
    output_tokens = usage.get("output_tokens", 0)
    cache_creation = usage.get("cache_creation_input_tokens", 0)
    cache_read = usage.get("cache_read_input_tokens", 0)
    total_tokens = input_tokens + output_tokens + cache_creation + cache_read

    # Context window occupancy at the end of the iteration: everything fed
    # into the model on its final turn (fresh input + cached prefixes).
    final = iterations[-1] if iterations else usage
    context_used = (
        final.get("input_tokens", 0)
        + final.get("cache_read_input_tokens", 0)
        + final.get("cache_creation_input_tokens", 0)
    )

    # Per-model entry gives us the model's max context window for a %.
    model_usage = result.get("modelUsage", {}) or {}
    entry = model_usage.get(model)
    if entry is None and model_usage:
        # Fall back to whichever model did the most work.
        entry = max(model_usage.values(), key=lambda m: m.get("inputTokens", 0))
    context_window = (entry or {}).get("contextWindow", 0)

    cost = result.get("total_cost_usd", 0.0)
    num_turns = result.get("num_turns", 0)
    duration_s = result.get("duration_ms", 0) / 1000

    print(f"\n{'-'*60}")
    print("Run summary")
    print(f"  Turns:           {num_turns}")
    print(f"  Duration:        {duration_s:.1f}s")
    print(f"  Tokens used:     {_fmt_int(total_tokens)} total")
    print(
        f"    input {_fmt_int(input_tokens)} | output {_fmt_int(output_tokens)} | "
        f"cache write {_fmt_int(cache_creation)} | cache read {_fmt_int(cache_read)}"
    )
    if context_window:
        pct = context_used / context_window * 100
        print(
            f"  Context window:  {_fmt_int(context_used)} / "
            f"{_fmt_int(context_window)} ({pct:.1f}%)"
        )
    else:
        print(f"  Context window:  {_fmt_int(context_used)}")
    print(f"  Cost:            ${cost:.4f}")
    print(f"{'-'*60}")

    return {"tokens": total_tokens, "cost": cost}


def run_claude(
    issue_number: int, issue_title: str, model: str, abort_on_failure: bool = False
) -> dict:
    prompt = PROMPT_TEMPLATE.format(number=issue_number)
    print(f"\n{'='*60}")
    print(f"Issue #{issue_number}: {issue_title}")
    print(f"{'='*60}")
    proc = subprocess.run(
        ["claude", "--model", model, "-p", prompt, "--output-format", "json"],
        capture_output=True,
        text=True,
        check=abort_on_failure,
    )

    try:
        result = json.loads(proc.stdout)
    except json.JSONDecodeError:
        # Couldn't parse a structured result — surface raw output and bail.
        if proc.stdout:
            print(proc.stdout)
        if proc.stderr:
            print(proc.stderr, file=sys.stderr)
        return {"tokens": 0, "cost": 0.0}

    # Print the agent's final text just like the old text-mode output.
    print(result.get("result", ""))

    if result.get("is_error"):
        print(
            f"  (claude reported an error: {result.get('subtype', 'unknown')})",
            file=sys.stderr,
        )

    return summarise_run(result, model)


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

    total_tokens = 0
    total_cost = 0.0
    for issue in issues:
        stats = run_claude(
            issue["number"],
            issue["title"],
            model=args.model,
            abort_on_failure=args.abort_on_failure,
        )
        total_tokens += stats["tokens"]
        total_cost += stats["cost"]

    print("\nAll issues processed.")
    print(
        f"Grand total across {len(issues)} issue(s): "
        f"{total_tokens:,} tokens, ${total_cost:.4f}"
    )


if __name__ == "__main__":
    main()
