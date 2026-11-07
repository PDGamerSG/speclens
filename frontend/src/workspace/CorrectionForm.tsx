import { Check, LoaderCircle, X } from 'lucide-react'
import { useState } from 'react'
import type { Inspection } from './types'

export function CorrectionForm({ inspection, onSave, onClose, busy }: {
  inspection: Inspection;
  onSave: (value: { verdict: 'good' | 'defect'; defect_type: string; rule_text: string; reviewer: string }) => Promise<void>;
  onClose: () => void; busy: boolean;
}) {
  const [verdict, setVerdict] = useState<'good' | 'defect'>(inspection.verdict === 'good' ? 'defect' : 'good')
  const [kind, setKind] = useState(inspection.type === 'good' ? 'print' : inspection.type)
  const [rule, setRule] = useState('')
  const [reviewer, setReviewer] = useState(() => localStorage.getItem('speclens-reviewer') || '')
  return <form className="correction-form" onSubmit={e => {
    e.preventDefault()
    localStorage.setItem('speclens-reviewer', reviewer.trim())
    void onSave({ verdict, defect_type: verdict === 'good' ? 'good' : kind, rule_text: rule.trim(), reviewer: reviewer.trim() })
  }}>
    <div className="section-heading"><h3>Teach a quality standard</h3><button type="button" className="icon-button" aria-label="Close correction" onClick={onClose} disabled={busy}><X size={17} /></button></div>
    <p className="muted small">Your correction becomes a standard for the next matching part.</p>
    <fieldset className="disposition-options" disabled={busy}><legend>Correct decision</legend>
      <label className={verdict === 'good' ? 'chosen' : ''}><input type="radio" name="verdict" value="good" checked={verdict === 'good'} onChange={() => setVerdict('good')} />Accept part</label>
      <label className={verdict === 'defect' ? 'chosen reject-choice' : ''}><input type="radio" name="verdict" value="defect" checked={verdict === 'defect'} onChange={() => setVerdict('defect')} />Reject part</label>
    </fieldset>
    {verdict === 'defect' && <label className="field-label">Defect class<select value={kind} onChange={e => setKind(e.target.value)} disabled={busy}><option value="print">Ink or print</option><option value="crack">Shell crack</option><option value="hole">Hole</option><option value="cut">Cut or notch</option></select></label>}
    <label className="field-label">What should the inspector learn?<textarea autoFocus value={rule} onChange={e => setRule(e.target.value)} placeholder="Describe the visual difference and the standard to apply next time." minLength={10} maxLength={2000} required rows={4} disabled={busy} /></label>
    <label className="field-label">Reviewed by<input value={reviewer} onChange={e => setReviewer(e.target.value)} placeholder="Your name" required maxLength={80} disabled={busy} /></label>
    <button className="button primary full-width" type="submit" disabled={busy || rule.trim().length < 10 || !reviewer.trim()}>{busy ? <LoaderCircle size={16} className="spin" /> : <Check size={16} />}{busy ? 'Saving to memory…' : 'Save correction & remember'}</button>
  </form>
}
