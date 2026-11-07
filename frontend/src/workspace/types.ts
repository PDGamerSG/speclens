export interface ScopeSettings { factory: string; part_family: string; spec_text: string }
export interface Status {
  ok: boolean; model_configured: boolean; memory_configured: boolean; model: string;
  spent_usd: number; budget_usd: number; default_factory: string; default_part: string; default_spec: string;
}
export interface Sample { id: string; name: string; detail: string; image_url: string; expected_verdict: 'good' | 'defect' }
export interface MemoryFact { id: string; text: string; source_id: string; type: string; reviewer?: string; rule_text?: string; source_inspection_id?: string }
export interface Inspection {
  id: string; scope_id: string; factory: string; part_family: string; spec_text: string;
  verdict: 'good' | 'defect' | 'uncertain'; defect: boolean; type: string; confidence: number;
  rationale: string; box_px: number[] | null; image_url: string; image_width: number; image_height: number;
  memory_enabled: boolean; memory_status: 'disabled' | 'empty' | 'recalled'; memories: MemoryFact[];
  source_kind?: 'synthetic_sample' | 'upload' | 'unknown'; source_group?: string | null; sample_id?: string | null;
  filename: string; image_sha256: string; ms: number; cost_usd: number; created_at: string; model: string;
}
export interface Correction {
  id: string; inspection_id: string; scope_id: string; rule_text: string; reviewer: string;
  original_verdict: string; original_type: string; original_rationale: string; image_url: string;
  verdict: 'good' | 'defect'; defect_type: string; created_at: string; sync_status: 'pending' | 'synced'; sync_error: string | null;
}
export interface Comparison {
  id: string; baseline: Inspection; with_memory: Inspection; created_at: string;
  reuse_reason?: 'reused_image' | 'shared_source_photo' | 'not_used_for_correction';
  changed: boolean; held_out: boolean; expected_verdict: 'good' | 'defect' | null; note: string;
}
export interface Overview {
  scope_id: string; bank_id: string; inspections: Inspection[]; corrections: Correction[]; comparisons: Comparison[];
  stats: { inspections: number; corrections: number; synced: number; pending: number };
}
export type View = 'inspect' | 'standards' | 'history' | 'compare';
export type PartInput = { sample: Sample; file?: never } | { file: File; sample?: never };
