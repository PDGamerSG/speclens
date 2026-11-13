# Factory pilot operations and traceability

Research date: 14 November 2026, Asia/Kolkata. This is a bounded public-source investigation and a proposed workflow; no factory interviews or field observations have been performed.

## Conclusion

Start with an operator-assisted inspection station for one part family, one capture setup and a named quality owner. Make the quality decision, the physical part/lot, the approved inspection recipe and the responsible person traceable. Adding a PLC connector or a wider dashboard before these records exist would not resolve those gaps.

The one-part/one-station constraint is a proposal for the pilot, not a discovered customer requirement. A customer demanding unattended line-rate inspection needs a different latency, hardware and validation investigation before this architecture is selected.

## Primary evidence

| ID | Claim type | Opened primary source and location | What it supports | Limits |
|---|---|---|---|---|
| OP1 | Fact about the published reference | [OPC Foundation, OPC UA for Machine Vision, Part 1, section 5: Use cases](https://reference.opcfoundation.org/specs/OPC-40100-1/5), subsections Recipe Management and Result Transfer | A recipe stores a vision task's properties/procedures/parameters; asynchronous result transfer includes product assignment, times and statuses. | This is an interoperability model. It does not require SpecLens to implement OPC UA for a first manual station, and it does not validate any particular model. The published reference inspected displays v1.0. |
| OP2 | Fact about the reference | [OPC Foundation, Part 1, section 4.1](https://reference.opcfoundation.org/specs/OPC-40100-1/4), Introduction to Machine Vision systems | Automated production systems often exchange a start signal and inspection result with a controller; the reference also includes an operator-started test bench within its broad automation model. | A use-case description is not evidence that every prospect needs a PLC or real-time conveyor deployment. |
| OP3 | Statistical definition and assumptions | [NIST/SEMATECH Engineering Statistics Handbook, 6.3.3.2 Proportions Control Charts](https://www.itl.nist.gov/div898/handbook/pmc/section3/pmc332.htm), definition of fraction nonconforming and binomial model | Fraction nonconforming divides nonconforming physical items by total items. The described model assumes a stable probability and independent successive units. | AI predictions are not ground truth. Repeated photos, comparison arms and correlated lots cannot automatically be treated as independent production units. |
| OP4 | Statistical description | [NIST/SEMATECH Engineering Statistics Handbook, 6.3.1 What are Control Charts?](https://www.itl.nist.gov/div898/handbook/pmc/section3/pmc31.htm), Characteristics of control charts | A control chart tracks a measured/computed quality characteristic against sample or time with a center and control limits. | A dashboard line or threshold alone is not a validated statistical process control chart. Customer-approved sampling and baseline conditions are needed. |

These sources were retrieved successfully as public HTML on 14 November 2026 IST. No publication/revision date is inferred from retrieval time. The JSON log records UTC timestamps, requested URLs, redirects, HTTP status and retrieval purpose.

## Proposed pilot workflow

1. A quality engineer publishes a part/specification revision and an approved inspection recipe. The recipe pins the part, specification, rule versions, model/prompt configuration, capture profile and review policy.
2. An operator starts a lot/session, identifies the physical part where available, chooses the recipe and captures a usable photo. Context travels with each inspection, rather than being inferred from a filename.
3. The inspector records the original model result and cited rule versions. The system routes uncertain/error cases and the site's chosen sample of accepted/rejected parts to a durable review queue.
4. A reviewer records final disposition: accept, reject, rework or hold according to the site's agreed choices. This action does not automatically teach the model.
5. An engineer can separately propose a reusable standard, with a clause, evidence image and intended scope. Only an approved, active standard becomes eligible for recall. Retirement blocks future use while retaining historical provenance.
6. A lot report separates physical part counts, model flags, final human dispositions, unresolved reviews, and system failures. A quality owner signs off using the site's process; the application must not label this regulatory certification.
7. A fixed validation dataset and frozen rule snapshot test whether the change transfers to other parts without increasing escapes, false rejects or review workload beyond agreed limits.

## Information required before a pilot commitment

- Exact part, defect classes and quality specification; what counts as a critical defect.
- Incoming inspection/bench review versus conveyor inspection; target arrival rate and allowed response time.
- Current reference decision and how inspectors resolve disagreement.
- Physical part identifiers, manufacturing lot identifiers, line/shift/camera identifiers and whether serial-level tracking is practical.
- Who can approve or retire a standard; whether independent second approval is available.
- Image confidentiality, permitted cloud providers, data residency and retention policy.
- Measured manual review time, reinspection volume and cost of each type of error. These determine value; no ROI estimate is asserted here.
- The single required hand-off to the factory's existing process: for example CSV, an inspection-result webhook, or a later machine interface.

## Product implications — proposals

- **Lots & Traceability** is different from a photo batch: one manufacturing lot can span several photo batches and shifts; several photos may represent one physical part.
- **Products & Specs** should own stable IDs, revisions, capture settings and frozen recipes. A content hash is useful for deduplication but does not establish tenant ownership or approval.
- **Review Queue** should preserve assignment, age, evidence, reason, actor and disposition history. It should not be a temporary sort of jobs in one browser.
- **Standards Library** should separate candidate, approved, superseded and retired rules, with scope checks and immediate retrieval filtering even while an external memory deletion is retrying.
- **Quality Insights** should keep evaluation calls out of production unit counts and show reviewed outcomes separately from model-predicted rejects. Formal control charts belong after sampling/denominator validation.
- **Reports & Connections** should begin with one reliable result export/hand-off. Broad ERP/MES connectors, OPC UA and automated ejection are conditional later work.

## Retrieval limitations and contrary evidence

The direct GS1 traceability overview/current-standard URLs returned HTTP 403, an alternate GS1 US path returned 404, and the attempted `ref.gs1.org/standards/gts/` path returned 404. Their contents are not used as evidence. ISO's public ISO 9001 overview returned a 403 challenge; no ISO conformity claim or normative requirement is inferred. Google returned a JavaScript/interstitial response without usable search results; DuckDuckGo returned a CAPTCHA. These are retrieval failures, not findings about the absence of standards or competing products. The investigation therefore uses explicitly logged direct primary-source retrieval rather than claiming an exhaustive search.

The OPC reference describes both industrial controller integration and a simple operator-started test bench. This argues against assuming that adding a PLC is the necessary first step for every pilot.
