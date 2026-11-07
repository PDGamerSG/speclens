import { useEffect, useState, type ReactNode } from 'react'
import { api } from '../api'
import type { EvalReport } from '../api/types'
import { CurvesPanel, ThresholdCallouts } from '../components/Curves'
import { Button, ErrorLine, NotRun, Spinner, Stat, cx } from '../components/ui'
import { sortCurves } from '../lib/curves'
import { dateTime, dur, pct, titleCase, usd } from '../lib/format'

function Panel({ title, sub, children, className }: { title: string; sub?: string; children: ReactNode; className?: string }) {
  return (
    <section className={cx('bg-panel border border-rule rounded-[3px] p-4 min-w-0', className)}>
      <h2 className="text-[15px] font-bold">{title}</h2>
      {sub && <p className="text-[12.5px] text-fg-3 mt-0.5 mb-3">{sub}</p>}
      {!sub && <div className="h-3" />}
      {children}
    </section>
  )
}

function Bar({ value, tone = 'fg' }: { value: number; tone?: 'fg' | 'pass' | 'signal' }) {
  return (
    <div className="flex-1 h-[6px] bg-well rounded-[1px] overflow-hidden min-w-[60px]">
      <div className={cx('h-full rounded-[1px]', tone === 'pass' ? 'bg-pass' : tone === 'signal' ? 'bg-signal' : 'bg-fg-2')} style={{ width: `${Math.max(0, Math.min(1, value)) * 100}%` }} />
    </div>
  )
}

const ci = (c: [number, number]) => `95% CI ${pct(c[0], 1)}–${pct(c[1], 1)}`

export function ResultsScreen() {
  const [data, setData] = useState<EvalReport | null>(null)
  const [error, setError] = useState<string | null>(null)
  const [loading, setLoading] = useState(true)

  const load = () => {
    setLoading(true)
    setError(null)
    api
      .evalReport()
      .then(setData)
      .catch((e) => setError(e instanceof Error ? e.message : String(e)))
      .finally(() => setLoading(false))
  }
  useEffect(load, [])

  const rb = data?.real_benchmark ?? null
  const fs = data?.forge_stats ?? null
  const sam = data?.sam_real ?? null
  const curves = sortCurves(data?.curves ?? [])
  const pending = (
    <NotRun title="Not run yet">
      Run <span className="num">python eval/run_eval.py</span>, then reload.
    </NotRun>
  )

  return (
    <main className="px-4 lg:px-6 pb-24 pt-5 max-w-[1680px] mx-auto">
      <div className="flex flex-wrap items-end justify-between gap-4 pb-4 border-b border-rule">
        <div className="max-w-[70ch]">
          <h1 className="text-[24px] font-bold tracking-[-0.015em] leading-tight">Benchmark results</h1>
          <p className="text-[14px] text-fg-2 mt-1.5">
            Precomputed by <span className="num text-[12.5px]">eval/run_eval.py</span> on the MVTec AD hazelnut test split and our forged sets.
            {data?.generated ? (
              <>
                {' '}
                Generated <span className="num text-[12.5px]">{dateTime(data.generated)}</span>.
              </>
            ) : null}
          </p>
        </div>
        <Button onClick={load} disabled={loading}>
          {loading && <Spinner />}
          Reload
        </Button>
      </div>
      {error && <div className="mt-4"><ErrorLine>{error}</ErrorLine></div>}
      {loading && !data && <p className="mt-6 text-fg-3 text-[13px]">Loading results</p>}

      {data && (
        <div className="grid gap-4 mt-5">
          <div className="grid xl:grid-cols-[minmax(0,1.3fr)_minmax(0,1fr)] gap-4">
            <Panel title="Real benchmark" sub={rb ? `Zero-shot Muse Spark on ${rb.n_defect} real defective and ${rb.n_good} good hazelnuts` : undefined}>
              {rb ? (
                <div className="grid gap-5">
                  <div className="grid grid-cols-2 sm:grid-cols-4 gap-4">
                    <Stat label="Recall" value={pct(rb.recall, 1)} sub={ci(rb.recall_ci)} tone="pass" />
                    <Stat label="Specificity" value={pct(rb.specificity, 1)} sub={ci(rb.specificity_ci)} tone="pass" />
                    <Stat label="Type accuracy" value={pct(rb.type_accuracy, 1)} />
                    <Stat label="Box hit" value={pct(rb.box_hit, 1)} />
                  </div>
                  <table className="w-full text-[12.5px]">
                    <thead className="text-fg-3 text-left">
                      <tr className="border-b border-rule">
                        <th className="font-semibold py-1.5">Defect type</th>
                        <th className="font-semibold py-1.5 text-right">Detected</th>
                        <th className="font-semibold py-1.5 pl-4 w-[45%]">Recall</th>
                      </tr>
                    </thead>
                    <tbody>
                      {Object.entries(rb.by_type).map(([t, v]) => (
                        <tr key={t} className="border-b border-rule/60 last:border-0">
                          <td className="py-1.5">{titleCase(t)}</td>
                          <td className="py-1.5 text-right num">
                            {v.detected}/{v.n}
                          </td>
                          <td className="py-1.5 pl-4">
                            <div className="flex items-center gap-2">
                              <Bar value={v.n ? v.detected / v.n : 0} tone="pass" />
                              <span className="num text-fg-2 w-12 text-right">{pct(v.n ? v.detected / v.n : 0)}</span>
                            </div>
                          </td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
              ) : (
                pending
              )}
            </Panel>

            <Panel title="Forge stats" sub="What one accepted, pixel-labelled defect costs">
              {fs ? (
                <div className="grid grid-cols-2 gap-4">
                  <Stat label="Acceptance rate" value={pct(fs.acceptance_rate, 1)} sub={`${fs.accepted} of ${fs.attempted} attempted`} />
                  <Stat label="Cost per accepted sample" value={usd(fs.cost_per_accepted_usd, 4)} tone="signal" />
                  <Stat label="Seconds per accepted sample" value={dur(fs.seconds_per_accepted * 1000)} />
                  <Stat label="Validator pass rate" value={pct(fs.validator_pass_rate, 1)} />
                  <Stat label="Mean SAM IoU" value={fs.mean_sam_iou == null ? '–' : fs.mean_sam_iou.toFixed(3)} />
                </div>
              ) : (
                pending
              )}
            </Panel>
          </div>

          <Panel title="Detection-threshold curves" sub="Forged defects faded and shrunk. Caught means the inspector's box overlaps the defect in at least 2 of 3 passes">
            {curves.length ? (
              <div className="grid gap-4">
                <ThresholdCallouts curves={curves} />
                <CurvesPanel curves={curves} />
              </div>
            ) : (
              pending
            )}
          </Panel>

          <div className="grid lg:grid-cols-3 gap-4">
            <Panel title="In-context examples" sub="What the inspector sees in its prompt">
              {data.in_context.length ? (
                <div className="overflow-x-auto">
                  <table className="w-full text-[12.5px]">
                    <thead className="text-fg-3 text-left">
                      <tr className="border-b border-rule">
                        <th className="font-semibold py-1.5 pr-2">Condition</th>
                        <th className="font-semibold py-1.5 text-right">Recall</th>
                        <th className="font-semibold py-1.5 text-right">Specificity</th>
                        <th className="font-semibold py-1.5 text-right pl-2">n</th>
                      </tr>
                    </thead>
                    <tbody>
                      {data.in_context.map((r) => (
                        <tr key={r.condition} className="border-b border-rule/60 last:border-0 align-top">
                          <td className="py-1.5 pr-2">
                            <span className="num text-fg-3 mr-1.5">{r.condition}</span>
                            {r.label}
                          </td>
                          <td className="py-1.5 num text-right">{pct(r.recall)}</td>
                          <td className="py-1.5 num text-right">{pct(r.specificity)}</td>
                          <td className="py-1.5 num text-right text-fg-3 pl-2">{r.n}</td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
              ) : (
                pending
              )}
            </Panel>

            <Panel title="Faint-defect lift" sub="Detections on the hardest severity levels">
              {data.faint_lift.length ? (
                <ul className="grid gap-3">
                  {data.faint_lift.map((r) => (
                    <li key={r.condition}>
                      <div className="flex items-baseline justify-between gap-2 text-[12.5px]">
                        <span className="text-fg-2">{r.label}</span>
                        <span className="num shrink-0">
                          {r.detected}/{r.n}
                        </span>
                      </div>
                      <div className="flex items-center gap-2 mt-1">
                        <Bar value={r.n ? r.detected / r.n : 0} tone="signal" />
                        <span className="num text-[11.5px] text-fg-3 w-10 text-right">{pct(r.n ? r.detected / r.n : 0)}</span>
                      </div>
                    </li>
                  ))}
                </ul>
              ) : (
                pending
              )}
            </Panel>

            <Panel title="SAM 3.1 on real defects" sub={sam ? `Tight box prompts on ${sam.n} real defects, IoU against ground-truth masks` : undefined}>
              {sam ? (
                <div className="grid gap-4">
                  <div className="grid grid-cols-2 gap-4">
                    <Stat label="Median IoU" value={sam.median_iou.toFixed(3)} />
                    <Stat label="Mean IoU" value={sam.mean_iou.toFixed(3)} />
                  </div>
                  <ul className="grid gap-1.5">
                    {Object.entries(sam.by_type).map(([t, v]) => (
                      <li key={t} className="grid grid-cols-[64px_1fr_44px] items-center gap-2 text-[12.5px]">
                        <span>{titleCase(t)}</span>
                        <Bar value={v} />
                        <span className="num text-right text-fg-2">{v.toFixed(2)}</span>
                      </li>
                    ))}
                  </ul>
                </div>
              ) : (
                pending
              )}
            </Panel>
          </div>

          {data.blind_spot ? (
            <Panel title="White-print blind spot" sub={data.blind_spot.finding}>
              <ul className="grid gap-3 max-w-[90ch]">
                {data.blind_spot.rows.map((r) => (
                  <li key={r.label}>
                    <div className="flex items-baseline justify-between gap-2 text-[12.5px]">
                      <span className="text-fg-2">{r.label}</span>
                      <span className="num shrink-0">
                        {r.detected}/{r.n}
                      </span>
                    </div>
                    <div className="flex items-center gap-2 mt-1">
                      <Bar value={r.n ? r.detected / r.n : 0} tone={r.tone} />
                      <span className="num text-[11.5px] text-fg-3 w-10 text-right">{pct(r.n ? r.detected / r.n : 0)}</span>
                    </div>
                  </li>
                ))}
              </ul>
              <p className="mt-4 text-[12.5px] text-fg-3 max-w-[90ch]">
                <span className="text-fg-2">Spec amendment tested:</span> {data.blind_spot.amendment}
              </p>
            </Panel>
          ) : null}

          <Panel title="Notes">
            {data.notes.length ? (
              <ul className="grid gap-1.5 text-[13.5px] text-fg-2 max-w-[90ch] list-disc pl-5 marker:text-fg-3">
                {data.notes.map((n, i) => (
                  <li key={i}>{n}</li>
                ))}
              </ul>
            ) : (
              <p className="text-[13px] text-fg-3">No notes.</p>
            )}
          </Panel>
        </div>
      )}
    </main>
  )
}
