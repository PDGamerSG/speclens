import type { Batch, BatchJob, Comparison, Correction, DashboardData, Inspection, MemoryFact, Overview, PartInput, Sample, ScopeSettings, Status, Taxonomy } from './types'

const BASE = '/api/workspace'
async function request<T>(path: string, init?: RequestInit): Promise<T> {
  let response: Response
  try { response = await fetch(BASE + path, init) }
  catch { throw new Error('The inspection server is unreachable. Check the connection and try again.') }
  if (!response.ok) {
    let message = 'This request could not be completed.'
    try {
      const body = await response.json()
      if (typeof body.detail === 'string') message = body.detail
      else if (Array.isArray(body.detail)) message = body.detail.map((d: { msg?: string }) => d.msg || 'Invalid field').join(' ')
    } catch { /* Keep a useful error if the gateway returned HTML. */ }
    throw new Error(message)
  }
  return response.json() as Promise<T>
}
function scopeQuery(scope: ScopeSettings, extra: Record<string, string> = {}) {
  return new URLSearchParams({ ...Object.fromEntries(Object.entries(scope).filter((entry): entry is [string, string] => typeof entry[1] === 'string')), ...extra })
}
const json = (body: unknown): RequestInit => ({ method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(body) })
function photoForm(input: PartInput, scope: ScopeSettings) {
  const form = new FormData()
  if (input.file) form.append('file', input.file, input.file.name)
  else form.append('sample_id', input.sample.id)
  for (const [key, value] of Object.entries(scope)) if (typeof value === 'string') form.append(key, value)
  return form
}
export const workspaceApi = {
  status: () => request<Status>('/status'),
  samples: () => request<{ samples: Sample[] }>('/samples'),
  overview: (scope: ScopeSettings, before?: string, limit?: number) => request<Overview>('/overview?' + scopeQuery(scope, { ...(before ? { before } : {}), ...(limit ? { limit: String(limit) } : {}) })),
  exportRecords: () => request<{ inspections: Inspection[]; corrections: Correction[]; comparisons: Comparison[] }>('/export'),
  findInspection: async (id: string, scope: ScopeSettings): Promise<Inspection> => {
    let before: string | undefined
    const seen = new Set<string>()
    do {
      const page = await request<Overview>('/overview?' + scopeQuery(scope, { limit: '500', ...(before ? { before } : {}) }))
      const inspection = page.inspections.find(item => item.id === id)
      if (inspection) return inspection
      if (!page.has_more || !page.next_before || seen.has(page.next_before)) break
      before = page.next_before; seen.add(before)
    } while (before)
    throw new Error('The source inspection is unavailable. Refresh the workspace or ask an admin to check its retention.')
  },
  inspect: (input: PartInput, scope: ScopeSettings, memory: boolean) => {
    const form = photoForm(input, scope)
    form.append('memory_enabled', String(memory))
    return request<Inspection>('/inspect', { method: 'POST', body: form })
  },
  correct: (body: { inspection_id: string; verdict: 'good' | 'defect'; defect_type: string; rule_text: string; reviewer: string }) => request<Correction>('/corrections', json(body)),
  sync: (id: string) => request<Correction>(`/corrections/${encodeURIComponent(id)}/sync`, json({})),
  recall: (scope: ScopeSettings) => request<{ memories: MemoryFact[]; bank_id: string }>('/recall', json(scope)),
  reflect: (scope: ScopeSettings) => request<{ summary: string; bank_id: string }>('/reflect', json(scope)),
  queueInspection: (file: File, scope: ScopeSettings, memory: boolean, batchId: string) => {
    const form = photoForm({ file }, scope)
    form.append('memory_enabled', String(memory))
    form.append('batch_id', batchId)
    return request<BatchJob>('/jobs/inspect', { method: 'POST', body: form })
  },
  batch: (batchId: string) => request<Batch>(`/batches/${encodeURIComponent(batchId)}`),
  exportUrl: `${BASE}/export`,
  deleteData: () => request<{ inspections: number; corrections: number; memory_failed: number }>('/data', {
    method: 'DELETE', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ confirm: 'DELETE' }) }),
  dashboard: (scope: ScopeSettings, days: number) => request<DashboardData>('/dashboard?' + scopeQuery(scope, { days: String(days) })),
  parseSpec: (spec_text: string) => request<Taxonomy>('/specs/parse', json({ spec_text })),
  extractSpec: (source: { file: File } | { text: string }, useModel: boolean) => {
    const form = new FormData()
    if ('file' in source) form.append('file', source.file, source.file.name)
    else form.append('spec_text', source.text)
    form.append('use_model', String(useModel))
    return request<{ spec_text: string; taxonomy: Taxonomy }>('/specs/extract', { method: 'POST', body: form })
  },
  compare: (input: PartInput, scope: ScopeSettings, expected: string) => {
    const form = photoForm(input, scope)
    form.append('expected_verdict', expected)
    return request<Comparison>('/compare', { method: 'POST', body: form })
  },
}
export function shortId(id: string) { return id.replace(/^(insp-|correction-|compare-)/, '').slice(0, 8).toUpperCase() }
export function dateTime(value: string) { return new Date(value).toLocaleString([], { month: 'short', day: 'numeric', hour: '2-digit', minute: '2-digit' }) }
export function decision(verdict: string) { return verdict === 'good' ? 'Accept' : verdict === 'defect' ? 'Reject' : 'Review' }
