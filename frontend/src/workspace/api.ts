import type { Comparison, Correction, Inspection, MemoryFact, Overview, PartInput, Sample, ScopeSettings, Status } from './types'

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
const json = (body: unknown): RequestInit => ({ method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(body) })
function photoForm(input: PartInput, scope: ScopeSettings) {
  const form = new FormData()
  if (input.file) form.append('file', input.file, input.file.name)
  else form.append('sample_id', input.sample.id)
  for (const [key, value] of Object.entries(scope)) form.append(key, value)
  return form
}
export const workspaceApi = {
  status: () => request<Status>('/status'),
  samples: () => request<{ samples: Sample[] }>('/samples'),
  overview: (scope: ScopeSettings) => request<Overview>('/overview?' + new URLSearchParams({ ...scope })),
  inspect: (input: PartInput, scope: ScopeSettings, memory: boolean) => {
    const form = photoForm(input, scope)
    form.append('memory_enabled', String(memory))
    return request<Inspection>('/inspect', { method: 'POST', body: form })
  },
  correct: (body: { inspection_id: string; verdict: 'good' | 'defect'; defect_type: string; rule_text: string; reviewer: string }) => request<Correction>('/corrections', json(body)),
  sync: (id: string) => request<Correction>(`/corrections/${encodeURIComponent(id)}/sync`, json({})),
  recall: (scope: ScopeSettings) => request<{ memories: MemoryFact[]; bank_id: string }>('/recall', json(scope)),
  reflect: (scope: ScopeSettings) => request<{ summary: string; bank_id: string }>('/reflect', json(scope)),
  compare: (input: PartInput, scope: ScopeSettings, expected: string) => {
    const form = photoForm(input, scope)
    form.append('expected_verdict', expected)
    return request<Comparison>('/compare', { method: 'POST', body: form })
  },
}
export function time(value: string) { return new Date(value).toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' }) }
export function dateTime(value: string) { return new Date(value).toLocaleString([], { month: 'short', day: 'numeric', hour: '2-digit', minute: '2-digit' }) }
export function decision(verdict: string) { return verdict === 'good' ? 'Accept' : verdict === 'defect' ? 'Reject' : 'Review' }
