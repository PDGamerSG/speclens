export interface ScopeSettings { factory: string; part_family: string; spec_text: string; revision_id?: string; lot_id?: string; station_id?: string; physical_part_id?: string; capture_id?: string; retake_of?: string }
export interface Status {
  ok: boolean; model_configured: boolean; memory_configured: boolean; model: string;
  spent_usd: number; budget_usd: number; default_factory: string; default_part: string; default_spec: string;
  cache?: { prompt_tokens: number; cached_tokens: number; hit_rate: number; saved_usd: number };
}
export interface Sample { id: string; name: string; detail: string; image_url: string; expected_verdict: 'good' | 'defect' }
export interface MemoryFact { id: string; text: string; source_id: string; type: string; reviewer?: string; rule_text?: string; source_inspection_id?: string }
export interface Inspection {
  demo_seed?: string;
  id: string; scope_id: string; factory: string; part_family: string; spec_text: string;
  verdict: 'good' | 'defect' | 'uncertain'; defect: boolean; type: string; confidence: number;
  rationale: string; box_px: number[] | null; image_url: string; image_width: number; image_height: number;
  memory_enabled: boolean; memory_status: 'disabled' | 'empty' | 'recalled'; memories: MemoryFact[];
  // Recorded since citation checks. Results saved before that have none of the three.
  cited_ids?: string[]; uncited_ids?: string[]; unknown_citations?: string[];
  source_kind?: 'synthetic_sample' | 'upload' | 'unknown'; source_group?: string | null; sample_id?: string | null;
  filename: string; image_sha256: string; ms: number; cost_usd: number; created_at: string; model: string;
  pilot?: { revision_id: string; product_id: string; lot_id: string; station_id: string; physical_part_id: string; capture_id: string; retake_of?: string | null; [key: string]: unknown };
  part_visible?: boolean; prompt_tokens?: number; cached_tokens?: number;
  mask_url?: string; overlay_url?: string; measurement?: Measurement | null; size_note?: string; reference_crops?: string[];
}
export interface Measurement {
  length_px: number; width_px: number; area_px: number; mm_per_px: number | null;
  length_mm: number | null; width_mm: number | null; area_mm2: number | null; limit_mm: number | null; within_limit: boolean | null;
}
export interface Correction {
  id: string; inspection_id: string; scope_id: string; rule_text: string; reviewer: string;
  original_verdict: string; original_type: string; original_rationale: string; image_url: string;
  verdict: 'good' | 'defect'; defect_type: string; created_at: string; sync_status: 'pending' | 'synced' | 'demo'; sync_error: string | null;
  crop_url?: string;
}
export interface Comparison {
  id: string; baseline: Inspection; with_memory: Inspection; created_at: string;
  reuse_reason?: 'reused_image' | 'shared_source_photo' | 'not_used_for_correction';
  changed: boolean; held_out: boolean; expected_verdict: 'good' | 'defect' | null; note: string;
}
export interface SpecClass { defect_type: string; label: string; clause: string; description: string; limit_mm: number | null }
export interface Taxonomy { part_name: string; part_width_mm: number | null; classes: SpecClass[]; source: 'rules' | 'model' | 'fallback' }
export interface Overview {
  scope_id: string; bank_id: string; inspections: Inspection[]; corrections: Correction[]; comparisons: Comparison[];
  stats: { inspections: number; corrections: number; synced: number; pending: number; comparisons?: number };
  taxonomy?: Taxonomy; has_more?: boolean; next_before?: string | null;
}
export type Section = 'inspect' | 'batch' | 'standards' | 'compare' | 'dashboard' | 'history';
export type PartInput = { sample: Sample; file?: never } | { file: File; sample?: never };
export interface DashboardData {
  days: number; since: string;
  totals: {
    inspections: number; accepted: number; rejected: number; review: number; reject_rate: number | null; review_rate: number | null;
    corrections: number; overturned: number; corrected_share: number | null; memory_inspections: number; citation_rate: number | null; unknown_citations?: number;
    cost_usd: number; cost_per_inspection: number | null; latency_p50_ms: number | null; latency_p95_ms: number | null;
  };
  daily: { day: string; inspections: number; accepted: number; rejected: number; review: number; cost_usd: number }[];
  pareto: { defect_type: string; label: string; clause: string; count: number; share: number }[];
  corrections_weekly: { week: string; corrections: number }[];
  cache: { prompt_tokens: number; cached_tokens: number; hit_rate: number; saved_usd: number };
}
export interface BatchJob {
  id: string; kind: string; batch_id: string | null; status: 'queued' | 'running' | 'done' | 'failed';
  result: Inspection | null; error: { status_code: number; detail: string } | null; attempts: number; created_at: string; filename: string;
}
export interface Batch { batch_id: string; counts: Record<'queued' | 'running' | 'done' | 'failed', number>; finished: boolean; jobs: BatchJob[] }
