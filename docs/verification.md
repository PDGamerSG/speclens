# Verification record

## Automated application checks

The final local `./scripts/check.sh` run passed **53 Python tests**, **seven browser scenarios**, the production build, and clean lint. The same command runs in CI.

The [GitHub run for deddb6a](https://github.com/PDGamerSG/speclens/actions/runs/42373503827) passed 46 Python tests, five browser scenarios, the production build, and lint. These tests simulate external vision and Hindsight calls.

The macOS setup script completed successfully. The Docker image built on Linux ARM64 and served its UI, status, and sample images. Direct requests for the SQLite database and ledger returned 404. A missing model key produced the expected 503 setup response.

## Live external services

The [sanitized integration record](evidence/live-integration.json) comes from an actual Meta vision and Hindsight Cloud run on November 7, 2026. It confirms:

- A live vision response with memory disabled.
- A confirmed retain and recall linked to the stable correction ID.
- A later inspection of a different source photo that cited the correction.
- A Hindsight standards reflection.
- A paired comparison with identical image, model, and base specification.
- Four durable inspection records and the linked correction.

Both comparison arms rejected the marked part. This check proves live integration behavior; it does not demonstrate a learning improvement or establish accuracy on factory data. Inputs were synthetic. The report separates vision spend from Hindsight billing.

## Live memory ablation

The [complete four-case record](evidence/memory-ablation.json) uses a separate teaching source (01) and two held-aside source photos (02 and 03). Each test photo contributes one faint-print image and one untouched control. Both comparison arms use the same normalized pixels, model, and base specification; call order is alternated by the service. A human-written rule is retained once, then recalled for each memory-enabled inspection.

| Observed count | Memory off | Memory on |
|---|---:|---:|
| Correct verdicts | 3/4 | 4/4 |
| Marked parts detected | 1/2 | 2/2 |
| False alarms on untouched controls | 0/2 | 0/2 |

The changed decision concerned the faint B2 marking on source 03. Without memory, the model described natural stripes and gloss. With memory, it identified the faint printed characters and cited the retained correction. See the [actual comparison screenshot](screenshots/comparison-live.png).

This is one exploratory pass on four synthetic cases from two correlated source-photo groups, not evidence of production accuracy or a stable causal effect. No repeated-run confidence estimate is available. The earlier integration check correctly caught its marked sample in both arms.

![Observed detection and false-alarm counts](screenshots/memory-ablation.png)

## Band Desktop

Official Band Desktop 0.4.18 was installed with a verified application signature. `band doctor` reported a reachable daemon, a connected account, and three connected configured agents. The app was opened and its account/agent connections checked. This record does not claim that the implementation was authored through Band.
