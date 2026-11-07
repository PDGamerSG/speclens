# Third-party software, data and prior work

## Runtime models

All runtime models are Meta models, called through the Meta Model API (`https://api.meta.ai/v1`):
- `muse-spark-1.3`
- `muse-image-1.0`
- `sam-3.1`

No other learned model runs at runtime. OpenCV, NumPy and Pillow are classical image-processing libraries.

## Python packages (`backend/requirements.txt`)

| Package | License |
|---|---|
| fastapi, starlette, uvicorn, sse-starlette, python-multipart, httpx, python-dotenv | MIT or BSD |
| openai (used only as an OpenAI-compatible client pointed at api.meta.ai) | Apache-2.0 |
| meta-sam-parser | SAM License (Meta) |
| numpy | BSD-3-Clause |
| opencv-python-headless | Apache-2.0 (OpenCV), MIT (wrapper) |
| pillow | MIT-CMU (HPND) |
| pytest | MIT |

## Frontend packages

See `frontend/package.json`: React (MIT), Vite (MIT), Tailwind CSS (MIT), TypeScript (Apache-2.0) and any listed chart library (MIT).

## Data

- **MVTec AD**, `hazelnut` category: CC BY-NC-SA 4.0, © MVTec Software GmbH. It is used only for local evaluation and is **not redistributed**: `eval/download_mvtec.py` fetches it from a Hugging Face mirror into the gitignored `data/` folder. Bergmann et al., "MVTec AD: A Comprehensive Real-World Dataset for Unsupervised Anomaly Detection", CVPR 2019.
- **Sample good parts** in `fixtures/parts/` and the **demo replay** in `fixtures/demo_run/` were generated with Muse Image (`muse-image-1.0`) for this project.

## Patterns and prior work (no code copied verbatim)

- **Meta Model API docs and the Meta model cookbook** (`meta-models/meta-model-cookbook`, MIT): the request shapes for Muse Image edits, SAM 3.1 Responses calls with `meta_sam_parser`, and retry handling.
- **Related work** we position against:
  - AnomalyAgent (arXiv 2604.07900), agentic anomaly synthesis
  - DualAnoDiff and AnomalyDiffusion, few-shot defect synthesis that needs real defects
  - MMAD (ICLR 2025), a VLM anomaly benchmark
  - Walkdown, a hackathon entry that uses Muse Image for false-alarm stress images
  - CounterForge, VLM regression tests with controlled image changes
