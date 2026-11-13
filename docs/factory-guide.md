# Factory workspace guide

The Factory workspace connects products, specification revisions, capture setup, lots, human review and quality follow-up. Open **Factory workspace** from the public inspection desk. It uses the existing inspector and provider settings; creating a team, setting up records and importing validation results do not require model calls.

This is an inspection evidence workspace. People remain responsible for physical containment, disposition and material release. A software workflow or imported result does not establish factory accuracy or regulatory compliance.

## Create or join a team

For a shared sample workspace, use the credentials displayed below **Sign in**: username `demo.speclens`, password `SpecLensDemo2026!`. This public account has engineer access to the dedicated **SpecLens Demo Factory**, with an example approved revision, capture station and open lot. Everyone using these credentials shares its records; use sample data only. The published login is provisioned on the hosted site, separate from private teams. Local installations need their own accounts.

Choose **Create a team** to register a new isolated workspace. Supply a display name, team name, globally unique username and password. Usernames are case-insensitive, use 3–64 letters, digits, dots, underscores or hyphens, and are not verified email addresses. Passwords use 12–256 characters. The creator becomes the first admin.

To add a colleague, an admin opens **Team**, chooses a role and creates an invitation. Copy the token while it is displayed and share it privately with the intended person. It is shown once, expires after 48 hours and can create one new member. The recipient chooses **Join with invitation** and registers a new username/password. There is no email delivery or invitation-link verification service.

| Action | Admin | Engineer | Operator | Viewer |
| --- | --- | --- | --- | --- |
| Read team operational records, validation and lot exports | Yes | Yes | Yes | Yes |
| Create products, draft revisions and capture stations; update station setup | Yes | Yes | No | No |
| Approve/retire specification revisions or standards | Yes | No | No | No |
| Open lots and capture parts | Yes | Yes | Yes | No |
| Close/reopen lots, review decisions, propose standards, manage issues, import validation | Yes | Yes | No | No |
| List/manage members, create invitations, delete team operational data | Yes | No | No | No |

Role checks run on the server. An admin can change a member's role or deactivate membership. Deactivation revokes existing sessions; reactivation requires a fresh sign-in. The final active admin cannot be demoted or deactivated. Keep a second trusted admin for continuity.

Sessions expire seven days after sign-in. **Sign out** revokes the current session. **Return to public demo** also signs out; team data is not copied into the anonymous workspace. An expired, revoked or inactive session requires sign-in and does not silently become anonymous access to team records.

There is no self-service password reset, account recovery, password-change screen, verified email, MFA or SSO in this release. Store passwords securely. An admin cannot recover another member's password through the app. Operational data deletion also does not delete authentication accounts.

## Prepare an approved inspection recipe

In **Products & Specs**, add the product code, product name, factory and optional description. Create a draft with a revision label, specification text and capture instructions. A revision's text is immutable after creation; use a new revision for a replacement.

The draft is parsed locally without a provider call. Numbered clauses under a `REJECT` heading produce defect classes, for example:

```text
Part: Shell
Nominal width: 20 mm
REJECT
4.1 Crack: Reject cracks longer than 2 mm.
4.2 Print: Reject any visible ink marking.
```

Inspect the displayed classes, clauses, limits, part width and capture instructions. Text that the rule reader cannot interpret gets a generic defect class. Revise the specification as a new draft if that reading is unsuitable. The API also accepts a complete administrator-confirmed taxonomy at approval; changing a separate demo/model reading does not rewrite the approved factory recipe.

An admin checks **I have checked the specification and parsed defect classes**, then chooses **Approve revision**. Approval validates and freezes the taxonomy and instructions. Width must be a positive finite number or unknown (`null`); defect limits must be finite nonnegative numbers or `null`. There must be 1–12 unique valid defect classes. Numeric-looking strings, booleans, NaN and infinity are rejected.

Retiring a revision prevents new captures under it. A retired revision cannot be reactivated; create and approve a replacement. Historical evidence remains. Approved revision IDs and team IDs define the inspection scope, so display-name changes cannot mix histories.

In **Capture Stations**, create a named station for the product and write its lighting, angle and setup instructions. A station records human setup context; it does not calibrate a camera. An engineer or admin can update instructions or deactivate it. Captures require an active compatible station, and recipe changes can invalidate work queued against an older version.

## Open a lot and capture physical parts

In **Lots**, select an approved revision and an active station for the same product. Add a lot reference and optional notes. The new lot is open and keeps its chosen revision/station identity. Open its detail view and choose **Capture a part**, or use **Capture Desk**.

Choose a JPG, PNG or WebP still photo, take a camera photo, or explicitly choose a generated sample. Supply a physical part ID such as `PART-001`. Use that same ID for every view or retake of the same physical item in that lot; use a new ID for a different item. The app cannot identify a physical object or enforce your labeling procedure for you. Generated samples are demonstrations, not factory validation evidence.

The desk shows the selected product/revision, station and both sets of instructions. **Use approved quality standards** controls recall; unapproved, retired or wrong-revision standards cannot enter a new factory prompt. Photo/model failures remain visible. A required recall failure stops the inspection rather than substituting a baseline result.

Each submission has a stable capture ID. Retrying the same submission retains that ID so a timeout or restart cannot save duplicate assessments. Reusing it for a different image, part or context is rejected. Choose **Start a new capture attempt** when a changed recipe needs a new attempt. The earlier attempt remains recorded.

For a retake, use the review's retake action or **Retake failed capture** in the lot trail. This supplies `retake_of` and keeps the original physical part ID. A valid completed replacement links to the earlier attempt; failed or quarantined history remains visible. A retake adds an attempt, not another physical part.

Every saved factory assessment creates an open human review, including model Accept and Reject results. The captured context preserves revision/taxonomy, station, actor and approved source versions. If a revision, station or used standard changes during inference, the saved result can be quarantined. Preserve that evidence and take a new eligible capture; a quarantined recommendation cannot be accepted as current evidence.

## Review and close a lot

An engineer or admin opens **Review Queue**, selects the case and may claim it. Claiming assigns the signed-in actor; reviewer names cannot be supplied as someone else. Inspect the photo, model reason, context and relevant clause, then record an outcome and reason.

| Outcome | Meaning for lot resolution |
| --- | --- |
| Accept | A human accepted this assessment for the physical item; separate from the model recommendation and any downstream release decision |
| Reject | A human rejected the item on the recorded evidence |
| Hold | The physical item remains unresolved pending investigation |
| Retake | A replacement capture is required; the old case and reason remain |

Closing a review requires both an outcome and reason. Reopening preserves disposition history. Closing a review never teaches a standard or overwrites the original model result.

Close **all** open reviews before closing the lot, including earlier reviews that have a newer retake. Held, requested-retake and quarantined work needs a valid linked replacement; the latest physical-part review must end in Accept or Reject. Pending/running captures and unresolved failed captures also block closure. A closed lot rejects new captures. An engineer or admin can reopen it.

The lot view separates physical parts, capture attempts and review state. Comparing model outputs is evaluation activity and does not add production captures to the lot. Nonconformance closure is a separate workflow; the app does not automatically release material or enforce a full quality-system release policy.

## Propose and govern reusable standards

From a review with an eligible inspection, choose **Propose a standard** and record the corrected verdict, defect class and visual rule. Quarantined evidence cannot teach a standard; capture a valid replacement first. The original model result remains. For factory inspections this creates a **candidate** in **Standards**, excluded from memory sync and future recall until approved.

An admin reviews the source inspection, revision, clause and rule, then approves the candidate. Approval is saved before retryable Hindsight sync starts. An approved standard can remain visibly pending if synchronization fails; approval and successful memory storage are separate states. Engineers/admins can retry an eligible correction sync. Approval does not itself close the current human review.

Retiring a standard blocks new use locally immediately, even if a remote fact still exists. A retired standard cannot be reactivated. Published rule text and source identity are immutable; propose a replacement from a suitable inspection. Existing assessments retain their provenance, and an affected call already in flight is preserved and quarantined.

## Record nonconformances and activity

In **Nonconformances**, link a quality issue to a lot and optionally one of that lot's inspections. Supply a title, description and minor/major/critical severity. Record the requirement or clause, containment, known root cause, corrective action, resolution, and effectiveness/closure evidence as appropriate. An assignee must be an active team member; the member picker is available with admin team data.

Marking an issue contained requires recorded containment. Closing requires corrective action and resolution. Requirement, root cause and evidence support your quality review but are not universally mandatory fields. Reopening preserves history. This is a bounded issue register, not a complete regulated CAPA system or a verification that actions worked in the factory.

**Activity** records attributable lifecycle changes and targets. Domain changes and their events share a database transaction. Review and issue histories retain their prior transitions. This is application lifecycle history, not a cryptographically signed or tamper-proof security audit; server/database operators retain privileged access.

## Import matched validation results

**Validation** evaluates precomputed outputs. Paste a JSON array of cases, or load an object with `cases` and optional `configuration`. Give the run a name. Engineers/admins can import; all active members can read/export saved runs.

Each case supplies `sample_id`, `physical_part_id`, `lot_id`, `session_id`, known `truth` (`good`/`defect`), and `baseline`/`with_memory` outputs (`good`, `defect`, `uncertain`, `error`). Optional severity is minor/major/critical. Maximum 2,000 samples per run. See the [API example](api/factory.md#validation-imports).

Inputs, labels, IDs and configuration are importer assertions. The app does not run providers, verify provenance, confirm linkage to operational lots, or prove that teaching and evaluation data are independent. Importing incurs no model cost.

Input order declares attempt order. The first occurrence of each physical part supplies its paired result; repeated views must have consistent truth, predictions, lot and severity. Unique sample IDs are required. Retakes cannot inflate the independent-part denominator or hide the declared first attempt.

Results separate escaped defects, false rejects, Review workload, technical errors and decision coverage. Review/error remain unresolved, not successful defect detections. Parts sharing a lot or capture session are joined into connected clusters for paired 95% bootstrap intervals. Fewer than two candidate clusters gives no interval; few clusters can yield unstable/degenerate intervals. Different IDs do not establish independence, representativeness or lack of leakage. Zero observed failures is not a proven failure-rate bound.

Each saved run has immutable inputs, configuration, selected samples, clusters and a SHA-256 manifest digest. Export preserves the declared inputs and calculated result; the digest does not authenticate the source or prove factory performance.

## Export, retention and deletion

From a lot detail, **Export lot JSON** downloads the complete record set, independent of UI filters. It includes product/revision/station, every capture, saved assessment and review, relevant corrections and revision standards, issues, activity, part-resolution state and explicit counts. **Export lot CSV** flattens every capture attempt, including failed/pending attempts with empty assessment fields.

JSON evidence entries identify media by authenticated URL, availability and SHA-256 digest when the stored file is available. Image bytes are not embedded. Download the required files separately while signed in to the same team and retain them with the manifest if you need an offline package. Missing files are explicit; a manifest is not proof that an image will remain accessible forever. Model aliases and stochastic outputs also limit exact reproducibility.

Anonymous demo records are eligible for the nightly `RETENTION_DAYS` purge, 90 days by default. Team factory evidence is excluded from that age-based purge. Completed job/upload cleanup can run separately without erasing captures, reviews or factory evidence. Session expiry does not delete operational records.

Explicit operational deletion is available to an admin through `DELETE /api/workspace/data` with `{"confirm":"DELETE"}`. Wait for queued/running jobs to finish. The operation removes team operational records, linked media and configured Hindsight banks; remote memory failure stops deletion so it can be retried. Inspect returned cleanup failure counts. It leaves team/user accounts, memberships, sessions, invitations and auth limits in place. There is no complete account/team erasure endpoint in this release. Backups and provider retention need separate handling by the deployment operator.

Keep private exports and backups according to your team's retention decision. Use the [deployment guide](deployment.md#factory-workspace-release-migration-and-retention) for migration, backup verification and recovery.
