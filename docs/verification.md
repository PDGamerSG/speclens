# Verification record

## Automated application checks

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

## Band Desktop

Official Band Desktop 0.4.18 was installed with a verified application signature. `band doctor` reported a reachable daemon, a connected account, and three connected configured agents. A project work session and its evidence remain a team task; installation alone does not prove development work was performed through Band.
