import { FileUp, LoaderCircle, Sparkles, X } from 'lucide-react'
import { useEffect, useRef, useState } from 'react'
import { workspaceApi as api } from './api'
import type { ScopeSettings, Status, Taxonomy } from './types'

const SOURCE: Record<Taxonomy['source'], string> = {
  rules: 'Read from the numbered reject clauses.',
  model: 'Read by the vision model and saved for this specification.',
  fallback: 'No numbered reject clauses found, so every defect uses one class. Add clauses such as "4.1 Hole: ..." under a REJECT heading, or read it with the model.',
}

export function SettingsDialog({ initial, status, busy, onClose, onSave }: {
  initial: ScopeSettings; status: Status | null; busy: boolean; onClose: () => void; onSave: (next: ScopeSettings) => void;
}) {
  const [draft, setDraft] = useState(initial)
  const [taxonomy, setTaxonomy] = useState<Taxonomy | null>(null)
  const [specBusy, setSpecBusy] = useState<'file' | 'model' | null>(null)
  const [specError, setSpecError] = useState<string | null>(null)
  const dialog = useRef<HTMLElement>(null)
  const specFile = useRef<HTMLInputElement>(null)
  const specText = draft.spec_text || status?.default_spec || ''

  // Reading by rules is free, so the class list follows the text as it is edited.
  useEffect(() => {
    let current = true
    const timer = setTimeout(() => {
      if (!specText.trim()) { setTaxonomy(null); return }
      api.parseSpec(specText).then(next => { if (current) setTaxonomy(next) }).catch(() => { if (current) setTaxonomy(null) })
    }, 400)
    return () => { current = false; clearTimeout(timer) }
  }, [specText])

  const readSpec = async (kind: 'file' | 'model', source: { file: File } | { text: string }) => {
    setSpecBusy(kind); setSpecError(null)
    try {
      const reply = await api.extractSpec(source, kind === 'model')
      setDraft(current => ({ ...current, spec_text: reply.spec_text }))
      setTaxonomy(reply.taxonomy)
    } catch (e) { setSpecError(e instanceof Error ? e.message : 'The specification could not be read.') }
    finally { setSpecBusy(null) }
  }

  useEffect(() => {
    const previous = document.activeElement as HTMLElement | null
    const focusable = () => Array.from(dialog.current?.querySelectorAll<HTMLElement>('button:not([disabled]), input, textarea, select, [tabindex="0"]') || [])
    focusable()[0]?.focus()
    const onKey = (event: KeyboardEvent) => {
      if (event.key === 'Escape') { event.preventDefault(); onClose() }
      if (event.key === 'Tab') {
        const items = focusable()
        const first = items[0]
        const last = items.at(-1)
        if (event.shiftKey && document.activeElement === first) { event.preventDefault(); last?.focus() }
        else if (!event.shiftKey && document.activeElement === last) { event.preventDefault(); first?.focus() }
      }
    }
    document.addEventListener('keydown', onKey)
    return () => { document.removeEventListener('keydown', onKey); previous?.focus() }
  }, [onClose])

  const cache = status?.cache
  return <div className="modal-backdrop">
    <button type="button" className="modal-dismiss" aria-label="Close workspace settings" onClick={onClose} />
    <section className="settings-modal" ref={dialog} role="dialog" aria-modal="true" aria-labelledby="settings-title">
      <header className="settings-head"><h2 id="settings-title">Workspace settings</h2><button className="icon-button" aria-label="Close settings" onClick={onClose}><X size={19} /></button></header>
      <form onSubmit={e => {
        e.preventDefault()
        if (!busy) onSave({ factory: draft.factory.trim(), part_family: draft.part_family.trim(), spec_text: draft.spec_text.trim() })
      }}>
        <label className="field-label">Factory or workspace<input value={draft.factory} onChange={e => setDraft({ ...draft, factory: e.target.value })} required maxLength={100} /></label>
        <label className="field-label">Part family<input value={draft.part_family} onChange={e => setDraft({ ...draft, part_family: e.target.value })} required maxLength={100} /></label>
        <label className="field-label">Base quality specification<textarea value={specText} onChange={e => setDraft({ ...draft, spec_text: e.target.value })} rows={7} maxLength={12000} /></label>
        <div className="spec-tools">
          <button type="button" className="button secondary compact" disabled={busy || !!specBusy} onClick={() => specFile.current?.click()}>
            {specBusy === 'file' ? <LoaderCircle size={14} className="spin" /> : <FileUp size={14} />}Import PDF or text
          </button>
          <button type="button" className="button secondary compact" disabled={busy || !!specBusy || !status?.model_configured || !specText.trim()}
            title={status?.model_configured ? 'One vision model call. The reading is saved for this specification.' : 'Needs MODEL_API_KEY on the server.'}
            onClick={() => void readSpec('model', { text: specText })}>
            {specBusy === 'model' ? <LoaderCircle size={14} className="spin" /> : <Sparkles size={14} />}Read with the model
          </button>
          <input ref={specFile} type="file" accept=".pdf,.txt,application/pdf,text/plain" className="sr-only" tabIndex={-1} aria-label="Specification file" onChange={e => {
            const file = e.target.files?.[0]
            if (file) void readSpec('file', { file })
            e.target.value = ''
          }} />
        </div>
        {specError && <p className="spec-error" role="alert">{specError}</p>}
        {taxonomy && <div className="spec-classes" aria-label="Reject classes in this specification">
          <h3>Reject classes{taxonomy.part_width_mm ? ` · part width ${taxonomy.part_width_mm} mm` : ''}</h3>
          <ul>{taxonomy.classes.map(c => <li key={c.defect_type} title={c.description}>
            <strong>{c.label}</strong>{c.clause && <span>{c.clause}</span>}{c.limit_mm !== null && <span>&gt; {c.limit_mm} mm</span>}
          </li>)}</ul>
          <p>{SOURCE[taxonomy.source]}</p>
        </div>}
        <p className="settings-note">Memory is separated by factory, part family, and specification. Editing the specification starts a separate memory.</p>
        <div className="connection-details">
          <h3>Server connections</h3>
          <div><span>Vision model</span><span className={status?.model_configured ? 'state-ok' : 'state-warn'}>{status?.model_configured ? 'Configured' : 'MODEL_API_KEY needed'}</span></div>
          <div><span>Hindsight memory</span><span className={status?.memory_configured ? 'state-ok' : 'state-warn'}>{status?.memory_configured ? 'Endpoint configured' : 'Connection needed'}</span></div>
          <div><span>Server vision spend</span><strong>{status ? `$${status.spent_usd.toFixed(3)} / $${status.budget_usd.toFixed(2)}` : 'Loading…'}</strong></div>
          <progress className="vision-budget" aria-label="Server vision budget used" max={status?.budget_usd || 1} value={status?.spent_usd || 0} />
          <div><span>Prompt cache</span><strong>{cache?.prompt_tokens ? `${Math.round(cache.hit_rate * 100)}% of input reused, $${cache.saved_usd.toFixed(4)} saved` : 'No calls yet'}</strong></div>
          <p>Vision usage counts against the server budget. Hindsight usage is billed separately.</p>
          <p>Credentials stay on the server and never reach this browser.</p>
        </div>
        <button type="submit" className="button primary full-width" disabled={busy}>Save workspace</button>
      </form>
    </section>
  </div>
}
