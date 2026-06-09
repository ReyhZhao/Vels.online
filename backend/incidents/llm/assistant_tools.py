"""Tools the incident assistant can call in the agentic loop (ADR-0011/0012).

Read tools (lookup_incidents, query_alerts, lookup_assets) reuse the same
authorization as the REST endpoints and default-narrow to the incident's org; a
staff caller may widen with scope="all". Write tools (add_internal_comment,
add_task_comment, self_assign, add_tag, link_known_asset) auto-execute through the
existing models and record an assistant-initiated (autonomous) timeline event.
add_task_comment lets the assistant work a MANUAL task by recording its research
findings as a task-scoped internal comment; it never runs or closes a task and rejects
automated/wazuh_response tasks (ADR-0013).

Every executor closes over the bound (incident, user) so the model can never widen
beyond what the caller may see, regardless of the args it passes.
"""
from assistants.tools import ToolResult, ToolSpec
from assistants.web_search import build_web_search_tool
from assistants import pap_guard

from incidents.services.events import record_event
from incidents.services.visibility import filter_incidents_for_user

_LIMIT = 10


def _record_autonomous(incident, user, action_type, detail):
    record_event(
        incident, "assistant_action", actor=user,
        payload={"action_type": action_type, "autonomous": True, "detail": detail},
    )


# ── read tools ──────────────────────────────────────────────────────────────────

def _scope_to_org(qs, incident, user, args):
    """Default-narrow to the incident's org; staff may widen with scope='all'."""
    if user.is_staff and (args or {}).get("scope") == "all":
        return qs
    return qs.filter(organization=incident.organization)


def _lookup_incidents(incident, user):
    def executor(args):
        from incidents.models import Incident
        q = ((args or {}).get("query") or "").strip()
        qs = filter_incidents_for_user(Incident.objects.all(), user)
        qs = _scope_to_org(qs, incident, user, args).exclude(pk=incident.pk)
        if q:
            from django.db.models import Q
            qs = qs.filter(Q(title__icontains=q) | Q(description__icontains=q))
        rows = list(qs.order_by("-created_at").values(
            "display_id", "title", "severity", "state", "created_at")[:_LIMIT])
        for r in rows:
            r["created_at"] = r["created_at"].isoformat() if r["created_at"] else None
        return ToolResult(content=rows, summary=f"{len(rows)} related incidents", count=len(rows))
    return ToolSpec(
        name="lookup_incidents",
        description="Search other incidents (related campaigns, the same indicator elsewhere). "
                    "Scoped to this incident's organisation by default; staff may pass scope='all'.",
        parameters={"type": "object", "properties": {
            "query": {"type": "string", "description": "Text to match in title/description."},
            "scope": {"type": "string", "enum": ["org", "all"], "description": "staff-only widen"},
        }},
        executor=executor,
    )


def _query_alerts(incident, user):
    def executor(args):
        from alerts.models import Alert
        q = ((args or {}).get("query") or "").strip()
        qs = Alert.objects.all()
        if not user.is_staff:
            from security.models import OrganizationMembership
            org_ids = OrganizationMembership.objects.filter(user=user).values_list("organization_id", flat=True)
            qs = qs.filter(organization_id__in=org_ids)
        qs = _scope_to_org(qs, incident, user, args)
        if q:
            qs = qs.filter(title__icontains=q)
        rows = list(qs.order_by("-created_at").values(
            "display_id", "title", "severity", "state", "source_kind", "created_at")[:_LIMIT])
        for r in rows:
            r["created_at"] = r["created_at"].isoformat() if r["created_at"] else None
        return ToolResult(content=rows, summary=f"{len(rows)} alerts", count=len(rows))
    return ToolSpec(
        name="query_alerts",
        description="Search alerts in the app (does the same indicator appear elsewhere?). "
                    "Scoped to this incident's organisation by default; staff may pass scope='all'.",
        parameters={"type": "object", "properties": {
            "query": {"type": "string", "description": "Text to match in the alert title."},
            "scope": {"type": "string", "enum": ["org", "all"], "description": "staff-only widen"},
        }},
        executor=executor,
    )


def _lookup_assets(incident, user):
    def executor(args):
        from incidents.models import Asset
        from django.db.models import Q
        q = ((args or {}).get("query") or "").strip()
        qs = Asset.objects.all()
        if not user.is_staff:
            from security.models import OrganizationMembership
            org_ids = OrganizationMembership.objects.filter(user=user).values_list("organization_id", flat=True)
            qs = qs.filter(organization_id__in=org_ids)
        qs = _scope_to_org(qs, incident, user, args)
        if q:
            qs = qs.filter(Q(name__icontains=q) | Q(agent_name__icontains=q) | Q(ip_address__icontains=q))
        rows = list(qs.values("id", "name", "kind", "agent_name", "ip_address", "role")[:_LIMIT])
        for r in rows:
            r["ip_address"] = str(r["ip_address"]) if r["ip_address"] else None
        return ToolResult(content=rows, summary=f"{len(rows)} assets", count=len(rows))
    return ToolSpec(
        name="lookup_assets",
        description="Look up assets (hosts) to understand exposure and ownership. "
                    "Scoped to this incident's organisation by default; staff may pass scope='all'.",
        parameters={"type": "object", "properties": {
            "query": {"type": "string", "description": "Text to match in name/agent_name/ip."},
            "scope": {"type": "string", "enum": ["org", "all"], "description": "staff-only widen"},
        }},
        executor=executor,
    )


# ── write (auto-execute) tools — ADR-0012 ─────────────────────────────────────────

def _add_internal_comment(incident, user):
    def executor(args):
        from incidents.models import Comment
        text = ((args or {}).get("text") or "").strip()
        if not text:
            return ToolResult(error="empty comment text", summary="empty comment")
        Comment.objects.create(
            incident=incident, author=user, body=text,
            kind=Comment.KIND_USER, is_internal=True,
        )
        _record_autonomous(incident, user, "add_internal_comment", {"preview": text[:80]})
        return ToolResult(content={"ok": True}, summary="added internal comment")
    return ToolSpec(
        name="add_internal_comment", is_write=True,
        description="Add a staff-only internal comment to this incident.",
        parameters={"type": "object", "properties": {
            "text": {"type": "string", "description": "The comment body."}}, "required": ["text"]},
        executor=executor,
    )


def _self_assign(incident, user):
    def executor(args):
        incident.assignee = user
        incident.save(update_fields=["assignee", "updated_at"])
        _record_autonomous(incident, user, "self_assign", {"assignee": user.username})
        return ToolResult(content={"assignee": user.username}, summary=f"assigned to {user.username}")
    return ToolSpec(
        name="self_assign", is_write=True,
        description="Assign this incident to the current analyst (you).",
        parameters={"type": "object", "properties": {}},
        executor=executor,
    )


def _add_tag(incident, user):
    def executor(args):
        tag = ((args or {}).get("tag") or "").strip()
        if not tag:
            return ToolResult(error="empty tag", summary="empty tag")
        tags = list(incident.tags or [])
        if tag in tags:
            return ToolResult(content={"tags": tags}, summary=f"tag '{tag}' already present")
        tags.append(tag)
        incident.tags = tags
        incident.save(update_fields=["tags", "updated_at"])
        _record_autonomous(incident, user, "add_tag", {"tag": tag})
        return ToolResult(content={"tags": tags}, summary=f"added tag '{tag}'")
    return ToolSpec(
        name="add_tag", is_write=True,
        description="Add a free-form label/tag to this incident.",
        parameters={"type": "object", "properties": {
            "tag": {"type": "string", "description": "The tag to add."}}, "required": ["tag"]},
        executor=executor,
    )


def _add_task_comment(incident, user):
    def executor(args):
        from incidents.models import Comment, Task
        from incidents.llm.action_authority import task_workable_by_assistant

        task_id = (args or {}).get("task_id")
        text = ((args or {}).get("text") or "").strip()
        if task_id is None:
            return ToolResult(error="task_id is required", summary="missing task_id")
        if not text:
            return ToolResult(error="empty comment text", summary="empty comment")
        task = Task.objects.filter(pk=task_id).select_related("incident").first()
        if not task_workable_by_assistant(task, incident):
            return ToolResult(
                error="task is not a manual task on this incident; the assistant only works "
                      "manual tasks and never runs automated or wazuh_response tasks",
                summary="task not workable",
            )
        comment = Comment.objects.create(
            incident=incident, task=task, author=user, body=text,
            kind=Comment.KIND_USER, is_internal=True,
        )
        record_event(
            incident, "comment_added", actor=user,
            payload={"target_type": "comment", "target_id": comment.id, "is_internal": True},
        )
        _record_autonomous(incident, user, "add_task_comment",
                           {"task_id": task.id, "task_title": task.title, "preview": text[:80]})
        return ToolResult(content={"ok": True, "task_id": task.id},
                          summary=f"added findings to task '{task.title}'")
    return ToolSpec(
        name="add_task_comment", is_write=True,
        description="Record your research findings as a staff-only internal comment on one of this "
                    "incident's MANUAL tasks. Use this to work a manual task: after researching it, "
                    "write up what you found here. Only works on manual tasks; it cannot run, close, "
                    "or comment on automated/wazuh_response tasks.",
        parameters={"type": "object", "properties": {
            "task_id": {"type": "integer", "description": "Id of the manual task (from the task list in context)."},
            "text": {"type": "string", "description": "The findings to record on the task."}},
            "required": ["task_id", "text"]},
        executor=executor,
    )


def _link_known_asset(incident, user):
    def executor(args):
        from incidents.models import Asset, IncidentAsset
        asset_id = (args or {}).get("asset_id")
        name = ((args or {}).get("name") or "").strip()
        qs = Asset.objects.filter(organization=incident.organization)
        asset = None
        if asset_id is not None:
            asset = qs.filter(pk=asset_id).first()
        elif name:
            asset = qs.filter(name__iexact=name).first() or qs.filter(name__icontains=name).first()
        if asset is None:
            return ToolResult(error="no matching known asset in this org", summary="asset not found")
        _, created = IncidentAsset.objects.get_or_create(
            incident=incident, asset=asset, defaults={"added_by": user})
        if not created:
            return ToolResult(content={"asset": asset.name}, summary=f"'{asset.name}' already linked")
        _record_autonomous(incident, user, "link_known_asset", {"asset": asset.name})
        return ToolResult(content={"asset": asset.name}, summary=f"linked asset '{asset.name}'")
    return ToolSpec(
        name="link_known_asset", is_write=True,
        description="Link an asset already known in this organisation to this incident.",
        parameters={"type": "object", "properties": {
            "asset_id": {"type": "integer", "description": "Asset id (preferred)."},
            "name": {"type": "string", "description": "Asset name, if id unknown."}}},
        executor=executor,
    )


# ── assembly ──────────────────────────────────────────────────────────────────

def build_incident_tools(incident, user, grounding, include_web_search=True):
    """Build the incident assistant's tool set, bound to (incident, user).

    Read tools + auto-execute write tools, plus web_search (PAP-guarded) when
    enabled and available.
    """
    from assistants.web_search import web_search_available

    tools = [
        _lookup_incidents(incident, user),
        _query_alerts(incident, user),
        _lookup_assets(incident, user),
        _add_internal_comment(incident, user),
        _add_task_comment(incident, user),
        _self_assign(incident, user),
        _add_tag(incident, user),
        _link_known_asset(incident, user),
    ]

    uses_native = False  # provider may set this; web_search tool only for non-native
    if include_web_search and web_search_available():
        indicators = pap_guard.collect_incident_indicators(grounding)
        pap_level = (grounding.get("incident", {}) or {}).get("pap", "")

        def guard(query):
            return pap_guard.check_web_search_query(query, indicators, pap_level)

        tools.append(build_web_search_tool(guard=guard))

    return tools
