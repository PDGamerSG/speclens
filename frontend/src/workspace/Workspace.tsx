import { ArrowDownToLine, ArrowLeftRight, ArrowRight, BookOpen, Box, Check, CheckCircle2, ChevronDown, ChevronRight, CircleHelp, ClipboardCheck, Clock3, FlaskConical, History, Layers3, LoaderCircle, MemoryStick, RefreshCw, ScanLine, Settings2, ShieldCheck, Sparkles, Upload, X, XCircle } from 'lucide-react'
import { useCallback, useEffect, useRef, useState } from 'react'
import { workspaceApi as api, dateTime, decision, time } from './api'
import { CorrectionForm } from './CorrectionForm'
import { PartViewer } from './PartViewer'
import { photoError } from './photo'
import type { Comparison, Correction, Inspection, Overview, PartInput, Sample, ScopeSettings, Status, View } from './types'

const DEFAULT_SCOPE: ScopeSettings = { factory: 'Bangalore Foods', part_family: 'Whole hazelnut', spec_text: '' }
const EMPTY_STATS = { inspections: 0, corrections: 0, synced: 0, pending: 0 }
const NAV = [{ id: 'inspect', label: 'Inspection desk', icon: ScanLine }, { id: 'standards', label: 'Quality memory', icon: BookOpen }, { id: 'history', label: 'Inspection history', icon: History }, { id: 'compare', label: 'Memory comparison', icon: ArrowLeftRight }] as const
function storedScope(): ScopeSettings {
  try { const s = JSON.parse(localStorage.getItem('speclens-scope') || 'null'); if (s && typeof s.factory === 'string' && typeof s.part_family === 'string' && typeof s.spec_text === 'string') return s }
  catch { /* A new workspace uses the documented defaults. */ }
  return DEFAULT_SCOPE
}
function message(error: unknown) { return error instanceof Error ? error.message : 'This action could not be completed.' }
function shortId(id: string) { return id.replace(/^(insp-|correction-|compare-)/, '').slice(0, 8).toUpperCase() }
function Badge({ verdict }: { verdict: string }) { return <span className={`decision-badge ${verdict}`}>{verdict === 'good' ? <Check size={12} /> : verdict === 'defect' ? <X size={12} /> : <CircleHelp size={12} />}{decision(verdict)}</span> }

export default function Workspace() {
  const [view, setView] = useState<View>('inspect')
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
  const [notice, setNotice] = useState<string | null>(null)
  const [correcting, setCorrecting] = useState(false)
  const [showSettings, setShowSettings] = useState(false)
  const [draft, setDraft] = useState<ScopeSettings>(scope)
  const [summary, setSummary] = useState<string | null>(null)
  const [comparison, setComparison] = useState<Comparison | null>(null)
  const [expected, setExpected] = useState('')
  const [historyQuery, setHistoryQuery] = useState('')
  const upload = useRef<HTMLInputElement>(null)
  const objectUrl = useRef<string | null>(null)
  const [loaded, setLoaded] = useState(false)
  const dialog = useRef<HTMLElement>(null)

  const refresh = useCallback(async () => {
    const [state, health] = await Promise.all([api.overview(scope), api.status()])
    setOverview(state); setStatus(health)
  }, [scope])
  useEffect(() => {
    let active = true
    Promise.all([api.status(), api.samples(), api.overview(scope)]).then(([health, pictures, state]) => {
      if (!active) return
      setStatus(health); setSamples(pictures.samples); setOverview(state); setLoaded(true)
      setInput(current => current || (pictures.samples[1] ? { sample: pictures.samples[1] } : null))
    }).catch(e => { if (active) { setError(message(e)); setLoaded(true) } })
    return () => { active = false }
  }, [scope])
  useEffect(() => {
    if (objectUrl.current) { URL.revokeObjectURL(objectUrl.current); objectUrl.current = null }
    if (input?.file) { objectUrl.current = URL.createObjectURL(input.file); setPreview(objectUrl.current) }
    else setPreview(input?.sample?.image_url || null)
  }, [input])
  useEffect(() => () => { if (objectUrl.current) URL.revokeObjectURL(objectUrl.current) }, [])
  useEffect(() => { if (!notice) return; const timer = setTimeout(() => setNotice(null), 7000); return () => clearTimeout(timer) }, [notice])

  useEffect(() => {
    if (!showSettings) return
    const previous = document.activeElement as HTMLElement | null
    const modal = dialog.current
    const focusable = () => Array.from(modal?.querySelectorAll<HTMLElement>('button:not([disabled]), input, textarea, select, [tabindex="0"]') || [])
    focusable()[0]?.focus()
    const onKey = (event: KeyboardEvent) => {
      if (event.key === 'Escape') { event.preventDefault(); setShowSettings(false) }
      if (event.key === 'Tab') {
        const items = focusable(), first = items[0], last = items.at(-1)
        if (event.shiftKey && document.activeElement === first) { event.preventDefault(); last?.focus() }
        else if (!event.shiftKey && document.activeElement === last) { event.preventDefault(); first?.focus() }
      }
    }
    document.addEventListener('keydown', onKey)
    return () => { document.removeEventListener('keydown', onKey); previous?.focus() }
  }, [showSettings])

  const choose = (part: PartInput) => {
    setInput(part); setResult(null); setComparison(null); setCorrecting(false); setError(null)
    setExpected(part.sample?.expected_verdict || '')
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
  const saveCorrection = (value: { verdict: 'good' | 'defect'; defect_type: string; rule_text: string; reviewer: string }) => act('correct', async () => {
    if (!result) return
    const saved = await api.correct({ inspection_id: result.id, ...value })
    setCorrecting(false)
    setNotice(saved.sync_status === 'synced' ? 'Correction saved. This standard is now available in Hindsight memory.' : 'Correction saved locally. Memory sync is pending; retry it from Quality memory.')
    await refresh()
  })
  const runComparison = () => { if (input) void act('compare', async () => {
    const next = await api.compare(input, scope, expected || input.sample?.expected_verdict || '')
    setComparison(next); setView('compare'); await refresh()
  }) }
  const currentCorrection = result ? overview?.corrections.find(c => c.inspection_id === result.id) : undefined
  const stats = overview?.stats || EMPTY_STATS
  const historyItems = (overview?.inspections || []).filter(item => {
    const reviewer = overview?.corrections.find(c => c.inspection_id === item.id)?.reviewer || ''
    return `${item.filename} ${item.id} ${reviewer}`.toLowerCase().includes(historyQuery.trim().toLowerCase())
  })
  const title = NAV.find(n => n.id === view)?.label || 'Inspection desk'
  const generated = !!input?.sample
  const partName = result?.filename || input?.file?.name || input?.sample?.name || ''
  const sourceCounts = new Set(result?.memories.map(m => m.source_id) || []).size
  const exportHistory = () => {
    const blob = new Blob([JSON.stringify({ exported_at: new Date().toISOString(), scope, ...overview }, null, 2)], { type: 'application/json' })
    const url = URL.createObjectURL(blob), anchor = document.createElement('a')
    anchor.href = url; anchor.download = 'speclens-inspection-records.json'; anchor.click(); URL.revokeObjectURL(url)
  }

  return <div className="workspace-shell">
    <aside className="sidebar">
      <button type="button" className="brand" onClick={() => setView('inspect')} aria-label="SpecLens inspection desk"><span className="brand-mark"><ScanLine size={23} strokeWidth={1.9} /></span><span>SpecLens<span className="brand-period">.</span></span></button>
      <button className="workspace-switch" disabled={!!busy} onClick={() => { setDraft(scope); setShowSettings(true) }}><span className="factory-mark"><Box size={17} /></span><span><strong>{scope.factory}</strong><small>Quality workspace</small></span><ChevronDown size={14} /></button>
      <div className="nav-caption">Workspace</div>
      <nav aria-label="Main navigation">{NAV.map(item => <button key={item.id} aria-label={item.label} aria-current={view === item.id ? 'page' : undefined} className={'nav-item' + (view === item.id ? ' active' : '')} onClick={() => { setView(item.id); setError(null) }}><item.icon size={18} strokeWidth={1.65} /><span>{item.label}</span>{item.id === 'standards' && stats.corrections > 0 && <span className="nav-count">{stats.corrections}</span>}</button>)}</nav>
      <div className="sidebar-note"><span className="note-icon"><MemoryStick size={18} /></span><h3>A better second look.</h3><p>Every correction helps the next inspection follow your standards.</p><button onClick={() => setView('standards')}>View quality memory <ArrowRight size={14} /></button></div>
      <div className="sidebar-bottom"><button className="nav-item" disabled={!!busy} onClick={() => { setDraft({ ...scope, spec_text: scope.spec_text || status?.default_spec || '' }); setShowSettings(true) }}><Settings2 size={17} /><span>Workspace settings</span></button><a className="nav-item" href="https://github.com/PDGamerSG/speclens#readme" target="_blank" rel="noreferrer"><CircleHelp size={17} /><span>Setup & documentation</span></a><div className="operator"><div className="avatar">QA</div><div><strong>Quality engineer</strong><span>Human review enabled</span></div><ShieldCheck size={17} /></div></div>
    </aside>

    <div className="workspace-main">
      <header className="topbar"><div className="breadcrumb"><Layers3 size={16} /><span>{scope.factory}</span><ChevronRight size={13} /><strong>{title}</strong></div><div className="topbar-right"><span className={'connection' + (status?.memory_configured ? ' configured' : '')}><span />{status?.memory_configured ? 'Memory configured' : 'Memory not connected'}</span><button className="icon-button settings-shortcut" aria-label="Workspace settings" disabled={!!busy} onClick={() => { setDraft({ ...scope, spec_text: scope.spec_text || status?.default_spec || '' }); setShowSettings(true) }}><Settings2 size={18} /></button><div className="avatar small-avatar">QA</div></div></header>
      <main className="main-content">
        <div className="page-heading"><div><div className="heading-meta"><span className="live-square" />Quality control workspace</div><h1>{title}</h1><p>{view === 'inspect' ? 'Your standards. Every part. A little more learned each time.' : view === 'standards' ? 'The decisions your team has taught the inspector to remember.' : view === 'history' ? 'A traceable record of every inspection and human correction.' : 'Keep the part and specification fixed. See what memory changes.'}</p></div><button className="button secondary" onClick={() => upload.current?.click()} title="JPG, PNG or WebP · up to 8 MB" disabled={!!busy}><Upload size={16} />Upload part</button></div>
        <input ref={upload} type="file" accept="image/jpeg,image/png,image/webp" className="sr-only" aria-label="Upload part photo" onChange={e => { const file = e.target.files?.[0]; if (file && !busy) { const issue = photoError(file); if (issue) setError(issue); else { choose({ file }); setView('inspect') } }; e.target.value = '' }} />
        {error && <div className="alert error" role="alert"><XCircle size={18} /><span>{error}</span><button className="icon-button" aria-label="Dismiss error" onClick={() => setError(null)}><X size={16} /></button></div>}
        {notice && <div className="alert success" role="status"><CheckCircle2 size={18} /><span>{notice}</span><button className="icon-button" aria-label="Dismiss notification" onClick={() => setNotice(null)}><X size={16} /></button></div>}
        {!status?.model_configured && loaded && <div className="setup-banner"><Settings2 size={17} /><span>Workspace ready for setup. Connect the vision model and Hindsight to run live inspections.</span><button disabled={!!busy} onClick={() => { setDraft(scope); setShowSettings(true) }}>Connection details <ArrowRight size={14} /></button></div>}
        <div className="workspace-stats"><Stat icon={<ScanLine size={18} />} label="Parts inspected" value={stats.inspections} detail="In this workspace" /><Stat icon={<ClipboardCheck size={18} />} label="Human corrections" value={stats.corrections} detail="Standards from your team" /><Stat icon={<MemoryStick size={18} />} label="Remembered corrections" value={stats.synced} detail={stats.pending ? `${stats.pending} waiting to sync` : 'Saved to Hindsight'} accent /></div>

        {view === 'inspect' && <div className="inspection-layout">
          <section className="inspection-column"><div className="panel image-panel"><div className="panel-heading"><div><h2>Part inspection</h2><span className="small muted">{scope.part_family}</span></div><span className="subtle-pill"><span className="dot teal" />Visual inspection</span></div><PartViewer key={result?.image_url || preview || 'empty'} url={result?.image_url || preview} name={partName} result={result} busy={busy === 'inspect'} generated={generated} /><div className="sample-picker"><div className="section-heading"><h3>Try a sample part</h3><span className="small muted">Generated inspection examples</span></div><div className="samples">{samples.map(sample => <button key={sample.id} className={'sample-button' + (input?.sample?.id === sample.id ? ' selected' : '')} onClick={() => choose({ sample })} disabled={!!busy}><span className="sample-photo"><img src={sample.image_url} alt="" />{input?.sample?.id === sample.id && <span className="selected-check"><Check size={11} /></span>}</span><span>{sample.name}</span></button>)}</div></div></div><div className="workflow-note"><ShieldCheck size={18} /><div><strong>Your team makes the final call.</strong><span>SpecLens supports quality decisions. Review uncertain parts before release.</span></div></div></section>
          <aside className="decision-column"><section className="panel decision-panel"><div className="panel-heading"><h2>Inspection decision</h2><span className="subtle-text">{result ? shortId(result.id) : 'Ready when you are'}</span></div>
            <div className="memory-toggle-row"><div className="memory-label"><MemoryStick size={17} /><span>Use quality memory<small>Apply your team’s corrections</small></span></div><button role="switch" aria-checked={memory} aria-label="Use quality memory" className={'toggle' + (memory ? ' on' : '')} onClick={() => setMemory(!memory)} disabled={!!busy}><span /></button></div>
            {busy === 'inspect' ? <div className="decision-empty"><div className="empty-icon processing"><LoaderCircle className="spin" size={26} /></div><h3>Looking at the details</h3><p>{memory ? 'Recalling standards and checking this part against your specification.' : 'Checking this part against the base specification.'}</p></div> : result ? <div className="decision-result"><div className={'large-verdict ' + result.verdict}>{result.verdict === 'good' ? <CheckCircle2 size={30} strokeWidth={1.7} /> : result.verdict === 'defect' ? <XCircle size={30} strokeWidth={1.7} /> : <CircleHelp size={30} />}<div><h3>{decision(result.verdict)} part</h3><p>{result.verdict === 'good' ? 'Meets the visual specification' : result.verdict === 'defect' ? `${result.type.charAt(0).toUpperCase() + result.type.slice(1)} detected` : 'Needs a closer human review'}</p></div></div><div className="confidence-row"><span>Model confidence</span><strong>{Math.round(Math.max(0, Math.min(1, result.confidence)) * 100)}%</strong></div><div className="confidence-track"><span className={result.verdict} style={{ width: `${Math.max(0, Math.min(1, result.confidence)) * 100}%` }} /></div><div className="reasoning"><h4>Why this decision</h4><p>{result.rationale}</p></div><div className="inspection-meta"><span><Clock3 size={13} />{(result.ms / 1000).toFixed(1)}s</span><span>{result.memory_enabled ? `${sourceCounts} recalled standard${sourceCounts === 1 ? '' : 's'}` : 'Memory off'}</span></div>{currentCorrection ? <div className="reviewed-note"><CheckCircle2 size={15} /><span>Reviewed: {decision(currentCorrection.verdict).toLowerCase()} · {currentCorrection.reviewer}</span></div> : <button className="button secondary full-width" onClick={() => setCorrecting(!correcting)} disabled={!!busy}><ClipboardCheck size={16} />Correct this decision</button>}</div> : <div className="decision-empty"><div className="empty-icon"><ScanLine size={27} strokeWidth={1.4} /></div><h3>A fresh set of eyes</h3><p>Inspect this part to see its decision, reasoning, and recalled standards.</p></div>}
            {!correcting && <div className="decision-actions"><button className="button primary full-width large-button" onClick={inspect} disabled={!!busy || !loaded || !input}>{busy === 'inspect' ? <LoaderCircle className="spin" size={17} /> : <ScanLine size={17} />}{busy === 'inspect' ? 'Inspecting part…' : result ? 'Inspect again' : 'Inspect part'}{!busy && <ArrowRight size={16} />}</button><span className="action-footnote">{memory ? 'Vision + your quality memory' : 'Vision with the base specification'}</span></div>}
            {correcting && result && <CorrectionForm key={result.id} inspection={result} onSave={saveCorrection} onClose={() => setCorrecting(false)} busy={busy === 'correct'} />}
          </section>
          <section className="panel recalled-panel"><div className="panel-heading"><h2><Sparkles size={16} />Recalled for this part</h2>{sourceCounts > 0 && <span className="count-badge">{sourceCounts}</span>}</div>{result?.memories.length ? <div className="recalled-list">{Array.from(new Map(result.memories.map(fact => [fact.source_id, fact])).values()).map(fact => <div className="recalled-standard" key={fact.source_id}><span className="rule-line" /><p>{fact.rule_text || fact.text}</p><span>Correction {shortId(fact.source_id)} · {fact.reviewer || 'Quality engineer'}</span></div>)}</div> : <div className="memory-empty"><BookOpen size={22} strokeWidth={1.3} /><p>{result?.memory_status === 'disabled' ? 'Memory was off for this inspection.' : 'Your corrections will appear here when they are recalled for an inspection.'}</p></div>}<button className="panel-link" onClick={() => setView('standards')}>Open quality memory<ArrowRight size={14} /></button></section>
          {result && <button className="comparison-shortcut" onClick={() => { setView('compare'); setComparison(null) }}><FlaskConical size={18} /><span>See what memory changes<small>Compare the same part with memory off and on</small></span><ChevronRight size={17} /></button>}
          </aside>
        </div>}

        {view === 'standards' && <><div className="section-toolbar"><div><h2>Standards learned from your team</h2><p className="muted small">Scoped to {scope.factory} and {scope.part_family.toLowerCase()}. A specification change starts a separate memory.</p></div><button className="button secondary" onClick={() => void act('reflect', async () => { const r = await api.reflect(scope); setSummary(r.summary) })} disabled={!!busy || !stats.synced}>{busy === 'reflect' ? <LoaderCircle size={15} className="spin" /> : <Sparkles size={15} />}Summarize standards</button></div>{summary && <section className="panel reflection"><h3><Sparkles size={17} />What your inspector has learned</h3><p>{summary}</p><span className="small muted">Generated from Hindsight memory. Review the supporting corrections below.</span></section>}{overview?.corrections.length ? <div className="standards-grid">{overview.corrections.map(c => <Standard key={c.id} correction={c} busy={!!busy} onRetry={() => void act('sync', async () => { const saved = await api.sync(c.id); if (saved.sync_status === 'pending') throw new Error(saved.sync_error || 'Memory sync is still pending.'); await refresh(); setNotice('Correction synced to Hindsight.') })} />)}</div> : <Empty icon={<BookOpen size={35} strokeWidth={1.25} />} title="Your standards start with a correction" text="Inspect a sample, review the decision, and describe what the inspector should remember next time." action="Go to inspection desk" onAction={() => setView('inspect')} />}</>}

        {view === 'history' && <section className="panel history-panel"><div className="panel-heading"><h2>Inspection records</h2><div className="history-controls"><input type="search" aria-label="Search inspection history" placeholder="Part, ID or reviewer" value={historyQuery} onChange={e => setHistoryQuery(e.target.value)} /><button className="button secondary compact" onClick={exportHistory} disabled={!overview?.inspections.length}><ArrowDownToLine size={14} />Export records</button></div></div>{overview?.inspections.length ? <div className="table-scroll"><table><thead><tr><th>Part</th><th>Model decision</th><th>Memory</th><th>Confidence</th><th>Human decision</th><th>Time</th><th><span className="sr-only">Open</span></th></tr></thead><tbody>{historyItems.map(item => { const correction = overview.corrections.find(c => c.inspection_id === item.id); return <tr key={item.id}><td><div className="table-part"><img src={item.image_url} alt="" /><span><strong>{item.filename}</strong><small>{shortId(item.id)}</small></span></div></td><td><Badge verdict={item.verdict} /></td><td><span className={'table-memory' + (item.memory_enabled ? ' enabled' : '')}><MemoryStick size={13} />{item.memory_status === 'recalled' ? `${new Set(item.memories.map(m => m.source_id)).size} standard(s)` : item.memory_enabled ? 'No standards recalled' : 'Off'}</span></td><td>{Math.round(item.confidence * 100)}%</td><td>{correction ? <span className="review-label"><Check size={13} />{decision(correction.verdict)} · {correction.reviewer}</span> : <span className="muted">Unreviewed</span>}</td><td className="nowrap">{time(item.created_at)}</td><td><button className="icon-button" aria-label={`Open inspection ${shortId(item.id)}`} disabled={!!busy} onClick={() => { setResult(item); setInput(null); setCorrecting(false); setView('inspect') }}><ChevronRight size={17} /></button></td></tr> })}{!historyItems.length && <tr><td colSpan={7} className="history-no-matches">No matching inspections. Try another part, ID, or reviewer.</td></tr>}</tbody></table><div className="history-count" role="status">Showing {historyItems.length} of {overview.inspections.length} inspections. Export includes every record.</div></div> : <Empty icon={<History size={35} strokeWidth={1.25} />} title="A clear trail for every decision" text="Your inspections and human corrections will be recorded here, including the standards recalled for each part." action="Inspect your first part" onAction={() => setView('inspect')} />}</section>}

        {view === 'compare' && <div className="comparison-view"><section className="panel compare-setup"><div className="panel-heading"><div><h2>One part. Two inspections.</h2><p className="small muted">Same model and base specification. Only recalled memory changes.</p></div><FlaskConical size={23} className="muted" /></div><div className="compare-input"><img src={comparison?.baseline.image_url || preview || result?.image_url || samples[0]?.image_url} alt="Selected part for comparison" /><div><strong>{comparison?.baseline.filename || partName || 'Select a sample part'}</strong><p className="small muted">{comparison ? 'Recorded comparison · choose another part to run a new pair' : generated ? 'Generated sample · use another part after teaching a correction' : 'Upload a different part to check whether a standard transfers'}</p><select aria-label="Choose comparison sample" value={input?.sample?.id || ''} onChange={e => { const s = samples.find(s => s.id === e.target.value); if (s) choose({ sample: s }) }} disabled={!!busy}><option value="" disabled>Choose a sample part</option>{samples.map(s => <option key={s.id} value={s.id}>{s.name}</option>)}</select></div><label className="field-label expected-select">Expected decision<select value={expected || input?.sample?.expected_verdict || ''} onChange={e => setExpected(e.target.value)} disabled={!!busy}><option value="">Not labeled</option><option value="good">Accept</option><option value="defect">Reject</option></select></label><button className="button primary" onClick={runComparison} disabled={!!busy || !loaded || !input}>{busy === 'compare' ? <LoaderCircle size={16} className="spin" /> : <ArrowLeftRight size={16} />}{busy === 'compare' ? 'Running both inspections…' : 'Run comparison'}</button></div></section>
          {comparison ? <><div className="comparison-arms"><ComparisonArm label="Without memory" item={comparison.baseline} /><ComparisonArm label="With quality memory" item={comparison.with_memory} enhanced /></div><div className="comparison-disclosure"><FlaskConical size={18} /><p><strong>{comparison.changed ? 'The decisions differ on this part.' : 'Both inspections reached the same decision.'}</strong> {comparison.note} {!comparison.held_out && 'This image was used for a correction. Try a different part to check transfer.'}</p></div></> : <div className="comparison-explainer"><div><span className="comparison-step"><ScanLine size={21} /></span><h3>Inspect a part</h3><p>Start with the base specification.</p></div><ChevronRight size={18} /><div><span className="comparison-step"><ClipboardCheck size={21} /></span><h3>Teach a standard</h3><p>Correct a decision with a clear reason.</p></div><ChevronRight size={18} /><div><span className="comparison-step"><MemoryStick size={21} /></span><h3>Try another part</h3><p>See the recalled standard in action.</p></div></div>}
          {!!overview?.comparisons.length && <section className="panel previous-comparisons"><div className="panel-heading"><h2>Comparison history</h2><span className="small muted">Observed decisions, without assumed gains</span></div>{overview.comparisons.map(pair => <button className="comparison-history-row" key={pair.id} disabled={!!busy} onClick={() => { setComparison(pair); setInput(null); setExpected(pair.expected_verdict || '') }}><img src={pair.baseline.image_url} alt="" /><span><strong>{pair.baseline.filename}</strong><small>{dateTime(pair.created_at)} · {pair.held_out ? 'Not used for a correction' : 'Correction image'}</small></span><span>Memory off <Badge verdict={pair.baseline.verdict} /></span><ArrowRight size={14} /><span>Memory on <Badge verdict={pair.with_memory.verdict} /></span><ChevronRight size={16} /></button>)}</section>}
        </div>}
        <footer className="workspace-footer"><span><ShieldCheck size={13} />Decisions stay traceable. People stay in control.</span><span>Memory by <a href="https://hindsight.vectorize.io/" target="_blank" rel="noreferrer">Hindsight</a><span className="footer-divider" />SpecLens 0.1</span></footer>
      </main>
    </div>

    {showSettings && <div className="modal-backdrop"><button type="button" className="modal-dismiss" aria-label="Close workspace settings" onClick={() => setShowSettings(false)} /><section className="settings-modal" ref={dialog} role="dialog" aria-modal="true" aria-labelledby="settings-title"><div className="panel-heading"><h2 id="settings-title">Workspace settings</h2><button className="icon-button" aria-label="Close settings" onClick={() => setShowSettings(false)}><X size={19} /></button></div><form onSubmit={e => { e.preventDefault(); if (busy) return; const next = { factory: draft.factory.trim(), part_family: draft.part_family.trim(), spec_text: draft.spec_text.trim() }; localStorage.setItem('speclens-scope', JSON.stringify(next)); setLoaded(false); setOverview(null); setScope(next); setResult(null); setComparison(null); setCorrecting(false); setSummary(null); setHistoryQuery(''); setError(null); setShowSettings(false) }}><label className="field-label">Factory or workspace<input value={draft.factory} onChange={e => setDraft({ ...draft, factory: e.target.value })} required maxLength={100} /></label><label className="field-label">Part family<input value={draft.part_family} onChange={e => setDraft({ ...draft, part_family: e.target.value })} required maxLength={100} /></label><label className="field-label">Base quality specification<textarea value={draft.spec_text || status?.default_spec || ''} onChange={e => setDraft({ ...draft, spec_text: e.target.value })} rows={8} maxLength={12000} /></label><p className="small muted">Memory is separated by factory, part family, and specification. Editing this specification starts a separate memory bank.</p><div className="connection-details"><h3>Server connections</h3><div><span>Vision model</span><span className={status?.model_configured ? 'text-teal' : 'text-amber'}>{status?.model_configured ? 'Configured' : 'MODEL_API_KEY needed'}</span></div><div><span>Hindsight memory</span><span className={status?.memory_configured ? 'text-teal' : 'text-amber'}>{status?.memory_configured ? 'Endpoint configured' : 'Connection needed'}</span></div><p>Credentials are configured on the server in .env and never sent to this browser.</p></div><button type="submit" className="button primary full-width" disabled={!!busy}>Save workspace</button></form></section></div>}
  </div>
}

function Stat({ icon, label, value, detail, accent = false }: { icon: React.ReactNode; label: string; value: number; detail: string; accent?: boolean }) {
  return <div className={'stat' + (accent ? ' accent' : '')}><span className="stat-icon">{icon}</span><div><span className="stat-label">{label}</span><div className="stat-value">{value}<span>{detail}</span></div></div></div>
}
function Empty({ icon, title, text, action, onAction }: { icon: React.ReactNode; title: string; text: string; action: string; onAction: () => void }) {
  return <div className="empty-state"><span className="empty-state-icon">{icon}</span><h2>{title}</h2><p>{text}</p><button className="button primary" onClick={onAction}>{action}<ArrowRight size={15} /></button></div>
}
function Standard({ correction: c, busy, onRetry }: { correction: Correction; busy: boolean; onRetry: () => void }) {
  return <article className="panel standard-card"><div className="standard-card-top"><span className="standard-icon"><BookOpen size={19} /></span><span className={'sync-badge ' + c.sync_status}>{c.sync_status === 'synced' ? <CheckCircle2 size={12} /> : <Clock3 size={12} />}{c.sync_status === 'synced' ? 'In memory' : 'Sync pending'}</span></div><h3>{c.defect_type === 'good' ? 'Acceptable appearance' : `${c.defect_type.charAt(0).toUpperCase() + c.defect_type.slice(1)} standard`}</h3><p className="standard-rule">{c.rule_text}</p><div className="standard-source"><img src={c.image_url} alt="Source part for this correction" /><span><strong>{c.reviewer}</strong><small>{dateTime(c.created_at)}</small></span><Badge verdict={c.verdict} /></div><details className="source-reasoning"><summary>Original inspection reasoning<ChevronDown size={13} /></summary><p>{c.original_rationale}</p><span className="small muted">Correction {shortId(c.id)}</span></details>{c.sync_status === 'pending' && <div className="pending-note"><p>{c.sync_error || 'This correction is saved locally and is waiting to sync to Hindsight.'}</p><button className="button secondary compact" onClick={onRetry} disabled={busy}><RefreshCw size={13} />Retry sync</button></div>}</article>
}
function ComparisonArm({ label, item, enhanced = false }: { label: string; item: Inspection; enhanced?: boolean }) {
  return <section className={'panel comparison-arm' + (enhanced ? ' enhanced' : '')}><div className="panel-heading"><h2>{enhanced ? <MemoryStick size={17} /> : <ScanLine size={17} />}{label}</h2><Badge verdict={item.verdict} /></div><h3>{decision(item.verdict)} part</h3><p>{item.rationale}</p><div className="comparison-arm-meta"><span>{Math.round(item.confidence * 100)}% confidence</span><span>{(item.ms / 1000).toFixed(1)}s</span></div>{enhanced && <div className="comparison-memory"><BookOpen size={15} /><span>{new Set(item.memories.map(m => m.source_id)).size} correction(s) recalled</span></div>}</section>
}
