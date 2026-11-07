# Dependencies and data

## Services

- **Meta Model API** (`https://api.meta.ai/v1`): `muse-spark-1.3` supplies vision decisions. Image-generation and segmentation utilities support `muse-image-1.0` and `sam-3.1`. Meta’s service and model terms apply.
- **Hindsight**: the backend calls the documented retain, recall, and reflect HTTP APIs. Hindsight Cloud operates its own configured inference; self-hosted inference is configured by the operator. See the [Hindsight repository](https://github.com/vectorize-io/hindsight) and service terms.
- **Public Sans**: Google Fonts, SIL Open Font License 1.1. System fonts provide a fallback.

## Python packages

See `backend/requirements.txt` for exact versions. FastAPI, Uvicorn, HTTPX, python-dotenv, pytest, and their dependencies use their upstream licenses. The OpenAI-compatible client library is Apache-2.0; it is pointed at Meta’s API. NumPy is BSD-3-Clause, Pillow is HPND/MIT-CMU, and OpenCV is Apache-2.0 with wrapper and bundled-library notices. `meta-sam-parser` uses Meta’s SAM License. Consult each distribution’s license files for complete notices.

## Web packages

React, Vite, Tailwind CSS, Lucide, and the corresponding tools retain their upstream licenses. TypeScript is Apache-2.0 and Playwright is Apache-2.0. Lucide icons are ISC-licensed. The dependency lockfile records exact package versions.

## Images and evaluation data

The hazelnut photos in `fixtures/parts/` are generated images. Sample crack/hole images are synthetic composites. The white-print examples in `fixtures/speclens/` add deterministic ink overlays to generated photos; their masks identify every changed pixel. None represents a customer’s production part or a measured manufacturing defect.

MVTec AD data is not bundled. If used for a separate local evaluation, its CC BY-NC-SA 4.0 license and MVTec Software GmbH attribution apply. See Bergmann et al., “MVTec AD: A Comprehensive Real-World Dataset for Unsupervised Anomaly Detection,” CVPR 2019.
