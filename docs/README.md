# Documentation

Where to find each part of the SpecLens documentation. Product guides describe the repository as it is; research and proposals are labeled separately. Statements cite the file they come from, and anything the repository does not record is marked "Not recorded in the repository".

## Start here

| Document | What it covers |
| --- | --- |
| [README](../README.md) | What SpecLens is, the team, the live link, how it works and the quick start |
| [Demo guide](user-guide.md) | The anonymous photo inspection, correction and comparison desk |
| [Factory workspace guide](factory-guide.md) | Team setup, products, approved revisions, stations, lots, review, standards, issues and validation |
| [Setup](setup.md) | Local install, Windows, Docker, backups and connection checks |
| [Troubleshooting](TROUBLESHOOTING.md) | Setup, inspection, memory, test and deploy problems |

## Suggested reading order

1. [README](../README.md): what SpecLens does and the "How it works" diagram.
2. [Demo guide](user-guide.md) or [Factory workspace guide](factory-guide.md): follow the workflow you are using.
3. [Architecture](ARCHITECTURE.md): the underlying inspector and service boundaries; the factory guides describe the added team domain.
4. [Configuration](CONFIGURATION.md): the settings each part reads.
5. [Test plan](testing/test-plan.md): what the checks prove and what they do not.

## Reference

| Document | What it covers |
| --- | --- |
| [Architecture](ARCHITECTURE.md) | The parts, outside services, the main request, the data model and deployment |
| [Configuration](CONFIGURATION.md) | Every environment variable, its default and what reads it |
| [Demo HTTP API](api/README.md) | Existing inspection routes and anonymous demo behavior |
| [Factory HTTP API](api/factory.md) | Team authentication, permissions, typed workflows, validation, capture context and lot exports |
| [Design](design.md) | The product's acceptance rules, boundaries and visual direction |
| [Deployment](deployment.md) | The Vercel frontend, the Lightsail server, publishing, backups and recovery |
| [Threat model](security/threat-model.md) | What data the site stores and sends, and how it is protected |
| [Test plan](testing/test-plan.md) | What is tested, how to run it and what CI runs |

## Records and evidence

These record what happened. They do not change as the code changes, so an older record can describe an earlier release.

| Document | What it covers |
| --- | --- |
| [Verification record](verification.md) | Results from automated checks and live runs |
| [Demo walkthrough](demo.md) | How to record the demo, with a three-minute script |
| [Submission materials](submission/README.md) | The project summary, with an [article draft](submission/article.md), [social drafts](submission/social.md), the [demo video](submission/SpecLens-demo-1080p.mp4), its [transcript](submission/SpecLens-demo-transcript.md) and [subtitles](submission/SpecLens-demo-English.srt) |
| [Live integration report](evidence/live-integration.json) | Raw record of a live Meta and Hindsight run |
| [Memory ablation report](evidence/memory-ablation.json) | Raw record of the four-case memory test, with a [chart](evidence/memory-ablation.svg) |
| [Public release report](evidence/public-release.json) | Raw record of the first public deployment checks |
| [SpecLens release report](evidence/speclens-release.json) | Raw record of the release checks under the SpecLens name |
| [Implementation plan](implementation-plan.md) | The original build plan, kept as history. It names Tailwind, which `frontend/package.json` does not list |
| [Architecture page](architecture.html) | A static page that draws the correction and recall loop |

## Research and proposals

These retain the source research and original proposals. The team workspace described in the factory guides is implemented in the repository; research findings and proposed later extensions are not evidence of factory performance or regulatory compliance. Older walkthroughs, screenshots and release reports describe the releases when they were recorded.

| Document | What it covers |
| --- | --- |
| [Factory pilot roadmap](research/2026-11-14-factory-pilot/00-roadmap.md) | Original source audit, vendor comparison and roadmap, with a [visual roadmap](research/2026-11-14-factory-pilot/roadmap.html); use the factory guide/API for current shipped behavior |
| [Quality workflow research](research/2026-11-14-factory-pilot/06-additional-quality-workflows.md) | Primary-source rationale for the bounded issue register, containment, corrective action and closure evidence |

## Other files

- [`images/`](images/) holds the README and user guide screenshots.
- [`screenshots/`](screenshots/) holds earlier screenshots used by the records above.
- [`frontend/README.md`](../frontend/README.md) covers the web interface commands.
- [`THIRD_PARTY.md`](../THIRD_PARTY.md) lists dependency and data notices.
