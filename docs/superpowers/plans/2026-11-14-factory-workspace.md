# Factory workspace implementation plan

Design: [factory workspace](../specs/2026-11-14-factory-workspace-design.md). User approval: “implement it” plus additional sections. Baseline `4148283`. Stop condition: connected sections with durable isolated records and passing relevant software checks, published to main with accurate deployment status.

## Task 1 — Team-owned domain and access

Owner: backend implementer. Create `backend/app/pilot/{tables,store,auth,routes}.py`, additive migration 0003, schema registration, and `tests/test_pilot.py`. Implement the HTTP/internal contracts in the design. Reuse engine/migration/parser patterns; never read runtime secrets or touch production. Tests first for session/membership isolation and lifecycle transitions. Do not edit existing workspace services/routes, main/public middleware or frontend; root owns integration.

## Task 2 — Factory workspace UI

Owner: frontend implementer. Create `frontend/src/pilot/` with typed API, authentication, navigation and connected domain sections. Integrate into Workspace with a clearly labeled Factory workspace entry and demo return path. Reuse existing CSS/fonts/icons and inspection desk. Implement controlled selectors/capture context plus first-class review/standards actions; reload from API after changes. Own frontend changes and browser tests, coordinating exact response shapes with Task 1. Test real workflows through the stubbed API server; no fake populated production data.

## Task 3 — Validation and additional research

Owner: evaluation implementer. Research issue containment/action/audit workflows using opened official primary sources and save the bounded evidence/log. Implement pure evaluation in `backend/app/pilot/validation.py`, API in `validation_routes.py`, and meaningful tests. Imported matched results need part/lot/session grouping, first-attempt semantics, explicit failures/Review, no leakage claims without provenance, uncertainty limitations, immutable manifests and no provider calls. Reuse Task 1 repository/auth contracts. Do not edit frontend, db schema or workspace service.

## Task 4 — Inspection integration and reporting

Owner: root. Extend stable Scope revision identity, scoped taxonomy, old route permissions and auth owner, context propagation through job submission/runner/service, deterministic capture/result association, review creation, standard proposal/approval/retirement eligibility, quarantine, retention and complete lot JSON/CSV exports. Register routers. Add tests before behavior changes for the integration invariants. Keep public demo compatibility.

## Task 5 — Review, verification and release

Inspect all agent diffs and test evidence; resolve contract gaps. Run backend tests, build/lint and browser suite; review security/ownership/lifecycle boundaries and restart/withdrawal cases. Update user/API/deployment docs and research status to implemented/proposed accurately. Commit, push/merge to main after checks, backup/deploy existing backend, and verify health/static version and non-mutating live endpoints. If external access blocks deployment, report exact limitation without representing a push as deployment.

## Global constraints

- Native agents share one checkout; file ownership above prevents edit conflicts. No nested agents, commits/pushes/deploys or paid calls from children.
- Additive migration; preserve existing anonymous data and all old interfaces by default.
- New state is team-owned, input-validated, versioned and audited; roles enforced on server.
- Human disposition is independent of reusable teaching; approval and memory sync are distinct.
- Retired/unapproved/wrong-scope evidence never enters a new prompt. Preserve and quarantine in-flight affected results.
- Explicit denominators and error/Review workload; no industrial-accuracy or regulatory-compliance claims.
- No decorative placeholder sections or new hosted service dependency.
