# SpecLens web interface

React, TypeScript, Vite, WebGL, and Lucide. The browser sends requests only to the SpecLens backend. Vision and Hindsight keys remain on the server.

```bash
npm ci
npm run dev       # http://localhost:5173; API proxy -> http://127.0.0.1:8770
npm run build     # production assets in dist/
npm run lint
npx playwright install chromium
npm run test:e2e
```

Set `VITE_API_TARGET` to override the development proxy. The API and UI can be served together with `../scripts/dev.sh`; see the [main README](../README.md).

`src/workspace/Workspace.tsx` holds the page state and layout. `PartViewer.tsx` and `scan.ts` draw the stage and point cloud, `Ticket.tsx` shows the decision, and `sections.tsx` holds quality memory, comparison, and history. Set `E2E_PORT` to run the browser tests on another port. `PartViewer.tsx` handles zoom and model boxes. `CorrectionForm.tsx` collects the human standard. `api.ts` defines the HTTP boundary and visible failures.

Browser tests launch a temporary backend with real routes and SQLite. Only external vision and Hindsight transport are simulated; these tests are not evidence of live model accuracy.
