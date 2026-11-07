import { useMemo } from 'react'
import type { Part, Sample, SeverityKind, SeverityPoint } from '../api/types'
import { CurvesPanel, ThresholdCallouts } from '../components/Curves'
import { ZoomWindow } from '../components/Zoom'
import { Button, ErrorLine, NotRun, Spinner, cx } from '../components/ui'
import { typeColor } from '../lib/colors'
import { sortCurves } from '../lib/curves'
import { dateTime, level, mm, titleCase } from '../lib/format'
import { SEVERITY_VARIANTS, stageStatus, useStore } from '../state/store'

const LADDER: { kind: SeverityKind; levels: number[] }[] = [
  { kind: 'opacity', levels: [1, 0.5, 0.25, 0.12] },
  { kind: 'size', levels: [0.6, 0.35, 0.2] },
]

export function RunPicker() {
  const { state, actions } = useStore()
  if (!state.runs.length) return null
  return (
    <label className="flex items-center gap-2 min-w-0 max-w-full text-[12.5px] text-fg-3">
      Run
      <select
        value={state.run?.id ?? ''}
        onChange={(e) => void actions.loadRun(e.target.value)}
        disabled={state.streaming !== 'idle'}
        className="num h-8 min-w-0 flex-1 sm:flex-none sm:w-[340px] bg-well border border-rule-2 rounded-[3px] px-2 text-[12px] text-fg"
      >
        {!state.run && <option value="">Choose a run</option>}
        {state.runs.map((r) => (
          <option key={r.id} value={r.id}>
            {r.id}, {r.accepted} accepted{r.demo ? ', replay' : ''}, {dateTime(r.created)}
          </option>
        ))}
      </select>
    </label>
  )
}

function Variant({ p, kind, lv, sample, size }: { p?: SeverityPoint; kind: SeverityKind; lv: number; sample: Sample; size: [number, number] | null }) {
  // caught = the inspector's box overlaps the defect; elsewhere = it claimed a defect, but somewhere else
  const elsewhere = !!p && !p.detected && !!p.flagged
  return (
    <figure className="min-w-0">
      <div className={cx('relative aspect-square rounded-[2px] overflow-hidden bg-well', p ? (p.detected ? 'ring-1 ring-pass/60' : elsewhere ? 'ring-1 ring-signal/70' : 'ring-1 ring-miss/70') : 'ring-1 ring-rule')}>
        {p ? <ZoomWindow src={p.url} bbox={sample.bbox} size={size} pad={2.6} minSide={120} className="absolute inset-0" alt={`${kind} ${level(lv)}`} /> : null}
        {p && (
          <span className={cx('absolute inset-x-0 bottom-0 h-[3px]', p.detected ? 'bg-pass' : elsewhere ? 'bg-signal' : 'bg-miss')} aria-hidden />
        )}
      </div>
      <figcaption className="mt-1 flex items-center justify-between gap-1 text-[10.5px] leading-tight">
        <span className="num text-fg-3">{level(lv)}</span>
        {p ? (
          <span className={cx('inline-flex items-center gap-0.5 font-semibold', p.detected ? 'text-pass' : elsewhere ? 'text-signal' : 'text-miss')} title={`predicted ${p.pred_type}, confidence ${p.confidence.toFixed(2)}`}>
            <svg viewBox="0 0 12 12" className="size-2.5" aria-hidden>
              {p.detected ? <path d="M2.5 6.2l2.2 2.2L9.5 3.6" fill="none" stroke="currentColor" strokeWidth="1.8" /> : <path d="M3 3l6 6M9 3l-6 6" stroke="currentColor" strokeWidth="1.8" />}
            </svg>
            <span className="max-sm:sr-only">{p.detected ? 'caught' : elsewhere ? 'box off' : 'missed'}</span>
          </span>
        ) : (
          <span className="text-fg-3/60">…</span>
        )}
      </figcaption>
    </figure>
  )
}

function Strip({ sample, points, types, part }: { sample: Sample; points: SeverityPoint[]; types: string[]; part?: Part }) {
  const size: [number, number] | null = part ? [part.width, part.height] : null
  const find = (kind: SeverityKind, lv: number) => points.find((p) => p.kind === kind && Math.abs(p.level - lv) < 1e-6)
  const extra = points.filter((p) => !LADDER.some((g) => g.kind === p.kind && g.levels.some((l) => Math.abs(l - p.level) < 1e-6)))
  return (
    <li className="grid grid-cols-[72px_minmax(0,1fr)] sm:grid-cols-[96px_minmax(0,1fr)] gap-3 py-3 border-b border-rule">
      <div className="min-w-0">
        <div className="relative aspect-square rounded-[2px] overflow-hidden bg-well">
          {sample.crop_composite_url && <img src={sample.crop_composite_url} alt="" className="absolute inset-0 size-full object-cover" />}
        </div>
        <div className="mt-1 flex items-center gap-1 text-[12px] font-semibold">
          <span className="size-2 rounded-[1px]" style={{ background: typeColor(sample.defect_type, types) }} aria-hidden />
          {titleCase(sample.defect_type)}
        </div>
        <div className="num text-[10.5px] text-fg-3">
          {sample.id} {mm(sample.size_mm)}
        </div>
      </div>
      <div className="grid md:grid-cols-[4fr_3fr] gap-x-4 gap-y-2 min-w-0 max-w-[1040px]">
        {LADDER.map((g) => (
          <div key={g.kind} className="min-w-0">
            <div className="text-[11.5px] text-fg-3 mb-1">{g.kind === 'opacity' ? 'Opacity' : 'Size'}</div>
            <div className={cx('grid gap-1.5', g.kind === 'opacity' ? 'grid-cols-4' : 'grid-cols-4 md:grid-cols-3')}>
              {g.levels.map((lv) => (
                <Variant key={lv} p={find(g.kind, lv)} kind={g.kind} lv={lv} sample={sample} size={size} />
              ))}
            </div>
          </div>
        ))}
        {extra.length > 0 && (
          <div className="md:col-span-2 flex flex-wrap gap-1.5">
            {extra.map((p) => (
              <div key={`${p.kind}${p.level}`} className="w-16">
                <Variant p={p} kind={p.kind} lv={p.level} sample={sample} size={size} />
              </div>
            ))}
          </div>
        )}
      </div>
    </li>
  )
}

export function StressScreen() {
  const { state, actions } = useStore()
  const run = state.run
  const types = useMemo(() => run?.taxonomy.defects.map((d) => d.defect_type) ?? [], [run?.taxonomy])
  const accepted = useMemo(() => (run?.samples ?? []).filter((s) => s.status === 'accepted').sort((a, b) => types.indexOf(a.defect_type) - types.indexOf(b.defect_type) || a.id.localeCompare(b.id)), [run?.samples, types])
  const bySample = useMemo(() => {
    const m = new Map<string, SeverityPoint[]>()
    for (const p of run?.severity ?? []) {
      const a = m.get(p.sample_id) ?? []
      a.push(p)
      m.set(p.sample_id, a)
    }
    return m
  }, [run?.severity])
  const partById = useMemo(() => new Map(state.parts.map((p) => [p.id, p])), [state.parts])

  const stressActive = state.streaming === 'stress' || stageStatus(state.stages.stress) === 'active'
  const expected = accepted.length * SEVERITY_VARIANTS
  const done = run?.severity.length ?? 0
  const curves = useMemo(() => sortCurves(run?.curves ?? [], types), [run?.curves, types])
  const shown = accepted.filter((s) => bySample.has(s.id) || stressActive)

  return (
    <main className="px-4 lg:px-6 pb-24 pt-5 max-w-[1680px] mx-auto">
      <div className="flex flex-wrap items-end justify-between gap-4 pb-4 border-b border-rule">
        <div className="max-w-[68ch]">
          <h1 className="text-[24px] font-bold tracking-[-0.015em] leading-tight">How small and how faint before the inspector misses it</h1>
          <p className="text-[14px] text-fg-2 mt-1.5">
            Every accepted forgery is faded and shrunk by deterministic OpenCV code, and each variant is shown to the Muse Spark inspector. A defect counts as caught when the inspector's box overlaps it. The ground truth is known by construction.
          </p>
        </div>
        <div className="flex flex-wrap items-center gap-3 min-w-0 max-w-full">
          <RunPicker />
          {run && (
            <Button
              variant={curves.length ? 'line' : 'primary'}
              onClick={() => void actions.startStress()}
              disabled={state.streaming !== 'idle' || !accepted.length || run.status === 'running'}
            >
              {stressActive && <Spinner />}
              {stressActive ? (
                <>
                  Inspecting <span className="num">{done}/{expected || '–'}</span>
                </>
              ) : run.status === 'running' ? (
                'Forging in progress'
              ) : curves.length ? (
                'Run stress test again'
              ) : (
                'Run stress test'
              )}
            </Button>
          )}
        </div>
      </div>
      {state.runError && <div className="mt-3"><ErrorLine>{state.runError}</ErrorLine></div>}

      {!run ? (
        <div className="mt-6 max-w-xl">
          <NotRun title="No run to stress-test yet">
            Forge a run first.{' '}
            <a href="#/forge" className="text-fg underline underline-offset-4">
              Go to Forge
            </a>
          </NotRun>
        </div>
      ) : (
        <>
          {expected > 0 && (stressActive || (done > 0 && done < expected)) && (
            <div className="mt-4 h-[3px] bg-rule rounded-[1px] overflow-hidden" role="progressbar" aria-valuemin={0} aria-valuemax={expected} aria-valuenow={done} aria-label="Variants inspected">
              <div className="h-full bg-signal transition-[width] duration-300" style={{ width: `${Math.min(100, (done / expected) * 100)}%` }} />
            </div>
          )}

          <section className="mt-5">
            {curves.length ? (
              <ThresholdCallouts curves={curves} />
            ) : (
              <NotRun title={stressActive ? 'Inspecting variants' : 'No detection curves for this run yet'}>
                {stressActive
                  ? 'Curves appear as soon as the first sample’s ladder is inspected.'
                  : accepted.length
                    ? 'Run the stress test to find where each defect type stops being detected.'
                    : run.status === 'running'
                      ? 'Waiting for accepted samples.'
                      : 'This run has no accepted samples to stress-test.'}
              </NotRun>
            )}
          </section>

          {curves.length > 0 && (
            <section className="mt-6">
              <h2 className="text-[15px] font-bold mb-3">Detection-threshold curves</h2>
              <CurvesPanel curves={curves} />
            </section>
          )}

          {shown.length > 0 && (
            <section className="mt-8">
              <div className="flex flex-wrap items-baseline justify-between gap-2 mb-1">
                <h2 className="text-[15px] font-bold">Every variant the inspector saw</h2>
                <span className="text-[12px] text-fg-3">
                  <span className="num text-fg-2">{done}</span> of <span className="num text-fg-2">{expected}</span> inspected, <span className="num text-pass">{(run.severity ?? []).filter((p) => p.detected).length}</span> caught, <span className="num text-signal">{(run.severity ?? []).filter((p) => !p.detected && p.flagged).length}</span> flagged with the box off the defect, <span className="num text-miss">{(run.severity ?? []).filter((p) => !p.detected && !p.flagged).length}</span> missed
                  {run.controls ? (
                    <>
                      . False alarms on unedited parts: <span className="num text-fg-2">{run.controls.flagged}/{run.controls.n}</span>
                    </>
                  ) : null}
                </span>
              </div>
              <ul>
                {shown.map((s) => (
                  <Strip key={s.id} sample={s} points={bySample.get(s.id) ?? []} types={types} part={partById.get(s.part_id)} />
                ))}
              </ul>
            </section>
          )}
        </>
      )}
    </main>
  )
}
