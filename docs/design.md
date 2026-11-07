# SpecLens design

SpecLens is a visual quality inspection workspace for manufacturing teams. A quality engineer inspects a part, corrects an incorrect decision, and sees that correction recalled during inspection of a different part.

## Acceptance
- Real Meta vision inspection with visible reasoning and a defect box.
- Human correction with an explicit acceptance rule, saved durably in SQLite.
- Hindsight retain, recall and reflect, scoped to a factory and part family.
- Recall results cite the source correction. Memory-disabled inspection uses the identical base specification and image.
- Correction storage survives restarts; failed Hindsight writes stay visibly pending and can be retried.
- Memory failures remain visible and do not silently claim a successful learning step.
- A responsive operator workspace, correction history, memory view and comparison view.
- No fabricated counts, customers or performance claims. Sample images are labeled as generated examples.

## Architecture
Reuse the Python FastAPI vision pipeline and React/Vite toolchain. Add a focused inspection service, a SQLite inspection/correction store, and an HTTP Hindsight adapter. Store each correction with the original model decision, the operator rule, source image hash and a stable document ID. One bank per factory/part/spec revision prevents cross-scope leakage. Retrieve only corrections from that bank before a new inspection; do not read local corrections into the inspection prompt as a substitute for Hindsight. Hindsight is the memory system; SQLite is the auditable application record.

## Visual direction
A light one-page inspection bench. See `frontend/.21st/DESIGN.md` for the current tokens. The original concept was a light operator workspace: navy #142D42 navigation, paper #F5F7FA canvas, white #FFFFFF surfaces, teal #087F76 primary actions, amber #B86B14 review states, ink #1A2B3C text. Use Public Sans for the interface and tabular figures for measurements. The product image occupies the largest surface. Verdict and correction controls stay next to it. The memory sidebar shows concrete cited standards rather than decorative activity.

## Boundaries
One part family and one approval workflow for the submission. No accounts, billing, team administration, or unattended production rejection. Operators remain responsible for final disposition.
