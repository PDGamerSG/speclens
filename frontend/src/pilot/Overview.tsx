import { AlertTriangle, ArrowRight, BookOpenCheck, Boxes, CheckCircle2, ClipboardCheck, LoaderCircle, ShieldAlert } from 'lucide-react'
import { useEffect, useState } from 'react'
import { dateTime } from '../workspace/api'
import { errorMessage, pilotApi } from './api'
import type { Attention, Insights, Rate, Section, SectionProps } from './types'

const PERIODS = [7, 30, 90]
const percent = (rate: Rate | null | undefined) => rate?.rate == null ? '–' : `${Math.round(rate.rate * 100)}%`
const ATTENTION_ICON = { quarantine: AlertTriangle, issue: ShieldAlert, review: ClipboardCheck, standard: BookOpenCheck, lot: Boxes }

function age(hours: number | null) {
  if (hours == null) return ''
  if (hours < 1) return 'just now'
  if (hours < 48) return `${Math.round(hours)} h`
  return `${Math.round(hours / 24)} d`
}

function Steps({ data, navigate }: Pick<SectionProps, 'data' | 'navigate'>) {
  const steps: [string, boolean, Section][] = [
    ['Add a product and approve its specification', data.revisions.some(r => r.status === 'approved'), 'products'],
    ['Describe a capture station', data.stations.some(s => s.active), 'stations'],
    ['Open a lot against the approved revision', data.lots.length > 0, 'lots'],
    ['Capture the first part', data.captures.length > 0, 'capture'],
    ['Record a human decision', data.reviews.some(r => r.status === 'closed'), 'review'],
  ]
  const next = steps.find(step => !step[1])
  return <section className="pilot-panel factory-onboarding" aria-labelledby="factory-start">
    <h2 id="factory-start">Set up your first inspection line</h2>
    <ol>{steps.map(([label, done, section]) => <li key={label} className={done ? 'done' : ''}>
      {done ? <CheckCircle2 size={17} /> : <span className="step-dot" />}
      <button className="text-link" onClick={() => navigate(section)}>{label}</button>
    </li>)}</ol>
    {next && <button className="button primary" onClick={() => navigate(next[2])}>{next[0]}<ArrowRight size={15} /></button>}
  </section>
}

export function Overview({ data, navigate, onOpen }: SectionProps & { onOpen: (item: Attention) => void }) {
  const [days, setDays] = useState(30)
  const [view, setView] = useState<Insights | null>(null)
  const [error, setError] = useState('')
  const records = data.captures.length + data.reviews.length + data.lots.length
  useEffect(() => {
    let current = true
    pilotApi.insights(days).then(next => { if (current) { setView(next); setError('') } })
      .catch(reason => { if (current) setError(errorMessage(reason)) })
    return () => { current = false }
  }, [days, records])

  if (!data.lots.length) return <div className="pilot-stack"><Steps data={data} navigate={navigate} /></div>
  if (!view) return <div className="pilot-loading" role="status">{error ? <p>{error}</p> : <><LoaderCircle size={24} className="spin" /><p>Reading the team’s records…</p></>}</div>

  const k = view.kpis
  const peak = Math.max(1, ...view.daily.map(d => d.captures))
  const defectPeak = Math.max(1, ...view.defects.map(d => d.flagged))
  return <div className="factory-overview">
    <div className="factory-period">
      <p>{k.captures} captures of {k.parts} physical parts in the last {days} days</p>
      <label>Period<select aria-label="Overview period" value={days} onChange={event => setDays(Number(event.target.value))}>
        {PERIODS.map(p => <option key={p} value={p}>Last {p} days</option>)}
      </select></label>
    </div>

    <dl className="factory-kpis">
      <div><dt title="Parts accepted on their first capture, out of parts with a final accept or reject.">First-pass yield</dt><dd>{percent(k.first_pass_yield)}</dd><small>{k.first_pass_yield.count} of {k.first_pass_yield.denominator} decided parts</small></div>
      <div><dt>Rejected by reviewers</dt><dd className="reject">{percent(k.human_reject_rate)}</dd><small>{k.hold_rate.count} on hold</small></div>
      <div><dt title="Closed accept or reject decisions where the model's recommendation matched the reviewer.">Model agreed with reviewer</dt><dd>{percent(k.model_agreement)}</dd><small>{k.model_agreement.denominator} compared</small></div>
      <div><dt>Open reviews</dt><dd className={k.open_reviews ? 'review' : ''}>{k.open_reviews}</dd><small>{k.oldest_open_review_hours != null ? `oldest ${age(k.oldest_open_review_hours)}` : 'queue is clear'}</small></div>
      <div><dt>Open lots</dt><dd>{k.open_lots}</dd><small>{view.open_lots.filter(l => l.ready_to_close).length} ready to close · {k.closed_lots} closed</small></div>
      <div><dt>Open quality issues</dt><dd className={k.critical_open_issues ? 'reject' : ''}>{k.open_issues}</dd><small>{k.critical_open_issues} critical</small></div>
    </dl>

    <section className="pilot-panel" aria-labelledby="daily-title">
        <header className="factory-card-head"><h2 id="daily-title">Captures and decisions per day</h2></header>
        <div className="factory-bars" role="img" aria-label={`Captures per day over ${days} days, peak ${peak}`}>
          {view.daily.map(d => <div key={d.day} className="factory-bar" title={`${d.day}: ${d.captures} captures, ${d.accept} accepted, ${d.reject} rejected, ${d.hold} held, ${d.retake} retakes, ${d.open} awaiting review`}>
            {(['open', 'retake', 'hold', 'reject', 'accept'] as const).map(key => <span key={key} className={`seg ${key}`} style={{ height: `${d[key] / peak * 100}%` }} />)}
          </div>)}
        </div>
        <div className="factory-legend"><span className="accept">Accepted</span><span className="reject">Rejected</span><span className="hold">Hold</span><span className="retake">Retake</span><span className="open">Awaiting review</span></div>
    </section>

    <div className="factory-grid">
      <section className="pilot-panel factory-attention" aria-labelledby="attention-title">
        <header><h2 id="attention-title">Needs attention</h2><span>{view.attention.length ? `${view.attention.length} items` : 'Nothing waiting'}</span></header>
        {view.attention.length ? <ol>{view.attention.map(item => {
          const Icon = ATTENTION_ICON[item.kind]
          return <li key={`${item.kind}:${item.id}`} className={`attention-${item.kind}${item.severity ? ' ' + item.severity : ''}`}>
            <button onClick={() => onOpen(item)}>
              <Icon size={17} />
              <span><strong>{item.title}</strong><small>{item.detail}</small></span>
              <em>{age(item.age_hours)}</em>
            </button>
          </li>
        })}</ol> : <p className="pilot-help">No quarantined results, serious issues, waiting reviews or proposals. Good shift.</p>}
      </section>
      <section className="pilot-panel" aria-labelledby="lots-title">
        <header className="factory-card-head"><h2 id="lots-title">Open lots</h2><button className="text-link" onClick={() => navigate('lots')}>All lots<ArrowRight size={14} /></button></header>
        {view.open_lots.length ? <ul className="factory-lots">{view.open_lots.map(lot => <li key={lot.id}>
          <button onClick={() => onOpen({ kind: 'lot', id: lot.id, section: 'lots', title: lot.reference, detail: '', age_hours: null, priority: 0 })}>
            <span><strong>{lot.reference}</strong><small>{lot.product} · opened {dateTime(lot.opened_at)}</small></span>
            {lot.ready_to_close ? <span className="pilot-status pilot-status-accept">ready to close</span>
              : <span className="pilot-status pilot-status-hold">{lot.unresolved_parts} unresolved</span>}
          </button>
        </li>)}</ul> : <p className="pilot-help">Every lot is closed.</p>}
      </section>

    </div>

    <section className="pilot-panel" aria-labelledby="products-title">
      <header className="factory-card-head"><h2 id="products-title">Product lines</h2><button className="text-link" onClick={() => navigate('products')}>Products & specs<ArrowRight size={14} /></button></header>
      <div className="factory-table-scroll"><table className="factory-table">
        <thead><tr><th>Product</th><th>Parts</th><th>Captures</th><th>First-pass yield</th><th>Decisions</th><th>Open issues</th></tr></thead>
        <tbody>{view.products.filter(row => row.captures).map(row => {
          const total = Math.max(1, row.accept + row.reject + row.hold + row.retake + row.open)
          return <tr key={row.product_id}>
            <td><strong>{row.name}</strong><small>{row.code}</small></td>
            <td>{row.parts}</td><td>{row.captures}</td>
            <td><span className="factory-meter"><span style={{ width: `${(row.first_pass_yield.rate || 0) * 100}%` }} /></span>{percent(row.first_pass_yield)}</td>
            <td><span className="factory-mix" title={`${row.accept} accepted, ${row.reject} rejected, ${row.hold} held, ${row.retake} retakes, ${row.open} open`}>
              {(['accept', 'reject', 'hold', 'retake', 'open'] as const).map(key => <span key={key} className={key} style={{ width: `${row[key] / total * 100}%` }} />)}
            </span></td>
            <td>{row.open_issues ? <span className="pilot-status pilot-status-major">{row.open_issues} open</span> : '–'}</td>
          </tr>
        })}</tbody>
      </table></div>
    </section>

    <div className="factory-grid">
      <section className="pilot-panel" aria-labelledby="defects-title">
        <header className="factory-card-head"><h2 id="defects-title">Defects the model flagged</h2><span className="pilot-help">dark: confirmed by a reviewer</span></header>
        {view.defects.length ? <ol className="factory-pareto">{view.defects.map(d => <li key={d.defect_type}>
          <span>{d.label}{d.clause && <small> clause {d.clause}</small>}</span>
          <span className="factory-pareto-track" title={`${d.flagged} flagged, ${d.confirmed} rejected by a reviewer`}>
            <span className="flagged" style={{ width: `${d.flagged / defectPeak * 100}%` }} />
            <span className="confirmed" style={{ width: `${d.confirmed / defectPeak * 100}%` }} />
          </span>
          <strong>{d.confirmed}/{d.flagged}</strong>
        </li>)}</ol> : <p className="pilot-help">No defects flagged in this period.</p>}
      </section>
      <section className="pilot-panel" aria-labelledby="recent-title">
      <header className="factory-card-head"><h2 id="recent-title">Recent activity</h2><button className="text-link" onClick={() => navigate('activity')}>Full trail<ArrowRight size={14} /></button></header>
      <ol className="factory-recent">{[...data.activity].filter(event => !event.action.startsWith('session')).sort((a, b) => b.created_at.localeCompare(a.created_at)).slice(0, 6).map(event => <li key={event.id}>
        <strong>{event.action.replaceAll('_', ' ').replaceAll('.', ' ')}</strong>
        <small><time dateTime={event.created_at}>{dateTime(event.created_at)}</time> · {event.actor?.name || 'System'}</small>
      </li>)}</ol>
      </section>
    </div>

  </div>
}
