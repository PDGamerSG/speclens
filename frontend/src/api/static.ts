// Hosted demo: no backend and no keys. Replays a recorded live run from static files, so anyone can
// explore the app without spending Meta credits. Built with `npm run build:static`.

import type {
  Api,
  CallRecord,
  CreateRunBody,
  EvalReport,
  Health,
  Inspection,
  Ledger,
  Part,
  Run,
  RunEvent,
  RunListItem,
  StreamHandlers,
  StreamOptions,
  Taxonomy,
} from './types'

const DEMO = '/files/fixtures/demo_run'
const LOCAL_ONLY = 'This hosted demo replays a recorded run. Run the app locally with a Meta API key for this.'

interface Recording {
  run: Run
  events: { t: number; event: RunEvent['type']; data: unknown }[]
}

let recordingPromise: Promise<Recording> | null = null
const replays = new Map<string, Run>()
const calls: CallRecord[] = []
let nextId = 1

async function getJson<T>(path: string): Promise<T> {
  const res = await fetch(path)
  if (!res.ok) throw new Error(`${res.status}: could not load ${path}`)
  return (await res.json()) as T
}

function recording(): Promise<Recording> {
  recordingPromise ??= (async () => {
    const [run, text] = await Promise.all([
      getJson<Run>(`${DEMO}/run.json`),
      fetch(`${DEMO}/events.jsonl`).then((r) => r.text()),
    ])
    const events = text.split('\n').filter((l) => l.trim()).map((l) => JSON.parse(l))
    return { run: { ...run, demo: true }, events }
  })()
  return recordingPromise
}

function apply(run: Run, e: RunEvent) {
  switch (e.type) {
    case 'sample': {
      const i = run.samples.findIndex((s) => s.id === e.data.id)
      if (i >= 0) run.samples[i] = e.data
      else run.samples.push(e.data)
      break
    }
    case 'severity':
      run.severity.push(e.data)
      break
    case 'curves':
      run.curves = e.data.curves
      break
    case 'controls':
      run.controls = e.data
      break
    case 'run_completed':
      run.status = 'completed'
      run.summary = e.data.summary
      break
  }
}

function openRunEvents(id: string, handlers: StreamHandlers, opts: StreamOptions): () => void {
  let closed = false
  let timer: ReturnType<typeof setTimeout> | undefined

  const close = () => {
    if (closed) return
    closed = true
    clearTimeout(timer)
    handlers.onClose?.()
  }

  recording()
    .then(({ events }) => {
      const stressStart = events.findIndex((e) => e.event === 'stage' && (e.data as { stage?: string }).stage === 'stress')
      const list = opts.until === 'stress_completed' ? events.slice(Math.max(0, stressStart)) : events
      let i = 0
      const step = () => {
        if (closed) return
        if (i >= list.length) return close()
        const ev = list[i]
        i += 1
        let data = ev.data as Record<string, unknown>
        if (ev.event === 'call') {
          data = { ...data, run_id: id, status: 'replay' }
          calls.push(data as unknown as CallRecord)
        } else if (ev.event === 'sample') {
          data = { ...data, run_id: id }
        }
        const event = { type: ev.event, data } as RunEvent
        const run = replays.get(id)
        if (run) apply(run, event)
        handlers.onEvent(event)
        if (ev.event === opts.until) return close()
        const next = list[i]
        timer = setTimeout(step, next ? Math.min(700, Math.max(0, (next.t - ev.t) * 1000) / 6) : 0)
      }
      step()
    })
    .catch((e: unknown) => {
      handlers.onConnectionError?.(e instanceof Error ? e.message : 'Could not load the recording.')
      close()
    })

  return close
}

export const staticApi: Api = {
  mode: 'live',
  health: async () => {
    const health: Health = {
      ok: true,
      demo_mode: true,
      models: ['muse-spark-1.3', 'muse-image-1.0', 'sam-3.1'],
      spent_usd: calls.reduce((n, c) => n + c.cost_usd, 0),
      budget_usd: 0,
    }
    return health
  },
  ledger: async (limit = 200) => {
    const by_model: Ledger['by_model'] = {}
    for (const c of calls) {
      by_model[c.model] ??= { calls: 0, cost_usd: 0 }
      by_model[c.model].calls += 1
      by_model[c.model].cost_usd += c.cost_usd
    }
    return { calls: calls.slice(-limit), spent_usd: calls.reduce((n, c) => n + c.cost_usd, 0), by_model }
  },
  defaultSpec: async () => ({ spec_text: (await recording()).run.spec_text }),
  taxonomy: async (): Promise<Taxonomy> => (await recording()).run.taxonomy,
  parts: async () => {
    const parts: Part[] = [1, 2, 3, 4, 5].map((n) => ({
      id: `sample-hazelnut_gen_0${n}`,
      name: `hazelnut gen 0${n}`,
      url: `/files/fixtures/parts/hazelnut_gen_0${n}.jpg`,
      mask_url: null,
      width: 1024,
      height: 1024,
      source: 'sample',
    }))
    return { parts }
  },
  uploadParts: async () => {
    throw new Error(LOCAL_ONLY)
  },
  createRun: async (_body: CreateRunBody) => {
    const { run } = await recording()
    const run_id = `demo-${nextId}`
    nextId += 1
    replays.set(run_id, {
      ...run,
      id: run_id,
      created: Date.now() / 1000,
      status: 'running',
      samples: [],
      severity: [],
      curves: [],
      controls: null,
      summary: null,
    })
    return { run_id }
  },
  runs: async () => {
    const { run } = await recording()
    const item: RunListItem = {
      id: run.id,
      created: run.created,
      status: 'completed',
      per_type: run.per_type,
      accepted: run.samples.filter((s) => s.status === 'accepted').length,
      demo: true,
    }
    return { runs: [item] }
  },
  run: async (id) => {
    const replay = replays.get(id)
    return replay ? structuredClone(replay) : (await recording()).run
  },
  startStress: async () => ({ ok: true }),
  exportUrl: () => '/files/fixtures/demo_export.zip',
  inspect: async () => {
    const recorded = await getJson<Inspection>('/files/fixtures/demo_inspect/inspection.json')
    return { ...recorded, rationale: `Recorded demo result, not your photo. ${recorded.rationale}` }
  },
  evalReport: () => getJson<EvalReport>('/files/eval.json'),
  openRunEvents,
}
