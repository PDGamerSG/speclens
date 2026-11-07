# SpecLens frontend

Vite + React + TypeScript + Tailwind CSS v4. The browser talks only to our FastAPI backend (`/api`, `/files`); it never calls a Meta model and holds no API keys. Every Meta call happens in `backend/` and shows up in the call-log drawer.

## Commands

```bash
npm install

# live: proxies /api and /files to the backend (default http://localhost:8765)
npm run dev

# point the proxy somewhere else
VITE_API_TARGET=http://localhost:8000 npm run dev

# mock mode: no backend needed; every endpoint and the SSE stream are faked in the browser
VITE_MOCK=1 npm run dev
VITE_MOCK=1 VITE_MOCK_DEMO=1 npm run dev     # also reports demo_mode, so the DEMO REPLAY badge shows
VITE_MOCK=1 VITE_MOCK_SPEED=3 npm run dev    # mock pipeline 3x faster

npm run build      # tsc -b && vite build, output in dist/
```

On Windows PowerShell, set the variables first: `$env:VITE_MOCK='1'; npm run dev`.

The dev server listens on all interfaces (`server.host: true`) and accepts any host header, so a cloudflared quick tunnel works for phone testing. Phones need HTTPS for the live camera on the Inspect screen:

```bash
cloudflared tunnel --url http://localhost:5173
```

## Mock mode

`src/api/mock.ts` implements the same `Api` interface as the real client (`src/api/client.ts`). It runs a fake pipeline with realistic timing: taxonomy, part location, Muse Image forging with critic retries, compositing, SAM labels, eight validators, then the severity ladder and detection curves. It emits the same SSE event names and fills the call ledger. Images are drawn procedurally on a canvas (`src/api/mockArt.ts`); no real photos are bundled.

## Screens

- **Forge** (`#/forge`): spec to taxonomy, good-part gallery with masks and uploads (`capture="environment"` opens a phone camera), the forge controls, the live stage timeline and the forged-defect grid. Click a card for the before/after slider, raw-vs-composite toggle, full image with mask overlay, prompt, critic notes and validators.
- **Stress test** (`#/stress`): per-type threshold callouts, detection-threshold curves (size and opacity, 95% Wilson whiskers, a table view), and the severity strip of every variant marked caught or missed.
- **Inspect** (`#/inspect`): webcam capture or photo upload to `POST /api/inspect`, with an optional run of forged examples.
- **Results** (`#/results`): renders `GET /api/eval`; empty sections say "Not run yet".

The call-log drawer (bottom right) polls `GET /api/ledger` every 3 s and merges live SSE `call` events.

## Layout

```
src/
  api/        types.ts (contract types), client.ts (fetch + EventSource), mock.ts, mockArt.ts, index.ts (picks live or mock)
  state/      store.tsx (app state, SSE stream handling, ledger polling)
  components/ Header, CallLog, StageTimeline, SampleCard, SampleDetail, BeforeAfter, Zoom, Curves, ErrorBoundary, ui
  screens/    Forge, Stress, Inspect, Results
  lib/        format, colors, curves (threshold headlines), useImageSize
```
