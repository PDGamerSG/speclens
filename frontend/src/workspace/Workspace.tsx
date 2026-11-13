import { BarChart3, BookOpen, Camera, CheckCircle2, ChevronDown, History, RefreshCw, ScanLine, Settings2, ArrowLeftRight, Upload, X, XCircle } from 'lucide-react'
import { useCallback, useEffect, useRef, useState } from 'react'
import { workspaceApi as api } from './api'
import { BatchSection } from './Batch'
import { Chief } from './Chief'
import { DashboardSection } from './Dashboard'
import { downloadJson } from './download'
import { InkFilter, Rolling } from './marks'
import { PartViewer } from './PartViewer'
import { photoError } from './photo'
import { CompareSection, RecordsSection, StandardsSection } from './sections'
import { SettingsDialog } from './SettingsDialog'
import { Ticket, type CorrectionValue } from './Ticket'
import type { Comparison, DashboardData, Inspection, Overview, PartInput, Sample, ScopeSettings, Section, Status } from './types'

const DEFAULT_SCOPE: ScopeSettings = { factory: 'Bangalore Foods', part_family: 'Whole hazelnut', spec_text: '' }
const EMPTY_STATS = { inspections: 0, corrections: 0, synced: 0, pending: 0 }
const NAV: { id: Section; label: string; short: string; icon: typeof ScanLine }[] = [
  { id: 'inspect', label: 'Inspection desk', short: 'Inspect', icon: ScanLine },
  { id: 'standards', label: 'Quality memory', short: 'Memory', icon: BookOpen },
  { id: 'compare', label: 'Memory comparison', short: 'Compare', icon: ArrowLeftRight },
  { id: 'dashboard', label: 'Quality dashboard', short: 'Trends', icon: BarChart3 },
  { id: 'history', label: 'Inspection history', short: 'History', icon: History },
]

function storedScope(): ScopeSettings {
  try {
    const saved = JSON.parse(localStorage.getItem('speclens-scope') || 'null')
    if (saved && typeof saved.factory === 'string' && typeof saved.part_family === 'string' && typeof saved.spec_text === 'string') return saved
  } catch { /* A new workspace uses the documented defaults. */ }
  return DEFAULT_SCOPE
}
const message = (error: unknown) => error instanceof Error ? error.message : 'This action could not be completed.'

export default function Workspace() {
  const [scope, setScope] = useState<ScopeSettings>(storedScope)
  const [status, setStatus] = useState<Status | null>(null)
  const [samples, setSamples] = useState<Sample[]>([])
  const [overview, setOverview] = useState<Overview | null>(null)
  const [input, setInput] = useState<PartInput | null>(null)
  const [preview, setPreview] = useState<string | null>(null)
  const [result, setResult] = useState<Inspection | null>(null)
  const [memory, setMemory] = useState(true)
  const [busy, setBusy] = useState<string | null>(null)
  const [error, setError] = useState<string | null>(null)
  const [connectionError, setConnectionError] = useState<string | null>(null)
  const [connectionAttempt, setConnectionAttempt] = useState(0)
  const [notice, setNotice] = useState<string | null>(null)
  const [correcting, setCorrecting] = useState(false)
  const [showSettings, setShowSettings] = useState(false)
  const [summary, setSummary] = useState<string | null>(null)
  const [comparison, setComparison] = useState<Comparison | null>(null)
  const [openedRecord, setOpenedRecord] = useState(false)
  const [expected, setExpected] = useState('')
  const [historyQuery, setHistoryQuery] = useState('')
  const [loaded, setLoaded] = useState(false)
  const [active, setActive] = useState<Section>('inspect')
  const [board, setBoard] = useState<DashboardData | null>(null)
  const [days, setDays] = useState(30)
  const upload = useRef<HTMLInputElement>(null)
  const camera = useRef<HTMLInputElement>(null)
  const currentInput = useRef<PartInput | null>(null)
  const objectUrl = useRef<string | null>(null)

  const selectInput = useCallback((part: PartInput | null) => {
    currentInput.current = part
    setInput(part)
    if (part) setExpected(part.sample?.expected_verdict || '')
  }, [])
  const refresh = useCallback(async () => {
    const [state, health] = await Promise.all([api.overview(scope), api.status()])
    setOverview(state); setStatus(health)
    api.dashboard(scope, days).then(setBoard).catch(() => { /* The dashboard is secondary; the desk keeps working. */ })
  }, [scope, days])
  useEffect(() => {
    const lifecycle = new AbortController()
    api.dashboard(scope, days).then(next => { if (!lifecycle.signal.aborted) setBoard(next) }).catch(() => { /* Shown as loading. */ })
    return () => lifecycle.abort()
  }, [scope, days])

  useEffect(() => {
    const lifecycle = new AbortController()
    Promise.all([api.status(), api.samples(), api.overview(scope)]).then(([health, pictures, state]) => {
      if (lifecycle.signal.aborted) return
      setStatus(health); setSamples(pictures.samples); setOverview(state); setLoaded(true)
      setConnectionError(null)
      if (!currentInput.current && pictures.samples[1]) selectInput({ sample: pictures.samples[1] })
    }).catch(e => { if (!lifecycle.signal.aborted) setConnectionError(message(e)) })
    return () => lifecycle.abort()
  }, [scope, connectionAttempt, selectInput])
  useEffect(() => {
    if (objectUrl.current) { URL.revokeObjectURL(objectUrl.current); objectUrl.current = null }
    if (input?.file) { objectUrl.current = URL.createObjectURL(input.file); setPreview(objectUrl.current) }
    else setPreview(input?.sample?.image_url || null)
  }, [input])
  useEffect(() => () => { if (objectUrl.current) URL.revokeObjectURL(objectUrl.current) }, [])
  useEffect(() => {
    if (!notice) return
    const timer = setTimeout(() => setNotice(null), 7000)
    return () => clearTimeout(timer)
  }, [notice])
  useEffect(() => {
    const watcher = new IntersectionObserver(entries => {
      for (const entry of entries) if (entry.isIntersecting) setActive(entry.target.id as Section)
    }, { rootMargin: '-35% 0px -60% 0px' })
    for (const item of NAV) { const section = document.getElementById(item.id); if (section) watcher.observe(section) }
    // The last section can be too short to reach the observer band, so the end of the page selects it.
    const atEnd = () => { if (window.innerHeight + window.scrollY >= document.documentElement.scrollHeight - 4) setActive('history') }
    window.addEventListener('scroll', atEnd, { passive: true })
    return () => { watcher.disconnect(); window.removeEventListener('scroll', atEnd) }
  }, [])

  const goTo = (id: Section) => {
    setActive(id)
    document.getElementById(id)?.scrollIntoView({ block: 'start' })
  }
  const choose = (part: PartInput) => {
    selectInput(part); setResult(null); setComparison(null); setOpenedRecord(false); setCorrecting(false); setError(null)
  }
  const takeFile = (file: File) => {
    if (busy) return
    const issue = photoError(file)
    if (issue) setError(issue)
    else choose({ file })
  }
  const act = async (label: string, operation: () => Promise<void>) => {
    if (busy || !loaded) return
    setBusy(label); setError(null); setNotice(null)
    try { await operation() } catch (e) { setError(message(e)) } finally { setBusy(null) }
  }
  const inspect = () => { if (input) void act('inspect', async () => {
    const next = await api.inspect(input, scope, memory)
    setResult(next); setCorrecting(false)
    await refresh()
  }) }
  const saveCorrection = (value: CorrectionValue) => act('correct', async () => {
    if (!result) return
    const saved = await api.correct({ inspection_id: result.id, ...value })
    setCorrecting(false)
    setNotice(saved.sync_status === 'synced' ? 'Correction saved. This standard is now available in Hindsight memory.' : 'Correction saved here. Memory sync is pending; retry it from Quality memory.')
    await refresh()
  })
  const runComparison = () => { if (input) void act('compare', async () => {
    const next = await api.compare(input, scope, expected)
    setComparison(next); setOpenedRecord(false)
    await refresh()
  }) }
  const retrySync = (id: string) => void act('sync', async () => {
    const saved = await api.sync(id)
    if (saved.sync_status === 'pending') throw new Error(saved.sync_error || 'Memory sync is still pending.')
    await refresh()
    setNotice('Correction synced to Hindsight.')
  })
  const openSettings = () => setShowSettings(true)
  const closeSettings = useCallback(() => setShowSettings(false), [])
  const saveSettings = (next: ScopeSettings) => {
    localStorage.setItem('speclens-scope', JSON.stringify(next))
    setLoaded(false); setOverview(null); setScope(next); setResult(null); setComparison(null); setOpenedRecord(false)
    setCorrecting(false); setSummary(null); setHistoryQuery(''); setError(null); setConnectionError(null); setShowSettings(false); setBoard(null)
  }

  const correction = result ? overview?.corrections.find(c => c.inspection_id === result.id) : undefined
  const stats = overview?.stats || EMPTY_STATS
  const generated = result ? result.source_kind === 'synthetic_sample' : !!input?.sample
  const partName = result?.filename || input?.file?.name || input?.sample?.name || ''

  return <div className="page">
    <InkFilter />
    <header className="topbar">
      <button type="button" className="brand" onClick={() => goTo('inspect')} aria-label="SpecLens inspection desk"><Chief size={40} /><span>SpecLens.</span></button>
      <nav className="main-nav" aria-label="Main navigation">
        {NAV.map(item => <button key={item.id} aria-label={item.label} aria-current={active === item.id ? 'true' : undefined} className={'nav-item' + (active === item.id ? ' active' : '')} onClick={() => goTo(item.id)}>
          <item.icon size={17} strokeWidth={1.8} /><span>{item.short}</span>
        </button>)}
      </nav>
      <div className="topbar-right">
        <button className="workspace-switch" disabled={!!busy} onClick={openSettings}><span><strong>{scope.factory}</strong><small>{scope.part_family}</small></span><ChevronDown size={14} /></button>
        <button className="icon-button settings-shortcut" aria-label="Workspace settings" disabled={!!busy} onClick={openSettings}><Settings2 size={18} /></button>
      </div>
    </header>

    <div className="toasts">
      {(error || connectionError) && <div className="alert error" role="alert">
        <XCircle size={18} /><span>{error || connectionError}</span>
        {connectionError
          ? <button className="button secondary compact" onClick={() => { setConnectionError(null); setError(null); setLoaded(false); setConnectionAttempt(attempt => attempt + 1) }}><RefreshCw size={14} />Retry connection</button>
          : <button className="icon-button" aria-label="Dismiss error" onClick={() => setError(null)}><X size={16} /></button>}
      </div>}
      {notice && <div className="alert success" role="status"><CheckCircle2 size={18} /><span>{notice}</span><button className="icon-button" aria-label="Dismiss notification" onClick={() => setNotice(null)}><X size={16} /></button></div>}
    </div>

    <main className="content">
      <section id="inspect" className="bench-section" aria-labelledby="inspect-title">
        <div className="hero-line">
          <h1>Correct it once. It remembers the next part.</h1>
          <dl className="tally">
            <div><dt>Inspected</dt><dd><Rolling value={stats.inspections} /></dd></div>
            <div><dt>Corrected</dt><dd><Rolling value={stats.corrections} /></dd></div>
            <div><dt>{stats.pending ? `${stats.pending} waiting to sync` : 'In memory'}</dt><dd><Rolling value={stats.synced} /></dd></div>
          </dl>
        </div>
        <h2 id="inspect-title" className="sr-only">Inspection desk</h2>
        {loaded && !status?.model_configured && <button className="setup-banner" disabled={!!busy} onClick={openSettings}><Settings2 size={16} />The vision model is not connected, so inspections will show a setup error. See connection details.</button>}
        <div className="bench">
          <div className="bench-main">
            <PartViewer url={result?.image_url || preview} name={partName} result={result} busy={busy === 'inspect' || busy === 'compare'} generated={generated} onFile={takeFile} />
            <div className="part-rail" role="group" aria-label="Choose a part">
              <button className={'rail-tile rail-upload' + (input?.file ? ' selected' : '')} onClick={() => upload.current?.click()} title="JPG, PNG or WebP, up to 8 MB" disabled={!!busy}>
                <span className="rail-photo">{input?.file && preview ? <img src={preview} alt="" /> : <Upload size={20} />}</span><span>Upload part</span>
              </button>
              <button className="rail-tile rail-camera" onClick={() => camera.current?.click()} title="Use the phone camera, top-down, one part in frame" disabled={!!busy}>
                <span className="rail-photo"><Camera size={20} /></span><span>Take photo</span>
              </button>
              {samples.map(sample => <button key={sample.id} className={'rail-tile' + (input?.sample?.id === sample.id ? ' selected' : '')} onClick={() => choose({ sample })} disabled={!!busy}>
                <span className="rail-photo"><img src={sample.image_url} alt="" /></span><span>{sample.name}</span>
              </button>)}
            </div>
            <input ref={upload} type="file" accept="image/jpeg,image/png,image/webp" className="sr-only" aria-label="Upload part photo" onChange={e => {
              const file = e.target.files?.[0]
              if (file) takeFile(file)
              e.target.value = ''
            }} />
            <input ref={camera} type="file" accept="image/*" capture="environment" className="sr-only" tabIndex={-1} aria-label="Take a part photo" onChange={e => {
              const file = e.target.files?.[0]
              if (file) takeFile(file)
              e.target.value = ''
            }} />
          </div>
          <Ticket result={result} correction={correction} classes={overview?.taxonomy?.classes} busy={busy} ready={loaded} canInspect={!!input} memory={memory} onMemory={setMemory}
            correcting={correcting} onCorrecting={setCorrecting} onInspect={inspect} onSave={saveCorrection} onCompare={() => goTo('compare')} />
        </div>
      </section>

      <BatchSection scope={scope} memory={memory} busy={!!busy || !loaded} onFinished={() => void refresh()}
        onOpen={item => { setResult(item); selectInput(null); setCorrecting(false); goTo('inspect') }} />

      <StandardsSection corrections={overview?.corrections || []} summary={summary} synced={stats.synced} busy={busy} part={scope.part_family} factory={scope.factory}
        onSummarize={() => void act('reflect', async () => { const reply = await api.reflect(scope); setSummary(reply.summary) })} onRetry={retrySync} onInspect={() => goTo('inspect')} />

      <CompareSection comparison={comparison} history={overview?.comparisons || []} samples={samples} selectedSample={openedRecord ? '' : input?.sample?.id || ''}
        partName={partName} preview={preview} generated={generated} expected={expected} busy={busy} canRun={loaded && !!input && !openedRecord}
        onSample={sample => choose({ sample })} onExpected={setExpected} onRun={runComparison}
        onOpen={pair => { setComparison(pair); setOpenedRecord(true); setExpected(pair.expected_verdict || '') }}
        onExport={() => { if (comparison) downloadJson(`speclens-${comparison.id}.json`, { format_version: 1, exported_at: new Date().toISOString(), ...comparison }) }} />

      <DashboardSection data={board} days={days} part={scope.part_family} factory={scope.factory} onDays={setDays} onInspect={() => goTo('inspect')} />

      <RecordsSection overview={overview} query={historyQuery} busy={!!busy} onQuery={setHistoryQuery}
        onExport={() => downloadJson('speclens-inspection-records.json', { format_version: 1, exported_at: new Date().toISOString(), scope, ...overview })}
        onOpen={item => { setResult(item); selectInput(null); setCorrecting(false); goTo('inspect') }} onInspect={() => goTo('inspect')} />
    </main>

    <footer className="page-footer">
      <span>People make the final call. Every decision stays traceable.</span>
      <span>Memory by <a href="https://hindsight.vectorize.io/" target="_blank" rel="noreferrer">Hindsight</a></span>
      <a href="https://github.com/PDGamerSG/speclens#readme" target="_blank" rel="noreferrer">Setup and source</a>
    </footer>

    {showSettings && <SettingsDialog initial={{ ...scope, spec_text: scope.spec_text || status?.default_spec || '' }} status={status} busy={!!busy} onClose={closeSettings} onSave={saveSettings}
      onDeleted={removed => {
        setShowSettings(false); setResult(null); setComparison(null); setOpenedRecord(false); setSummary(null); setBoard(null)
        setNotice(`Deleted ${removed.inspections} inspection${removed.inspections === 1 ? '' : 's'} and ${removed.corrections} correction${removed.corrections === 1 ? '' : 's'}${removed.memory_failed ? '. Some memory could not be removed yet; try again later' : ''}.`)
        void refresh()
      }} />}
  </div>
}
