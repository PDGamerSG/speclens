# SpecLens demo walkthrough

Use the normal app at http://localhost:8770 with real Meta and Hindsight credentials. Do not record the simulated browser-test server as live model evidence.

## Prepare

Run `scripts/system_check.py` once to check both connections. Open the app and create a fresh workspace named for your recording. Keep the default whole-hazelnut specification. Close notifications and increase browser zoom if needed.

The samples are generated images. The white markings are controlled ink overlays with exact masks; the demo should say so. Use different source photos for teaching and transfer, such as **White marking** and **Another marking**. Do not teach on a part and present that same image as a new example.

## Three-minute recording

**0:00–0:20 — The problem.** Show the inspection desk. Explain: “A visual inspector can read a specification and still misinterpret a faint mark. SpecLens lets a quality engineer turn a correction into a standard the next inspection can recall.”

**0:20–0:50 — Establish a decision.** Select White marking, turn quality memory off, and inspect. Read the actual verdict and rationale. If the model catches the ink correctly, say so. A demonstration must not force or invent a miss.

**0:50–1:25 — Teach the standard.** Open Correct this decision. Choose Reject / Print and enter: “Sharp white printed characters on the shell are ink. Reject them as print defects. Broad, smooth natural highlights alone remain acceptable.” Enter your reviewer name and save. The saved correction includes the model’s original reasoning. Wait for the confirmed Hindsight sync; if it remains pending, show the retry state honestly.

**1:25–1:55 — Recall on another part.** Select Another marking, turn memory on, and inspect. Point to the cited standard under Recalled for this part. Explain that Hindsight retrieved the correction and the base specification stayed fixed. Report the actual decision; a recalled rule is an observed memory step even when both runs reach the same verdict.

**1:55–2:25 — Compare.** Open Memory comparison and run both arms. Show the observed verdicts and rationales. Mention that the same image, model, and specification were used. This is one paired observation; model outputs can vary.

**2:25–2:50 — Persistence and context.** Open Quality memory, summarize the standards, then open history. Reload to show that the correction and original decision remain. Briefly show workspace settings: each factory, part family, and specification revision has its own memory bank.

**2:50–3:00 — Close.** “The useful part is the traceable correction: what the model said, what the engineer changed, and which later inspection used that standard.” Show https://github.com/PDGamerSG/speclens.

## Sixty-second cut

Inspect without memory → enter a clear correction → wait for Hindsight sync → inspect a different part with memory → highlight the cited correction. State the observed result without claiming a general accuracy gain.

## Video titles

- Teaching a Visual Inspector Your Standards with Hindsight
- SpecLens: A Correction the Next Inspection Can Recall
- From Quality Review to Cited Agent Memory
- Why Inspection Corrections Need Their Own Memory
- One Part, Two Inspections: Testing Quality Memory
