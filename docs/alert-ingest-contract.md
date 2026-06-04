# Alert Ingestion API Contract

This document is the canonical reference for external integrators sending alerts
into the platform. It covers the two available endpoints, the required ECS entity
envelope, and the migration path from v1 to v2.

---

## Endpoints

| Version | URL | Envelope |
|---------|-----|----------|
| v1 | `POST /api/alerts/` | Optional (accepted but not required) |
| v2 | `POST /api/v2/alerts/` | **Required** — requests without a valid envelope are rejected with HTTP 422 |

New integrations **must** target v2. v1 remains available as a migration path for
existing callers while they add envelope support.

---

## Authentication

All ingest requests must be made by an authenticated **staff** user.

- Non-authenticated requests → `401 Unauthorized`
- Non-staff authenticated requests → `403 Forbidden`

---

## Request body

```json
{
  "org": "acme",
  "source_kind": "external",
  "source_ref": { "ticket_id": "INC-1234" },
  "title": "Suspicious outbound connection",
  "description": "Host contacted known C2 IP.",
  "severity": "high",
  "pap": "amber",
  "tlp": "green",
  "entities": {
    "host.name": "web-prod-01",
    "source.ip": "10.0.0.55",
    "user.name": "CORP\\alice"
  }
}
```

### Fields

| Field | Type | Required | Notes |
|-------|------|----------|-------|
| `org` | string | Yes | Organisation slug |
| `source_kind` | enum | Yes | One of: `wazuh_event`, `vulnerability`, `agent_finding`, `api`, `workflow`, `external` |
| `source_ref` | object | No | Arbitrary source metadata stored as-is |
| `title` | string | Conditional | Required for `workflow` and `external` source kinds |
| `description` | string | No | Free-text alert description |
| `severity` | enum | No | `critical`, `high`, `medium`, `low`, `info` |
| `pap` | enum | No | `white`, `green`, `amber`, `red` |
| `tlp` | enum | No | `white`, `green`, `amber`, `red` |
| `entities` | object | **Required on v2** | ECS entity envelope (see below) |

---

## ECS Entity Envelope

The `entities` field carries normalised, queryable entities used for alert
correlation. Keys must be [ECS](https://www.elastic.co/guide/en/ecs/current/)
field names from the supported set; values must be non-empty strings.

### Supported ECS fields

| ECS field | Example | Normalisation |
|-----------|---------|---------------|
| `host.name` | `"WEB-PROD-01"` | Lowercased → `"web-prod-01"` |
| `source.ip` | `"192.168.1.10"` | Lowercased |
| `user.name` | `"CORP\\alice"`, `"alice@corp.example"`, `"alice"` | Domain prefix stripped, lowercased → `"alice"` |
| `file.hash.sha256` | `"A3B4..."` (64 hex chars) | Lowercased |
| `process.name` | `"SVCHOST.EXE"` | Lowercased → `"svchost.exe"` |

Unknown keys (e.g. `host.group`, `cloud.region`) are silently ignored. At least
one **recognised** key with a non-empty value is required on v2.

### Validation errors (v2)

| Condition | HTTP status | `detail` |
|-----------|-------------|---------|
| `entities` absent or `null` | `422` | `entities is required. …` |
| `entities` is not an object | `422` | `entities is required. …` |
| `entities` is empty `{}` | `422` | `entities must be an object containing at least one recognised ECS field …` |
| All keys unrecognised or all values empty | `422` | `entities must be an object containing at least one recognised ECS field …` |

---

## Successful response (HTTP 201)

Returns the full serialised alert, including its `display_id` (e.g. `"AL-0042"`),
`state` (`"new"`), and any derived `severity` or `title` for platform-native source
kinds.

---

## Migration guide (v1 → v2)

1. Add the `entities` object to every ingest request.
2. Populate at least one recognised ECS field from the alert's source data — e.g.
   the originating hostname, source IP, or username.
3. Change the endpoint URL from `/api/alerts/` to `/api/v2/alerts/`.
4. Handle the new `422 Unprocessable Entity` response code in your error handling.

Wazuh shippers should map Wazuh's existing `agent.name` → `host.name` and
`data.srcip` → `source.ip` fields before calling v2.
