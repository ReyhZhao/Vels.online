"""Constrained rich-text sanitizer for incident Reports (PRD #632, ADR-0029 amendment).

``sanitize_report_richtext(html) -> html`` is the single security boundary for the
Report free-text blocks (``intro_text``, ``outro_text``, ``recommendations_text`` and
the editable Executive Summary). It reduces arbitrary input to a *tiny* allowlist so
author- or LLM-supplied formatting can never carry script, event handlers, or arbitrary
markup into a customer-facing Report.

The allowlist IS the whole policy (kept deliberately small so "cannot express
``<script>``/``onerror``/``javascript:``" holds by construction):

* Tags: ``p, br, strong, em, u, ul, ol, li`` — nothing else.
* Attributes: none anywhere, EXCEPT a single ``class`` on ``p``/``li`` restricted to the
  fixed set ``indent-1``, ``indent-2``, ``indent-3`` (capped indent → fixed CSS rules).
* No inline ``style``, links, images, colors, headings, or tables.

This mirrors ADR-0029's ethos: leak-safety is *structural*, not author discipline. The
TipTap editor is configured to emit only this subset, so this server pass is
defense-in-depth over a constrained-but-untrusted client.
"""
import nh3

# The complete tag allowlist — overrides nh3's (much larger) default set.
ALLOWED_TAGS = {"p", "br", "strong", "em", "u", "ul", "ol", "li"}

# Only ``class`` is allowed, only on ``p``/``li``; values are further restricted by
# ``_attribute_filter`` to the indent set below.
ALLOWED_ATTRIBUTES = {"p": {"class"}, "li": {"class"}}

# The only permissible ``class`` values (capped indent depth).
ALLOWED_INDENT_CLASSES = {"indent-1", "indent-2", "indent-3"}

# script/style content is dropped entirely (not just the tags) — nh3's default, made
# explicit here so the security posture is visible at the call site.
CLEAN_CONTENT_TAGS = {"script", "style"}


def _attribute_filter(tag: str, attr: str, value: str):
    """Drop any class value outside the fixed indent set; keep nothing else.

    nh3 calls this for every surviving attribute. Returning ``None`` drops the
    attribute. We only ever see ``class`` here (it is the only allowlisted attribute),
    and we keep just the indent tokens — so an attacker cannot smuggle a styling/utility
    class through.
    """
    if attr == "class":
        kept = [c for c in value.split() if c in ALLOWED_INDENT_CLASSES]
        return " ".join(kept) if kept else None
    return None


def sanitize_report_richtext(html: str) -> str:
    """Return ``html`` reduced to the Report rich-text allowlist.

    Idempotent: sanitising already-clean output is a no-op. Empty/None input returns "".
    """
    if not html:
        return ""
    return nh3.clean(
        html,
        tags=ALLOWED_TAGS,
        clean_content_tags=CLEAN_CONTENT_TAGS,
        attributes=ALLOWED_ATTRIBUTES,
        attribute_filter=_attribute_filter,
        link_rel=None,
        strip_comments=True,
    )
