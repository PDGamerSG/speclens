import type { Inspection, Taxonomy } from '../workspace/types'

export type Role = 'admin' | 'engineer' | 'operator' | 'viewer'
export interface Session { authenticated: boolean; user: { id: string; username: string; name: string } | null; team: { id: string; name: string } | null; role: Role | null }
export const SIGNED_OUT: Session = { authenticated: false, user: null, team: null, role: null }
export interface RecordBase { id: string; kind: string; owner_id: string; version: number; created_at: string; updated_at: string; demo_seed?: string }
export interface Actor { id: string; name: string; username: string; role: Role }
export interface Product extends RecordBase { code: string; name: string; factory: string; description?: string }
export interface Revision extends RecordBase { product_id: string; label: string; spec_text: string; capture_instructions: string; taxonomy: Taxonomy; status: 'draft' | 'approved' | 'retired'; approver?: Actor | null }
export interface Station extends RecordBase { name: string; product_id: string; instructions: string; active: boolean }
export interface Lot extends RecordBase { reference: string; revision_id: string; station_id: string; notes?: string; status: 'open' | 'closed' }
export interface Capture extends RecordBase { lot_id: string; revision_id: string; station_id: string; physical_part_id: string; capture_id?: string; inspection_id?: string; retake_of?: string | null; status: string; error?: string | null; resolved_by?: string | null }
export type Outcome = 'accept' | 'reject' | 'hold' | 'retake'
export interface Review extends RecordBase { inspection_id: string; capture_id?: string; lot_id: string; revision_id: string; physical_part_id?: string; status: 'open' | 'claimed' | 'closed'; outcome?: Outcome | null; reason?: string; assignee?: Actor | null; inspection?: Inspection; resolved_by?: string | null; quarantined?: boolean; quarantine_reason?: string; history?: unknown[] }
export interface Standard extends RecordBase { correction_id: string; inspection_id: string; revision_id: string; clause?: string; rule_text: string; verdict: 'good' | 'defect'; defect_type: string; status: 'candidate' | 'approved' | 'retired'; approver?: Actor | null; sync_status?: string; sync_error?: string | null; reason?: string }
export interface Issue extends RecordBase { title: string; lot_id: string; inspection_id?: string | null; severity: 'minor' | 'major' | 'critical'; description: string; requirement?: string; root_cause?: string; evidence?: string; containment?: string; corrective_action?: string; resolution?: string; assignee?: string | null; status: 'open' | 'contained' | 'closed'; history?: unknown[] }
export interface Activity extends RecordBase { action: string; actor?: Actor | null; target_id: string; details?: Record<string, unknown> }
export interface Overview { products: Product[]; revisions: Revision[]; stations: Station[]; lots: Lot[]; captures: Capture[]; reviews: Review[]; standards: Standard[]; nonconformances: Issue[]; activity: Activity[] }
export interface Member { id: string; user_id: string; username: string; name: string; role: Role; active: boolean; version: number }
export interface TeamData { members: Member[]; invites: { id: string; role: Role; expires_at: string | number; used_at: string | null }[] }
export type Prediction = 'good' | 'defect' | 'uncertain' | 'error'
export interface ValidationCase { sample_id: string; physical_part_id: string; lot_id: string; session_id: string; truth: 'good' | 'defect'; severity?: string; baseline: Prediction; with_memory: Prediction }
export interface Rate { count: number; denominator: number; rate: number | null }
export interface EvaluationArm { matrix: Record<'good' | 'defect', Record<Prediction, number>>; escaped_defects: Rate; false_rejects: Rate; review: Rate; errors: Rate; decision_coverage: Rate }
export interface ValidationRun extends RecordBase { name: string; source: string; configuration: Record<string, unknown>; manifest: { cases: ValidationCase[]; aggregation: string; input_order_is_attempt_order: boolean; sha256: string }; results: { counts: { samples: number; physical_parts: number; repeated_views: number; lots: number; sessions: number; clusters: number; truth: { good: number; defect: number } }; baseline: EvaluationArm; with_memory: EvaluationArm; paired: { resolved_improvements: number; resolved_regressions: number; unchanged: number; transitions: Record<Prediction, Record<Prediction, number>> }; uncertainty: { method: string; clusters: number; confidence: number; replicates: number; delta_rates: Record<string, { estimate: number | null; lower: number | null; upper: number | null }> }; limitations: string[] } }
export type Section = 'products' | 'stations' | 'lots' | 'capture' | 'review' | 'standards' | 'validation' | 'issues' | 'activity' | 'team'
export type RunAction = (label: string, operation: () => Promise<unknown>, success?: string) => Promise<boolean>
export interface SectionProps { data: Overview; session: Session; busy: boolean; run: RunAction; navigate: (section: Section) => void }
