import type { Issue, Lot, Member, Overview, Product, Revision, Role, Session, Standard, Station, TeamData, ValidationCase, ValidationRun, Review } from './types'

const BASE = '/api/workspace/pilot'
export class PilotError extends Error { status: number; constructor(message: string, status: number) { super(message); this.status = status } }
async function request<T>(path: string, init?: RequestInit): Promise<T> {
  let response: Response
  try { response = await fetch(BASE + path, { credentials: 'same-origin', cache: 'no-store', ...init }) }
  catch { throw new Error('The factory server is unreachable. Check your connection and retry.') }
  if (!response.ok) {
    let message = 'This request could not be completed. Retry or refresh the workspace.'
    try {
      const body = await response.json()
      if (typeof body.detail === 'string') message = body.detail
      else if (Array.isArray(body.detail)) message = body.detail.map((field: { msg?: string }) => field.msg || 'Invalid field').join(' ')
    } catch { /* A gateway may return an HTML error. */ }
    throw new PilotError(message, response.status)
  }
  if (response.status === 204) return undefined as T
  return response.json() as Promise<T>
}
const body = (value: unknown, method = 'POST'): RequestInit => ({ method, headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(value) })
export const pilotApi = {
  session: () => request<Session>('/session'),
  register: (value: { username: string; password: string; name: string; team_name: string }) => request<Session>('/register', body(value)),
  login: (value: { username: string; password: string }) => request<Session>('/login', body(value)),
  join: (value: { token: string; username: string; password: string; name: string }) => request<Session>('/join', body(value)),
  logout: () => request<unknown>('/logout', body({})),
  overview: () => request<Overview>('/overview'),
  team: () => request<TeamData>('/team'),
  invite: (role: Role) => request<{ token: string; expires_at: string | number }>('/invites', body({ role })),
  member: (id: string, value: Pick<Member, 'version' | 'role' | 'active'>) => request<Member>(`/members/${encodeURIComponent(id)}`, body(value, 'PATCH')),
  product: (value: { code: string; name: string; factory: string; description?: string }) => request<Product>('/products', body(value)),
  revision: (value: { product_id: string; label: string; spec_text: string; capture_instructions: string }) => request<Revision>('/revisions', body(value)),
  revise: (id: string, version: number, status: 'approved' | 'retired') => request<Revision>(`/revisions/${encodeURIComponent(id)}`, body({ version, status }, 'PATCH')),
  station: (value: { name: string; product_id: string; instructions: string }) => request<Station>('/stations', body(value)),
  updateStation: (id: string, value: { version: number; active: boolean; instructions?: string }) => request<Station>(`/stations/${encodeURIComponent(id)}`, body(value, 'PATCH')),
  lot: (value: { reference: string; revision_id: string; station_id: string; notes?: string }) => request<Lot>('/lots', body(value)),
  updateLot: (id: string, version: number, status: 'open' | 'closed') => request<Lot>(`/lots/${encodeURIComponent(id)}`, body({ version, status }, 'PATCH')),
  review: (id: string, value: { version: number; status: 'open' | 'claimed' | 'closed'; outcome?: string; reason?: string }) => request<Review>(`/reviews/${encodeURIComponent(id)}`, body(value, 'PATCH')),
  standard: (id: string, value: { version: number; status: 'approved' | 'retired'; reason?: string }) => request<Standard>(`/standards/${encodeURIComponent(id)}`, body({ ...value, ...(value.reason ? {} : { reason: undefined }) }, 'PATCH')),
  issue: (value: { title: string; lot_id: string; inspection_id?: string; severity: 'minor' | 'major' | 'critical'; description: string; requirement?: string; root_cause?: string; evidence?: string; containment?: string; assignee?: string }) => request<Issue>('/nonconformances', body(value)),
  updateIssue: (id: string, value: { version: number; status: 'open' | 'contained' | 'closed'; containment?: string; corrective_action?: string; resolution?: string; root_cause?: string; evidence?: string; assignee?: string | null }) => request<Issue>(`/nonconformances/${encodeURIComponent(id)}`, body(value, 'PATCH')),
  validation: () => request<{ runs: ValidationRun[] }>('/validation'),
  evaluate: (value: { name: string; cases: ValidationCase[]; configuration?: Record<string, unknown> }) => request<ValidationRun>('/validation', body(value)),
  exportLot: (id: string, csv = false) => `${BASE}/lots/${encodeURIComponent(id)}/${csv ? 'csv' : 'export'}`,
}
export const errorMessage = (error: unknown) => error instanceof Error ? error.message : 'This action could not be completed.'
