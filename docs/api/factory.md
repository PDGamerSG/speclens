# Factory workspace HTTP API

This reference covers the implemented team domain, plus its integration with the existing [inspection API](README.md). All factory routes use `/api/workspace/pilot`. The browser uses relative URLs and an HttpOnly session cookie; there is no API-key or bearer-token login scheme for users.

## Identity, ownership and errors

Registration creates an isolated team. Active membership determines the current role on each request. Team operational records, old inspection/history/job/media routes, and exports use the stable team ID as owner. An anonymous demo cookie cannot select a team. Missing/wrong-team/wrong-kind records return 404.

Sessions use `speclens_session`, expire after seven days, and are revoked by logout or membership deactivation. The server stores only a SHA-256 session-token hash; the cookie is HttpOnly, SameSite=Strict, path `/`, and Secure over HTTPS. No cookie means an unauthenticated session response; an invalid/expired/revoked cookie returns 401 and does not fall back to anonymous team access. Logout can clear an invalid cookie.

Writes accept the same origin or an exact configured `SPECLENS_ALLOWED_ORIGINS` entry with the request's scheme. Foreign origins and `Sec-Fetch-Site: cross-site` are rejected. Reverse-proxy HTTPS metadata must be correct. Registration/login/join have independent durable limits even with `SPECLENS_PUBLIC=0`: per 15-minute window, 80 combined attempts per address, 40 per action/address, and 12 per action/normalized username. Accepted and failed attempts count; 429 includes `Retry-After`.

Factory records have server-controlled `id`, `kind`, `owner_id`, `version`, `created_at` and `updated_at`, followed by kind-specific fields. IDs are meaningful only with their team owner. Lists are complete for this bounded workspace. Updates require the last read integer `version`; success increments it. A stale version returns 409. Domain mutation and its activity event commit together. Actor objects `{id,name,username,role}` derive from the session; clients cannot choose reviewers or claim assignees.

Errors use FastAPI's `detail` field. 401 means sign-in/session failure, 403 insufficient role or rejected origin, 404 inaccessible reference, 409 lifecycle/version conflict, 422 invalid input, and 429 account-attempt limit. Existing inspection routes can additionally return provider, spend, upload and queue errors. Optional request strings are trimmed; unknown fields in factory mutation bodies are rejected.

Role abbreviations below: **all** = any active member; **setup** = admin/engineer; **capture** = admin/engineer/operator. Admin alone publishes revisions/standards and manages membership.

## Account and team routes

| Method/path | Access | Body and response |
| --- | --- | --- |
| `GET /session` | Public | `{authenticated,user,team,role}`; signed-out user/team/role are null |
| `POST /register` | Public | `{username,password,name,team_name}` → 201 session, sets cookie; initial role admin |
| `POST /login` | Public | `{username,password}` → session and a new cookie |
| `POST /logout` | Public | Revokes supplied session, clears cookie → signed-out session shape |
| `POST /join` | Public | `{token,username,password,name}` → 201 session; atomically consumes a valid invitation |
| `GET /team` | Admin | `{members:[{id,user_id,username,name,role,active,version}],invites:[{id,role,expires_at,used_at}]}` |
| `POST /invites` | Admin | `{role}` → 201 `{token,expires_at}`; token returned once, stored hashed, valid 48 hours |
| `PATCH /members/{id}` | Admin | `{version,role,active}` → updated member; preserves at least one active admin |

`user` is `{id,username,name}`; `team` is `{id,name}`. Username is case-insensitive, globally unique, 3–64 characters matching `[A-Za-z0-9_.-]+`. Password is 12–256 characters on registration/join; login accepts existing passwords up to 256. Name and team name are nonempty and at most 100 characters. Roles are `admin`, `engineer`, `operator`, `viewer`. Invitation/session expiry fields in the database/team API use Unix seconds; operational record dates use UTC ISO strings.

Join creates a new local account; it is not an email-verification or existing-account team-switch flow. Role changes apply to existing sessions. Deactivation revokes all that user's sessions for the team; reactivation does not revive them. No password reset/change, account recovery, MFA, SSO or full account-erasure endpoint is implemented.

## Overview and setup records

`GET /overview` requires any active member and returns arrays named `products`, `revisions`, `stations`, `lots`, `captures`, `reviews`, `standards`, `nonconformances`, `activity`. No UI-filter or history-page limit truncates this response. Review records contain `inspection_id` and may embed the inspection. Standard `sync_status` is read from the durable correction state independently of approval status. Validation runs use their separate endpoint below.

| Method/path | Access | Body and behavior |
| --- | --- | --- |
| `POST /products` | Setup | `{code,name,factory,description?}` → 201 product; code ≤64, name/factory ≤100, description ≤4000 |
| `POST /revisions` | Setup | `{product_id,label,spec_text,capture_instructions?}` → 201 draft with locally parsed taxonomy; label ≤64, text ≤12000, instructions ≤4000 |
| `PATCH /revisions/{id}` | Admin | `{version,status:'approved'\|'retired',taxonomy?}` → revision; approval confirms and freezes taxonomy/instructions, retirement cannot be reversed |
| `POST /stations` | Setup | `{name,product_id,instructions}` → 201 active station; name ≤100, instructions 1–4000 |
| `PATCH /stations/{id}` | Setup | `{version,active,instructions?}` → station; setup version changes are visible to queued/in-flight captures |
| `POST /lots` | Capture | `{reference,revision_id,station_id,notes?}` → 201 open lot; reference ≤100, notes ≤4000 |
| `PATCH /lots/{id}` | Setup | `{version,status:'open'\|'closed'}` → lot; closure checks all attempts and reviews |

All references must be same-team and correct-kind. A lot requires an approved revision and active station for the same product. Its revision/station identity cannot be edited. Revision text/identity cannot be edited after creation; create a replacement. Stations record instructions, not automatic calibration.

Approved taxonomy shape:

```json
{
  "part_name": "Shell",
  "part_width_mm": 20,
  "source": "rules",
  "found_reject_section": true,
  "classes": [
    {
      "defect_type": "crack",
      "label": "Crack",
      "clause": "4.1",
      "description": "Reject visible cracks longer than 2 mm.",
      "limit_mm": 2
    }
  ]
}
```

Approval validates supplied taxonomy or the stored draft when omitted. There must be 1–12 unique defect types, at most 24 lowercase letters/digits separated by single underscores; `good` is reserved. Part width is finite and >0 or null; class limits are finite and ≥0 or null. Strings/booleans/non-finite numbers are rejected as dimensions. Source is `rules`, `model` or `fallback`. Part name/label/clause are strings ≤100, description ≤4000, and `found_reject_section` is boolean. Missing optional text/width/limit fields are normalized, including `limit_mm:null`; labels default from the defect name, source to `rules`, and the section flag to false. Approved taxonomy and capture instructions are immutable.

## Captures and existing inspection routes

Use `POST /api/workspace/inspect` or `POST /api/workspace/jobs/inspect` with the existing photo fields (`file` or `sample_id`, optional `memory_enabled`) and these multipart fields:

| Field | Factory rule |
| --- | --- |
| `revision_id` | Required approved team revision |
| `lot_id` | Required open lot for that revision |
| `station_id` | Required active compatible station selected on the lot |
| `physical_part_id` | Required nonempty physical-item label, ≤100 characters |
| `capture_id` | Stable retry identity, 1–64 letters/digits/underscores/hyphens; server generates one if omitted, but clients should retain an explicit ID for retries |
| `retake_of` | Optional prior same-team capture of the same physical part, lot and revision |

Capture access requires admin/engineer/operator. The server derives product, factory, spec, actor, instructions, taxonomy, revision/station versions and approved source versions. Client display names or alternate specification text do not override that recipe. Context is preserved in `inspection.pilot` through the durable job path and checked at execution time. Reusing the same capture identity for changed pixels or context returns 409. Retry/recovery associates one saved assessment and one review with the capture.

Capture states include `pending`, `done`, `failed` and `quarantined` (technical job states are separate). Every saved factory assessment creates an open human review. Withdrawal during inference preserves provenance and quarantines the evidence. A valid retake links `retake_of`/`resolved_by`; it does not erase the prior failure or disposition.

Existing scope reads such as `/api/workspace/overview` and `/dashboard` accept `revision_id` for the controlled team scope. `/compare` and `/jobs/compare` use an approved factory revision as evaluation activity; those calls do not create production captures/reviews or inflate lot counts. Old media, records, jobs and export routes honor the authenticated team boundary. An invalid session is not permission to use anonymous fallbacks.

## Reviews and standards

`PATCH /reviews/{id}` requires setup access. Body: `{version,status:'open'|'claimed'|'closed',outcome?:'accept'|'reject'|'hold'|'retake',reason?}`. A closed review requires outcome and nonempty reason ≤4000. Non-closed reviews cannot set an outcome. Claiming assigns the signed-in actor; closing records `reviewer` and timestamp. Reopening appends history and clears current disposition. It does not teach, change the inspection's model verdict or clear quarantine. Quarantined evidence cannot be accepted.

Lot closure requires every open review closed, including older attempts. Held/retake/quarantined cases need an explicitly linked valid replacement. The newest capture's human review must be closed Accept/Reject; pending/running or unresolved failed work blocks closure. Closed lots reject captures. Export and closure use the same part-resolution policy.

Standards are proposed with existing `POST /api/workspace/corrections` (setup access): `{inspection_id,verdict:'good'|'defect',defect_type,rule_text,reviewer?}`. Rule text is 10–2000 characters; a good verdict uses `good`, a defect uses an allowed defect class. For signed-in requests, actor/reviewer derive from the session. A pilot inspection creates a candidate standard linked to correction, inspection, revision, clause and source photo. Quarantined evidence returns 409; use a valid replacement inspection. Identical retries repair a missing candidate after an interrupted proposal without duplicating the correction or changing an existing standard's state.

`PATCH /standards/{id}` requires admin: `{version,status:'approved'|'retired',reason?}`. Approval requires an approved revision, records `approver`, commits locally, then starts retryable correction sync. A pending sync does not undo approval. `POST /api/workspace/corrections/{id}/sync` permits setup roles to retry an eligible correction. Candidates are excluded from retain/recall; only approved current standard versions for the exact team/revision are eligible. Retirement blocks new use immediately and cannot be reversed. Published standard content is immutable. No standard action disposes of the current physical item.

## Nonconformances and activity

Setup roles may `POST /nonconformances` with:

```json
{
  "title": "Cracks at fixture edge",
  "lot_id": "lot-…",
  "severity": "major",
  "description": "Affected parts isolated for review.",
  "requirement": "Clause 4.1",
  "containment": "Hold the affected tray."
}
```

Optional fields: `inspection_id` (must belong to this lot/team), `assignee` (active team `user_id` or null), `requirement`, `root_cause`, `evidence`. Title ≤200, description/containment ≤4000, requirement/root cause/evidence ≤2000. Severity is `minor`, `major` or `critical`.

`PATCH /nonconformances/{id}` accepts `{version,status:'open'|'contained'|'closed',containment?,corrective_action?,resolution?,requirement?,root_cause?,evidence?,assignee?}`. Action/resolution ≤4000. Contained requires containment; closed requires corrective action and resolution. Closure actor/time and transition history are retained. Reopen by setting `open`. Optional cause/evidence do not constitute verified effectiveness or a full regulated CAPA workflow. Issue closure and lot/material release are separate.

Activity is the `activity` array in overview: immutable event records with `actor`, `action`, `target_id`, `details` and common metadata. The application records lifecycle changes transactionally. It does not provide tamper-proof security logging or a public event mutation endpoint.

## Validation imports

`GET /validation` requires any active member and returns `{runs:[...]}`. `POST /validation` requires setup access and returns a 201 immutable run:

```json
{
  "name": "Matched intake results",
  "cases": [
    {
      "sample_id": "sample-001",
      "physical_part_id": "part-001",
      "lot_id": "study-lot-1",
      "session_id": "study-session-1",
      "truth": "defect",
      "severity": "major",
      "baseline": "good",
      "with_memory": "uncertain"
    }
  ],
  "configuration": {"provenance_note": "Importer-supplied; not independently verified"}
}
```

Name is 1–160 characters; 1–2000 cases; IDs are nonempty strings ≤120. Truth is `good`/`defect`; predictions are `good`/`defect`/`uncertain`/`error`; optional severity is minor/major/critical. Configuration must be finite JSON, ≤12,000 UTF-8 bytes and ≤8 nested levels. Duplicate sample IDs are rejected. Repeated physical-part IDs must keep identical truth, paired predictions, lot and severity, while recording every imported view. First input occurrence per physical part supplies the evaluated result.

No inference/provider call runs. IDs, truth, outputs, ordering and provenance are unverified declarations, not checked references to production records. Results include counts; both 2×4 truth/output matrices; escaped-defect/all-defective and false-reject/all-good rates; Review/error workload and decision coverage over all parts; paired transitions/improvements/regressions; and descriptive 95% intervals for memory-minus-baseline changes.

Parts connected through any lot/session are sampled together in a paired cluster bootstrap (1000 fixed replicates). Fewer than two clusters gives no interval. Missing truth denominators give null rates; replicates without a relevant truth class are excluded and counted in `valid_replicates`. Small/degenerate intervals and zero observed failures are not proof of generalization or industrial accuracy. Review/error are never treated as correct binary detections.

The run includes `source:'imported_unverified'`, configuration, immutable manifest/cases/selected IDs/clusters/SHA-256 digest, results and explicit limitations. No update route exists. Different IDs do not prove independence or absence of training/teaching leakage.

## Complete lot reports, retention and deletion

All active members can download `GET /lots/{id}/export` (JSON attachment) and `GET /lots/{id}/csv` (CSV attachment). Both read the full team-owned lot beyond UI filters. JSON format version 2 includes lot/product/revision/station, captures, inspections, reviews, relevant corrections and revision standards, nonconformances, activity, part resolution and counts for physical parts, attempts, assessments, reviews, unresolved parts and missing media.

`evidence` lists media URL, record/field, availability and SHA-256 for available workspace files. Bytes are not embedded; media requires the same active team session. CSV has one row per capture, with lot/physical/capture/retake IDs, capture status, inspection/model verdict, human outcome/review/reviewer/reason, quarantine, revision/station/time and image URL. It includes failed and pending captures with absent assessment fields. Potential spreadsheet formulas in text are escaped. JSON carries the complete nested histories and media hashes.

Factory operational evidence is excluded from the anonymous `RETENTION_DAYS` age purge (default 90). Finished job/upload cleanup can occur separately. Admin-only `DELETE /api/workspace/data` with `{"confirm":"DELETE"}` removes team operational records, linked media and configured memory banks after active jobs finish. Remote memory deletion failure preserves local records for retry. Inspect `media_failed`/`memory_failed` cleanup counts. Users, teams, memberships, sessions, invitations and auth-limit records remain; this is not full account erasure. Backups/provider retention are separate operational responsibilities.

Implementation: `backend/app/pilot/{auth,routes,store,tables,integration,resolution,reports,validation,validation_routes}.py`, the workspace service/routes, and additive migration `0003_factory_workspace.py`. See the [factory guide](../factory-guide.md) and [deployment procedure](../deployment.md#factory-workspace-release-migration-and-retention).
