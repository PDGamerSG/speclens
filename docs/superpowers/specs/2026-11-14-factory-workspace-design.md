# Factory workspace implementation

The user approved implementation of the researched factory-pilot roadmap on 14 November 2026 and requested additional substantive sections. This design turns that direction into one integrated release. It extends the working photo-inspection application; it does not establish industrial accuracy or authorize autonomous material release.

## Product scope

Preserve the anonymous demo. Add a separate signed-in factory workspace with Products & Specs, Capture Stations, Lots, Review Queue, Standards, Validation, Nonconformances, Activity, and Team. Reuse the photo desk, batch jobs, images, history, Hindsight synchronization, specification parser and visual style. Separate human disposition from teaching. Support a complete operator → engineer → quality-owner handover and complete evidence export.

Accounts use named usernames and locally hashed passwords with revocable opaque sessions; they do not claim verified email or enterprise SSO. Registration creates a new isolated team, while one-use expiring invitations create additional members. Roles are admin, engineer, operator, viewer. Admin manages membership and publishes revisions/standards; engineer reviews/proposes; operator captures; viewer reads. The initial team admin is also its quality owner. No external identity-provider subscription is required. Public registration and login need independent brute-force limits even when the demo limiter is disabled. Sessions/cookies and every old media/record/job endpoint must honor the current team boundary and inactive membership.

Additional sections beyond the original roadmap: Nonconformances (linked quality issue, severity, containment, corrective action, owner and closure history) and Activity (append-only attributable lifecycle events). This is a small quality-issue register, not a complete regulated CAPA system. Capture Stations record instructions and setup context; they do not claim automatic camera calibration.

## Persistence and compatibility

Expand the schema additively in migration 0003. Keep existing inspections/corrections untouched. New tables hold users, teams, memberships, hashed sessions/invitations, and versioned, team-owned pilot records. A shared pilot-record repository stores validated product/revision/station/lot/capture/review/standard/nonconformance/event/validation objects with kind, owner, version, timestamp and JSON payload. The typed API owns shape/lifecycle and cross-record invariants; IDs and row versions are server controlled. Use compare-and-swap updates and explicit 409 conflicts rather than silent lost updates. Relationships must be same-team and correct-kind. Events share the mutation transaction.

An authenticated team's existing workspace owner ID is its stable `team-…` ID. Anonymous owner cookies remain separate. Scope gains optional `revision_id`; its pilot identity uses stable team + revision IDs, not editable names. Each approved revision freezes specification text, human-confirmed parsed taxonomy and capture instructions. Revision text is immutable after creation; a replacement is a new revision. The global text blob remains deduplicated storage; owner-specific parsed taxonomy must not mutate another workspace's reading.

Inspections carry immutable `pilot` context: product/revision/lot/station IDs, physical part, capture ID, actor, instructions/taxonomy snapshot, approved source versions, capture time and available model/prompt identity. All inference paths preserve this context through the existing queue. A deterministic capture/result association prevents duplicate saved assessments after recovery. Lots/captures/review records survive technical job cleanup. Pilot retention is explicit and separate from anonymous demo age-based purge. Administrative deletion clears team operational records and media without granting another member that permission.

## Internal contracts

`app.pilot.store.PilotStore(engine)` owns typed pilot records. Record shape: `{id, kind, owner_id, version, created_at, updated_at, ...fields}`. Methods: `list(owner_id, kind)`, `get(owner_id,id,kind=None)`, `create(owner_id,kind,fields,actor=None,id=None)`, `update(owner_id,id,version,changes,actor=None)`, `event(owner_id,actor,action,target_id,details=None)`, `delete_records(owner_id)`. Not-found/invalid/conflict errors use `HTTPException` 404/422/409 where applicable. `actor` is `{id,name,username,role}`. An internal repository operation is not an authorization boundary: API/service callers enforce roles.

`app.pilot.auth.current_identity(request, engine=None)` returns `None` for no session, otherwise `{user:{id,username,name},team:{id,name},role}`. An invalid/expired/revoked cookie must not fall through as anonymous access to team data. `require_identity(request, roles=None)` raises 401/403; it uses the existing workspace service's engine, including tests. Root integrates `public.owner`, main router registration, old route permissions, inspection context and service hooks.

`PilotStore.capture_context(owner_id, actor, *, revision_id, lot_id, station_id, physical_part_id, capture_id, retake_of=None)` validates approved revision/open lot/active compatible station and returns an immutable context dictionary with `spec_text`, `taxonomy`, `factory`, `part_family`, `revision_id`, `product_id`, `lot_id`, `station_id`, `physical_part_id`, `capture_id`, `actor`, and instructions. Root reserves/records capture submissions using the repository. Context reads are rechecked at execution time. Root creates review cases when a pilot inspection persists.

## HTTP contract

All new routes live at `/api/workspace/pilot`, preserving existing public routing. JSON errors use FastAPI `detail`. List records initially use the complete pilot overview for this bounded workspace; exports are complete and declare record counts. UI filters do not pretend to search unloaded history.

- `GET /session`: `{authenticated,user,team,role}`; unauthenticated fields null.
- `POST /register`: `{username,password,name,team_name}` → session; creates team admin and cookie.
- `POST /login`: `{username,password}` → session. `POST /logout`: revokes cookie/session.
- `GET /team`: `{members:[{id,user_id,username,name,role,active,version}],invites:[{id,role,expires_at,used_at}]}`.
- `POST /invites`: `{role}` → `{token,expires_at}`; token returned once, stored hashed, one use.
- `POST /join`: `{token,username,password,name}` → session.
- `PATCH /members/{id}`: `{version,role,active}`; cannot remove/demote final admin.
- `GET /overview`: `{products,revisions,stations,lots,captures,reviews,standards,nonconformances,activity}`; each value is an array of typed records, team scoped. Review records include their inspection or inspection ID sufficient to reopen the existing desk.
- `POST /products`: `{code,name,factory,description?}` → product.
- `POST /revisions`: `{product_id,label,spec_text,capture_instructions?}` → draft revision including parsed taxonomy. `PATCH /revisions/{id}`: `{version,status:'approved'|'retired'}`. Admin only; a retired revision is not silently reactivated.
- `POST /stations`: `{name,product_id,instructions}` → active station. `PATCH /stations/{id}`: `{version,active,instructions?}`.
- `POST /lots`: `{reference,revision_id,station_id,notes?}` → open lot. `PATCH /lots/{id}`: `{version,status:'open'|'closed'}`. Closing blocks unresolved captures/reviews.
- `PATCH /reviews/{id}`: `{version,status:'open'|'claimed'|'closed',outcome?:'accept'|'reject'|'hold'|'retake',reason?}`. Actor assignment is server-derived; closing requires outcome/reason. Hold/retake leave the physical item unresolved and are shown explicitly. Reopening preserves history. This action never teaches.
- Standards are created by the existing correction operation as candidates. `PATCH /standards/{id}`: `{version,status:'approved'|'retired',reason?}`; admin approval, engineer proposals. Approval triggers the existing retryable correction sync. Retirement blocks eligibility locally immediately. List fields include correction/inspection/revision IDs, clause, rule_text, verdict, defect_type, status, approver and sync status.
- `POST /nonconformances`: `{title,lot_id,inspection_id?,severity:'minor'|'major'|'critical',description,containment?,assignee?}`. `PATCH /nonconformances/{id}`: `{version,status:'open'|'contained'|'closed',containment?,corrective_action?,resolution?,assignee?}`. Closure requires corrective action and resolution; audit history preserved.
- `GET /lots/{id}/export`: complete JSON evidence manifest; root implements joining inspection/media/disposition evidence. `GET /lots/{id}/csv`: flattened complete report.
- `GET /validation`: `{runs:[...]}`; `POST /validation`: `{name,cases:[...],configuration?:{...}}` → immutable run. Cases: `{sample_id,physical_part_id,lot_id,session_id,truth:'good'|'defect',severity?,baseline:'good'|'defect'|'uncertain'|'error',with_memory:same}`. Imported model outputs are evaluation inputs, not executed or verified live inference. Reject duplicate sample IDs and inconsistent repeated-part truth/predictions; make aggregation explicit. Return matrix, escaped defects, false rejects, Review/error coverage, paired changes, cluster-level uncertainty and independence limitations. No claims from Review-as-positive accuracy. Importing precomputed results incurs no model cost.

Existing multipart inspect/jobs routes accept optional `revision_id`, `lot_id`, `station_id`, `physical_part_id`, `capture_id`, `retake_of`. Signed-in pilot submissions require the full applicable context. ScopeSettings may include these optional strings; omit unset values. Existing demo calls keep working unchanged. Pilot compare runs remain evaluation activity and cannot inflate production lot counts.

## Governance and failure behavior

Only active approved standard versions for the precise team/revision enter recall/crops/summary. A saved pilot correction stays a candidate and is excluded from outbox retain until approval. Old anonymous corrections keep their existing semantics. Recheck eligibility after retrieval and before provider use. If approval/revision is withdrawn during an active provider call, preserve provenance and quarantine the resulting review case; never erase historical evidence or silently treat the result as current.

Every pilot inspection creates an open human review case. Model recommendation and human decision remain separate. A failed required service/capture stays pending/failed under its stable identity. Closed lots cannot receive new captures. Reports distinguish physical items, capture attempts, comparison/evaluation calls, model verdicts, human disposition and unresolved work. Retakes do not create independent parts or hide the first result.

## Verification and release

Use real database/API tests for identity, role isolation, invitation replay, session revocation, immutable revisions, compare-and-swap conflicts, lifecycle rules, standards retirement, durable context, duplicate submission, retention, and complete reports. Use pure-data validation tests for Review/error handling and correlated repeated views. Browser tests cover account creation, controlled product/station/lot setup, inspection-to-review, standards approval/retirement, issue closure, activity, validation import, exports and narrow layouts without paid providers. Run existing backend, frontend build/lint, and Playwright regressions.

Release only after review and checks, then publish to main and deploy through the existing documented backup/deploy path. Actual factory performance still requires permissioned representative parts and a quality owner; these software features do not supply that evidence.
