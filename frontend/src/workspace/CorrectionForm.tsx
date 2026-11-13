import { Check, LoaderCircle, X } from 'lucide-react'
import { useEffect, useRef, useState } from 'react'
import type { Inspection, SpecClass } from './types'

const FALLBACK: SpecClass[] = ['print', 'crack', 'hole', 'cut'].map(kind => ({ defect_type: kind, label: kind.charAt(0).toUpperCase() + kind.slice(1), clause: '', description: '', limit_mm: null }))

export function CorrectionForm({ inspection, classes, onSave, onClose, busy }: {
  inspection: Inspection; classes?: SpecClass[];
  onSave: (value: { verdict: 'good' | 'defect'; defect_type: string; rule_text: string; reviewer: string }) => Promise<void>;
  onClose: () => void; busy: boolean;
}) {
  const [verdict, setVerdict] = useState<'good' | 'defect'>(inspection.verdict === 'good' ? 'defect' : 'good')
  const options = classes?.length ? classes : FALLBACK
  const [kind, setKind] = useState(() => options.some(c => c.defect_type === inspection.type) ? inspection.type : options[0].defect_type)
  const [rule, setRule] = useState('')
  const [reviewer, setReviewer] = useState(() => localStorage.getItem('speclens-reviewer') || '')
  const form = useRef<HTMLFormElement>(null)
  useEffect(() => { form.current?.scrollIntoView({ block: 'nearest' }) }, [])
  return <form ref={form} className="correction-form" onSubmit={e => {
    e.preventDefault()
    localStorage.setItem('speclens-reviewer', reviewer.trim())
    void onSave({ verdict, defect_type: verdict === 'good' ? 'good' : kind, rule_text: rule.trim(), reviewer: reviewer.trim() })
  }}>
    <div className="form-head"><h3>Teach a quality standard</h3><button type="button" className="icon-button" aria-label="Close correction" onClick={onClose} disabled={busy}><X size={17} /></button></div>
    <p className="form-note">Your correction becomes a standard for the next matching part.</p>
    <fieldset className="disposition-options" disabled={busy}><legend>Correct decision</legend>
      <label className={verdict === 'good' ? 'chosen' : ''}><input type="radio" name="verdict" value="good" checked={verdict === 'good'} onChange={() => setVerdict('good')} />Accept part</label>
      <label className={verdict === 'defect' ? 'chosen reject-choice' : ''}><input type="radio" name="verdict" value="defect" checked={verdict === 'defect'} onChange={() => setVerdict('defect')} />Reject part</label>
    </fieldset>
    {verdict === 'defect' && <label className="field-label">Defect class<select value={kind} onChange={e => setKind(e.target.value)} disabled={busy}>{options.map(c => <option key={c.defect_type} value={c.defect_type}>{c.clause ? `${c.label} (clause ${c.clause})` : c.label}</option>)}</select></label>}
    <label className="field-label">What should the inspector learn?<textarea value={rule} onChange={e => setRule(e.target.value)} placeholder="Describe the visual difference and the standard to apply next time." minLength={10} maxLength={2000} required rows={4} disabled={busy} /></label>
    <label className="field-label">Reviewed by<input value={reviewer} onChange={e => setReviewer(e.target.value)} placeholder="Your name" required maxLength={80} disabled={busy} /></label>
    <button className="button primary full-width" type="submit" disabled={busy || rule.trim().length < 10 || !reviewer.trim()}>{busy ? <LoaderCircle size={16} className="spin" /> : <Check size={16} />}{busy ? 'Saving to memory…' : 'Save correction & remember'}</button>
  </form>
}
