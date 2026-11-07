# Chief Skill implementation plan

Goal: ship and verify the correction → retain → recall → new inspection workflow today.
Stack: FastAPI, SQLite, Hindsight HTTP API, Meta vision, React, Vite, Tailwind.
Spec: docs/design.md. Execute inline, commit roughly every ten minutes while making progress.

1. Establish the repository, dependency environments, design context, and baseline checks.
2. Write failing behavioral tests for scope isolation, correction persistence, Hindsight failure handling and memory-enabled inspection. Implement a SQLite store, Hindsight adapter and inspection service; run the tests.
3. Add validated workspace API routes, sample image retrieval, paired comparison and correction retry. Prove endpoint behavior with FastAPI tests.
4. Build the operator workspace, memory library and comparison results. Keep loading, offline, empty and error states explicit. Run TypeScript build and lint.
5. Exercise the UI in a headless browser, run live Hindsight/Meta checks when credentials are available, record actual results, and produce setup and demo documentation.
6. Push the tested application and report any remaining credential or publishing requirement.

Completed: durable scoped memory, operator workspace, seven browser scenarios, 53 Python checks, live Meta/Hindsight integration, a held-aside synthetic ablation, Docker packaging, CI, and reviewable submission drafts.
