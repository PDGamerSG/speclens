// Types mirror docs/api-contract.md exactly (snake_case, same optionality).

export type DefectType = string

export interface TaxonomyItem {
  defect_type: DefectType
  clause: string
  description: string
  severity_note: string
}

export interface Taxonomy {
  part_name: string
  part_width_mm: number
  defects: TaxonomyItem[]
}

export interface Part {
  id: string
  name: string
  url: string
  mask_url: string | null
  width: number
  height: number
  source: 'sample' | 'upload'
}

export interface CallRecord {
  t: number
  model: string
  op: string
  ms: number
  status: number | string
  cost_usd: number
  run_id: string | null
  cached_tokens?: number
}

export interface Validator {
  id: string
  name: string
  passed: boolean
  detail: string
}

export interface Critic {
  realism: number
  matches_type: boolean
  artifacts: string
  verdict: 'accept' | 'reject'
  revised_prompt: string
}

export type SampleStatus = 'forging' | 'accepted' | 'rejected' | 'failed'

export interface Sample {
  id: string
  run_id: string
  part_id: string
  defect_type: DefectType
  status: SampleStatus
  attempt: number
  prompt: string
  original_url: string
  crop_original_url: string
  crop_raw_url: string | null
  crop_composite_url: string | null
  composite_url: string | null
  mask_url: string | null
  overlay_url: string | null
  bbox: [number, number, number, number] | null
  area_px: number
  size_mm: number | null
  sam_iou: number | null
  critic: Critic | null
  validators: Validator[]
  cost_usd: number
  ms: number
}

export type SeverityKind = 'opacity' | 'size'

export interface SeverityPoint {
  sample_id: string
  defect_type: DefectType
  kind: SeverityKind
  level: number
  url: string
  size_mm: number | null
  /** The inspector's box overlaps the defect. */
  detected: boolean
  /** Any defect claim, including one in the wrong place. Missing on runs recorded before location checks. */
  flagged?: boolean
  box_px?: [number, number, number, number] | null
  pred_type: string
  confidence: number
}

export interface CurveCell {
  kind: SeverityKind
  level: number
  n: number
  detected: number
  flagged?: number
  rate: number
  ci_low: number
  ci_high: number
  mean_size_mm: number | null
}

export interface Curve {
  defect_type: DefectType
  cells: CurveCell[]
  threshold_note: string
}

export interface RunSummary {
  accepted: number
  rejected: number
  failed: number
  cost_usd: number
  seconds: number
  mean_sam_iou: number | null
}

export interface Run {
  id: string
  created: number
  status: 'running' | 'completed' | 'failed'
  spec_text: string
  taxonomy: Taxonomy
  part_ids: string[]
  per_type: number
  samples: Sample[]
  severity: SeverityPoint[]
  curves: Curve[]
  /** Unedited parts inspected as a false-alarm control. */
  controls?: { n: number; flagged: number } | null
  summary: RunSummary | null
  demo: boolean
}

export interface RunListItem {
  id: string
  created: number
  status: Run['status']
  per_type: number
  accepted: number
  demo: boolean
}

export interface Health {
  ok: true
  demo_mode: boolean
  models: string[]
  spent_usd: number
  budget_usd: number
}

export interface Ledger {
  calls: CallRecord[]
  spent_usd: number
  by_model: Record<string, { calls: number; cost_usd: number }>
}

export interface CreateRunBody {
  spec_text: string
  taxonomy: Taxonomy
  part_ids: string[]
  per_type: number
  stress: boolean
}

export interface Inspection {
  verdict: 'defect' | 'good' | 'uncertain'
  defect: boolean
  type: string
  confidence: number
  rationale: string
  box_px: [number, number, number, number] | null
  image_url: string
  overlay_url: string | null
  mask_url: string | null
  ms: number
  cost_usd: number
}

export interface EvalReport {
  generated: number
  real_benchmark: {
    n_good: number
    n_defect: number
    recall: number
    recall_ci: [number, number]
    specificity: number
    specificity_ci: [number, number]
    type_accuracy: number
    box_hit: number
    by_type: Record<string, { n: number; detected: number }>
  } | null
  in_context: { condition: string; label: string; recall: number; specificity: number; n: number }[]
  faint_lift: { condition: string; label: string; detected: number; n: number }[]
  sam_real: { n: number; median_iou: number; mean_iou: number; by_type: Record<string, number> } | null
  forge_stats: {
    attempted: number
    accepted: number
    acceptance_rate: number
    mean_sam_iou: number | null
    cost_per_accepted_usd: number
    seconds_per_accepted: number
    validator_pass_rate: number
  } | null
  curves: Curve[]
  notes: string[]
  /** Targeted blind-spot experiment (eval/blind_spot.py); optional, added after the core eval. */
  blind_spot?: {
    finding: string
    amendment: string
    rows: { label: string; detected: number; n: number; tone: 'pass' | 'signal' }[]
  } | null
}

// ---- SSE ----

export type StageName =
  | 'taxonomy'
  | 'locate'
  | 'forge'
  | 'composite'
  | 'label'
  | 'critic'
  | 'validate'
  | 'export'
  | 'stress'

export interface StageEvent {
  stage: StageName
  status: 'start' | 'done'
  sample_id?: string
  detail?: string
}

export type RunEvent =
  | { type: 'run_started'; data: { run_id: string; total_samples: number } }
  | { type: 'stage'; data: StageEvent }
  | { type: 'call'; data: CallRecord }
  | { type: 'sample'; data: Sample }
  | { type: 'severity'; data: SeverityPoint }
  | { type: 'curves'; data: { curves: Curve[] } }
  | { type: 'controls'; data: { n: number; flagged: number } }
  | { type: 'run_completed'; data: { summary: RunSummary } }
  | { type: 'stress_completed'; data: { curves: Curve[] } }
  | { type: 'error'; data: { message: string } }

export type RunEventName = RunEvent['type']

export const RUN_EVENT_NAMES: RunEventName[] = [
  'run_started',
  'stage',
  'call',
  'sample',
  'severity',
  'curves',
  'controls',
  'run_completed',
  'stress_completed',
  'error',
]

export interface StreamHandlers {
  onEvent: (e: RunEvent) => void
  /** Connection-level problem (not a server `error` event). */
  onConnectionError?: (message: string) => void
  /** Called once when the stream is finished (terminal event or server closed it). */
  onClose?: () => void
}

export interface StreamOptions {
  /** Close the stream after this event. `run_completed` for a normal run; `stress_completed` after POST /stress. */
  until: 'run_completed' | 'stress_completed'
}

export interface InspectOptions {
  spec_text?: string
  use_examples_run_id?: string
}

export interface Api {
  readonly mode: 'live' | 'mock'
  health(): Promise<Health>
  ledger(limit?: number): Promise<Ledger>
  defaultSpec(): Promise<{ spec_text: string }>
  taxonomy(spec_text: string): Promise<Taxonomy>
  parts(): Promise<{ parts: Part[] }>
  uploadParts(files: File[]): Promise<{ parts: Part[] }>
  createRun(body: CreateRunBody): Promise<{ run_id: string }>
  runs(): Promise<{ runs: RunListItem[] }>
  run(id: string): Promise<Run>
  startStress(id: string): Promise<{ ok: true }>
  exportUrl(id: string): string
  inspect(file: Blob, opts: InspectOptions): Promise<Inspection>
  evalReport(): Promise<EvalReport>
  /** Opens the run's SSE stream. Returns a function that closes it. */
  openRunEvents(id: string, handlers: StreamHandlers, opts: StreamOptions): () => void
}
