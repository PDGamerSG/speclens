# SpecLens roadmap: earn a real factory pilot

Research date: **14 November 2026, Asia/Kolkata**. Historical application baseline: `main` at `3e39563`. The user selected a real factory pilot as the leading outcome and subsequently approved implementation.

**Implementation update:** the shared factory workspace now implements accounts/roles, controlled product revisions, stations/lots, durable physical-part captures and retakes, independent human review, approved standards, nonconformances, activity, complete lot exports and imported validation. The [factory guide](../../factory-guide.md) describes shipped behavior and limitations; [additional workflow research](06-additional-quality-workflows.md) covers issue containment and activity. Findings below describe the historical baseline and the broader conditional roadmap. Imported validation does not execute or verify live inference, and real factory performance remains unmeasured.

## Recommendation

Build toward an **operator-assisted inspection station for one part family, one controlled capture setup, and one named quality owner**. The first useful expansion is a shared, traceable review workflow: an operator submits a lot item, an engineer records a disposition, a separately approved standard can influence later inspections, and a supervisor can reconstruct the evidence.

This pilot boundary is a proposal, not a discovered customer requirement. A factory needing air-gapped processing, several simultaneous defects, or unattended conveyor-speed decisions may require different product and hardware work before a pilot is feasible.

The principal opportunity to test is whether **specification-linked text and visual corrections, applied through retrieval, help on later unseen physical parts with less engineer effort**. Competitors already advertise correction reuse and controlled inspection deployments. SpecLens must demonstrate a useful workflow and measured transfer; the broad idea is not established as unique.

Three research agents independently covered the source/workflows, competitors, and evaluation/reliability. The synthesis also examines factory operations references. Read the [visual roadmap](roadmap.html) for the sequence, and the four supporting reports for evidence:

| Report | What it establishes |
| --- | --- |
| [Code and workflow audit](01-code-and-workflows.md) | Implemented, partial, and missing capabilities, with source locations and change boundaries |
| [Market and positioning](02-market-and-positioning.md) | Five competitors, 16 primary-source evidence entries, exact retrieval attempts, and contrary evidence |
| [Evaluation and reliability](03-evaluation-and-reliability.md) | Factory dataset design, paired evaluation, capture limits, and proposed release gates |
| [Pilot operations](04-pilot-operations.md) | Recipe/result provenance, physical-unit denominators, pilot workflow, and discovery questions |

## What is already built

SpecLens already provides single and batch inspection, phone capture, Accept/Reject/Review assessments, specification text/PDF import and class extraction, correction memory with retryable synchronization, reference crops, masks and estimated dimensions, paired comparison, saved history, a dashboard, export/delete, and retention. These are foundations to reuse.

The code audit identifies operational gaps behind several familiar labels:

| Existing behavior | Gap for a shared factory pilot |
| --- | --- |
| Browser-cookie workspace separation and typed reviewer name | Authenticated people, recoverable team membership, server-enforced roles, and attributable actions |
| Persisted specification text identified by hash | Tenant-owned part/revision catalog, approved taxonomy, effective revision, and immutable inspection recipe |
| Correction saved and immediately eligible for memory after sync | Separate human disposition, proposed standards, approval, conflict review, supersession, and retirement |
| Batch results ordered for attention; history marks uncorrected cases | Durable review cases, assignment, closure, handover, and reopening |
| Upload batch IDs in technical job records | Manufacturing lot/physical-item/capture relationships that survive job cleanup |
| Dashboard assessment counts and model reject rate | Physical-unit denominators, human outcomes, production/evaluation separation, review backlog, and uncertainty |
| Server history pagination and several exports | Complete searchable history in the UI and reproducible, server-filtered lot evidence exports |

Two issues deserve explicit treatment in the foundation work. Identical specification text currently shares mutable derived taxonomy across visitor scopes; this is a scope/integrity gap, not evidence of inspection-record leakage. Batch relationships currently depend on job records eligible for cleanup after seven days. A photo batch therefore cannot serve as durable manufacturing traceability. See the [code audit](01-code-and-workflows.md) for exact locations and qualifications.

The existing Lightsail deployment and optional Postgres/R2/worker adapters are separate from product scope. A migration should follow measured throughput, recovery, connectivity, and data-handling needs. Render, R2, and Redis are not assumed to have been provisioned.

## What the market evidence changes

The opened sources describe vendor capabilities; they are not independent product trials or performance benchmarks.

| Primary evidence | Finding | Roadmap consequence |
| --- | --- | --- |
| [LandingLens](https://landing.ai/landinglens), label book and Upload/Label/Train/Deploy sections | Collaborative defect definitions and iteration are established workflows. | “No code” and “learns from examples” are insufficient positioning on their own. |
| [Roboflow Workflow Evals](https://docs.roboflow.com/workflows/evaluate/workflow-evals), About and Deploy Gates | Captured evaluation configurations and promotion gates are documented. | Build a small, repeatable factory validation path rather than another generic workflow builder. |
| [Instrumental Trace](https://instrumental.com/product/trace/), serial search and virtual teardowns | Images and test evidence are connected to identifiable units. | Unit/lot identity and evidence reconstruction precede more dashboard charts. |
| [Overview training guidance](https://docs.overview.ai/docs/guides/ov20i/train-ai/), “Label from the image only” | Capture visibility, lighting, optics, and variation are part of the inspection problem. | Verify visible defect coverage before promising performance or dimensional measurement. |
| [Robovision Indurion](https://robovision.ai/indurion), Built for production and stages 3–7 | Validated corrections distributed across machines, immutable datasets, and controlled recipe/model changes are explicitly advertised. | Treat correction reuse as competitive overlap. Test the narrower spec-clause/retrieval workflow hypothesis. |
| [OPC Foundation machine vision use cases](https://reference.opcfoundation.org/specs/OPC-40100-1/5), Recipe Management and Result Transfer | Recipes hold task properties/parameters; results include product assignment, time, and status. | Preserve product/recipe/result provenance. OPC UA integration is conditional on the actual station. |
| [NIST proportions charts](https://www.itl.nist.gov/div898/handbook/pmc/section3/pmc332.htm), definition and binomial assumptions | Fraction nonconforming uses physical units; the described model assumes independent units and stable probability. | Separate photos and model calls from physical items. A model trend is not validated SPC or ground truth. |

Evidence types, supporting locations, feature conditions, and limitations are expanded in the supporting reports. A [synthesis source check](05-synthesis-source-checks.json) reopens the closest correction-reuse competitor and the evaluation-gate documentation.

## Proposed sections and the jobs they serve

Use four primary destinations for the first pilot: **Inspect, Review, Products & Specs, Pilot Results**. Keep team management in settings. The richer section names below describe workflows; they do not all need separate top-level pages.

| Proposed section | Operator/engineer job | Initial scope | Expansion trigger |
| --- | --- | --- | --- |
| **Inspect** — extend existing | Choose the approved part/revision and lot; follow capture instructions; submit and recover pending work. | Existing single/batch viewer plus stable capture identity, station context, retake links, and clear processing/review status. | Multiple views or defects become required by the chosen part, rather than added speculatively. |
| **Review Queue** — new | Find, claim, assess, hold, request a retake, and close work; hand unresolved items to the next person. | Open/claimed/closed cases with named actors, reasons, history, and independent human dispositions. Every pilot assessment is reviewed initially. | Assignment/escalation automation follows observed backlog and staffing. |
| **Products & Specs** — new controlled catalog | Maintain part identity, specification revision, confirmed classes/clauses, capture protocol, and active recipe. | One approved part/revision with draft/approved/retired state; immutable taxonomy/recipe snapshots. Reuse existing import/parser. | Revision comparison and import automation when a second real revision or product needs them. |
| **Standards Library** — evolve Quality Memory within Products & Specs | Propose, inspect evidence, approve, supersede, and retire reusable standards. | Candidate/approved/retired states, scope, clause, evidence, approver, version, and memory-sync status shown separately. | A Defect Atlas tab groups approved visual examples after enough reviewed cases exist. |
| **Lots & Traceability** — start inside Pilot Results | Find a physical lot/item, all its captures, unresolved decisions, and applicable revisions. | Durable lot and item/capture relationships independent of jobs; complete CSV/JSON evidence packet. Existing history becomes a drilldown. | Supplier/work-order links when a real incoming-inspection process supplies those identifiers. |
| **Validation Lab** — start as an engineer tool | Compare a frozen baseline and approved memory release on independently labeled, held-out parts. | Correct benchmark semantics, locked manifests, matched runs, per-class errors, Review rate, workload, latency, and uncertainty. Reuse comparison tooling. | A richer UI follows a repeatable evaluation with real factory data. |
| **Quality Insights** — evolve Dashboard | See reviewed outcomes, aged cases, failure backlog, and measured pilot performance. | Explicit physical-item counts, AI/human separation, production/evaluation filters, lot/station/timezone context. | Control charts require a valid sampling plan and stable process assumptions. |
| **Team & Connections** — settings first | Control access and hand results to the existing quality process. | Named members and a small permission model; one agreed export contract. | Signed webhooks or one actual MES/QMS connector when a receiving system and owner are known. |

This puts daily work before administrative breadth. Reports can live in lot detail, comparison inside validation, and visual defect examples inside standards. Avoid filling navigation with empty modules.

## Priority and dependency roadmap

Priorities below express dependency and pilot value judgments, not scored customer demand. Phases are gated milestones, not calendar estimates. Dataset collection and reference labeling can proceed alongside foundation work once the factory agrees to them.

| Phase | Deliverable | Why now | Exit evidence |
| --- | --- | --- | --- |
| **0 — Agree the pilot** | Named quality owner, one part/station, visible defect scope, capture protocol, identifiers, cloud permission, labeling and retention plan. | Hardware visibility, offline constraints, and the quality decision may invalidate the proposed workflow. | Factory-approved pilot brief and representative images; unresolved feasibility issues recorded. |
| **1 — Establish identity and revisions** | Authenticated shared team; stable tenant/part IDs; owned approved specification and taxonomy; pinned recipe and actor provenance. | Review ownership and approval are meaningless without verified actors and stable scope. | Access boundaries enforced across records/media/jobs; draft/retired revisions cannot start pilot work; demo and pilot records remain separate. |
| **2 — Complete the review loop** | Durable lot/item/capture identity; review cases and independent dispositions; governed standards; complete evidence export. | Turns the existing AI demo into an attributable handover between operator and engineer. | A real item's capture, AI result, human decision, approved sources, and lot report survive reload, retry, retirement, and job cleanup. |
| **3 — Validate in shadow operation** | Corrected benchmark, locked holdout, frozen standards, observed station latency/reliability, and human review of every pilot result. | Demonstrates whether the mechanism helps and what workload/errors remain. | Customer-set limits with denominators and uncertainty; no unexamined critical-defect or workflow regression. |
| **4 — Expand conditionally** | One needed integration, selective alerts, another part/station, or an alternate deployment topology. | Expansion follows actual operational value and measured constraints. | Repeat validation on the changed scope and a named process owner for each integration. |

Before factory use, phase 2 must address duplicate-result crash windows, evidence retention versus active standards, and history completeness. The source audit identifies a possible retry window that can create multiple saved assessments; it has not been reproduced as a live incident. Preserve a stable submission/result key and count physical units independently of model attempts.

Later candidates include incoming supplier review, an evidence-backed nonconformance hand-off, capture drift alerts, bilingual capture instructions, and offline capture. Each has a concrete trigger: supplied process data, a named receiving workflow, measured drift, operator language needs, or observed connectivity limits. They are not current commitments. Full CAPA/ERP, billing, generic chat, fleet orchestration, and autonomous ejection are outside the initial pilot scope.

## Concrete first implementation proposal

**Build the foundation for one shared controlled part, then the review workflow on top.** This section records the original proposal, subsequently authorized and implemented in the factory workspace. It does not establish production readiness or factory accuracy.

The first engineering increment should establish a verified pilot team, small server-enforced roles, one tenant-owned part/spec revision, human-confirmed taxonomy, and immutable recipe/capture context attached to submitted jobs and resulting inspections. Reuse the current parser, inspection service, stores, and media viewer. Keep existing demo cookie scopes distinct; do not silently turn historical corrections into approved shared standards.

An existing identity provider or verified identity proxy is preferable to inventing password handling. Provider choice depends on the actual pilot's account and hosting requirements. Proposed permissions: operators capture and view assigned pilot work; quality engineers review and propose standards; an authorized quality approver activates revisions/publishes or retires standards; administrators manage membership. One person may hold multiple roles in a small pilot, and self-approval policy must be explicit.

The following increment adds separate `ReviewCase`, append-only human `Disposition`, and governed `Standard` records, plus durable `Lot`/physical-item/`Capture` associations. A human can accept/reject/hold/request a retake without writing a reusable rule. A standard can be proposed from evidence without changing the original model assessment. Approval authorizes inclusion; publication freezes an approved set and records its evaluation/release decision. Retirement immediately blocks new recall, crops, and summaries even if remote memory deletion is retrying.

Jobs record a frozen recipe and check withdrawal state before sending evidence to a model. If a source in that recipe has been withdrawn, queued work goes on hold pending an approved release; it does not silently substitute another rule set. Evidence already sent to a provider cannot be removed from the response. A withdrawal during an active call therefore preserves the exact result/provenance, flags the withdrawn release, and quarantines the result for named review or rerun. Such a result cannot silently close the case as usable pilot evidence.

**Acceptance scenarios for the controlled pilot workflow:**

1. An authorized engineer can find and review an operator's item after reload; another team cannot read its images, jobs, rules, or reports. A removed member cannot keep acting through a stale session.
2. Identical specification text in two teams cannot mutate the other team's approved taxonomy or revision. Captures record the exact approved revision, taxonomy, model/prompt configuration, capture profile, and standards release.
3. Closing or reopening a review records actor, time, reason, and history, while preserving the original AI assessment. Closing alone does not teach memory. Concurrent claims/dispositions do not silently overwrite one another.
4. Unapproved, retired, superseded, or wrong-scope standards cannot be supplied to a new model call or generated summary. A withdrawal during an active call quarantines the resulting case. Historical results retain their original provenance. Active approved standards and required evidence have deliberate retention rules.
5. Retries and worker restart do not create an extra physical-unit count or lose an item. Lots remain reconstructable after technical job cleanup; retakes and comparison runs are distinguishable.
6. A server-filtered lot report includes every selected record beyond 100, both AI and human decisions, unresolved cases, exact versions, and explicit missing-evidence status.
7. Required image/evidence or service failure leaves an item pending human handling. A missing segmentation mask is not assumed to prove the model's rejection; evidence requirements are defect-specific.

These scenarios require targeted access, lifecycle, concurrency/restart, migration, API, and browser checks when implemented. Existing software test counts do not validate real defect detection. No paid model calls or factory uploads are required to design or test the state transitions using stubs.

## Pilot experiment and decision gates

The experiment tests both product usability and the central memory hypothesis. See the [evaluation report](03-evaluation-and-reliability.md) for the full protocol.

Collect representative real acceptable parts and relevant defects/severities, including lighting/session variation and retakes. Have qualified reviewers label them against the controlled specification; adjudicate disagreements and preserve an ambiguous/insufficient-evidence category. Split by physical part, lot, capture session, and source lineage where possible. Crops, augmentations, and repeat photos of the same part must stay together. Reserve later parts that were never used to author rules, prompts, or thresholds.

Predeclare how required views become one physical-part decision event. For the proposed single-view pilot, report the first prescribed attempt's outcome and eventual reviewed outcome separately. Preserve every invalid capture, failure, and retake; additional attempts do not create independent parts. Do not select the last or best answer to hide an initial false Accept. A future multi-view protocol needs its own frozen aggregation rule before testing.

Freeze both arms' model/prompt/specification and processing configuration. Run a memory-off baseline and an approved-memory snapshot on matched held-out cases, with no evaluation-time learning. Report stochastic repeat handling and clustered uncertainty at the appropriate independent unit; a collection of correlated photos is not a large independent sample. A temporal shadow period tests whether the capture and review workflow works under actual conditions.

| Measure | Required interpretation |
| --- | --- |
| Defect escape | Defective physical units assessed Accept / all independently labeled defective units, with class/severity counts and uncertainty. Review is shown separately. |
| False reject | Acceptable physical units assessed Reject / all independently labeled acceptable units. Do not pool this with Review. |
| Review and failure load | Review outcomes, inference/capture errors, unresolved items, and human handling time with explicit denominators. Report eventual decisions after review separately. |
| Operational value | Median/p95 end-to-end and human review time, retakes, queue age, service failures, and measured cost per item including retries and human work. |
| Memory transfer | Paired changes in escapes, false rejects, Review, workload, and per-class performance on unseen source parts; show both gains and regressions. |
| Evidence quality | Whether recalled sources were actually cited and support the stated clause/decision. “Recalled” is not equivalent to “cited correctly.” |

Current benchmark treatment can count Review as a positive defect flag. Its aggregate accuracy/recall must not become the pilot acceptance claim. Current correction share, model confidence, and model-predicted reject rate also do not estimate real accuracy. Nominal-width millimetre estimates remain estimates until the imaging/calibration/uncertainty procedure is validated.

The quality owner must set numerical escape/reject/workload/latency limits and acceptable evidence uncertainty by defect severity **before** seeing the locked results. Insufficient examples of a rare critical defect are an unresolved validation gap, even if no misses are observed. Start with human-confirmed shadow operation and retain the factory's material-release procedure.

Stop or revise the proposition if important defects are not visible, required cloud use is prohibited, memory fails to transfer or causes unacceptable regressions, review effort erases the benefit, or people cannot reconstruct and trust the evidence. A narrow successful class does not establish coverage of every material, part, defect, or station.

## Discovery and commercial hypotheses

The most promising initial user is a quality team facing recurring, visually expressible interpretation disagreements tied to a specification. This is a hypothesis, not proven demand. Ask the quality owner to show recent disputed cases and the actual decision/reporting process before making a larger platform commitment.

Record the part/material, minimum visible defect, severity, co-occurring defects/views, arrival rate, staffing, identifiers, existing QMS/MES hand-off, connectivity, data restrictions, language needs, and retention requirements. Measure current review time, repeat disputes, unnecessary rejects, and cost of escaped defects with the factory; no ROI is inferred from vendor marketing.

A potential value test compares the same agreed workload before and during the pilot, accounting for changing part/defect mix and review coverage. Ask whether the team continues using the workflow, who owns the purchase, and whether observed savings justify hosting, model calls, review, and support. Pricing and revenue projections require that evidence; this report does not invent them.

## Research limits and verification boundary

This is a bounded public-source screen plus a repository audit, not a systematic market review, customer study, regulatory assessment, or independent vendor benchmark. Five vendors were examined. Vendor capability descriptions may have plan/configuration conditions. Public benchmark datasets can help development but their material coverage and licensing may limit commercial use; they do not validate the target factory.

Exact retrieval attempts and supporting passages are recorded in the market/evaluation reports, [operations log](04-operations-search-log.json), and [synthesis check log](05-synthesis-source-checks.json). Cognex requests were rate-limited; GS1/ISO leads were inaccessible or unresolved; several search endpoints returned interstitials or a CAPTCHA. No absence, novelty, or compliance claim follows from these failures. Publication dates are not inferred from retrieval dates.

This research changes documentation only. Application tests and live model/provider checks are not rerun for a report. Documentation verification covers local links, referenced source locations, whitespace, structured logs, and visual layout. The prior release baseline is a historical reference; these documents do not certify present live-service performance.
