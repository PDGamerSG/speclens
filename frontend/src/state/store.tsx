import { createContext, useCallback, useContext, useEffect, useMemo, useReducer, useRef, type ReactNode } from 'react'
import { api } from '../api'
import type {
  CallRecord,
  Health,
  Ledger,
  Part,
  Run,
  RunEvent,
  RunListItem,
  Sample,
  SeverityPoint,
  StageName,
  Taxonomy,
} from '../api/types'

export const PIPELINE: { stage: StageName; label: string; by: string }[] = [
  { stage: 'taxonomy', label: 'Taxonomy', by: 'Muse Spark' },
  { stage: 'locate', label: 'Locate', by: 'Spark + SAM' },
  { stage: 'forge', label: 'Forge', by: 'Muse Image' },
  { stage: 'composite', label: 'Composite', by: 'OpenCV' },
  { stage: 'label', label: 'Label', by: 'SAM 3.1' },
  { stage: 'critic', label: 'Critic', by: 'Muse Spark' },
  { stage: 'validate', label: 'Validate', by: '8 checks' },
  { stage: 'stress', label: 'Stress', by: 'Muse Spark' },
]

export interface StageState {
  active: string[]
  done: string[]
  detail?: string
}
export type StageStatus = 'idle' | 'active' | 'done'

export function stageStatus(st?: StageState): StageStatus {
  if (!st) return 'idle'
  if (st.active.length) return 'active'
  if (st.done.length) return 'done'
  return 'idle'
}

export const SEVERITY_VARIANTS = 7 // opacity 1.0/0.5/0.25/0.12 + size 0.6/0.35/0.2

interface State {
  health: Health | null
  healthError: string | null
  specText: string
  defaultSpec: string
  taxonomy: Taxonomy | null
  taxonomyBusy: boolean
  taxonomyError: string | null
  excluded: string[]
  parts: Part[]
  partsLoaded: boolean
  partsError: string | null
  uploading: boolean
  selected: string[]
  perType: number
  stress: boolean
  run: Run | null
  totalSamples: number | null
  stages: Partial<Record<StageName, StageState>>
  streaming: 'idle' | 'run' | 'stress'
  starting: boolean
  runError: string | null
  runStartedAt: number | null
  runs: RunListItem[]
  ledger: Ledger | null
  liveCalls: CallRecord[]
  lastCallAt: number
}

const initial: State = {
  health: null,
  healthError: null,
  specText: '',
  defaultSpec: '',
  taxonomy: null,
  taxonomyBusy: false,
  taxonomyError: null,
  excluded: [],
  parts: [],
  partsLoaded: false,
  partsError: null,
  uploading: false,
  selected: [],
  perType: 4,
  stress: true,
  run: null,
  totalSamples: null,
  stages: {},
  streaming: 'idle',
  starting: false,
  runError: null,
  runStartedAt: null,
  runs: [],
  ledger: null,
  liveCalls: [],
  lastCallAt: 0,
}

type Action =
  | { type: 'patch'; patch: Partial<State> }
  | { type: 'events'; events: RunEvent[] }
  | { type: 'parts'; parts: Part[]; selectNew?: boolean }
  | { type: 'runLoaded'; run: Run; authoritative: boolean }
  | { type: 'togglePart'; id: string }
  | { type: 'toggleType'; t: string }

export function callKey(c: CallRecord) {
  return `${c.t}|${c.model}|${c.op}|${c.ms}`
}

const sevKey = (p: SeverityPoint) => `${p.sample_id}|${p.kind}|${p.level}`

function stagesFromRun(run: Run): Partial<Record<StageName, StageState>> {
  const ids = run.samples.map((s) => s.id)
  const st: Partial<Record<StageName, StageState>> = {}
  const finished = run.status !== 'running'
  if (!finished && !ids.length) return st
  for (const p of PIPELINE) {
    if (p.stage === 'stress') continue
    st[p.stage] = { active: [], done: p.stage === 'taxonomy' || p.stage === 'locate' ? ['_run'] : ids }
  }
  if (run.curves.length || run.severity.length) st.stress = { active: [], done: ['_run'] }
  return st
}

function mergeRun(cur: Run | null, next: Run, authoritative: boolean): Run {
  if (!cur || cur.id !== next.id) return next
  if (authoritative) {
    // keep on-screen order stable: existing samples first, new ones after
    const pos = new Map(cur.samples.map((s, i) => [s.id, i]))
    const samples = next.samples.slice().sort((a, b) => (pos.get(a.id) ?? 1e9) - (pos.get(b.id) ?? 1e9))
    return { ...next, samples }
  }
  // live stream wins over a snapshot that may be older
  const byId = new Map(next.samples.map((s) => [s.id, s]))
  for (const s of cur.samples) byId.set(s.id, s)
  const order = [...cur.samples.map((s) => s.id), ...next.samples.map((s) => s.id).filter((id) => !cur.samples.some((s) => s.id === id))]
  const sev = new Map(next.severity.map((p) => [sevKey(p), p]))
  for (const p of cur.severity) sev.set(sevKey(p), p)
  return {
    ...next,
    status: cur.status === 'completed' ? cur.status : next.status,
    samples: order.map((id) => byId.get(id)!).filter(Boolean),
    severity: [...sev.values()],
    curves: cur.curves.length ? cur.curves : next.curves,
    summary: cur.summary ?? next.summary,
  }
}

function applyEvents(s: State, events: RunEvent[]): State {
  let run = s.run ? { ...s.run, samples: s.run.samples.slice(), severity: s.run.severity.slice() } : null
  const stages = { ...s.stages }
  let liveCalls = s.liveCalls
  let { totalSamples, runError, lastCallAt } = s
  for (const e of events) {
    switch (e.type) {
      case 'run_started':
        totalSamples = e.data.total_samples
        break
      case 'stage': {
        const { stage, status, sample_id, detail } = e.data
        const key = sample_id ?? '_run'
        const prev = stages[stage] ?? { active: [], done: [] }
        const next: StageState = { active: prev.active.slice(), done: prev.done.slice(), detail: detail ?? prev.detail }
        if (status === 'start') {
          if (!next.active.includes(key)) next.active.push(key)
        } else {
          next.active = next.active.filter((k) => k !== key)
          if (!next.done.includes(key)) next.done.push(key)
        }
        stages[stage] = next
        break
      }
      case 'call':
        liveCalls = [...liveCalls, e.data].slice(-600)
        lastCallAt = Date.now()
        break
      case 'sample': {
        if (!run) break
        const i = run.samples.findIndex((x) => x.id === e.data.id)
        if (i >= 0) run.samples[i] = e.data as Sample
        else run.samples.push(e.data)
        if (e.data.status !== 'forging') {
          // a finished sample has been through every per-sample stage, so count it in the timeline
          for (const { stage } of PIPELINE) {
            if (stage === 'taxonomy' || stage === 'locate' || stage === 'stress') continue
            const prev = stages[stage] ?? { active: [], done: [] }
            stages[stage] = {
              ...prev,
              active: prev.active.filter((k) => k !== e.data.id),
              done: prev.done.includes(e.data.id) ? prev.done : [...prev.done, e.data.id],
            }
          }
        }
        break
      }
      case 'severity': {
        if (!run) break
        const k = sevKey(e.data)
        const i = run.severity.findIndex((p) => sevKey(p) === k)
        if (i >= 0) run.severity[i] = e.data
        else run.severity.push(e.data)
        break
      }
      case 'controls':
        if (run) run.controls = e.data
        break
      case 'curves':
      case 'stress_completed':
        if (run) run.curves = e.data.curves
        if (e.type === 'stress_completed') {
          const st = stages.stress ?? { active: [], done: [] }
          stages.stress = { ...st, active: [], done: st.done.length ? st.done : ['_run'] }
        }
        break
      case 'run_completed':
        if (run) run = { ...run, status: 'completed', summary: e.data.summary }
        break
      case 'error':
        runError = e.data.message
        break
    }
  }
  return { ...s, run, stages, liveCalls, totalSamples, runError, lastCallAt }
}

function reducer(s: State, a: Action): State {
  switch (a.type) {
    case 'patch':
      return { ...s, ...a.patch }
    case 'events':
      return applyEvents(s, a.events)
    case 'parts': {
      const byId = new Map(s.parts.map((p) => [p.id, p]))
      const fresh: string[] = []
      for (const p of a.parts) {
        if (!byId.has(p.id)) fresh.push(p.id)
        byId.set(p.id, p)
      }
      const parts = [...byId.values()]
      let selected = s.selected.filter((id) => byId.has(id))
      if (a.selectNew) selected = [...new Set([...selected, ...fresh])]
      else if (!s.partsLoaded && !selected.length) selected = parts.slice(0, 4).map((p) => p.id)
      return { ...s, parts, selected, partsLoaded: true, partsError: null }
    }
    case 'runLoaded': {
      const run = mergeRun(s.run, a.run, a.authoritative)
      const sameRun = s.run?.id === a.run.id
      return {
        ...s,
        run,
        stages: sameRun && s.streaming !== 'idle' ? s.stages : sameRun && Object.keys(s.stages).length ? { ...stagesFromRun(run), ...s.stages } : stagesFromRun(run),
        totalSamples: sameRun ? s.totalSamples ?? (run.per_type * run.taxonomy.defects.length || null) : run.per_type * run.taxonomy.defects.length || null,
      }
    }
    case 'togglePart':
      return { ...s, selected: s.selected.includes(a.id) ? s.selected.filter((x) => x !== a.id) : [...s.selected, a.id] }
    case 'toggleType':
      return { ...s, excluded: s.excluded.includes(a.t) ? s.excluded.filter((x) => x !== a.t) : [...s.excluded, a.t] }
  }
}

function errMsg(e: unknown) {
  return e instanceof Error ? e.message : String(e)
}

interface Actions {
  setSpec(text: string): void
  resetSpec(): void
  readSpec(): Promise<Taxonomy | null>
  toggleType(t: string): void
  togglePart(id: string): void
  setSelected(ids: string[]): void
  uploadParts(files: File[]): Promise<void>
  setPerType(n: number): void
  setStress(b: boolean): void
  forge(): Promise<void>
  loadRun(id: string): Promise<void>
  startStress(): Promise<void>
  refreshRuns(): Promise<void>
}

const Ctx = createContext<{ state: State; actions: Actions } | null>(null)

export function StoreProvider({ children }: { children: ReactNode }) {
  const [state, dispatch] = useReducer(reducer, initial)
  const stateRef = useRef(state)
  stateRef.current = state
  const closeStream = useRef<(() => void) | null>(null)
  const buffer = useRef<RunEvent[]>([])
  const raf = useRef<number | null>(null)

  const flush = useCallback(() => {
    raf.current = null
    const events = buffer.current
    buffer.current = []
    if (events.length) dispatch({ type: 'events', events })
  }, [])

  const push = useCallback(
    (e: RunEvent) => {
      buffer.current.push(e)
      if (raf.current == null) raf.current = requestAnimationFrame(flush)
    },
    [flush],
  )

  const refreshRuns = useCallback(async () => {
    try {
      const { runs } = await api.runs()
      dispatch({ type: 'patch', patch: { runs: runs.slice().sort((a, b) => b.created - a.created) } })
    } catch {
      /* the header shows backend health */
    }
  }, [])

  const openStream = useCallback(
    (id: string, mode: 'run' | 'stress') => {
      closeStream.current?.()
      dispatch({ type: 'patch', patch: { streaming: mode, runError: null } })
      closeStream.current = api.openRunEvents(
        id,
        {
          onEvent: push,
          onConnectionError: (message) => dispatch({ type: 'patch', patch: { runError: message } }),
          onClose: () => {
            flush()
            closeStream.current = null
            dispatch({ type: 'patch', patch: { streaming: 'idle' } })
            api
              .run(id)
              .then((run) => dispatch({ type: 'runLoaded', run, authoritative: true }))
              .catch(() => undefined)
            void refreshRuns()
          },
        },
        { until: mode === 'run' ? 'run_completed' : 'stress_completed' },
      )
    },
    [flush, push, refreshRuns],
  )

  const loadRun = useCallback(
    async (id: string) => {
      try {
        const run = await api.run(id)
        if (stateRef.current.run?.id !== id) {
          closeStream.current?.()
          dispatch({ type: 'patch', patch: { stages: {}, totalSamples: null, runError: null, runStartedAt: run.status === 'running' ? run.created * 1000 : null } })
        }
        dispatch({ type: 'runLoaded', run, authoritative: true })
        if (run.status === 'running' && stateRef.current.streaming === 'idle') openStream(id, 'run')
      } catch (e) {
        dispatch({ type: 'patch', patch: { runError: errMsg(e) } })
      }
    },
    [openStream],
  )

  // boot
  useEffect(() => {
    let alive = true
    const health = () =>
      api
        .health()
        .then((h) => alive && dispatch({ type: 'patch', patch: { health: h, healthError: null } }))
        .catch((e) => alive && dispatch({ type: 'patch', patch: { healthError: errMsg(e) } }))
    void health()
    const hTimer = setInterval(health, 10_000)
    api
      .defaultSpec()
      .then(({ spec_text }) => {
        if (!alive) return
        dispatch({ type: 'patch', patch: { defaultSpec: spec_text, specText: stateRef.current.specText || spec_text } })
      })
      .catch(() => undefined)
    api
      .parts()
      .then(({ parts }) => alive && dispatch({ type: 'parts', parts }))
      .catch((e) => alive && dispatch({ type: 'patch', patch: { partsError: errMsg(e), partsLoaded: true } }))
    api
      .runs()
      .then(({ runs }) => {
        if (!alive) return
        const sorted = runs.slice().sort((a, b) => b.created - a.created)
        dispatch({ type: 'patch', patch: { runs: sorted } })
        if (sorted[0] && !stateRef.current.run) void loadRun(sorted[0].id)
      })
      .catch(() => undefined)
    return () => {
      alive = false
      clearInterval(hTimer)
    }
  }, [loadRun])

  // call ledger: poll every 3 s (SSE `call` events fill the gaps in between)
  useEffect(() => {
    let alive = true
    const poll = () =>
      api
        .ledger(200)
        .then((ledger) => alive && dispatch({ type: 'patch', patch: { ledger } }))
        .catch(() => undefined)
    void poll()
    const t = setInterval(poll, 3000)
    return () => {
      alive = false
      clearInterval(t)
    }
  }, [])

  useEffect(() => () => closeStream.current?.(), [])

  const readSpec = useCallback(async () => {
    dispatch({ type: 'patch', patch: { taxonomyBusy: true, taxonomyError: null } })
    try {
      const taxonomy = await api.taxonomy(stateRef.current.specText)
      dispatch({ type: 'patch', patch: { taxonomy, taxonomyBusy: false, excluded: [] } })
      return taxonomy
    } catch (e) {
      dispatch({ type: 'patch', patch: { taxonomyBusy: false, taxonomyError: errMsg(e) } })
      return null
    }
  }, [])

  const forge = useCallback(async () => {
    const s = stateRef.current
    if (s.starting || s.streaming !== 'idle') return
    dispatch({ type: 'patch', patch: { starting: true, runError: null } })
    try {
      const taxonomy = s.taxonomy ?? (await readSpec())
      if (!taxonomy) throw new Error('Read the spec first: the taxonomy could not be built.')
      const cur = stateRef.current
      const tax: Taxonomy = { ...taxonomy, defects: taxonomy.defects.filter((d) => !cur.excluded.includes(d.defect_type)) }
      if (!tax.defects.length) throw new Error('Include at least one defect type.')
      if (!cur.selected.length) throw new Error('Select at least one good part.')
      const body = { spec_text: cur.specText, taxonomy: tax, part_ids: cur.selected, per_type: cur.perType, stress: cur.stress }
      const { run_id } = await api.createRun(body)
      const skeleton: Run = {
        id: run_id,
        created: Date.now() / 1000,
        status: 'running',
        spec_text: body.spec_text,
        taxonomy: tax,
        part_ids: body.part_ids,
        per_type: body.per_type,
        samples: [],
        severity: [],
        curves: [],
        summary: null,
        demo: cur.health?.demo_mode ?? false,
      }
      closeStream.current?.()
      dispatch({
        type: 'patch',
        patch: { run: skeleton, stages: {}, totalSamples: tax.defects.length * body.per_type, starting: false, runStartedAt: Date.now() },
      })
      openStream(run_id, 'run')
      void refreshRuns()
      api
        .run(run_id)
        .then((run) => dispatch({ type: 'runLoaded', run, authoritative: false }))
        .catch(() => undefined)
    } catch (e) {
      dispatch({ type: 'patch', patch: { starting: false, runError: errMsg(e) } })
    }
  }, [openStream, readSpec, refreshRuns])

  const startStress = useCallback(async () => {
    const s = stateRef.current
    if (!s.run || s.streaming !== 'idle') return
    const id = s.run.id
    dispatch({ type: 'patch', patch: { runError: null } })
    try {
      await api.startStress(id)
      dispatch({
        type: 'patch',
        patch: {
          run: { ...s.run, severity: [], curves: [], controls: null },
          stages: { ...s.stages, stress: { active: ['_run'], done: [] } },
        },
      })
      openStream(id, 'stress')
    } catch (e) {
      dispatch({ type: 'patch', patch: { runError: errMsg(e) } })
    }
  }, [openStream])

  const uploadParts = useCallback(async (files: File[]) => {
    if (!files.length) return
    dispatch({ type: 'patch', patch: { uploading: true, partsError: null } })
    try {
      const { parts } = await api.uploadParts(files.slice(0, 10))
      dispatch({ type: 'parts', parts, selectNew: true })
    } catch (e) {
      dispatch({ type: 'patch', patch: { partsError: errMsg(e) } })
    } finally {
      dispatch({ type: 'patch', patch: { uploading: false } })
    }
  }, [])

  const actions = useMemo<Actions>(
    () => ({
      setSpec: (text) => dispatch({ type: 'patch', patch: { specText: text } }),
      resetSpec: () => dispatch({ type: 'patch', patch: { specText: stateRef.current.defaultSpec } }),
      readSpec,
      toggleType: (t) => dispatch({ type: 'toggleType', t }),
      togglePart: (id) => dispatch({ type: 'togglePart', id }),
      setSelected: (ids) => dispatch({ type: 'patch', patch: { selected: ids } }),
      uploadParts,
      setPerType: (n) => dispatch({ type: 'patch', patch: { perType: Math.max(1, Math.min(12, n)) } }),
      setStress: (b) => dispatch({ type: 'patch', patch: { stress: b } }),
      forge,
      loadRun,
      startStress,
      refreshRuns,
    }),
    [forge, loadRun, readSpec, refreshRuns, startStress, uploadParts],
  )

  return <Ctx.Provider value={{ state, actions }}>{children}</Ctx.Provider>
}

export function useStore() {
  const v = useContext(Ctx)
  if (!v) throw new Error('useStore outside StoreProvider')
  return v
}

/** Ledger rows from polling plus SSE `call` events not yet in the poll. */
export function useCalls() {
  const { state } = useStore()
  return useMemo(() => {
    const polled = state.ledger?.calls ?? []
    const keys = new Set(polled.map(callKey))
    const minT = polled.length ? Math.min(...polled.map((c) => c.t)) : 0
    const extras = state.liveCalls.filter((c) => !keys.has(callKey(c)) && c.t >= minT)
    const seen = new Set<string>()
    const all = [...polled, ...extras].filter((c) => {
      const k = callKey(c)
      if (seen.has(k)) return false
      seen.add(k)
      return true
    })
    all.sort((a, b) => b.t - a.t)
    const byModel: Record<string, { calls: number; cost_usd: number }> = {}
    for (const [m, v] of Object.entries(state.ledger?.by_model ?? {})) byModel[m] = { ...v }
    let spent = state.ledger?.spent_usd ?? state.health?.spent_usd ?? 0
    for (const c of extras) {
      const b = (byModel[c.model] ??= { calls: 0, cost_usd: 0 })
      b.calls += 1
      b.cost_usd += c.cost_usd
      spent += c.cost_usd
    }
    const total = Object.values(byModel).reduce((a, v) => a + v.calls, 0) || all.length
    return { calls: all, byModel, spent, total, budget: state.health?.budget_usd ?? null }
  }, [state.ledger, state.liveCalls, state.health])
}

export function isDemo(state: State) {
  return Boolean(state.health?.demo_mode || state.run?.demo)
}
