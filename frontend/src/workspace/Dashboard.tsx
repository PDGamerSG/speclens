import { ArrowDown } from 'lucide-react'
import { Chief } from './Chief'
import type { DashboardData } from './types'

const percent = (value: number | null) => value === null ? '–' : `${Math.round(value * 100)}%`
const PERIODS = [7, 30, 90]

function DailyBars({ daily }: { daily: DashboardData['daily'] }) {
  const peak = Math.max(1, ...daily.map(d => d.inspections))
  return <div className="day-bars" role="img" aria-label={`Decisions per day, peak ${peak}`}>
    {daily.map(d => <div key={d.day} className="day-bar" title={`${d.day}: ${d.accepted} accepted, ${d.rejected} rejected, ${d.review} for review`}>
      <span className="seg review" style={{ height: `${d.review / peak * 100}%` }} />
      <span className="seg reject" style={{ height: `${d.rejected / peak * 100}%` }} />
      <span className="seg accept" style={{ height: `${d.accepted / peak * 100}%` }} />
    </div>)}
  </div>
}

export function DashboardSection({ data, days, part, factory, onDays, onInspect, onHistory }: {
  data: DashboardData | null; days: number; part: string; factory: string;
  onDays: (days: number) => void; onInspect: () => void; onHistory: () => void;
}) {
  const t = data?.totals
  const weeklyPeak = Math.max(1, ...(data?.corrections_weekly || []).map(w => w.corrections))
  return <section id="dashboard" className="page-section" aria-labelledby="dashboard-title">
    <header className="section-head">
      <div><h2 id="dashboard-title">Quality dashboard</h2><p>{`Decisions, defects and corrections for ${part.toLowerCase()} at ${factory}.`}</p></div>
      <div className="section-actions">
        <button className="text-link jump-link" aria-label="Inspection history" onClick={onHistory}><ArrowDown size={14} />Every inspection</button>
        <label className="period-select">Period<select value={days} onChange={e => onDays(Number(e.target.value))} aria-label="Dashboard period">
          {PERIODS.map(p => <option key={p} value={p}>Last {p} days</option>)}
        </select></label>
      </div>
    </header>
    {!data || !t ? <p className="dash-loading">Loading the dashboard…</p> : t.inspections === 0 ? <div className="empty-state">
      <Chief size={72} />
      <div><h3>No inspections in this period</h3><p>The dashboard fills in as parts are inspected under this specification.</p></div>
      <button className="button secondary" onClick={onInspect}>Go to inspection desk</button>
    </div> : <>
      <dl className="kpis">
        <div><dt>Inspected</dt><dd>{t.inspections}</dd></div>
        <div><dt>Reject rate</dt><dd className="reject">{percent(t.reject_rate)}</dd></div>
        <div><dt>Sent to review</dt><dd className="review">{percent(t.review_rate)}</dd></div>
        <div><dt title="Inspections an engineer corrected. A lower share means the model agrees with your engineers more often.">Corrected by engineers</dt><dd>{percent(t.corrected_share)}</dd></div>
        <div><dt title="Memory-on inspections whose rationale cited a recalled correction ID">Memory cited</dt><dd>{percent(t.citation_rate)}{!!t.unknown_citations && <small className="dash-warning"> {t.unknown_citations} citation{t.unknown_citations === 1 ? '' : 's'} not in recall</small>}</dd></div>
        <div><dt>Cost per inspection</dt><dd>{t.cost_per_inspection === null ? '–' : `$${t.cost_per_inspection.toFixed(4)}`}</dd></div>
        <div><dt>Median time</dt><dd>{t.latency_p50_ms === null ? '–' : `${(t.latency_p50_ms / 1000).toFixed(1)}s`}</dd></div>
      </dl>
      <div className="dash-grid">
        <article className="dash-card wide">
          <h3>Decisions per day</h3>
          <DailyBars daily={data.daily} />
          <div className="dash-legend"><span className="accept">Accepted {t.accepted}</span><span className="reject">Rejected {t.rejected}</span><span className="review">Review {t.review}</span></div>
        </article>
        <article className="dash-card">
          <h3>Defect Pareto</h3>
          {data.pareto.length ? <ol className="pareto">{data.pareto.map(p => <li key={p.defect_type}>
            <span className="pareto-label">{p.label}{p.clause && <small> {p.clause}</small>}</span>
            <span className="pareto-track"><span style={{ width: `${p.share * 100}%` }} /></span>
            <strong>{p.count}</strong>
          </li>)}</ol> : <p className="dash-note">No rejects in this period.</p>}
        </article>
        <article className="dash-card">
          <h3>Corrections per week</h3>
          {data.corrections_weekly.length ? <ol className="pareto">{data.corrections_weekly.map(w => <li key={w.week}>
            <span className="pareto-label">Week of {new Date(w.week + 'T00:00:00').toLocaleDateString([], { month: 'short', day: 'numeric' })}</span>
            <span className="pareto-track"><span style={{ width: `${w.corrections / weeklyPeak * 100}%` }} /></span>
            <strong>{w.corrections}</strong>
          </li>)}</ol> : <p className="dash-note">No corrections in this period.</p>}
          <p className="dash-note">{t.overturned} of {t.corrections} corrections changed the decision.</p>
        </article>
        <article className="dash-card">
          <h3>Spend and prompt cache</h3>
          <p className="dash-figure">${t.cost_usd.toFixed(3)}<small> model spend in this period</small></p>
          {data.cache.prompt_tokens
            ? <p className="dash-figure">{Math.round(data.cache.hit_rate * 100)}%<small> of prompt tokens served from cache, server-wide</small></p>
            : <p className="dash-note">No prompt cache data yet.</p>}
          {t.latency_p95_ms !== null && <p className="dash-note">95% of inspections finished within {(t.latency_p95_ms / 1000).toFixed(1)}s.</p>}
        </article>
      </div>
    </>}
  </section>
}
