import { ArrowDownToLine, ArrowLeftRight, Check, CheckCircle2, ChevronDown, ChevronRight, CircleHelp, Clock3, LoaderCircle, MemoryStick, RefreshCw, ScanLine, Sparkles, X } from 'lucide-react'
import type { ReactNode } from 'react'
import { dateTime, decision, shortId } from './api'
import { Chief } from './Chief'
import type { Comparison, Correction, Inspection, Overview, Sample } from './types'

export function Badge({ verdict }: { verdict: string }) {
  return <span className={`decision-badge ${verdict}`}>{verdict === 'good' ? <Check size={12} /> : verdict === 'defect' ? <X size={12} /> : <CircleHelp size={12} />}{decision(verdict)}</span>
}

function Empty({ title, text, action, onAction }: { title: string; text: string; action: string; onAction: () => void }) {
  return <div className="empty-state">
    <Chief size={72} />
    <div><h3>{title}</h3><p>{text}</p></div>
    <button className="button secondary" onClick={onAction}>{action}</button>
  </div>
}

function SectionHead({ id, title, lead, children }: { id: string; title: string; lead: string; children?: ReactNode }) {
  return <header className="section-head">
    <div><h2 id={id}>{title}</h2><p>{lead}</p></div>
    {children && <div className="section-actions">{children}</div>}
  </header>
}

function Standard({ correction: c, busy, onRetry }: { correction: Correction; busy: boolean; onRetry: () => void }) {
  return <article className="standard-card">
    <span className="ticket-hole small" aria-hidden="true" />
    <div className="standard-top">
      <h3>{c.defect_type === 'good' ? 'Acceptable appearance' : `${c.defect_type.charAt(0).toUpperCase() + c.defect_type.slice(1)} standard`}</h3>
      <span className={'sync-badge ' + c.sync_status}>{c.sync_status === 'synced' ? <CheckCircle2 size={12} /> : <Clock3 size={12} />}{c.sync_status === 'synced' ? 'In memory' : 'Sync pending'}</span>
    </div>
    <p className="standard-rule handwritten">{c.rule_text}</p>
    <div className="standard-source">
      <img src={c.crop_url || c.image_url} alt={c.crop_url ? 'Defect region the model sees as a reference' : 'Source part for this correction'} />
      <span><strong className="handwritten">{c.reviewer}</strong><small>{dateTime(c.created_at)}</small></span>
      <Badge verdict={c.verdict} />
    </div>
    <details className="source-reasoning">
      <summary>Original inspection reasoning<ChevronDown size={13} /></summary>
      <p>{c.original_rationale}</p>
      <small>Correction {shortId(c.id)}</small>
    </details>
    {c.sync_status === 'pending' && <div className="pending-note">
      <p>{c.sync_error || 'This correction is saved here and is waiting to reach Hindsight.'}</p>
      <button className="button secondary compact" onClick={onRetry} disabled={busy}><RefreshCw size={13} />Retry sync</button>
    </div>}
  </article>
}

export function StandardsSection({ corrections, summary, synced, busy, part, factory, onSummarize, onRetry, onInspect }: {
  corrections: Correction[]; summary: string | null; synced: number; busy: string | null; part: string; factory: string;
  onSummarize: () => void; onRetry: (id: string) => void; onInspect: () => void;
}) {
  return <section id="standards" className="page-section" aria-labelledby="standards-title">
    <SectionHead id="standards-title" title="Quality memory" lead={`What your team has taught it for ${part.toLowerCase()} at ${factory}. Changing the specification starts a separate memory.`}>
      <button className="button secondary" onClick={onSummarize} disabled={!!busy || !synced}>{busy === 'reflect' ? <LoaderCircle size={15} className="spin" /> : <Sparkles size={15} />}Summarize standards</button>
    </SectionHead>
    {summary && <div className="reflection"><h3>What your inspector has learned</h3><p>{summary}</p><small>Written by Hindsight from your corrections. Check it against the tags below.</small></div>}
    {corrections.length
      ? <div className="standards-grid">{corrections.map(c => <Standard key={c.id} correction={c} busy={!!busy} onRetry={() => onRetry(c.id)} />)}</div>
      : <Empty title="Your standards start with a correction" text="Inspect a sample, correct the decision, and write what the inspector should remember." action="Go to inspection desk" onAction={onInspect} />}
  </section>
}

function ComparisonArm({ label, item, enhanced = false, expected }: { label: string; item: Inspection; enhanced?: boolean; expected?: Comparison['expected_verdict'] }) {
  const standards = new Set(item.memories.map(m => m.source_id)).size
  return <section className={'comparison-arm' + (enhanced ? ' enhanced' : '')}>
    <header><span>{enhanced ? <MemoryStick size={16} /> : <ScanLine size={16} />}{label}</span><Badge verdict={item.verdict} /></header>
    <h3>{decision(item.verdict)} part</h3>
    {expected && <div className={'comparison-outcome' + (expected === item.verdict ? ' aligned' : ' differs')}>
      {expected === item.verdict ? <CheckCircle2 size={14} /> : <CircleHelp size={14} />}
      <span>{expected === item.verdict ? 'Matches' : 'Differs from'} the selected label: {decision(expected).toLowerCase()}</span>
    </div>}
    <p>{item.rationale}</p>
    <footer>
      <span>{Math.round(item.confidence * 100)}% confidence</span>
      <span>{(item.ms / 1000).toFixed(1)}s</span>
      {enhanced && <span>{standards} correction{standards === 1 ? '' : 's'} recalled</span>}
      {!!item.prompt_tokens && <span>{Math.round((item.cached_tokens || 0) / item.prompt_tokens * 100)}% from cache</span>}
    </footer>
  </section>
}

export function CompareSection({ comparison, history, samples, selectedSample, partName, preview, generated, expected, busy, canRun, onSample, onExpected, onRun, onOpen, onExport }: {
  comparison: Comparison | null; history: Comparison[]; samples: Sample[]; selectedSample: string; partName: string; preview: string | null; generated: boolean;
  expected: string; busy: string | null; canRun: boolean; onSample: (sample: Sample) => void; onExpected: (value: string) => void;
  onRun: () => void; onOpen: (pair: Comparison) => void; onExport: () => void;
}) {
  const image = comparison?.baseline.image_url || preview || samples[0]?.image_url
  return <section id="compare" className="page-section" aria-labelledby="compare-title">
    <SectionHead id="compare-title" title="Memory comparison" lead="One part, two inspections. The model and specification stay fixed, so only recalled memory changes.">
      {comparison && <button className="button secondary" onClick={onExport}><ArrowDownToLine size={14} />Export comparison</button>}
    </SectionHead>
    <div className="compare-input">
      {image && <img src={image} alt="Selected part for comparison" />}
      <div className="compare-part">
        <strong>{comparison?.baseline.filename || partName || 'Select a sample part'}</strong>
        <p>{comparison ? 'Recorded comparison. Choose another part to run a new pair.' : generated ? 'Generated sample. Try a different part after teaching a correction.' : 'Use a different part to check that a standard transfers.'}</p>
      </div>
      <label className="field-label">Part
        <select aria-label="Choose comparison sample" value={selectedSample} onChange={e => { const sample = samples.find(s => s.id === e.target.value); if (sample) onSample(sample) }} disabled={!!busy}>
          <option value="" disabled>Choose a sample part</option>
          {samples.map(s => <option key={s.id} value={s.id}>{s.name}</option>)}
        </select>
      </label>
      <label className="field-label">Expected decision
        <select value={expected} onChange={e => onExpected(e.target.value)} disabled={!!busy}>
          <option value="">Not labeled</option><option value="good">Accept</option><option value="defect">Reject</option>
        </select>
      </label>
      <button className="button primary" onClick={onRun} disabled={!!busy || !canRun}>{busy === 'compare' ? <LoaderCircle size={16} className="spin" /> : <ArrowLeftRight size={16} />}{busy === 'compare' ? 'Running both inspections…' : 'Run comparison'}</button>
    </div>
    {comparison && <>
      <div className="comparison-arms">
        <ComparisonArm label="Without memory" item={comparison.baseline} expected={comparison.expected_verdict} />
        <ComparisonArm label="With quality memory" item={comparison.with_memory} expected={comparison.expected_verdict} enhanced />
      </div>
      <p className="comparison-disclosure"><strong>{comparison.changed ? 'The decisions differ on this part.' : 'Both inspections reached the same decision.'}</strong> {comparison.note} {!comparison.held_out && (comparison.reuse_reason === 'shared_source_photo' ? 'This sample shares a source photo with a correction, so use a different photo to check transfer.' : 'This image was used for a correction, so try a different part to check transfer.')}</p>
    </>}
    {!!history.length && <div className="previous-comparisons">
      <h3>Earlier comparisons</h3>
      {history.map(pair => <button className="comparison-history-row" key={pair.id} disabled={!!busy} onClick={() => onOpen(pair)}>
        <img src={pair.baseline.image_url} alt="" />
        <span className="history-name"><strong>{pair.baseline.filename}</strong><small>{dateTime(pair.created_at)}, {pair.held_out ? 'not used for a correction' : pair.reuse_reason === 'shared_source_photo' ? 'shared source photo' : 'correction image'}</small></span>
        <span className="history-arm">Memory off <Badge verdict={pair.baseline.verdict} /></span>
        <span className="history-arm">Memory on <Badge verdict={pair.with_memory.verdict} /></span>
        <ChevronRight size={16} />
      </button>)}
    </div>}
  </section>
}

export function RecordsSection({ overview, query, busy, onQuery, onExport, onOpen, onInspect }: {
  overview: Overview | null; query: string; busy: boolean; onQuery: (value: string) => void; onExport: () => void;
  onOpen: (item: Inspection) => void; onInspect: () => void;
}) {
  const reviewOf = (id: string) => overview?.corrections.find(c => c.inspection_id === id)
  const items = (overview?.inspections || []).filter(item => `${item.filename} ${item.id} ${reviewOf(item.id)?.reviewer || ''}`.toLowerCase().includes(query.trim().toLowerCase()))
  return <section id="history" className="page-section" aria-labelledby="history-title">
    <SectionHead id="history-title" title="Inspection history" lead="Every decision stays on record, with the model’s original call beside the human one.">
      <input type="search" aria-label="Search inspection history" placeholder="Part, ID or reviewer" value={query} onChange={e => onQuery(e.target.value)} />
      <button className="button secondary" onClick={onExport} disabled={!overview?.inspections.length}><ArrowDownToLine size={14} />Export records</button>
    </SectionHead>
    {overview?.inspections.length ? <div className="table-scroll">
      <table>
        <thead><tr><th>Part</th><th>Model decision</th><th>Memory</th><th>Confidence</th><th>Human decision</th><th>Time</th><th><span className="sr-only">Open</span></th></tr></thead>
        <tbody>
          {items.map(item => {
            const correction = reviewOf(item.id)
            const standards = new Set(item.memories.map(m => m.source_id)).size
            return <tr key={item.id}>
              <td><div className="table-part"><img src={item.image_url} alt="" /><span><strong>{item.filename}</strong><small>{shortId(item.id)}</small></span></div></td>
              <td><Badge verdict={item.verdict} /></td>
              <td>{item.memory_status === 'recalled' ? `${standards} standard${standards === 1 ? '' : 's'}` : item.memory_enabled ? 'None recalled' : 'Off'}</td>
              <td>{Math.round(item.confidence * 100)}%</td>
              <td>{correction ? <span className="review-label"><Check size={13} />{decision(correction.verdict)} by {correction.reviewer}</span> : <span className="quiet">Unreviewed</span>}</td>
              <td className="nowrap">{dateTime(item.created_at)}</td>
              <td><button className="icon-button" aria-label={`Open inspection ${shortId(item.id)}`} disabled={busy} onClick={() => onOpen(item)}><ChevronRight size={17} /></button></td>
            </tr>
          })}
          {!items.length && <tr><td colSpan={7} className="history-no-matches">No matching inspections. Try another part, ID, or reviewer.</td></tr>}
        </tbody>
      </table>
      <p className="history-count" aria-live="polite">Showing {items.length} of {overview.inspections.length} inspections. Export includes every record.</p>
    </div> : <Empty title="A clear trail for every decision" text="Inspections and corrections appear here as you work." action="Inspect your first part" onAction={onInspect} />}
  </section>
}
