import { ArrowRight, Check, ClipboardCheck, LoaderCircle, MemoryStick, ScanLine } from 'lucide-react'
import { useEffect, useRef } from 'react'
import { decision, shortId } from './api'
import { Chief, type Mood } from './Chief'
import { CorrectionForm } from './CorrectionForm'
import { Rolling } from './marks'
import type { Correction, Inspection, SpecClass } from './types'

export type CorrectionValue = { verdict: 'good' | 'defect'; defect_type: string; rule_text: string; reviewer: string }

const title = (text: string) => text.charAt(0).toUpperCase() + text.slice(1)

function verdictLine(item: Inspection) {
  if (item.verdict === 'good') return 'Meets the visual specification'
  if (item.verdict === 'defect') return `${title(item.type)} detected`
  return item.part_visible === false ? 'The part is not clear in this photo' : 'Needs a closer human review'
}

export function Ticket({ result, correction, classes, busy, ready, canInspect, memory, onMemory, correcting, onCorrecting, onInspect, onSave, onCompare }: {
  result: Inspection | null; correction?: Correction; classes?: SpecClass[]; busy: string | null; ready: boolean; canInspect: boolean; memory: boolean;
  onMemory: (value: boolean) => void; correcting: boolean; onCorrecting: (value: boolean) => void;
  onInspect: () => void; onSave: (value: CorrectionValue) => Promise<void>; onCompare: () => void;
}) {
  const panel = useRef<HTMLElement>(null)
  const inspecting = busy === 'inspect'
  const mood: Mood = inspecting ? 'looking' : result?.verdict === 'good' ? 'accept' : result?.verdict === 'defect' ? 'reject' : result ? 'review' : 'idle'
  const recalled = result ? Array.from(new Map(result.memories.map(fact => [fact.source_id, fact])).values()) : []
  const confidence = result ? Math.round(Math.max(0, Math.min(1, result.confidence)) * 100) : 0
  const cachedShare = result?.prompt_tokens ? Math.round((result.cached_tokens || 0) / result.prompt_tokens * 100) : null

  // On a phone the ticket sits below the photo, so bring the decision into view when it arrives.
  useEffect(() => {
    if (!result || !panel.current) return
    const box = panel.current.getBoundingClientRect()
    if (box.top > window.innerHeight * 0.7) panel.current.scrollIntoView({ block: 'start' })
  }, [result])

  return <div className="ticket-wrap">
    <section ref={panel} className="ticket decision-panel" aria-label="Inspection decision" aria-live="polite">
      <span className="ticket-hole" aria-hidden="true" />
      <header className="ticket-head">
        <h3>Inspection ticket</h3>
        <span>{result ? shortId(result.id) : 'New'}</span>
      </header>

      <div className="memory-toggle-row">
        <span className="memory-label"><MemoryStick size={17} />Use quality memory</span>
        <button role="switch" aria-checked={memory} aria-label="Use quality memory" className={'toggle' + (memory ? ' on' : '')} onClick={() => onMemory(!memory)} disabled={!!busy}><span /></button>
      </div>

      {inspecting ? <div className="ticket-empty">
        <Chief mood="looking" size={84} />
        <h3>Inspecting this part</h3>
        <p>{memory ? 'Recalling your standards, then checking the photo against the specification.' : 'Checking the photo against the base specification.'}</p>
      </div> : result ? <div className="decision-result">
        <div className={'verdict-line ' + result.verdict}>
          <Chief mood={mood} size={58} />
          <div><h3>{decision(result.verdict)} part</h3><p>{verdictLine(result)}</p></div>
        </div>
        <div className="confidence-row">
          <span title="The model’s own estimate. This is not a measured accuracy score.">Model confidence</span>
          <strong><Rolling value={confidence} />%</strong>
        </div>
        <div className="confidence-track"><span className={result.verdict} style={{ width: `${confidence}%` }} /></div>
        <div className="reasoning"><h4>Why this decision</h4><p>{result.rationale}</p></div>
        {result.measurement && <div className="measurement" aria-label="Defect size">
          <h4>Measured from the outline</h4>
          {result.measurement.length_mm !== null
            ? <p><strong>{result.measurement.length_mm} mm</strong> long · {result.measurement.area_mm2} mm²{result.measurement.limit_mm !== null && <> · limit {result.measurement.limit_mm} mm, <span className={result.measurement.within_limit ? 'within' : 'over'}>{result.measurement.within_limit ? 'within limit' : 'over limit'}</span></>}</p>
            : <p>{Math.round(result.measurement.length_px)} px long. Add the part width to the specification to measure in millimetres.</p>}
          {result.size_note && <p className="ticket-hint">{result.size_note}</p>}
        </div>}
        {result.part_visible === false && <p className="ticket-hint">Use a sharp, top-down photo of one part, or record the decision yourself below.</p>}
        <div className="inspection-meta">
          <span>{(result.ms / 1000).toFixed(1)}s</span>
          <span>{result.memory_enabled ? `${recalled.length} recalled standard${recalled.length === 1 ? '' : 's'}` : 'Memory off'}</span>
          {!!result.reference_crops?.length && <span title="Defect crops saved with corrections, shown to the model next to this photo.">{result.reference_crops.length} reference crop{result.reference_crops.length === 1 ? '' : 's'}</span>}
          {cachedShare !== null && <span title="Share of this request’s input tokens served from the Model API prompt cache.">{cachedShare}% of prompt from cache</span>}
        </div>
        {recalled.length > 0 && <div className="recalled-list">
          <h4>Standards applied</h4>
          {recalled.map(fact => <div className="recalled-standard" key={fact.source_id}>
            <p className="handwritten">{fact.rule_text || fact.text}</p>
            <span>Correction {shortId(fact.source_id)} by {fact.reviewer || 'Quality engineer'}</span>
          </div>)}
        </div>}
        {result.memory_status === 'empty' && <p className="ticket-hint">No standards apply yet. Correct a decision to teach the first one.</p>}
        {correction
          ? <div className="reviewed-note"><Check size={15} /><span>Reviewed: {decision(correction.verdict).toLowerCase()} by {correction.reviewer}</span></div>
          : !correcting && <button className="button secondary full-width" onClick={() => onCorrecting(true)} disabled={!!busy}><ClipboardCheck size={16} />Correct this decision</button>}
      </div> : <div className="ticket-empty idle">
        <Chief size={84} />
        <h3>Ready when the part is</h3>
        <ol className="ticket-steps">
          <li>Inspect a part</li>
          <li>Correct the decision if it is wrong</li>
          <li>The next part uses your standard</li>
        </ol>
      </div>}

      {correcting && result && <CorrectionForm key={result.id} inspection={result} classes={classes} onSave={onSave} onClose={() => onCorrecting(false)} busy={busy === 'correct'} />}
      {!correcting && <div className="decision-actions">
        <button className="button primary full-width large-button" onClick={onInspect} disabled={!!busy || !ready || !canInspect}>
          {inspecting ? <LoaderCircle className="spin" size={17} /> : <ScanLine size={17} />}
          {inspecting ? 'Inspecting part…' : ready && !canInspect ? 'Choose a part first' : result ? 'Inspect again' : 'Inspect part'}
        </button>
        {result && <button className="text-link" onClick={onCompare}>See what memory changes<ArrowRight size={14} /></button>}
      </div>}
    </section>
  </div>
}
