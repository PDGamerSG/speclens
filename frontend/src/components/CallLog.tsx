import { useEffect, useState } from 'react'
import { modelInfo } from '../lib/colors'
import { clock, dur, usd } from '../lib/format'
import { useCalls, useStore } from '../state/store'
import { ModelChip, cx } from './ui'

function StatusCell({ status }: { status: number | string }) {
  const ok = status === 200 || status === '200'
  const replay = String(status).toLowerCase() === 'replay'
  return <span className={cx('num', ok ? 'text-pass' : replay ? 'text-signal' : 'text-miss')}>{String(status)}</span>
}

export function CallLog() {
  const { state } = useStore()
  const { calls, byModel, spent, total, budget } = useCalls()
  const [open, setOpen] = useState(false)
  const [fresh, setFresh] = useState(false)

  useEffect(() => {
    if (!state.lastCallAt) return
    setFresh(true)
    const t = setTimeout(() => setFresh(false), 1200)
    return () => clearTimeout(t)
  }, [state.lastCallAt])

  useEffect(() => {
    if (!open) return
    const onKey = (e: KeyboardEvent) => e.key === 'Escape' && setOpen(false)
    window.addEventListener('keydown', onKey)
    return () => window.removeEventListener('keydown', onKey)
  }, [open])

  const share = budget ? Math.min(1, spent / budget) : 0
  const models = Object.entries(byModel).sort((a, b) => b[1].cost_usd - a[1].cost_usd)

  return (
    <>
      <button
        type="button"
        onClick={() => setOpen(true)}
        aria-expanded={open}
        aria-controls="call-log"
        className={cx(
          'fixed z-40 right-4 bottom-4 [bottom:max(16px,env(safe-area-inset-bottom))] inline-flex items-center gap-2.5 h-10 pl-3 pr-3.5 rounded-[4px] bg-raised border border-rule-2 shadow-[0_6px_24px_rgba(0,0,0,.45)] hover:border-fg-3 transition-opacity',
          open && 'opacity-0 pointer-events-none',
        )}
      >
        <span className={cx('size-2 rounded-full', fresh ? 'bg-signal' : 'bg-pass/80')} aria-hidden />
        <span className="text-[12.5px] font-semibold text-fg-2"><span className="hidden sm:inline">Meta calls</span><span className="sm:hidden">Calls</span></span>
        <span className="num text-[12.5px] text-fg-3">{total}</span>
        <span className="num text-[14px] text-fg">{usd(spent, 2)}</span>
      </button>

      <section
        id="call-log"
        aria-label="Meta model call log"
        aria-hidden={!open}
        inert={!open}
        className={cx(
          'fixed z-40 inset-x-0 bottom-0 h-[72vh] sm:h-[56vh] flex flex-col bg-page border-t border-rule-2 shadow-[0_-12px_40px_rgba(0,0,0,.5)] transition-transform duration-300 ease-out',
          open ? 'translate-y-0' : 'translate-y-full',
        )}
      >
        <header className="flex flex-wrap items-center gap-x-6 gap-y-3 px-4 lg:px-6 py-3 border-b border-rule">
          <div className="min-w-0">
            <h2 className="text-[15px] font-bold">Meta model calls</h2>
            <p className="text-[12px] text-fg-3">Every call the backend made, from its ledger. Refreshes every 3 s and on each live event.</p>
          </div>
          <div className="flex flex-wrap items-center gap-x-4 gap-y-2">
            {models.map(([m, v]) => (
              <span key={m} className="inline-flex items-center gap-2 text-[12px]">
                <ModelChip model={m} />
                <span className="num text-fg-2">{v.calls}</span>
                <span className="num text-fg">{usd(v.cost_usd, 3)}</span>
              </span>
            ))}
          </div>
          <div className="ml-auto flex items-center gap-4">
            <div className="min-w-[160px]">
              <div className="text-[13px]">
                <span className="num text-fg text-[15px]">{usd(spent, 2)}</span>
                <span className="text-fg-3"> of </span>
                <span className="num text-fg-2">{budget != null ? usd(budget, 0) : '–'}</span>
                <span className="text-fg-3"> budget</span>
              </div>
              <div className="h-[3px] bg-rule mt-1.5 rounded-[1px] overflow-hidden">
                <div className={cx('h-full', share > 0.8 ? 'bg-miss' : 'bg-signal')} style={{ width: `${share * 100}%` }} />
              </div>
            </div>
            <button type="button" onClick={() => setOpen(false)} className="size-9 grid place-items-center rounded-[3px] border border-rule-2 text-fg-2 hover:text-fg hover:bg-raised" aria-label="Close call log">
              <svg viewBox="0 0 16 16" className="size-4" aria-hidden>
                <path d="M3 6l5 5 5-5" fill="none" stroke="currentColor" strokeWidth="1.6" />
              </svg>
            </button>
          </div>
        </header>
        <div className="flex-1 overflow-auto">
          {calls.length === 0 ? (
            <p className="px-6 py-8 text-fg-3 text-[13px]">No calls yet. Read a spec or forge a run, and each Meta model call appears here as it happens.</p>
          ) : (
            <table className="w-full text-[12.5px]">
              <thead className="sticky top-0 bg-page text-fg-3 text-left">
                <tr className="border-b border-rule">
                  <th className="font-semibold px-4 lg:px-6 py-2 hidden sm:table-cell">Time</th>
                  <th className="font-semibold px-3 py-2 pl-4 sm:pl-3">Model</th>
                  <th className="font-semibold px-3 py-2">Op</th>
                  <th className="font-semibold px-3 py-2 text-right">Latency</th>
                  <th className="font-semibold px-3 py-2 text-right">Cost</th>
                  <th className="font-semibold px-3 py-2 text-right">Status</th>
                  <th className="font-semibold px-3 py-2 hidden md:table-cell">Run</th>
                  <th className="font-semibold px-3 pr-6 py-2 hidden lg:table-cell text-right">Cached</th>
                </tr>
              </thead>
              <tbody>
                {calls.map((c, i) => (
                  <tr key={`${c.t}${c.model}${c.op}${c.ms}${i}`} className="border-b border-rule/50 hover:bg-panel">
                    <td className="num px-4 lg:px-6 py-1.5 text-fg-3 hidden sm:table-cell">{clock(c.t)}</td>
                    <td className="px-3 py-1.5 pl-4 sm:pl-3">
                      <ModelChip model={c.model} />
                      <span className="sr-only">{modelInfo(c.model).label}</span>
                    </td>
                    <td className="px-3 py-1.5 text-fg-2">{c.op}</td>
                    <td className="num px-3 py-1.5 text-right text-fg-2">{dur(c.ms)}</td>
                    <td className="num px-3 py-1.5 text-right">{usd(c.cost_usd, 4)}</td>
                    <td className="px-3 py-1.5 text-right">
                      <StatusCell status={c.status} />
                    </td>
                    <td className="num px-3 py-1.5 text-fg-3 hidden md:table-cell truncate max-w-[200px]">{c.run_id ?? '–'}</td>
                    <td className="num px-3 pr-6 py-1.5 text-fg-3 hidden lg:table-cell text-right">{c.cached_tokens ? c.cached_tokens.toLocaleString() : '–'}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          )}
        </div>
      </section>
    </>
  )
}
