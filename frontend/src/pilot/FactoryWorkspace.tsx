import { Activity as ActivityIcon, ArrowLeft, BookOpenCheck, Boxes, Camera, ChartNoAxesCombined, CheckCircle2, ClipboardCheck, Factory, FolderKanban, LoaderCircle, LogOut, RefreshCw, ShieldAlert, Users, X } from 'lucide-react'
import { useCallback, useEffect, useRef, useState } from 'react'
import { Chief } from '../workspace/Chief'
import { InkFilter } from '../workspace/marks'
import { Activity } from './Activity'
import { Auth } from './Auth'
import { errorMessage, PilotError, pilotApi } from './api'
import { Issues } from './Issues'
import { CaptureDesk, Lots, Stations } from './Operations'
import { Products } from './Products'
import { Reviews, Standards } from './Review'
import { Team } from './Team'
import { SIGNED_OUT, type Capture, type Overview, type Review, type Section, type SectionProps, type Session, type TeamData, type ValidationRun } from './types'
import { Validation } from './Validation'
import { isReviewUnresolved } from './utils'
import './pilot.css'

const NAV = [
  { id: 'products', label: 'Products & specs', icon: FolderKanban, lead: 'Control the specification before the first capture.' },
  { id: 'stations', label: 'Capture stations', icon: Camera, lead: 'Record the setup your operators use for every photo.' },
  { id: 'lots', label: 'Lots', icon: Boxes, lead: 'Keep physical parts, capture attempts and disposition together.' },
  { id: 'capture', label: 'Capture', icon: Camera, lead: 'Inspect a physical part against its approved revision.' },
  { id: 'review', label: 'Review', icon: ClipboardCheck, lead: 'People make the final call. Every reason stays on record.' },
  { id: 'standards', label: 'Standards', icon: BookOpenCheck, lead: 'Propose, approve and retire the rules future inspections can use.' },
  { id: 'validation', label: 'Validation', icon: ChartNoAxesCombined, lead: 'Evaluate matched results with explicit denominators and limitations.' },
  { id: 'issues', label: 'Nonconformances', icon: ShieldAlert, lead: 'Track containment, corrective action and closure evidence.' },
  { id: 'activity', label: 'Activity', icon: ActivityIcon, lead: 'Follow attributable lifecycle changes across your team.' },
  { id: 'team', label: 'Team', icon: Users, lead: 'Give the right people the access their work needs.' },
] as const

export default function FactoryWorkspace({ session, onSession, onExit, initialError }: { session: Session; onSession: (session: Session) => void; onExit: () => void; initialError?: string | null }) {
  const [active, setActive] = useState<Section>('products')
  const [data, setData] = useState<Overview | null>(null)
  const [team, setTeam] = useState<TeamData | null>(null)
  const [runs, setRuns] = useState<ValidationRun[]>([])
  const [busy, setBusy] = useState<string | null>(null)
  const [error, setError] = useState<string | null>(null)
  const [notice, setNotice] = useState<string | null>(null)
  const [selectedLot, setSelectedLot] = useState('')
  const [selectedReview, setSelectedReview] = useState('')
  const [selectedIssue, setSelectedIssue] = useState('')
  const [captureLot, setCaptureLot] = useState('')
  const [retake, setRetake] = useState<{ captureId: string; partId: string } | null>(null)
  const [captureGeneration, setCaptureGeneration] = useState(0)
  const mounted = useRef(true)
  const loadId = useRef(0)
  const busyRef = useRef(false)
  const heading = useRef<HTMLHeadingElement>(null)
  useEffect(() => { mounted.current = true; return () => { mounted.current = false } }, [])
  const load = useCallback(async () => {
    const requestId = ++loadId.current
    const identity = await pilotApi.session()
    if (!mounted.current || requestId !== loadId.current) return
    if (!identity.authenticated || identity.team?.id !== session.team?.id || identity.user?.id !== session.user?.id || identity.role !== session.role) { onSession(identity); return }
    const [records, validations, members] = await Promise.all([pilotApi.overview(), pilotApi.validation(), session.role === 'admin' ? pilotApi.team() : Promise.resolve(null)])
    if (!mounted.current || requestId !== loadId.current) return
    const confirmed = await pilotApi.session()
    if (!mounted.current || requestId !== loadId.current) return
    if (!confirmed.authenticated || confirmed.team?.id !== session.team?.id || confirmed.user?.id !== session.user?.id || confirmed.role !== session.role) { onSession(confirmed); return }
    setData(records); setRuns(validations.runs); setTeam(members)
  }, [session.team?.id, session.user?.id, session.role, onSession])
  const fail = useCallback((error: unknown) => {
    if (!mounted.current) return
    if (error instanceof PilotError && error.status === 401) { onSession(SIGNED_OUT); return }
    setError(errorMessage(error))
  }, [onSession])
  useEffect(() => {
    if (!session.authenticated) return
    const start = new AbortController()
    Promise.resolve().then(() => { if (!start.signal.aborted) return load() }).catch(fail)
    const onFocus = () => { if (!busyRef.current) void load().catch(fail) }
    window.addEventListener('focus', onFocus)
    return () => { start.abort(); window.removeEventListener('focus', onFocus) }
  }, [session.authenticated, load, fail])
  useEffect(() => { heading.current?.focus({ preventScroll: true }) }, [active])
  const run: SectionProps['run'] = async (label, operation, success) => {
    if (busyRef.current || !mounted.current) return false
    busyRef.current = true; setBusy(label); setError(null); setNotice(null)
    try {
      await operation()
      if (!mounted.current) return false
      try { await load() } catch (error) { fail(error); setNotice('The action was saved. Refresh the workspace to load the latest records.'); return false }
      if (!mounted.current) return false
      if (success) setNotice(success)
      return true
    } catch (error) {
      fail(error)
      try { await load() } catch (reloadError) { if (reloadError instanceof PilotError && reloadError.status === 401) fail(reloadError) }
      return false
    } finally { busyRef.current = false; if (mounted.current) setBusy(null) }
  }
  const navigate = (section: Section) => { setActive(section); setError(null); if (!busyRef.current) void load().catch(fail) }
  const leave = async (demo: boolean) => {
    if (busyRef.current) return
    busyRef.current = true; setBusy('Signing out'); setError(null)
    try { await pilotApi.logout(); if (demo) onExit(); else onSession(SIGNED_OUT) } catch (error) { fail(error) } finally { busyRef.current = false; if (mounted.current) setBusy(null) }
  }
  if (!session.authenticated) return <Auth onSession={onSession} onExit={async () => { await pilotApi.logout(); onExit() }} initialError={initialError} />
  const current = NAV.find(item => item.id === active)!
  const unresolved = data?.reviews.filter(item => isReviewUnresolved(item, data)).length || 0
  const props: SectionProps = { data: data!, session, busy: !!busy, run, navigate }
  const startCapture = (lotId: string) => { setCaptureLot(lotId); setRetake(null); setCaptureGeneration(value => value + 1); navigate('capture') }
  const startCaptureRetake = (capture: Capture) => { setCaptureLot(capture.lot_id); setRetake({ captureId: capture.id, partId: capture.physical_part_id }); setCaptureGeneration(value => value + 1); navigate('capture') }
  const startRetake = (review: Review) => { const capture = data?.captures.find(item => item.id === review.capture_id || item.capture_id === review.capture_id || item.inspection_id === review.inspection_id); if (!capture) { setError('The original capture is unavailable. Refresh the workspace before retaking this part.'); return } setCaptureLot(review.lot_id); setRetake({ captureId: capture.id, partId: capture.physical_part_id }); setCaptureGeneration(value => value + 1); navigate('capture') }
  return <div className="pilot-app"><InkFilter /><a className="pilot-skip" href="#pilot-work">Skip to workspace</a><header className="pilot-header"><button className="brand" onClick={() => navigate('products')} aria-label="SpecLens factory workspace"><Chief size={36} /><span>SpecLens.</span></button><span className="pilot-area-label"><Factory size={15} />Factory workspace</span><div className="pilot-identity"><strong>{session.team?.name}</strong><span>{session.user?.name} / {session.role}</span></div><button className="icon-button" title="Sign out" aria-label="Sign out" disabled={!!busy} onClick={() => void leave(false)}><LogOut size={18} /></button></header><div className="pilot-shell"><aside className="pilot-sidebar"><nav aria-label="Factory sections">{NAV.map(item => <button key={item.id} aria-label={item.label} aria-current={active === item.id ? 'page' : undefined} className={'pilot-nav-item' + (active === item.id ? ' selected' : '')} onClick={() => navigate(item.id)} disabled={!!busy}><item.icon size={18} strokeWidth={1.8} /><span>{item.label}</span>{item.id === 'review' && unresolved > 0 && <small>{unresolved}</small>}</button>)}</nav><div className="pilot-sidebar-foot"><p>Human decisions.<br /><span className="handwritten">Traceable standards.</span></p><button className="text-link" disabled={!!busy} onClick={() => void leave(true)}><ArrowLeft size={15} />Return to public demo</button><small>Returning to the demo signs you out.</small></div></aside><main className="pilot-main" id="pilot-work"><header className="pilot-section-header"><div><h1 ref={heading} tabIndex={-1}>{current.label}</h1><p>{current.lead}</p></div><button className="button secondary compact" disabled={!!busy} aria-label="Refresh factory workspace" onClick={() => void run('Refresh workspace', async () => {}, 'Workspace refreshed.')}><RefreshCw size={15} className={busy === 'Refresh workspace' ? 'spin' : ''} />Refresh</button></header>{session.user?.username === 'demo.speclens' && session.team?.name === 'SpecLens Demo Factory' && <aside className="pilot-callout pilot-demo-notice" aria-label="Demo workspace notice"><strong>Explore a populated sample factory</strong><p>Illustrative products, parts, decisions and validation results. Seeded examples use synthetic images and staged outcomes; no model was run for them. Everyone using the demo login shares this workspace.</p>{data && <p className="pilot-demo-counts">{data.products.length} products · {data.lots.length} lots · {data.captures.length} captures · {data.standards.length} standards · {data.nonconformances.length} quality issues · {runs.length} validation runs</p>}</aside>}<div className="pilot-feedback" aria-live="polite">{error && <div className="alert error" role="alert"><span>{error}</span><button className="icon-button" aria-label="Dismiss factory error" onClick={() => setError(null)}><X size={16} /></button></div>}{notice && <div className="alert success" role="status"><CheckCircle2 size={17} /><span>{notice}</span><button className="icon-button" aria-label="Dismiss factory notification" onClick={() => setNotice(null)}><X size={16} /></button></div>}{busy && <p className="pilot-working" role="status"><LoaderCircle size={15} className="spin" />{busy}…</p>}</div>{!data ? <div className="pilot-loading" role="status">{error ? <><p>Workspace records could not load.</p><button className="button secondary" onClick={() => void run('Reload workspace', async () => {})}>Retry workspace connection</button></> : <><LoaderCircle size={26} className="spin" /><p>Loading your team’s workspace…</p></>}</div> : <>{active === 'products' && <Products {...props} />}{active === 'stations' && <Stations {...props} />}{active === 'lots' && <Lots {...props} selectedId={selectedLot} onSelect={setSelectedLot} onCapture={startCapture} onRetakeCapture={startCaptureRetake} />}{active === 'capture' && <CaptureDesk key={captureGeneration} {...props} lotId={captureLot} onLot={setCaptureLot} retake={retake} onRetakeUsed={() => setRetake(null)} />}{active === 'review' && <Reviews {...props} selectedId={selectedReview} onSelect={setSelectedReview} onRetake={startRetake} />}{active === 'standards' && <Standards {...props} />}{active === 'issues' && <Issues {...props} team={team} selectedId={selectedIssue} onSelect={setSelectedIssue} initialLotId={selectedLot || captureLot} />}{active === 'validation' && <Validation {...props} runs={runs} />}{active === 'activity' && <Activity {...props} />}{active === 'team' && <Team {...props} team={team} />}</>}<footer className="pilot-footer">People make the final call. This workspace records inspection evidence and quality follow-up; representative factory validation is still required.</footer></main></div></div>
}
