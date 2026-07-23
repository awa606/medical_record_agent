# Enterprise Integration Skeleton

This folder documents the Issue #77 enterprise skeleton. It is an Enterprise
Integration Skeleton and a pre-production architecture candidate only. It is not
production-ready and does not provide a real hospital HIS, EMR, IdP, endpoint,
certificate, credential, or patient-data integration.

## Scope

- Enterprise capabilities are controlled by environment feature flags and are
  disabled by default.
- Organization, Department, Membership, and RequestContext are contract models
  only. They are not persisted in the current SQLite schema.
- IdentityProvider, HISAdapter, and EMRAdapter are protocol boundaries with
  local or mock implementations only.
- Mock EMR writeback is allowed only after an active doctor approval exists for
  the current record revision.
- Idempotency-Key is enforced by an in-process skeleton store to prevent repeat
  mock writebacks during a process lifetime. A production deployment must
  replace this with a durable store.
- Structured audit events redact sensitive fields before they are written to the
  existing task audit log.

## Capability Status API

`GET /api/enterprise/capabilities` returns only capability names mapped to one
of these states:

- `disabled`
- `mock`
- `configured_unverified`
- `verified`

The response intentionally does not include URLs, keys, tokens, model names,
hospital identifiers, or vendor names. Default state is disabled for every
capability.

Key flags:

- `MRA_ENTERPRISE_ENABLED=1` enables the enterprise skeleton switch.
- `MRA_ENTERPRISE_IDENTITY_PROVIDER=local|mock_oidc|configured`
- `MRA_ENTERPRISE_HIS_ADAPTER=mock|configured`
- `MRA_ENTERPRISE_EMR_ADAPTER=mock|configured`
- `MRA_ENTERPRISE_*_VERIFIED=1` moves a configured capability to `verified`
  after an external verification process. This codebase still does not create a
  real adapter.

## Mock EMR Writeback

`POST /api/enterprise/emr/writeback` requires authentication and an
`Idempotency-Key` header.

Request body:

```json
{
  "task_id": 1,
  "organization_id": "org-1",
  "department_id": "dept-1"
}
```

Writeback is blocked when:

- enterprise or the mock EMR adapter is disabled;
- the task does not exist;
- the current user cannot access the task;
- the task has no active approval;
- the record is degraded, generated through fallback, unsafe, or still has
  unconfirmed fields or diagnoses.

The Mock EMR receipt is deterministic and contains no real hospital reference.
Repeating the same task and idempotency key returns the original response
without creating a second mock writeback. Reusing the key for a different task
returns a conflict.

## Audit And Observability

Enterprise audit events are structured as `EnterpriseAuditEvent` and sanitize
values for keys such as token, password, authorization, api_key, patient
name/text, draft, and conversation_text. The skeleton writes these sanitized
events to the existing task audit log and does not alter the SQLite schema.

Operational contracts are exposed in code and via read-only routes for metrics,
backup planning, upgrade preflight, and rollback planning. They are
contract-only hooks and do not execute backup, restore, migration, or rollback
commands.

## Unresolved Hospital Inputs

Before this can move beyond skeleton status, the project still needs:

- real hospital IdP metadata and approval for OIDC or SAML;
- HIS/EMR vendor API contracts, sandbox credentials, certificates, and test
  patient rules;
- durable idempotency storage and audit retention policy;
- reviewed schema migrations and rollback tests;
- hospital-approved monitoring, backup, restore, retention, and incident
  response procedures;
- security review for secrets, network allowlists, and deployment topology.
