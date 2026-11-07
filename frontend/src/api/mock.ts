// Mock backend, enabled with VITE_MOCK=1. Fakes every endpoint and the SSE stream
// with realistic timing, using procedural canvas art (no real photos).
// VITE_MOCK_DEMO=1 additionally reports demo_mode: true (shows the DEMO REPLAY badge).

import * as art from './mockArt'
import type {
  Api,
  CallRecord,
  Curve,
  CurveCell,
  EvalReport,
  Inspection,
  Part,
  Run,
  RunEvent,
  Sample,
  SeverityKind,
  SeverityPoint,
  StageEvent,
  StageName,
  StreamHandlers,
  StreamOptions,
  Taxonomy,
  TaxonomyItem,
  Validator,
} from './types'

const DEMO = import.meta.env.VITE_MOCK_DEMO === '1'
const SPEED = Number(import.meta.env.VITE_MOCK_SPEED || 1) || 1

const sleep = (ms: number) => new Promise((r) => setTimeout(r, ms / SPEED))
const now = () => Date.now() / 1000
const rand = art.rng(20261104)
const between = (a: number, b: number) => a + rand() * (b - a)
const clone = <T,>(v: T): T => JSON.parse(JSON.stringify(v)) as T

const MODELS = { image: 'muse-image-1.0', sam: 'sam-3.1', spark: 'muse-spark-1.3' }

// ------------------------------------------------------------------ spec + taxonomy

const DEFAULT_SPEC = `HAZELNUT VISUAL QA SPECIFICATION  HZ-QA-07 rev C
Part: whole in-shell hazelnut, nominal width 20 mm, inspected top-down on a dark conveyor by a camera inspector.

3. ACCEPTABLE (do not reject)
3.1 Natural shell colour variation, longitudinal stripes and gloss.
3.2 The rough, fuzzy cap (hilum) area and its natural boundary.
3.3 Small natural specks, dust shadows and lighting gradients.

4. REJECT
4.1 Hole: any drilled, bored or insect hole through the shell, any diameter. Typically 0.5-2 mm, dark inside, with a rough or torn rim.
4.2 Crack: any fracture of the shell, from a thin hairline split to a broken-away piece exposing the kernel.
4.3 Cut: any knife cut, slice or notch in the shell surface, usually straight-edged and 2-8 mm long, showing paler material inside.
4.4 Print: any ink, stamp, printed characters or marking on the shell, any size or colour.

5. Inspection must catch every reject class above at the smallest size listed.`

const TAXONOMY_ITEMS: TaxonomyItem[] = [
  {
    defect_type: 'hole',
    clause: '4.1',
    description: 'a tiny round black hole about one-fortieth to one-tenth of the part width with a rough torn light brown rim and matte dark interior',
    severity_note: 'any drilled, bored or insect hole through the shell, any diameter, typically 0.5-2 mm',
  },
  {
    defect_type: 'crack',
    clause: '4.2',
    description: 'a jagged dark brown hairline split about one-quarter to one-half of the part width with rough light tan edges',
    severity_note: 'any fracture of the shell, from a thin hairline split to a broken-away piece exposing the kernel',
  },
  {
    defect_type: 'cut',
    clause: '4.3',
    description: 'a straight-edged pale tan slice about one-tenth to two-fifths of the part width with smooth clean sides',
    severity_note: 'any knife cut, slice or notch in the shell surface, usually straight-edged and 2-8 mm long',
  },
  {
    defect_type: 'print',
    clause: '4.4',
    description: 'small crisp printed characters in pale ink about one-tenth of the part width on the brown shell surface',
    severity_note: 'any ink, stamp, printed characters or marking on the shell, any size or colour',
  },
]

// ------------------------------------------------------------------ ledger

const ledgerCalls: CallRecord[] = []
let spent = 0.0786

function record(model: string, op: string, ms: number, cost: number, runId: string | null, status: number | string = 200): CallRecord {
  const c: CallRecord = { t: now(), model, op, ms: Math.round(ms), status, cost_usd: cost, run_id: runId }
  if (model === MODELS.spark && rand() < 0.6) c.cached_tokens = Math.round(between(400, 1800))
  ledgerCalls.push(c)
  spent += cost
  return c
}

// ------------------------------------------------------------------ parts

const nuts = new Map<string, art.NutSpec>()
let parts: Part[] | null = null

function ensureParts(): Part[] {
  if (parts) return parts
  parts = []
  for (let i = 0; i < 6; i++) {
    const n = art.makeNut(101 + i * 37)
    const id = `mock-nut-${String(i).padStart(3, '0')}`
    nuts.set(id, n)
    parts.push({
      id,
      name: `Sample hazelnut ${String(i + 1).padStart(2, '0')}`,
      url: art.nutImage(n),
      mask_url: i < 4 ? art.nutMask(n) : null,
      width: art.FULL,
      height: art.FULL,
      source: 'sample',
    })
  }
  return parts
}

async function imageSize(file: File): Promise<[number, number]> {
  try {
    const bmp = await createImageBitmap(file)
    const s: [number, number] = [bmp.width, bmp.height]
    bmp.close()
    return s
  } catch {
    return [1024, 1024]
  }
}

// ------------------------------------------------------------------ runs + stream

interface MockRun {
  run: Run
  events: RunEvent[]
  listeners: Set<(e: RunEvent) => void>
  busy: boolean
  forged: Map<string, { nut: art.NutSpec; defect: art.DefectSpec }>
}

const runs = new Map<string, MockRun>()

function emit(m: MockRun, ev: RunEvent) {
  m.events.push(ev)
  for (const l of m.listeners) l(ev)
}

function call(m: MockRun, model: string, op: string, ms: number, cost: number, status: number | string = 200) {
  emit(m, { type: 'call', data: record(model, op, ms, cost, m.run.id, status) })
  return cost
}

function stage(m: MockRun, s: StageName, status: 'start' | 'done', sample_id?: string, detail?: string) {
  const data: StageEvent = { stage: s, status }
  if (sample_id) data.sample_id = sample_id
  if (detail) data.detail = detail
  emit(m, { type: 'stage', data })
}

function upsertSample(m: MockRun, s: Sample) {
  const i = m.run.samples.findIndex((x) => x.id === s.id)
  if (i >= 0) m.run.samples[i] = s
  else m.run.samples.push(s)
  emit(m, { type: 'sample', data: clone(s) })
}

const VALIDATOR_NAMES: [string, string][] = [
  ['V1', 'Pixels outside the defect are byte-identical'],
  ['V2', 'Defect lies on the part'],
  ['V3', 'Defect size is plausible'],
  ['V4', 'SAM 3.1 agrees with the diff mask'],
  ['V5', 'Edit stayed local'],
  ['V6', 'Muse Spark critic accepts realism'],
  ['V7', 'Not a near-duplicate'],
  ['V8', 'Provenance complete'],
]

function validators(iou: number, area: number, realism: number): Validator[] {
  const pct = ((area / (art.CROP * art.CROP)) * 100).toFixed(2)
  const details = [
    'every pixel with alpha 0 equals the original',
    '100% of defect pixels inside the part mask',
    `${pct}% of the crop`,
    `IoU ${iou.toFixed(2)}${iou < 0.5 ? ' (thin defect: lower bar)' : ''}`,
    `${1 + Math.floor(rand() * 3)} region(s); ${(Number(pct) * 1.3).toFixed(1)}% of crop changed before masking`,
    `realism ${realism}/5, type matches`,
    `min dHash distance ${Math.round(between(22, 44))}`,
    'all fields present',
  ]
  return VALIDATOR_NAMES.map(([id, name], i) => ({ id, name, passed: true, detail: details[i] }))
}

const ARTIFACT_NOTES = [
  'none visible; rim, lighting and shell texture are consistent',
  'edges slightly soft but consistent with the focus of the shot',
  'none visible; matches the surrounding striations',
]
const REJECT_NOTES = [
  'defect reads as a smudge rather than a hole; interior not dark enough',
  'the split looks painted on; no depth along the edges',
  'characters are blurred into a stain; not legible as print',
]

async function forgeSample(m: MockRun, idx: number, item: TaxonomyItem, part: Part, allowFail: boolean) {
  const nut = nuts.get(part.id) ?? art.makeNut(idx * 11 + 5)
  const id = `s${String(idx + 1).padStart(3, '0')}`
  const t0 = performance.now()
  let defect = art.placeDefect(nut, item.defect_type, 1000 + idx * 17)
  let prompt = `Edit this close-up photo of a ${m.run.taxonomy.part_name}. Add ${item.description} exactly at the center of the image. Keep the same lighting, focus, texture and camera angle. Do not change anything else in the photo.`
  let cost = 0
  const s: Sample = {
    id,
    run_id: m.run.id,
    part_id: part.id,
    defect_type: item.defect_type,
    status: 'forging',
    attempt: 1,
    prompt,
    original_url: part.url,
    crop_original_url: art.cropOriginalOnly(nut, defect),
    crop_raw_url: null,
    crop_composite_url: null,
    composite_url: null,
    mask_url: null,
    overlay_url: null,
    bbox: null,
    area_px: 0,
    size_mm: null,
    sam_iou: null,
    critic: null,
    validators: [],
    cost_usd: 0,
    ms: 0,
  }
  upsertSample(m, s)

  for (let attempt = 1; attempt <= 3; attempt++) {
    s.attempt = attempt
    stage(m, 'forge', 'start', id)
    await sleep(between(1600, 3200))
    if (allowFail && attempt === 1 && rand() < 0.06) {
      cost += call(m, MODELS.image, 'edit', between(30000, 60000), 0, 500)
      stage(m, 'forge', 'done', id, 'Muse Image returned 500 three times')
      Object.assign(s, { status: 'failed', cost_usd: cost, ms: Math.round(performance.now() - t0) * SPEED })
      upsertSample(m, s)
      return
    }
    cost += call(m, MODELS.image, 'edit', between(9800, 13500), 0.01)
    stage(m, 'forge', 'done', id)

    stage(m, 'composite', 'start', id)
    const img = art.forge(nut, defect)
    await sleep(220)
    Object.assign(s, { crop_raw_url: img.cropRaw, crop_composite_url: img.cropComposite, composite_url: img.composite })
    upsertSample(m, s)
    stage(m, 'composite', 'done', id, 'aligned, colour-matched, changed pixels composited')

    stage(m, 'label', 'start', id)
    await sleep(between(400, 800))
    const thin = item.defect_type === 'crack' || item.defect_type === 'cut'
    const iou = Number((thin ? between(0.32, 0.66) : between(0.82, 0.93)).toFixed(3))
    cost += call(m, MODELS.sam, 'segment', between(1900, 3100), 0.0025)
    Object.assign(s, {
      mask_url: img.mask,
      overlay_url: img.overlay,
      bbox: img.bbox,
      area_px: img.area,
      size_mm: Number(img.sizeMm.toFixed(2)),
      sam_iou: iou,
    })
    upsertSample(m, s)
    stage(m, 'label', 'done', id)

    stage(m, 'critic', 'start', id)
    await sleep(between(700, 1300))
    cost += call(m, MODELS.spark, 'critic', between(4800, 7900), between(0.0022, 0.0039))
    const accept = rand() < (attempt === 1 ? 0.8 : 0.85)
    const realism = accept ? (rand() < 0.6 ? 5 : 4) : rand() < 0.5 ? 2 : 3
    s.critic = {
      realism,
      matches_type: accept || rand() < 0.4,
      artifacts: accept ? ARTIFACT_NOTES[Math.floor(rand() * ARTIFACT_NOTES.length)] : REJECT_NOTES[Math.floor(rand() * REJECT_NOTES.length)],
      verdict: accept ? 'accept' : 'reject',
      revised_prompt: accept ? '' : `${prompt.replace('Edit this close-up photo', 'Edit this sharp close-up photo')} Make it clearly visible with real depth.`,
    }
    stage(m, 'critic', 'done', id, accept ? 'accept' : 'reject')

    if (!accept) {
      if (attempt === 3) {
        Object.assign(s, { status: 'rejected', cost_usd: cost, ms: Math.round((performance.now() - t0) * SPEED) })
        upsertSample(m, s)
        return
      }
      prompt = s.critic.revised_prompt
      defect = art.placeDefect(nut, item.defect_type, 1000 + idx * 17 + attempt * 101)
      Object.assign(s, { prompt, attempt: attempt + 1, cost_usd: cost })
      upsertSample(m, s)
      continue
    }

    stage(m, 'validate', 'start', id)
    await sleep(200)
    s.validators = validators(iou, img.area, realism)
    stage(m, 'validate', 'done', id, '8/8 passed')
    Object.assign(s, { status: 'accepted', cost_usd: cost, ms: Math.round((performance.now() - t0) * SPEED) })
    m.forged.set(id, { nut, defect })
    upsertSample(m, s)
    return
  }
}

// Detection rates per cell, shaped like the gate-test T6 ladder (docs/gate-results.md).
const RATES: Record<string, Record<SeverityKind, Record<string, number>>> = {
  hole: { opacity: { '1': 1, '0.5': 1, '0.25': 0.6, '0.12': 0.05 }, size: { '0.6': 1, '0.35': 0.95, '0.2': 0.55 } },
  crack: { opacity: { '1': 1, '0.5': 1, '0.25': 0.95, '0.12': 0.2 }, size: { '0.6': 1, '0.35': 0.9, '0.2': 0.2 } },
  print: { opacity: { '1': 1, '0.5': 1, '0.25': 0.8, '0.12': 0.6 }, size: { '0.6': 0.9, '0.35': 0.9, '0.2': 0.6 } },
  cut: { opacity: { '1': 1, '0.5': 0.95, '0.25': 0.7, '0.12': 0.2 }, size: { '0.6': 1, '0.35': 0.8, '0.2': 0.35 } },
}
const LADDER: [SeverityKind, number][] = [
  ['opacity', 1],
  ['opacity', 0.5],
  ['opacity', 0.25],
  ['opacity', 0.12],
  ['size', 0.6],
  ['size', 0.35],
  ['size', 0.2],
]

function wilson(k: number, n: number): [number, number] {
  if (n === 0) return [0, 1]
  const z = 1.96
  const p = k / n
  const d = 1 + (z * z) / n
  const c = (p + (z * z) / (2 * n)) / d
  const h = (z * Math.sqrt((p * (1 - p)) / n + (z * z) / (4 * n * n))) / d
  return [Math.max(0, c - h), Math.min(1, c + h)]
}

export function computeCurves(points: SeverityPoint[]): Curve[] {
  const types = [...new Set(points.map((p) => p.defect_type))]
  return types.map((t) => {
    const cells: CurveCell[] = []
    for (const [kind, level] of LADDER) {
      const ps = points.filter((p) => p.defect_type === t && p.kind === kind && p.level === level)
      if (!ps.length) continue
      const det = ps.filter((p) => p.detected).length
      const [lo, hi] = wilson(det, ps.length)
      const sizes = ps.map((p) => p.size_mm).filter((x): x is number => x != null)
      cells.push({
        kind,
        level,
        n: ps.length,
        detected: det,
        rate: det / ps.length,
        ci_low: Number(lo.toFixed(3)),
        ci_high: Number(hi.toFixed(3)),
        mean_size_mm: sizes.length ? Number((sizes.reduce((a, b) => a + b, 0) / sizes.length).toFixed(2)) : null,
      })
    }
    const op = cells.filter((c) => c.kind === 'opacity')
    const breakAt = op.findIndex((c) => c.rate < 0.8)
    const note =
      breakAt > 0 ? `detection breaks below ${op[breakAt - 1].level} opacity` : breakAt === 0 ? 'missed even at full opacity' : 'detected at every opacity tested'
    return { defect_type: t, cells, threshold_note: note }
  })
}

async function stress(m: MockRun) {
  stage(m, 'stress', 'start', undefined, 'severity ladder: opacity 1.0/0.5/0.25/0.12, size 0.6/0.35/0.2')
  const accepted = m.run.samples.filter((s) => s.status === 'accepted')
  const queue = accepted.slice()
  const worker = async () => {
    for (;;) {
      const s = queue.shift()
      if (!s) return
      const f = m.forged.get(s.id)
      if (!f) continue
      for (const [kind, level] of LADDER) {
        await sleep(between(140, 320))
        call(m, MODELS.spark, 'inspect', between(4600, 6800), between(0.0018, 0.0026))
        const rate = RATES[s.defect_type]?.[kind]?.[String(level)] ?? 0.7
        const detected = rand() < rate
        const p: SeverityPoint = {
          sample_id: s.id,
          defect_type: s.defect_type,
          kind,
          level,
          url: art.severityVariant(f.nut, f.defect, kind, level),
          size_mm: s.size_mm == null ? null : Number((kind === 'size' ? s.size_mm * level : s.size_mm).toFixed(2)),
          detected,
          pred_type: detected ? (rand() < 0.94 ? s.defect_type : 'crack') : 'none',
          confidence: Number((detected ? between(0.62, 0.97) : between(0.55, 0.9)).toFixed(2)),
        }
        m.run.severity.push(p)
        emit(m, { type: 'severity', data: p })
      }
      m.run.curves = computeCurves(m.run.severity)
      emit(m, { type: 'curves', data: { curves: clone(m.run.curves) } })
    }
  }
  await Promise.all([worker(), worker(), worker()])
  m.run.curves = computeCurves(m.run.severity)
  emit(m, { type: 'curves', data: { curves: clone(m.run.curves) } })
  stage(m, 'stress', 'done', undefined, `${m.run.severity.length} variants inspected`)
}

async function pipeline(m: MockRun, stressAfter: boolean) {
  const t0 = performance.now()
  const run = m.run
  const items = run.taxonomy.defects
  const selected = ensureParts().filter((p) => run.part_ids.includes(p.id))
  const usable = selected.length ? selected : ensureParts().slice(0, 1)
  const total = items.length * run.per_type
  emit(m, { type: 'run_started', data: { run_id: run.id, total_samples: total } })

  stage(m, 'taxonomy', 'start')
  await sleep(350)
  stage(m, 'taxonomy', 'done', undefined, `${items.length} defect types`)

  stage(m, 'locate', 'start')
  for (const p of usable) {
    await sleep(between(250, 450))
    call(m, MODELS.sam, 'segment', between(3400, 4600), 0.0025)
    void p
  }
  stage(m, 'locate', 'done', undefined, `${usable.length} part masks`)

  const jobs: { idx: number; item: TaxonomyItem; part: Part }[] = []
  for (let k = 0; k < run.per_type; k++) {
    for (const item of items) {
      const idx = jobs.length
      jobs.push({ idx, item, part: usable[idx % usable.length] })
    }
  }
  const queue = jobs.slice()
  const worker = async () => {
    for (;;) {
      const j = queue.shift()
      if (!j) return
      await forgeSample(m, j.idx, j.item, j.part, j.idx > 5)
    }
  }
  await Promise.all([worker(), worker(), worker(), worker()])

  if (stressAfter && run.samples.some((s) => s.status === 'accepted')) await stress(m)

  const acc = run.samples.filter((s) => s.status === 'accepted')
  const ious = acc.map((s) => s.sam_iou).filter((x): x is number => x != null)
  run.summary = {
    accepted: acc.length,
    rejected: run.samples.filter((s) => s.status === 'rejected').length,
    failed: run.samples.filter((s) => s.status === 'failed').length,
    cost_usd: Number(ledgerCalls.filter((c) => c.run_id === run.id).reduce((a, c) => a + c.cost_usd, 0).toFixed(4)),
    seconds: Math.round(((performance.now() - t0) / 1000) * SPEED),
    mean_sam_iou: ious.length ? Number((ious.reduce((a, b) => a + b, 0) / ious.length).toFixed(3)) : null,
  }
  run.status = 'completed'
  m.busy = false
  emit(m, { type: 'run_completed', data: { summary: clone(run.summary) } })
}

function stamp() {
  const d = new Date()
  const p = (n: number) => String(n).padStart(2, '0')
  return `${d.getFullYear()}${p(d.getMonth() + 1)}${p(d.getDate())}-${p(d.getHours())}${p(d.getMinutes())}${p(d.getSeconds())}`
}

function openRunEvents(id: string, handlers: StreamHandlers, opts: StreamOptions): () => void {
  const m = runs.get(id)
  let closed = false
  const close = () => {
    if (closed) return
    closed = true
    m?.listeners.delete(listener)
    handlers.onClose?.()
  }
  const deliver = (e: RunEvent) => {
    if (closed) return
    handlers.onEvent(clone(e))
    if (e.type === opts.until) close()
  }
  const listener = (e: RunEvent) => deliver(e)
  if (!m) {
    setTimeout(() => {
      handlers.onConnectionError?.('Run not found')
      close()
    }, 50)
    return close
  }
  // replay past events, then go live
  const past = m.events.slice()
  setTimeout(() => {
    for (const e of past) deliver(e)
    if (closed) return
    if (!m.busy) return close() // server would end the stream here
    m.listeners.add(listener)
  }, 30)
  return close
}

// ------------------------------------------------------------------ eval

function evalReport(): EvalReport {
  const t6: Record<string, [number, number, number, number, number, number, number]> = {
    hole: [5, 5, 3, 0, 5, 5, 3],
    crack: [5, 5, 5, 1, 5, 5, 1],
    print: [5, 5, 4, 3, 4, 5, 3],
  }
  const sizes: Record<string, number> = { hole: 1.1, crack: 4.9, print: 3.2 }
  const curves: Curve[] = Object.entries(t6).map(([t, row]) => {
    const pts: SeverityPoint[] = []
    LADDER.forEach(([kind, level], i) => {
      for (let k = 0; k < 5; k++)
        pts.push({
          sample_id: `${t}${k}`,
          defect_type: t,
          kind,
          level,
          url: '',
          size_mm: kind === 'size' ? sizes[t] * level : sizes[t],
          detected: k < row[i],
          pred_type: t,
          confidence: 0.8,
        })
    })
    return computeCurves(pts)[0]
  })
  return {
    generated: now() - 3600,
    real_benchmark: {
      n_good: 40,
      n_defect: 70,
      recall: 0.971,
      recall_ci: [0.902, 0.992],
      specificity: 0.95,
      specificity_ci: [0.835, 0.986],
      type_accuracy: 0.886,
      box_hit: 0.943,
      by_type: { crack: { n: 18, detected: 17 }, cut: { n: 17, detected: 16 }, hole: { n: 18, detected: 18 }, print: { n: 17, detected: 17 } },
    },
    in_context: [
      { condition: 'C0', label: 'Spec text only', recall: 1.0, specificity: 1.0, n: 20 },
      { condition: 'C1', label: 'Spec + 2 good images', recall: 1.0, specificity: 0.9, n: 20 },
      { condition: 'C2', label: 'Spec + 2 good + forged defects', recall: 1.0, specificity: 1.0, n: 20 },
      { condition: 'C3', label: 'Spec + 2 good + real defects', recall: 1.0, specificity: 1.0, n: 20 },
    ],
    faint_lift: [
      { condition: 'zero_shot', label: 'Zero-shot, faint levels (opacity ≤ 0.25, size 0.2)', detected: 21, n: 45 },
      { condition: 'forged_examples', label: 'With 8 forged examples in context', detected: 29, n: 45 },
    ],
    sam_real: { n: 10, median_iou: 0.867, mean_iou: 0.74, by_type: { hole: 0.9, print: 0.89, cut: 0.875, crack: 0.355 } },
    forge_stats: {
      attempted: 31,
      accepted: 28,
      acceptance_rate: 0.903,
      mean_sam_iou: 0.79,
      cost_per_accepted_usd: 0.0168,
      seconds_per_accepted: 23.4,
      validator_pass_rate: 0.968,
    },
    curves,
    notes: [
      'Mock data shaped like the gate-test results (docs/gate-results.md). Run eval/run_eval.py for real numbers.',
      'Zero-shot Muse Spark is already at ceiling on full-strength defects, so the headline is the detection threshold, not in-context lift.',
      'Severity variants are produced by deterministic OpenCV fades and shrinks of each forged delta; no extra model calls.',
    ],
  }
}

// ------------------------------------------------------------------ api

let inspectCount = 0

export const mockApi: Api = {
  mode: 'mock',
  async health() {
    await sleep(80)
    return { ok: true, demo_mode: DEMO, models: Object.values(MODELS), spent_usd: Number(spent.toFixed(4)), budget_usd: 100 }
  },
  async ledger(limit = 200) {
    await sleep(60)
    const calls = ledgerCalls.slice(-limit)
    const by_model: Record<string, { calls: number; cost_usd: number }> = {}
    for (const c of ledgerCalls) {
      const b = (by_model[c.model] ??= { calls: 0, cost_usd: 0 })
      b.calls++
      b.cost_usd += c.cost_usd
    }
    return { calls: clone(calls), spent_usd: Number(spent.toFixed(4)), by_model }
  },
  async defaultSpec() {
    await sleep(120)
    return { spec_text: DEFAULT_SPEC }
  },
  async taxonomy(spec_text) {
    await sleep(between(1300, 2100))
    record(MODELS.spark, 'taxonomy', between(5200, 8400), 0.0041, null)
    const low = spec_text.toLowerCase()
    const found = TAXONOMY_ITEMS.filter((t) => low.includes(t.defect_type))
    const width = /(\d+(?:\.\d+)?)\s*mm/.exec(low.split('width')[1] ?? '')
    const tax: Taxonomy = {
      part_name: 'whole in-shell hazelnut',
      part_width_mm: width ? Number(width[1]) : 20,
      defects: found.length ? clone(found) : clone(TAXONOMY_ITEMS),
    }
    return tax
  },
  async parts() {
    await sleep(150)
    return { parts: clone(ensureParts()) }
  },
  async uploadParts(files) {
    await sleep(between(900, 1500))
    const out: Part[] = []
    for (const f of files.slice(0, 10)) {
      const [w, h] = await imageSize(f)
      record(MODELS.sam, 'segment', between(3200, 4500), 0.0025, null)
      const c = document.createElement('canvas')
      c.width = w
      c.height = h
      const ctx = c.getContext('2d')!
      ctx.fillStyle = '#000'
      ctx.fillRect(0, 0, w, h)
      ctx.fillStyle = '#fff'
      ctx.beginPath()
      ctx.ellipse(w / 2, h / 2, w * 0.3, h * 0.34, 0, 0, Math.PI * 2)
      ctx.fill()
      const p: Part = {
        id: `upload-${Date.now().toString(36)}-${out.length}`,
        name: f.name || 'Upload',
        url: URL.createObjectURL(f),
        mask_url: c.toDataURL('image/png'),
        width: w,
        height: h,
        source: 'upload',
      }
      ensureParts().push(p)
      out.push(p)
    }
    return { parts: clone(out) }
  },
  async createRun(body) {
    await sleep(250)
    const id = `${stamp()}-${Math.floor(rand() * 0xffff).toString(16).padStart(4, '0')}`
    const run: Run = {
      id,
      created: now(),
      status: 'running',
      spec_text: body.spec_text,
      taxonomy: clone(body.taxonomy),
      part_ids: body.part_ids.slice(),
      per_type: body.per_type,
      samples: [],
      severity: [],
      curves: [],
      summary: null,
      demo: DEMO,
    }
    const m: MockRun = { run, events: [], listeners: new Set(), busy: true, forged: new Map() }
    runs.set(id, m)
    void pipeline(m, body.stress)
    return { run_id: id }
  },
  async runs() {
    await sleep(80)
    return {
      runs: [...runs.values()].map(({ run }) => ({
        id: run.id,
        created: run.created,
        status: run.status,
        per_type: run.per_type,
        accepted: run.samples.filter((s) => s.status === 'accepted').length,
        demo: run.demo,
      })),
    }
  },
  async run(id) {
    await sleep(90)
    const m = runs.get(id)
    if (!m) throw new Error(`404: run ${id} not found`)
    return clone(m.run)
  },
  async startStress(id) {
    await sleep(200)
    const m = runs.get(id)
    if (!m) throw new Error(`404: run ${id} not found`)
    if (m.busy) throw new Error('409: run is busy')
    m.busy = true
    m.run.severity = []
    m.run.curves = []
    void (async () => {
      await stress(m)
      m.busy = false
      emit(m, { type: 'stress_completed', data: { curves: clone(m.run.curves) } })
    })()
    return { ok: true }
  },
  exportUrl(id) {
    const m = runs.get(id)
    const manifest = {
      note: 'Mock export. The real backend returns a COCO zip with images, masks and provenance.',
      run_id: id,
      images: m?.run.samples.filter((s) => s.status === 'accepted').map((s) => ({ id: s.id, part_id: s.part_id, bbox: s.bbox, defect_type: s.defect_type })) ?? [],
    }
    return `data:application/json;charset=utf-8,${encodeURIComponent(JSON.stringify(manifest, null, 2))}`
  },
  async inspect(file, opts) {
    await sleep(between(1800, 2800))
    const name = file instanceof File ? file.name.toLowerCase() : ''
    const roll = inspectCount++ % 5
    const verdict: Inspection['verdict'] = name.includes('good') ? 'good' : roll === 1 || roll === 3 ? 'good' : roll === 4 ? 'uncertain' : 'defect'
    let cost = record(MODELS.spark, 'inspect', between(4800, 6400), 0.0024, null).cost_usd
    if (verdict !== 'good') cost += record(MODELS.sam, 'segment', between(1900, 2800), 0.0025, null).cost_usd
    const o = await art.mockInspectOverlay(file, verdict)
    const type = verdict === 'good' ? 'none' : ['hole', 'crack', 'print', 'cut'][inspectCount % 4]
    const withEx = opts.use_examples_run_id ? ' Compared against forged examples from the selected run.' : ''
    return {
      verdict,
      defect: verdict !== 'good',
      type,
      confidence: verdict === 'good' ? 0.93 : verdict === 'uncertain' ? 0.58 : 0.88,
      rationale:
        verdict === 'good'
          ? `Shell shows natural striations and an intact cap; no holes, cracks, cuts or markings.${withEx}`
          : verdict === 'uncertain'
            ? `A small dark spot near the centre could be a ${type}, but SAM 3.1 found no mask inside the box.${withEx}`
            : `A dark irregular ${type} with a torn rim, consistent with spec clause 4.${type === 'hole' ? 1 : type === 'crack' ? 2 : type === 'cut' ? 3 : 4}.${withEx}`,
      box_px: o.box,
      image_url: o.imageUrl,
      overlay_url: verdict === 'good' ? null : o.overlayUrl,
      mask_url: null,
      ms: Math.round(between(4800, 7200)),
      cost_usd: Number(cost.toFixed(4)),
    }
  },
  async evalReport() {
    await sleep(300)
    return evalReport()
  },
  openRunEvents,
}
