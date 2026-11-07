// Real HTTP client for the FastAPI backend. Follows docs/api-contract.md exactly.
// The browser only ever talks to our backend (/api, /files). No Meta API calls, no keys.

import {
  RUN_EVENT_NAMES,
  type Api,
  type CreateRunBody,
  type EvalReport,
  type Health,
  type Inspection,
  type InspectOptions,
  type Ledger,
  type Part,
  type Run,
  type RunEvent,
  type RunListItem,
  type StreamHandlers,
  type StreamOptions,
  type Taxonomy,
} from './types'

export class ApiError extends Error {
  status: number
  constructor(status: number, message: string) {
    super(message)
    this.status = status
  }
}

async function readError(res: Response): Promise<string> {
  try {
    const body = await res.json()
    const d = body?.detail ?? body?.message ?? body
    if (typeof d === 'string') return d
    return JSON.stringify(d)
  } catch {
    return res.statusText || 'Request failed'
  }
}

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  let res: Response
  try {
    res = await fetch(path, init)
  } catch {
    throw new ApiError(0, 'Backend unreachable. Is the API running on :8765?')
  }
  if (!res.ok) throw new ApiError(res.status, `${res.status}: ${await readError(res)}`)
  return (await res.json()) as T
}

function postJson<T>(path: string, body: unknown): Promise<T> {
  return request<T>(path, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(body),
  })
}

function openRunEvents(id: string, handlers: StreamHandlers, opts: StreamOptions): () => void {
  const es = new EventSource(`/api/runs/${encodeURIComponent(id)}/events`)
  let closed = false
  let sawTerminal = false
  let failures = 0

  const close = () => {
    if (closed) return
    closed = true
    es.close()
    handlers.onClose?.()
  }

  for (const name of RUN_EVENT_NAMES) {
    es.addEventListener(name, (ev: Event) => {
      // The server's own `error` event shares its name with EventSource's native
      // connection error. Only a MessageEvent with data is the server's.
      if (!(ev instanceof MessageEvent) || typeof ev.data !== 'string' || ev.data === '') return
      let data: unknown
      try {
        data = JSON.parse(ev.data)
      } catch {
        return
      }
      failures = 0
      handlers.onEvent({ type: name, data } as RunEvent)
      if (name === 'run_completed' || name === 'stress_completed') sawTerminal = true
      if (name === opts.until) close()
    })
  }

  es.onerror = () => {
    if (closed) return
    // The server ends the stream after the terminal event; EventSource would then
    // reconnect and replay forever. If we already saw a terminal event, stop here.
    if (sawTerminal) return close()
    failures += 1
    if (es.readyState === EventSource.CLOSED || failures >= 6) {
      handlers.onConnectionError?.('Lost the live event stream for this run.')
      close()
    }
    // Otherwise EventSource reconnects by itself; the replay is idempotent (upserts).
  }

  return close
}

export const liveApi: Api = {
  mode: 'live',
  health: () => request<Health>('/api/health'),
  ledger: (limit = 200) => request<Ledger>(`/api/ledger?limit=${limit}`),
  defaultSpec: () => request<{ spec_text: string }>('/api/default-spec'),
  taxonomy: (spec_text) => postJson<Taxonomy>('/api/taxonomy', { spec_text }),
  parts: () => request<{ parts: Part[] }>('/api/parts'),
  uploadParts: (files) => {
    const fd = new FormData()
    for (const f of files) fd.append('files', f, f.name)
    return request<{ parts: Part[] }>('/api/parts', { method: 'POST', body: fd })
  },
  createRun: (body: CreateRunBody) => postJson<{ run_id: string }>('/api/runs', body),
  runs: () => request<{ runs: RunListItem[] }>('/api/runs'),
  run: (id) => request<Run>(`/api/runs/${encodeURIComponent(id)}`),
  startStress: (id) => postJson<{ ok: true }>(`/api/runs/${encodeURIComponent(id)}/stress`, {}),
  exportUrl: (id) => `/api/runs/${encodeURIComponent(id)}/export`,
  inspect: (file: Blob, opts: InspectOptions) => {
    const fd = new FormData()
    const name = file instanceof File ? file.name : 'capture.jpg'
    fd.append('file', file, name)
    if (opts.spec_text) fd.append('spec_text', opts.spec_text)
    if (opts.use_examples_run_id) fd.append('use_examples_run_id', opts.use_examples_run_id)
    return request<Inspection>('/api/inspect', { method: 'POST', body: fd })
  },
  evalReport: () => request<EvalReport>('/api/eval'),
  openRunEvents,
}
