import { X } from 'lucide-react'
import { useEffect, useRef, useState } from 'react'
import type { ScopeSettings, Status } from './types'

export function SettingsDialog({ initial, status, busy, onClose, onSave }: {
  initial: ScopeSettings; status: Status | null; busy: boolean; onClose: () => void; onSave: (next: ScopeSettings) => void;
}) {
  const [draft, setDraft] = useState(initial)
  const dialog = useRef<HTMLElement>(null)

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
        <label className="field-label">Base quality specification<textarea value={draft.spec_text || status?.default_spec || ''} onChange={e => setDraft({ ...draft, spec_text: e.target.value })} rows={7} maxLength={12000} /></label>
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
