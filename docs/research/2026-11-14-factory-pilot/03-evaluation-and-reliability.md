# Evaluation and reliability for a real factory pilot

Research date: 14 November 2026, Asia/Kolkata. Public sources were retrieved on 13 November 2026 at 18:51–18:52 UTC, equivalent to 14 November at 00:21–00:22 IST. This is a bounded, source-led technical review, not an exhaustive literature review or a certification assessment. No paid model calls, factory-photo uploads, model training, application changes, or deployments were performed.

**Recommendation:** make the next release a human-supervised pilot for one defined inspection station and specification revision. Its first substantial addition should be a **Validation Lab** that separates escaped defects, false rejects, and Review workload on independent factory photos. Add capture controls and approved memory versions before interpreting correction recall as a production improvement. Follow offline validation with a shadow trial beside the existing inspection process. The evidence does not establish a safe operating point for SpecLens at any factory today.

Labels used below: **Fact** means an inspected source or repository behavior supports the statement; **Inference** means a bounded engineering conclusion from those facts; **Proposal** means a feature, protocol, or threshold to test with the customer. Every numerical operating threshold in this report is provisional and customer-set unless explicitly described as a statistical calculation.

## What the repository already establishes

| Observed implementation | What it supports | Remaining factory-pilot gap |
| --- | --- | --- |
| [README known limits](../../../README.md#known-limits) explicitly identifies the included inputs as synthetic and the millimetre estimate as dependent on top-down geometry. | Honest demonstration and engineering regression inputs. | No independent factory accuracy, measurement capability, or production defect prevalence follows from them. |
| [scripts/benchmark.py](../../../scripts/benchmark.py) accepts a custom labelled manifest, partitions teaching and evaluation by `source_group`, compares memory off/on, and saves paired results. | Reusable evaluation plumbing; separation of parent source photos is better than random splitting of composited variants. | Capture physical-part, lot, session, line, camera, lighting, spec, and adjudicated labels. Keep repeat views and derivative images together. Factory samples require factory-specific correction text: the default rules are hazelnut-specific. |
| [backend/app/bench.py](../../../backend/app/bench.py) counts both `defect` and `uncertain` as flagged, and reports Review rate. | A useful measure of whether a defect passes unchecked. | Its binary accuracy/F1/recall do not distinguish a correct Reject from a Review. Report a two-ground-truth-by-three-output matrix and workload separately. |
| The same statistics module bootstraps paired individual rows. | Preserves the memory-off/on pairing. | Related photos remain dependent even when teaching/test leakage is avoided. Resample independent part/lot/session groups for factory comparisons; few independent lots mean uncertain generalization regardless of image count. |
| [WorkspaceService.run](../../../backend/app/workspace/service.py) hashes canonical pixels, stores source metadata and recalled corrections, and scopes memory by factory/part/spec through [Scope](../../../backend/app/workspace/store.py). | Good foundations for lineage and isolation. | Exact-image hashing does not exclude near-duplicates, repeated physical parts, or shared acquisition sessions. A synced correction is eligible for use without a distinct QA approval/version-release state. |
| [inspector.py](../../../backend/app/inspect/inspector.py) requests a numeric model-reported confidence and makes an unsuitable-photo result Review. | An explicit review outcome and a basic semantic visibility check. | There is no inspected factory calibration evidence for that confidence value, or an explicit quantitative blur/glare/pose/resolution gate. The JSON schema does not itself constrain confidence to a calibrated probability. |
| The inspector docstring describes “no mask -> uncertain”, but the workspace calls it with `require_mask=False`. | A defect decision can survive a missing SAM mask in the actual workspace path. | Define and validate evidence requirements per clause. Do not infer a universal mask guarantee from the docstring. Logical defects such as a missing component may require different evidence from a surface scratch. |
| [measure.py](../../../backend/app/inspect/measure.py) uses `part_width_mm / model_reported_part_width_px`, then measures a SAM-mask rectangle. [save_mask](../../../backend/app/workspace/service.py) can change a Reject to Review when the estimate is within a clause limit. | A geometric estimate under stated assumptions. | No independently validated camera geometry, scale uncertainty, segmentation error, or repeatability budget. This estimate already influences a decision path, so test boundary cases explicitly. |
| The service resizes photos to at most 1280 pixels per side, and the vision-image helper in the inspector encodes the inspection view at at most 768 pixels per side. | Predictable bandwidth/cost handling. | Test the smallest customer-relevant defect after the actual preprocessing. A high-resolution upload does not mean the model sees all original detail. |
| Inspector result `ms` is taken from the vision JSON call; SAM time is not added. Recall, taxonomy work, queueing, and storage also surround that call. | A component timing measure. | Measure capture/upload-to-visible-result latency, plus queue, recall, vision, mask, retry, and persistence spans. Do not treat the existing `ms` as a line-cycle measurement. |
| [benchmark.py](../../../scripts/benchmark.py) names a list `cited`, but fills it from all `result.memories`; the [dashboard](../../../backend/app/workspace/dashboard.py) similarly counts available recalled records as citations. | Records which memory evidence was supplied. | Separate “retrieved”, “supplied to model”, and “source IDs explicitly cited in the output”. None proves the explanation is correct or that recall caused the decision. |
| The dashboard aggregates inspection records by scope, including paired comparison arms stored as inspections, and counts model verdicts. | Model-activity and operating-cost telemetry. | A model reject rate is not a production defect rate or final disposition rate. Give each physical part and production event an identity; exclude teaching, benchmarks, comparisons, and retakes from the relevant production denominator. |

These are code-reading observations, not reproduced runtime measurements. Useful existing foundations should be extended rather than replaced.

## Primary-source evidence map

| ID / source and date | Supporting location and observed fact | Implication for this pilot / limitation |
| --- | --- | --- |
| **S1 — Bergmann, Fauser, Sattlegger & Steger, “MVTec AD — A Comprehensive Real-World Dataset for Unsupervised Anomaly Detection,” CVPR 2019.** [Author-hosted paper](https://www.mvtec.com/fileadmin/Redaktion/mvtec.com/05_research_teaching/datasets/mvtec_ad.pdf); [official dataset page](https://www.mvtec.com/research-teaching/datasets/mvtec-ad), page publication date not shown. | Paper abstract: 5,354 high-resolution images, normal training images, anomalous test images, and pixel-precise anomaly regions. Dataset page “Abstract” describes 15 categories and both normal and defective test images. | **Fact:** image-level labels and localization ground truth answer different questions. **Proposal:** retain part decisions for all examples, and annotate masks on the defect subset where localization matters. This is an anomaly-detection benchmark, not a validation of SpecLens or a customer's specification. |
| **S2 — Heckler-Kram, Neudeck, Scheler, König & Steger, “The MVTec AD 2 Dataset: Advanced Scenarios for Unsupervised Anomaly Detection.”** IJCV 134, article 175, published **9 March 2026**, DOI [10.1007/s11263-026-02743-0](https://link.springer.com/article/10.1007/s11263-026-02743-0); [official dataset page](https://www.mvtec.com/research-teaching/datasets/mvtec-ad-2). | Abstract and §3.1: small defects, reflective/transparent and overlapping objects, variable normal appearance. §3.2 separates public and private tests. §3.3 changes exposure and lighting while holding other scene parameters constant; at least four lighting conditions per category. §3.4 describes human labeling guidelines, refinement, and manual/automated checks. §4.2.2 distinguishes threshold-dependent decisions from anomaly-map metrics; §4.2.3 measures runtime and memory. | **Fact:** realistic capture changes and labeling quality are explicit evaluation dimensions. **Proposal:** test seen/unseen customer lighting, small defects after resize, and an untouched later-lot test. Their measured model results do not predict this hosted vision model's performance; AU-PRO is not a factory escape rate. Use the publisher's publication date rather than assuming the original dataset release date. |
| **S3 — Bergmann, Batzner, Fauser, Sattlegger & Steger, “Beyond Dents and Scratches: Logical Constraints in Unsupervised Anomaly Detection and Localization.”** IJCV 130:947–969, published **22 February 2022**, DOI [10.1007/s11263-022-01578-9](https://link.springer.com/content/pdf/10.1007/s11263-022-01578-9.pdf); [official MVTec LOCO AD page](https://www.mvtec.com/research-teaching/datasets/mvtec-loco-ad). | Paper abstract and dataset “Abstract”: structural anomalies differ from violated logical constraints, such as a permitted object in the wrong location or a required object absent. The paper explicitly addresses localization ambiguity for logical anomalies. | **Inference:** a surface-defect-only test misses count, assembly, presence, and placement failures when these are in the agreed scope. A SAM mask is neither necessary evidence for every logical defect nor proof that a classification is correct. Include only the customer's relevant defect families. |
| **S4 — MVTec official dataset license terms**, no page publication dates shown. [AD](https://www.mvtec.com/research-teaching/datasets/mvtec-ad), [AD 2](https://www.mvtec.com/research-teaching/datasets/mvtec-ad-2), [LOCO AD](https://www.mvtec.com/research-teaching/datasets/mvtec-loco-ad). | Each page's “License Terms” states CC BY-NC-SA 4.0 and explicitly disallows commercial purposes; contact MVTec when use is unclear. | **Fact:** public availability does not make these datasets unrestricted commercial pilot material. Study their protocols and use permissioned customer photos as the acceptance dataset. Do not bundle these datasets into a factory product assuming permission. This is the source's stated restriction, not a conclusion about a particular customer's legal position. |
| **S5 — NIST, “Artificial Intelligence Risk Management Framework (AI RMF 1.0),” NIST AI 100-1**, **January 2023**, [official PDF](https://nvlpubs.nist.gov/nistpubs/ai/NIST.AI.100-1.pdf), DOI 10.6028/NIST.AI.100-1. | §1.2.2, printed p.7: the framework does not prescribe risk tolerance. Table 3, printed pp.29–30: MEASURE 1.3 independent/domain assessment, 2.1 documented test sets/metrics, 2.3 deployment-like conditions, 2.4 production monitoring, 2.5 validity/generalization limits, 2.6 safe failure and response times. Table 4, pp.32–33: MANAGE 2.4 disengagement, 3.2 pretrained-model monitoring, 4.1 post-deployment monitoring, override, recovery, and change management. | **Fact:** deployment-specific evaluation, monitoring, documented limits, and a way to disengage are established risk-management practices. **Proposal:** translate these into a release record, scoped rollback, and a shadow trial. AI RMF is voluntary and non-sector-specific; it neither certifies SpecLens nor supplies a universal numeric factory acceptance gate. PDF physical pages are 12, 34–35, and 37–38 for the cited printed pages. |
| **S6 — NIST AI RMF Playbook, “Measure,”** live official guidance; publication/revision date not displayed on the inspected page. [Official page](https://airc.nist.gov/airmf-resources/playbook/measure/). | MEASURE 2.3 “Suggested Actions” calls for false-positive/false-negative and prediction-latency measurements against ground truth in the deployment context. MEASURE 2.5 calls for operational limits, variance/interval estimates, post-alert actions, and logging inputs/configuration outside validity limits. MEASURE 2.6 discusses stress conditions and incident response. MEASURE 3.1 includes comparisons with simpler models and human/manual baselines. | **Inference:** a single accuracy percentage or dashboard reject trend is an inadequate pilot release argument. **Proposal:** use a multi-metric scorecard with explicit fallback actions and a manual-process baseline. These are suggested actions, not binding manufacturing requirements. |
| **S7 — Guo, Pleiss, Sun & Weinberger, “On Calibration of Modern Neural Networks,” ICML/PMLR 70:1321–1330**, **6–11 August 2017**. [Proceedings record](https://proceedings.mlr.press/v70/guo17a.html); [paper](https://proceedings.mlr.press/v70/guo17a/guo17a.pdf). | §2, paper pp.2–3: calibration means confidence corresponds to observed correctness; reliability diagrams and Expected Calibration Error estimate this empirically. §4.2, p.5: temperature scaling operates on a logit vector and fits its parameter on a validation set. | **Fact:** accuracy and calibration are different properties. **Inference:** a self-reported `0.95` from the current structured answer is not demonstrated to mean 95% correctness. This paper studies classification networks, not SpecLens or generative self-report scores. It does not justify directly applying temperature scaling when the necessary logits are unavailable, or treating an adjusted slider as a safety guarantee. |
| **S8 — NIST/SEMATECH e-Handbook, “7.2.4.1. Confidence intervals,”** page date not shown. [Official page](https://www.itl.nist.gov/div898/handbook/prc/section2/prc241.htm). | “One-sided confidence intervals” and “Exact Intervals for Small Numbers of Failures and/or Small Sample Sizes” explain bounds for binomial proportions and exact binomial inversion. | **Fact:** observed zero failures still requires a nonzero upper uncertainty bound. **Derivation below:** the zero-event one-sided 95% bound is `1 − 0.05^(1/n)` for independent Bernoulli trials. Independence and representative sampling matter; multiplying views of the same faulty part does not buy the same evidence as additional independent parts. |
| **S9 — Taylor & Kuyatt, “Guidelines for Evaluating and Expressing the Uncertainty of NIST Measurement Results,” NIST TN 1297**, **1994 edition**. [Official index](https://www.nist.gov/pml/nist-technical-note-1297), updated **6 May 2026**; [§7 Reporting Uncertainty](https://www.nist.gov/pml/nist-technical-note-1297/nist-tn-1297-7-reporting-uncertainty); [Appendix D.2](https://www.nist.gov/pml/nist-technical-note-1297/nist-tn-1297-appendix-d2-identification-uncertainty-components), updated **12 August 2025**. | §7.1–7.2 calls for reporting uncertainty, components, evaluation method, and coverage factor/basis where applicable. Appendix D.2 illustrates uncertainty budgets with statistical and other contributions. | **Inference:** a mask and an assumed part width do not alone establish a defensible millimetre measurement. **Proposal:** budget scale, pose, lens, part-height, segmentation, and reference-gauge uncertainty for the actual setup. TN 1297 is NIST measurement guidance, not a factory-specific certification rule; the inspected §7 web page says it is no longer updated. |
| **S10 — OpenCV, “Camera Calibration,” official 4.13.0 tutorial.** [Official versioned page](https://docs.opencv.org/4.13.0/dc/dbb/tutorial_py_calibration.html); generated **31 December 2025** as displayed, not a claimed publication date. | “Basics,” “Calibration,” “Undistortion,” and “Re-projection Error”: lens distortion, known pattern coordinates, camera parameters, and checking reprojection fit. | **Fact:** image geometry requires more than nominal object width. **Proposal:** calibrate fixed optics and verify the whole measurement process against independent reference measurements. Low reprojection error is not, by itself, a validated defect-size uncertainty or a dimensional acceptance test. |

## Priority feature and section candidates

The following are product proposals, not features mandated by the cited sources. Priorities assume the intended next step is a real factory trial with human final disposition.

| Priority / proposed section | Factory user's job and minimum usable content | Why now / effort boundary |
| --- | --- | --- |
| **P0 — Validation Lab** | Import permissioned photos plus a manifest; assign physical-part/lot/session groups; record spec-linked ground truth and adjudication; freeze teaching/tuning/test sets; compare baseline versus an approved memory release; export the three-outcome matrix, class/slice metrics, intervals, cost, and complete latency. Display the number of independent parts and lots next to image counts. | Largest evidence gap; reuses manifest-based benchmark and paired inspection plumbing. Start with import/export and one reproducible run record; a model-training platform is unnecessary. S1, S2, S5, S6, S8. |
| **P0 — Capture Station** | An approved recipe for camera/lens, fixture/pose, illumination/exposure, focus and resolution, ROI, reference target, and calibration/check date. Before inference, show a specific recapture/hold reason for blur, glare, occlusion, wrong part, missing required view, or stale setup. Retain the failed attempt separately. | Capture problems can dominate apparent model quality. Cheap fixture/lighting fixes may outperform more memory. Quantitative checks need customer-specific validation; a generic blur threshold is not a proven quality gate. S2, S9, S10. |
| **P0 — Approved Quality Standards** | Draft → QA approved → active → superseded/revoked states, with immutable history, spec clause, scope, reviewer, example provenance, release ID, and effective dates. Preview conflicts before activation. Show exactly which approved release an inspection used; roll back the active pointer. | Memory changes decision behavior without retraining. Treat a changed retrieval corpus/crop as a release change. Sync success is not QA approval. Reuse existing correction IDs and spec scopes, adding approval and release semantics. S5, S6; this precise workflow is our engineering proposal. |
| **P0 — Review and Final Disposition** | Queue Review, failures, and disagreements; record the independent QA label, final disposition, reason, actor, time, and linked inspection/physical part. Separate model recommendation, reviewer correction, and actual release/scrap/rework. | Otherwise neither escape nor false-reject metrics have a trusted denominator. Preserve the original model answer; an operator override should not silently rewrite evaluation labels. S5, S6. |
| **P0 — Pilot Monitor** | Production-only counts by product/spec/line/station/lighting/shift; model false-accept and false-reject estimates from labelled audits, Review burden, recapture/error/timeout rates, queue age, latency percentiles, cost, active release, and last validation status. Add an owner and action to each alert. | Aggregate dashboards can hide one failing line or illumination setting. Monitoring cannot estimate accuracy without labels, including audited AI Accepts. The initial monitor can be a daily CSV/report before a large analytics UI. S2, S5, S6. |
| **P1 — Evidence Packet** | Export the frozen dataset/split/label manifest, decision configuration, memory release, per-part original and processed image hashes, supplied/cited source IDs, raw/validated answer, applicable localization/measurement evidence, final disposition, exception log, and QA release decision. | Makes a small pilot reviewable and incident investigation possible. Start with a signed-off JSON/CSV bundle rather than a claim of immutable or certified audit storage. S5, S6, S9. |

Defer cross-line automatic memory transfer until it passes a new scope-specific test. Distinct machines or lighting can need different validation even for the same product. “Approved correction reuse with provenance and measured benefit” is a testable product hypothesis; this review makes no uniqueness claim about correction memory.

## Minimum practical validation protocol

### 1. Agree on the operating envelope and decision authority

**Proposal:** start with one product family, one exact spec revision, one station/camera/fixture, and a small set of visible, economically relevant defect classes. Write down accepted natural variation, reject clauses, minimum detectable defect scale, approved views/pose/lighting, throughput and review capacity, exclusions, and who owns the QA release decision. Include logical defects only when relevant to that spec. Human disposition remains the existing factory process throughout the pilot.

Agree the cost/severity of an AI false accept, false reject, delayed result, and unnecessary review before choosing a threshold. NIST explicitly leaves risk tolerance to the use case (S5); a food defect, cosmetic mark, and safety-critical crack cannot inherit one generic target.

### 2. Assemble ground truth with provenance

**Proposal:** use customer-owned or permissioned factory photos of physically distinct good and defective parts. Retained defect samples are useful but record whether they are aged, seeded, reworked, or photographed off-line. Keep a natural-prevalence consecutive production sample separate from a defect-enriched challenge set. Never report the enriched set's class mix as the factory defect rate.

The manifest should minimally include `sample_id`, `physical_part_id`, parent/source ID, lot/batch, capture session/time, line/station/camera and lighting recipe, product/spec revision, capture quality/view, image hash, ground-truth Accept/Reject/Unresolved, defect class/severity/clause, reviewer/adjudication, and applicable independent size/reference measurement. Store raw/processed image identities and preprocessing version. Masks are needed only for the subset and defect types for which localization/size is a decision requirement.

Have a qualified QA reviewer label all locked-test parts independently of the model. Have a second reviewer assess the critical, boundary, disputed, and a random normal subset; use a written adjudication rule. For high-consequence labels, require dual review for all relevant cases. Preserve disagreement rates and unresolved cases; do not manufacture certainty by forcing ambiguous labels. Report unresolved exclusions and their count alongside the full capture population. The model output or a prior correction is not ground truth.

**Provisional feasibility budget:** begin with 200–500 unique parts spanning at least three lots and two acquisition sessions, including a separately identified challenge set of at least 60 confirmed defects if available. This uncovers feasibility problems; it is not automatically enough to pass a low-escape acceptance gate. The customer's required error bound determines the eventual sample size. A pilot that cannot obtain enough genuine examples should retain an explicit “insufficient evidence” result.

### 3. Separate teaching, policy tuning, and untouched testing

Put every view, crop, duplicate, near-duplicate, synthetic derivative, and recapture of a physical part in the same group. Hold out later lots and capture sessions to expose context shift. Where these relations overlap, use the coarsest connected grouping rather than allowing related cases to cross sets. Check file/canonical hashes plus provenance and a manual near-duplicate screen; the existing exact-pixel hash is insufficient by itself.

Use teaching data to create corrections, tuning data to choose capture/review policy, and the locked test only for the release decision. Keep test labels away from the person writing correction text until the candidate is frozen. After a failed test informs a change, preserve its results and use a fresh untouched set for the next release claim. Do not silently iterate against one permanent “test” set.

### 4. Compare baseline and approved memory without retraining

Freeze the spec text and parsed taxonomy, model identifier and available provider revision, prompt/preprocessing versions, mask/measurement options, capture recipe, and approved memory release. Save the exact retrieved payload and reference-crop hashes for every test request: a bank name alone does not reproduce dynamic recall.

Run the same held-out parts under **A: current spec, memory off** and **B: same spec/model/configuration, frozen approved memory on**, without additional retraining. Randomize or counterbalance arm order and interleave in time. Record cost/cache state and timing because order can affect them. Keep provider errors/timeouts as explicit outcomes; never silently rerun only failed/wrong cases out of the analysis. A repeated subset can measure model variability, but repetitions do not increase the number of independent physical parts.

For the central hypothesis, ask: **Do a small set of retrieved, spec-clause-linked QA corrections reduce confirmed false accepts on unseen lots/sessions without exceeding the agreed false-reject and review-workload budgets?** Audit recalled evidence for correct scope, approval, relevance, and conflicts with explicit reject clauses. Also count existing correct cases that memory breaks. High recall/citation frequency alone does not answer this question.

If resources permit, add **C: the same approved standards as a short fixed reference sheet**, with no retrieval, to test whether retrieval improves over simply clarifying the specification. This is a competing explanation worth testing; extra complexity is unjustified if the fixed sheet performs as well. None of these comparisons makes a causal claim about proprietary provider training or guarantees that an upstream model alias stays unchanged.

Use paired changes and intervals across independent groups. At minimum report group-by-group results and leave-one-lot-out sensitivity. A cluster bootstrap by lot/session is a proposed improvement over today's row bootstrap; with very few groups, label those intervals exploratory and collect more groups rather than presenting a narrow interval as established transfer reliability.

### 5. Validate capture and size claims separately

Build a capture challenge set containing wrong part, partial part, blur, glare, shadow, over/underexposure, occlusion, wrong pose/distance, absent view, and small defects after the actual resize/compression chain. Include valid difficult photos so blocking everything does not pass. Measure invalid-capture pass rate and valid-capture block rate separately. Define the minimum pixel visibility of the smallest relevant defect empirically, using retained parts where possible.

For the first station, lock optics/fixture/lighting and verify a known reference in the relevant plane. If dimensions affect disposition, compare repeated image measurements against an independent appropriate gauge across positions, poses, operators/sessions, and defect scales around the clause boundary. Document bias, repeatability, scale/lens/pose/part-height and mask contributions to uncertainty. Calibration-pattern reprojection error is only one input (S9, S10). A single reference width, an arbitrary photo, or a SAM mask does not establish traceable metrology.

Until that evidence exists, display millimetres as an estimate and require QA confirmation of size-based recommendations. A measurement interval that overlaps a reject boundary belongs in the agreed Review workflow. Validate the actual code path, including missing masks and the existing within-limit-to-Review behavior, rather than assuming the displayed outline enforces correctness.

### 6. Run shadow inspection and exercise recovery

After offline feasibility, run the candidate beside the normal inspection process for representative shifts/lots, including an independently inspected sample of AI Accepts. In shadow mode, **AI escape** means a confirmed defective part that the model would accept; it is distinct from an actual released defective part after human QA. Record both concepts separately.

Measure the full path from capture/upload receipt to the result visible to the reviewer, plus human decision time and queue age. Test at the agreed concurrent arrival rate and on the intended factory network. Exercise required-memory recall failure, stale/mismatched spec, missing capture evidence, provider timeout, and rollback. Each must produce a visible hold/review/error with the affected part ID and preserve the manual inspection route. A green service-health endpoint is insufficient evidence for this behavior.

End the shadow phase with a QA review of mistakes, process impact, missing labels, workload, and the scorecard below. The calendar duration is secondary to sample and operating-condition coverage. A later assisted rollout is a new monitored stage with human final disposition, not an automatic consequence of a successful demo.

## Scorecard and provisional acceptance gates

Use a matrix with truth rows **Good / Defective** and model columns **Accept / Reject / Review**, plus separate capture-rejected, error, timeout, and unresolved-label outcomes. Compute at the physical-part decision-event level with a declared aggregation rule for multi-view parts. Keep the original per-view results. Show counts and denominators beside percentages, stratified by defect severity/type and product/spec/line/station/lighting/session.

| Metric / gate | Exact interpretation | Provisional example or customer decision |
| --- | --- | --- |
| AI defect escape | Confirmed defective parts with AI **Accept** / all confirmed defective parts. Report critical classes separately. | Example proposal: one-sided 95% upper bound ≤1% for the agreed noncritical scope. Critical defects require their own customer-set bound and zero observed critical false accepts before any release decision. A point estimate alone does not pass. |
| Accept contamination | Confirmed defects among AI Accepts / all independently labelled AI Accepts. | Customer-set maximum. Estimate from natural-prevalence or properly weighted audit sampling; a defect-enriched test does not estimate production contamination directly. |
| False reject | Confirmed good parts with AI **Reject** / all confirmed good parts. | Example proposal: one-sided 95% upper bound ≤5%, or a customer-agreed noninferiority margin versus the existing process. Review is excluded here and reported below. |
| Review and false-flag burden | Review / all eligible parts; also `(Reject + Review)` among confirmed good parts / all confirmed good parts. Report failures/recaptures separately. | Example proposal: Review ≤15% and review arrivals × measured service time below staffed capacity with headroom. The actual budget comes from the station workflow. No candidate passes by routing nearly everything to people. |
| Decision coverage | `(Accept + Reject)` / all eligible parts; also show unresolved/failure outcomes against all capture attempts. | Customer-set minimum at the escape/false-reject operating point. Coverage is not permission to bypass human disposition. |
| Memory benefit/regression | Paired escape, false-reject, Review, cost, and latency changes; fixed-by-memory and broken-by-memory cases; independent-group intervals. | Customer chooses whether benefit is enough. A candidate must meet absolute risk/workload gates and not introduce a critical regression. An interval spanning no benefit is “benefit unproven”, not a positive-lift claim. |
| Capture control | Invalid capture accepted by the quality gate / challenged invalid captures; valid capture blocked / challenged valid captures. | Proposal: no invalid challenge image yields an unqualified Accept in the tested corpus, while valid block/retake rate stays within the customer budget. Finite challenge coverage does not prove all future bad photos will be caught. |
| End-to-end service | p50/p95/p99 capture-to-visible-result, deadline exceedance, error/timeout, and queue age at target arrival rate. | p95 must fit the customer-assigned decision window; deadline misses must follow the agreed manual hold/review route. Example proposal: operational failure ≤1% in the measured shadow window. A 1-second conveyor and a 30-second bench task need different budgets. |
| Size evidence | Bias/error and repeatability against independent reference, with uncertainty at the clause boundary. | Customer/metrology owner defines allowable measurement error and guard-band/review policy from the actual tolerance. No arbitrary universal millimetre target. Without validation, size remains an estimate requiring confirmation. |
| Evidence completeness and rollback | Each test/production decision links to its part, spec, configuration, approved memory evidence, source image, output, and final QA record where required. An exercised rollback selects the prior approved release. | Proposal: 100% of locked-test decisions have required provenance; no pending/unapproved/revoked correction enters active memory; all defined failure drills recover through the approved manual route. Record the rollback duration and compare it with the customer's incident-response budget. |

**Sample-size reality check — a calculation, not an operating recommendation.** If independent confirmed defective parts have zero AI escapes, the one-sided exact 95% upper bound on escape probability is `1 − 0.05^(1/n)`. This follows by setting the probability of seeing zero events, `(1 − p)^n`, equal to `0.05` (S8).

| Independent defective parts with zero escapes | 95% upper escape bound |
| --- | --- |
| 30 | 9.50% |
| 60 | 4.87% |
| 100 | 2.95% |
| 299 | 1.00% (approximately 0.9969%) |
| 2,995 | 0.10% (approximately 0.09997%) |

Thus, zero misses in a few dozen examples is a useful feasibility result and weak evidence for a very low miss rate. These counts concern defective parts, not total production photos. They do not remove lot correlation, label error, distribution shift, or multiple-class testing; each critical slice needs adequate evidence of its own. A few independent lots can dominate uncertainty even when many images are available.

For score-based routing, first plot observed error versus the model-reported score with bin counts and uncertainty, and the escape/false-reject/workload tradeoff at candidate policies on tuning data. Test the frozen policy on untouched data and shifted lighting. Sparse bins or high-score mistakes are a reason to constrain the operating scope, not proof that a different slider value is calibrated. Do not label the current score a measured probability of safety.

## Approved memory, context drift, and audit design

**Proposal:** give each active decision policy a release ID comprising spec/taxonomy revision, prompt/preprocessing version, model identifier/version evidence, capture recipe, measurement policy, and approved memory release. Record exact recalled text and crop identities per request. Approval or revocation changes the active release; historical inspections keep the evidence they actually saw. Re-check recalled IDs against the approved active set after retrieval so a stale external bank cannot bypass a local revocation.

Corrections should state the clause, the observed evidence, the applicable product/station/material/finish, counterexamples/accepted variation, reviewer, and effective date. Use explicit supersession rather than deleting a previous record or quietly rewriting a rule. A new spec revision or changed station/lighting starts a revalidation decision; never assume factory-name/part-family equality proves transfer. Conflicting corrections need a QA resolution before activation. The current instruction that memory cannot cancel an explicit reject clause is a useful policy, but it still needs adversarial and ordinary-case verification.

Monitor both input changes and labelled outcome changes. Track capture-quality distributions and metadata by scope; review unusually high Review/Reject rates, but do not infer the cause from those rates alone. Changes could be actual process defects, lighting, material, taxonomy, memory, model behavior, or missing labels. A small continuously refreshed audit sample of AI Accepts is necessary to detect false accepts that voluntary corrections will miss. If audit sampling is unequal, retain selection probabilities for weighted rate estimates.

Minimum decision provenance should include original/processed image hashes and transform details, part/lot/session identity, raw spec plus approved parsed clauses, request and available model-version identifiers/time, prompt version, exact supplied memory/crops, output-cited IDs, raw/validated output, masks/measurement method where applicable, timing/error/retry spans and cost, human labels/adjudication/final disposition, and approval/rollback history. Request IDs and a model alias may still be insufficient to reproduce a provider's stochastic response exactly; the packet should state that limitation.

**Proposed stop/restrict triggers:** a confirmed new critical false accept; a failed class/scope gate; unapproved or wrong-scope memory; stale spec/capture validation; missing required evidence; or workload/latency beyond the staffed decision window. The owner can disable the affected AI scope and revert to the established manual process while investigating. Resume that scope only after documenting the cause, change, and relevant revalidation. Avoid disabling all factory operations merely because an advisory AI service fails.

## Low-effort experiments and what would falsify the recommendations

These are proposed experiments; none was executed during this research. They can begin with already permissioned retained parts and exports. Live inference experiments would incur normal provider usage when separately run.

| Experiment | Smallest useful design | Decision / falsifying observation |
| --- | --- | --- |
| Capture repeatability before more AI work | Photograph 10–20 retained good/bad/boundary parts repeatedly under the intended fixture and a small set of deliberate lighting/pose changes. Have QA assess whether the defect remains visible after actual preprocessing. | If defect evidence disappears or labels change with small allowed capture changes, fix the optics/recipe or narrow scope first. If capture is already stable, further capture UI investment may be lower priority. Repeated captures diagnose sensitivity; they are not independent accuracy samples. |
| Tiny-defect survival | Compare the original and actual 1280/768-pixel model-input chain on near-limit defects, with a human-confirmed reference and recorded defect size in pixels. | If relevant defects cease to be distinguishable after downsampling, the current input path falsifies the claimed minimum defect capability. Consider a validated crop/multi-view approach only if needed; do not assume more memory restores absent pixels. |
| Does memory actually help? | Frozen A/B arms on an untouched later lot/session, using a small approved set of clause-linked corrections. Optionally include a fixed reference-sheet arm. | More citation/recall with unchanged escapes, more false rejects/Review, newly broken critical cases, or lift disappearing after grouping falsifies the claimed operational benefit. A fixed sheet matching B weakens the case for retrieval complexity. |
| Reviewer agreement | Two QA reviewers independently label 30–50 boundary/normal/defect examples without seeing AI output; adjudicate with the actual spec owner. | High disagreement or missing clause interpretation falsifies the assumption that a clean model target already exists. Fix the label/spec protocol before increasing benchmark volume. The count is a provisional diagnostic budget. |
| Confidence audit | Bin the existing score against independently labelled correctness, separately for Accept and Reject and for ordinary/changed lighting. | High-score false accepts or materially different error rates at the same score falsify the interpretation of confidence as a transferable reliability probability. Sparse evidence is inconclusive, not calibrated. |
| Millimetre estimate check | Repeat image-based sizes around a clause boundary against an independent gauge across position, permitted tilt, part width/height, and sessions. | Excessive bias/variation or inconsistent accept/review behavior falsifies use of the current estimate for dimensional recommendations. If physical dimensions cannot be observed from this view, remove that use case from the pilot. |
| Failure and rollback drill | In a test workspace/harness, simulate unavailable required recall, revoked/wrong-scope evidence, provider timeout, missing required mask/view, and a release rollback. | An unqualified Accept, use of inactive evidence, lost part identity, or inability to return to a known release falsifies readiness for the shadow workflow. Define class-specific evidence rules first; not every logical defect requires a mask. |
| Daily monitor dry run | Generate one production-only report with known test/comparison/retake records present and several independently audited Accepts. | Inflated denominators, absence of false-accept estimates, or inability to locate the affected line/spec/release falsifies the report's usefulness as a factory quality monitor. |

The highest-impact unknowns are the actual factory part/defect classes, defect visibility and tolerance, trustworthy labels, target cycle time, acceptable review burden, and the consequences of mistakes. Evidence that the current manual process is faster/safer, that capture cannot show the relevant defects, or that memory adds no benefit under independent testing should shrink or stop the proposed AI scope. Positive results on one station do not settle transfer to another line, material, product, spec, or illumination recipe.

## Reproducible retrieval log

This review used direct official-source navigation and within-document searches, not search-result snippets or an exhaustive search engine screen. All external facts in the evidence map come from the opened documents. No inaccessible source was used as supporting evidence.

**Repository retrieval:** read `README.md`, `scripts/benchmark.py`, `backend/app/bench.py`, `backend/app/inspect/inspector.py`, `backend/app/inspect/measure.py`, and relevant portions of `workspace/service.py`, `store.py`, `memory.py`, `dashboard.py`, and `meta/client.py`. Exact locating queries included `rg --files -g AGENTS.md -g README.md -g 'benchmark.py' -g '*inspector*' -g '*measure*' -g '*memory*' -g '*telemetry*'` and `rg -n 'confidence|uncertain|measure\(|threshold|duplicate|fingerprint|source_group|revision|correction|recall|latency|elapsed|started|ms' ...`. No applicable `AGENTS.md` was found in the checked workspace/ancestor paths. `git status --short` was clean before this document was added.

**Public retrieval and inspection queries:**

| Query ID | Source/database and exact navigation/search | Opened evidence / outcome |
| --- | --- | --- |
| Q1 | Direct `www.mvtec.com/company/research/datasets/{mvtec-ad,mvtec-ad-2,mvtec-loco}`; within-page `Abstract`, `License Terms`, `paper`; follow official paper links. | Official pages redirected to `/research-teaching/datasets/…`; LOCO canonical slug is `mvtec-loco-ad`. S1–S4 read. |
| Q2 | Direct Springer AD 2 DOI article; within-text `3.1`, `3.3 Distribution Shift`, `3.4 High-Quality`, `4.2.2`, `4.2.3`, `TESTpriv`, `Published`. | Full HTML including dated article metadata and cited sections read. Cookie-error parameters appeared on the redirect URL, but the article full text was returned with HTTP 200. |
| Q3 | Direct `nvlpubs.nist.gov/nistpubs/ai/NIST.AI.100-1.pdf`; PDF searches `voluntary`, `risk tolerance`, `MEASURE 2.1`, `MEASURE 2.3`, `MEASURE 2.5`, `MEASURE 2.6`, `MEASURE 3.1`, `MANAGE 2.4`, `MANAGE 4.1`. | PDF extracted with the repository environment's `pypdf`; specific physical and printed page positions checked. S5 read. |
| Q4 | Direct AIRC Playbook Measure page; within-text `MEASURE 2.3`, `MEASURE 2.5`, `MEASURE 2.6`, `MEASURE 3.1`. | Read the relevant “About” and “Suggested Actions” blocks. No revision date inferred. S6 read. |
| Q5 | Direct PMLR `v70/guo17a.html`; follow PDF; searches `Reliability Diagrams`, `Expected Calibration Error`, `Temperature scaling`. | Bibliography metadata and §§2, 4.2 checked. S7 read. |
| Q6 | Direct NIST Handbook `prc241.htm`; searches `One-sided`, `Exact Intervals`, `Small Numbers of Failures`. | Exact-binomial expressions read; zero-event bound derived and independently calculated with Python `math`. S8 read. |
| Q7 | Direct NIST TN 1297 index; follow §7 and Appendix D.2; searches `7.1`, `components`, `coverage factor`, `Created`, `Updated`. | Reporting and uncertainty-budget passages checked; retained the §7 archival warning. S9 read. |
| Q8 | Direct OpenCV `/4.x/dc/dbb/tutorial_py_calibration.html`; inspect `Basics`, `Calibration`, `Undistortion`, `Re-projection Error`. | Redirected to 4.13.0; method and footer generation date read. S10 read. |

Raw HTTP retrievals used Python standard-library `urllib.request` with `User-Agent: Mozilla/5.0 (Public academic research)`, a 30-second timeout, and a maximum of eight concurrent independent requests. HTML text was extracted with standard-library `HTMLParser`, ignoring scripts, styles, navigation, headers, and footers. PDF extraction used the already installed `.venv/bin/python` / `pypdf`; no dependency was installed. The initial shell name `python` was unavailable, so retrieval continued with `python3`. LOCO PDF extraction emitted missing-`fontTools` encoding warnings, but title/date/abstract were readable and corroborated by the official dataset page; no ambiguous extracted formula from that PDF was used.

| Retrieval key | UTC time, 2026-11-13 | HTTP / bytes | SHA-256 prefix of retrieved bytes | URL correspondence |
| --- | --- | --- | --- | --- |
| `mvtec-ad` | 18:51:11 | 200 / 71,565 | `ef44971b18c61a0c` | Q1 original AD URL → S1/S4 canonical AD page |
| `mvtec-ad2` | 18:51:12 | 200 / 73,388 | `f43c010e4152a59b` | Q1 original AD 2 URL → S2/S4 canonical AD 2 page |
| `mvtec-loco` | 18:51:12 | 200 / 72,226 | `104a07da80d104a3` | Q1 original LOCO URL → S3/S4 canonical LOCO AD page |
| `guo` | 18:51:09 | 200 / 14,452 | `3b4d7ca0ab60cd88` | S7 PMLR proceedings record |
| `nist-rmf` | 18:51:12 | 200 / 1,946,127 | `7576edb531d98488` | S5 official PDF |
| `nist-measure` | 18:51:10 | 200 / 273,997 | `b394500995e37823` | S6 Playbook Measure |
| `nist-ci` | 18:51:08 | 200 / 16,849 | `04fe750da86c0687` | S8 Handbook |
| `nist-uncertainty` | 18:51:09 | 200 / 88,704 | `1be13dacc3f4facf` | S9 TN 1297 index |
| `mvtec-ad-paper` | 18:52:14 | 200 / 4,146,132 | `25e9d853482fb861` | S1 author-hosted PDF |
| `mvtec-ad2-paper` | 18:52:16 | 200 / 485,096 | `4cf5014854fd03b8` | S2 Springer article HTML; cookie-query redirect noted above |
| `mvtec-loco-paper` | 18:52:20 | 200 / 5,694,363 | `3db889a0f0a7db75` | S3 Springer PDF; same cookie-query redirect pattern |
| `guo-paper` | 18:52:12 | 200 / 828,420 | `df7c93f97204f8a3` | S7 PDF, using HTTPS equivalent of record's HTTP link |
| `nist-uncertainty-7` | 18:52:13 | 200 / 94,641 | `19cd56a6303773ae` | S9 §7 |
| `nist-uncertainty-d2` | 18:52:12 | 200 / 93,897 | `9e2ef4a79142a769` | S9 Appendix D.2 |
| `opencv-calibration` | 18:52:14 | 200 / 32,370 | `6506accea4b726b3` | Q8 `/4.x/` → S10 `/4.13.0/` |

The prefixes identify this retrieval, not permanent content versions; live HTML and redirect parameters can change. Raw downloads were used only as local temporary research material. To reproduce the HTTP method and the statistical calculation without contacting a paid API:

```python
import hashlib
import math
import urllib.request

urls = [
    "https://www.mvtec.com/company/research/datasets/mvtec-ad",
    "https://www.mvtec.com/company/research/datasets/mvtec-ad-2",
    "https://www.mvtec.com/company/research/datasets/mvtec-loco",
    "https://www.mvtec.com/fileadmin/Redaktion/mvtec.com/05_research_teaching/datasets/mvtec_ad.pdf",
    "https://link.springer.com/article/10.1007/s11263-026-02743-0",
    "https://link.springer.com/content/pdf/10.1007/s11263-022-01578-9.pdf",
    "https://nvlpubs.nist.gov/nistpubs/ai/NIST.AI.100-1.pdf",
    "https://airc.nist.gov/airmf-resources/playbook/measure/",
    "https://proceedings.mlr.press/v70/guo17a.html",
    "https://proceedings.mlr.press/v70/guo17a/guo17a.pdf",
    "https://www.itl.nist.gov/div898/handbook/prc/section2/prc241.htm",
    "https://www.nist.gov/pml/nist-technical-note-1297",
    "https://www.nist.gov/pml/nist-technical-note-1297/nist-tn-1297-7-reporting-uncertainty",
    "https://www.nist.gov/pml/nist-technical-note-1297/nist-tn-1297-appendix-d2-identification-uncertainty-components",
    "https://docs.opencv.org/4.x/dc/dbb/tutorial_py_calibration.html",
]
for url in urls:
    request = urllib.request.Request(
        url, headers={"User-Agent": "Mozilla/5.0 (Public academic research)"}
    )
    try:
        with urllib.request.urlopen(request, timeout=30) as response:
            content = response.read()
            print(url, response.status, response.url, len(content),
                  hashlib.sha256(content).hexdigest())
    except Exception as error:
        print(url, "RETRIEVAL_FAILED", type(error).__name__, str(error))

for n in (30, 60, 100, 299, 2995):
    print(n, "zero-event one-sided 95% upper bound", 1 - 0.05 ** (1 / n))
for target in (0.05, 0.01, 0.001):
    print(target, "independent zero-event trials required",
          math.ceil(math.log(0.05) / math.log(1 - target)))
```
