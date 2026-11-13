import { ArrowLeft, ArrowRight, Eye, EyeOff, Factory, LoaderCircle, LockKeyhole } from 'lucide-react'
import { useState } from 'react'
import { Chief } from '../workspace/Chief'
import { errorMessage, pilotApi } from './api'
import type { Session } from './types'
import { Field, Submit } from './ui'

const DEMO = { username: 'demo.speclens', password: 'SpecLensDemo2026!' }

function PasswordInput({ id, newPassword }: { id?: string; newPassword: boolean }) {
  const [shown, setShown] = useState(false)
  return <div className="pilot-password">
    <input id={id} name="password" type={shown ? 'text' : 'password'} required minLength={newPassword ? 12 : 1} maxLength={256} autoComplete={newPassword ? 'new-password' : 'current-password'} autoCapitalize="none" autoCorrect="off" spellCheck={false} />
    <button type="button" className="icon-button" aria-label={shown ? 'Hide password' : 'Show password'} aria-pressed={shown} onClick={() => setShown(value => !value)}>{shown ? <EyeOff size={17} /> : <Eye size={17} />}</button>
  </div>
}

export function Auth({ onSession, onExit, initialError }: { onSession: (session: Session) => void; onExit: () => Promise<void>; initialError?: string | null }) {
  const [mode, setMode] = useState<'login' | 'register' | 'join'>('login')
  const [error, setError] = useState<string | null>(initialError || null)
  const [busy, setBusy] = useState<false | 'form' | 'demo'>(false)
  const signIn = async (action: () => Promise<Session>, kind: 'form' | 'demo') => {
    if (busy) return
    setBusy(kind); setError(null)
    try { onSession(await action()) } catch (error) { setError(errorMessage(error)) } finally { setBusy(false) }
  }
  return <div className="pilot-auth">
    <header className="pilot-auth-header"><span className="brand"><Chief size={38} />SpecLens.</span><button className="text-link" onClick={async () => { if (busy) return; setBusy('form'); setError(null); try { await onExit() } catch (error) { setError(errorMessage(error)) } finally { setBusy(false) } }} disabled={!!busy}><ArrowLeft size={16} />Return to public demo</button></header>
    <main className="pilot-auth-layout">
      <div className="pilot-auth-intro"><Factory size={40} strokeWidth={1.4} /><h1>A shared desk for your factory.</h1><p>Freeze the spec. Capture the part. Keep the human decision on record.</p><ol className="pilot-auth-sequence"><li>Products & specs</li><li>Lots & captures</li><li>Review & standards</li></ol><p className="pilot-auth-note handwritten">One team. A clear trail from photo to disposition.</p></div>
      <section className="pilot-auth-card" aria-labelledby="pilot-auth-title">
        <h2 id="pilot-auth-title">{mode === 'login' ? 'Sign in to your team' : mode === 'register' ? 'Create your team workspace' : 'Join your team'}</h2>
        <div className="pilot-auth-tabs" role="group" aria-label="Account options">{(['login', 'register', 'join'] as const).map(option => <button key={option} type="button" className={mode === option ? 'selected' : ''} aria-pressed={mode === option} disabled={!!busy} onClick={() => { setMode(option); setError(null) }}>{option === 'login' ? 'Sign in' : option === 'register' ? 'Create a team' : 'Join with invitation'}</button>)}</div>
        {error && <div className="alert error" role="alert">{error}</div>}
        <form key={mode} className="pilot-form" onSubmit={event => {
          event.preventDefault()
          const fields = new FormData(event.currentTarget)
          const username = String(fields.get('username') || '').trim()
          const password = String(fields.get('password') || '')
          void signIn(() => mode === 'login' ? pilotApi.login({ username, password }) : mode === 'register'
            ? pilotApi.register({ username, password, name: String(fields.get('name')).trim(), team_name: String(fields.get('team_name')).trim() })
            : pilotApi.join({ username, password, name: String(fields.get('name')).trim(), token: String(fields.get('token')).trim() }), 'form')
        }}>
          <fieldset disabled={!!busy}>
            {mode === 'join' && <Field label="Invitation token"><input name="token" required autoComplete="off" maxLength={500} /></Field>}
            {mode !== 'login' && <Field label="Your name"><input name="name" required maxLength={100} autoComplete="name" /></Field>}
            <Field label="Username"><input name="username" required minLength={3} maxLength={64} pattern="[A-Za-z0-9_.\-]+" autoCapitalize="none" autoCorrect="off" spellCheck={false} autoComplete="username" /></Field>
            <Field label="Password"><PasswordInput newPassword={mode !== 'login'} /></Field>
            {mode !== 'login' && <p className="pilot-help">Use at least 12 characters. Usernames use letters, numbers, dots, underscores or hyphens.</p>}
            {mode === 'register' && <Field label="Team name"><input name="team_name" required maxLength={100} autoComplete="organization" /></Field>}
            <Submit busy={busy === 'form'} disabled={!!busy}>{mode === 'login' ? 'Sign in to workspace' : mode === 'register' ? 'Create team workspace' : 'Join team workspace'}</Submit>
          </fieldset>
        </form>
        {mode === 'login' && <aside className="pilot-demo-login" aria-label="Demo login credentials">
          <div className="pilot-demo-head"><h3>Try the factory demo</h3><span>Sample data</span></div>
          <p>Explore sample products, lot histories, inspection images, human reviews, standards, quality issues and validation results.</p>
          <button type="button" className="button secondary full-width" disabled={!!busy} onClick={() => void signIn(() => pilotApi.login(DEMO), 'demo')}>
            {busy === 'demo' ? <LoaderCircle size={15} className="spin" /> : null}Open the demo workspace{busy !== 'demo' && <ArrowRight size={16} />}
          </button>
          <dl><div><dt>Username</dt><dd><code>{DEMO.username}</code></dd></div><div><dt>Password</dt><dd><code>{DEMO.password}</code></dd></div></dl>
          <p className="pilot-help">Shared demo workspace with engineer access. Use sample data only.</p>
        </aside>}
        <p className="pilot-auth-privacy"><LockKeyhole size={14} aria-hidden="true" /><span>Named local accounts. Your team’s records stay separate from the public demo.</span></p>
      </section>
    </main>
  </div>
}
