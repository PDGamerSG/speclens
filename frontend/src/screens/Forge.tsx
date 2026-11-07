import { useEffect, useMemo, useRef, useState, type CSSProperties } from 'react'
import { api } from '../api'
import type { Part, Run } from '../api/types'
import { EmptySlot, SampleCard } from '../components/SampleCard'
import { SampleDetail } from '../components/SampleDetail'
import { StageTimeline } from '../components/StageTimeline'
import { Button, Checkbox, ErrorLine, Spinner, StepHead, Stepper, Switch, cx } from '../components/ui'
import { typeColor } from '../lib/colors'
import { dur, usd } from '../lib/format'
import { SEVERITY_VARIANTS, useCalls, useStore } from '../state/store'

export function useNow(active: boolean, ms = 1000) {
  const [now, setNow] = useState(() => Date.now())
  useEffect(() => {
    if (!active) return
    const t = setInterval(() => setNow(Date.now()), ms)
    return () => clearInterval(t)
  }, [active, ms])
  return now
}

function SpecSection() {
  const { state, actions } = useStore()
  const tax = state.taxonomy
  const changed = state.defaultSpec && state.specText !== state.defaultSpec
  return (
    <section className="px-4 lg:px-5 py-5 border-b border-rule">
      <StepHead
        n={1}
        title="Spec"
        right={
          changed ? (
            <Button variant="quiet" size="sm" onClick={actions.resetSpec}>
              Restore sample spec
            </Button>
          ) : null
        }
      />
      <label htmlFor="spec" className="sr-only">
        QA specification
      </label>
      <textarea
        id="spec"
        value={state.specText}
        onChange={(e) => actions.setSpec(e.target.value)}
        rows={7}
        spellCheck={false}
        placeholder="Paste the QA spec for your part"
        className="w-full resize-y bg-well border border-rule rounded-[3px] px-3 py-2.5 text-[12.5px] leading-[1.55] text-fg-2 focus:text-fg focus:border-rule-2 outline-none focus-visible:outline-2"
      />
      <div className="flex items-center gap-3 mt-2.5">
        <Button onClick={() => void actions.readSpec()} disabled={state.taxonomyBusy || !state.specText.trim()}>
          {state.taxonomyBusy ? <Spinner /> : null}
          {state.taxonomyBusy ? 'Reading spec' : tax ? 'Read spec again' : 'Read spec'}
        </Button>
        <span className="text-[12px] text-fg-3">Muse Spark turns the spec into defect types</span>
      </div>
      {state.taxonomyError && <div className="mt-3"><ErrorLine>{state.taxonomyError}</ErrorLine></div>}

      {tax && (
        <div className="mt-4">
          <div className="flex items-baseline justify-between gap-2 mb-2 text-[12px]">
            <span className="text-fg-2 truncate">
              {tax.part_name}
              {tax.part_width_mm ? (
                <>
                  , <span className="num">{tax.part_width_mm} mm</span> wide
                </>
              ) : null}
            </span>
            <span className="text-fg-3 shrink-0">
              <span className="num">{tax.defects.length - state.excluded.length}</span> of <span className="num">{tax.defects.length}</span> types
            </span>
          </div>
          <ul className="grid gap-1.5">
            {tax.defects.map((d) => {
              const on = !state.excluded.includes(d.defect_type)
              return (
                <li key={d.defect_type}>
                  <button
                    type="button"
                    aria-pressed={on}
                    onClick={() => actions.toggleType(d.defect_type)}
                    className={cx('w-full text-left grid grid-cols-[auto_1fr] gap-x-2.5 px-3 py-2.5 rounded-[3px] border transition-colors', on ? 'bg-panel border-rule hover:border-rule-2' : 'border-dashed border-rule opacity-50 hover:opacity-75')}
                  >
                    <span className="mt-[5px] size-2.5 rounded-[1px]" style={{ background: on ? typeColor(d.defect_type, tax.defects.map((x) => x.defect_type)) : 'var(--color-rule-2)' }} aria-hidden />
                    <span className="min-w-0">
                      <span className="flex items-baseline gap-2">
                        <span className="text-[14px] font-semibold capitalize">{d.defect_type}</span>
                        <span className="num text-[11px] text-fg-3">§{d.clause}</span>
                        <span className="ml-auto text-[11px] text-fg-3">{on ? 'included' : 'skipped'}</span>
                      </span>
                      <span className="block text-[12.5px] text-fg-2 leading-snug mt-0.5 line-clamp-2">{d.description}</span>
                      <span className="block text-[11.5px] text-fg-3 leading-snug mt-1">Spec limit: {d.severity_note}</span>
                    </span>
                  </button>
                </li>
              )
            })}
          </ul>
        </div>
      )}
    </section>
  )
}

function PartThumb({ part, selected, mask, onToggle, onMask }: { part: Part; selected: boolean; mask: boolean; onToggle: () => void; onMask: () => void }) {
  return (
    <div className="relative">
      <button
        type="button"
        onClick={onToggle}
        aria-pressed={selected}
        aria-label={`${part.name}${selected ? ', selected' : ''}`}
        className={cx('relative block w-full aspect-square overflow-hidden rounded-[2px] bg-well', selected ? 'ring-2 ring-signal ring-offset-2 ring-offset-page' : 'ring-1 ring-rule hover:ring-rule-2')}
      >
        <img src={part.url} alt="" loading="lazy" className={cx('absolute inset-0 size-full object-cover', !selected && 'opacity-60')} draggable={false} />
        {mask && part.mask_url && (
          <div
            className="absolute inset-0 mask-tint opacity-40"
            style={{ background: 'var(--color-part)', WebkitMaskImage: `url("${part.mask_url}")`, maskImage: `url("${part.mask_url}")` } as CSSProperties}
          />
        )}
        {mask && !part.mask_url && <span className="absolute inset-x-0 bottom-0 py-0.5 bg-well/80 text-[10px] text-fg-3 text-center">mask pending</span>}
        {selected && (
          <span className="absolute top-1 right-1 grid place-items-center size-4 rounded-[2px] bg-signal text-signal-ink" aria-hidden>
            <svg viewBox="0 0 16 16" className="size-3">
              <path d="M3.5 8.5l3 3 6-6.5" fill="none" stroke="currentColor" strokeWidth="2.2" />
            </svg>
          </span>
        )}
        {part.source === 'upload' && <span className="absolute top-1 left-1 px-1 rounded-[2px] bg-well/85 text-[10px] text-fg-2">yours</span>}
      </button>
      <button
        type="button"
        onClick={onMask}
        aria-pressed={mask}
        disabled={!part.mask_url}
        className={cx('absolute bottom-1 left-1 h-5 px-1.5 rounded-[2px] text-[10px] font-semibold disabled:hidden', mask ? 'bg-part text-signal-ink' : 'bg-well/85 text-fg-2 hover:text-fg')}
        aria-label={`${mask ? 'Hide' : 'Show'} part mask for ${part.name}`}
      >
        mask
      </button>
    </div>
  )
}

function PartsSection() {
  const { state, actions } = useStore()
  const [masks, setMasks] = useState<Set<string>>(new Set())
  const file = useRef<HTMLInputElement>(null)
  const allOn = state.parts.length > 0 && state.parts.filter((p) => p.mask_url).every((p) => masks.has(p.id))
  return (
    <section className="px-4 lg:px-5 py-5 border-b border-rule">
      <StepHead
        n={2}
        title="Good parts"
        right={<Switch id="masks-all" checked={allOn && masks.size > 0} onChange={(b) => setMasks(b ? new Set(state.parts.filter((p) => p.mask_url).map((p) => p.id)) : new Set())} label="Part masks" />}
      />
      <div className="flex items-center justify-between gap-2 mb-3 text-[12px] text-fg-3">
        <span>
          <span className="num text-fg-2">{state.selected.length}</span> of <span className="num text-fg-2">{state.parts.length}</span> selected
        </span>
        <button type="button" className="hover:text-fg underline underline-offset-4 decoration-rule-2" onClick={() => actions.setSelected(state.selected.length === state.parts.length ? [] : state.parts.map((p) => p.id))}>
          {state.selected.length === state.parts.length ? 'Select none' : 'Select all'}
        </button>
      </div>
      {!state.partsLoaded ? (
        <div className="grid grid-cols-4 lg:grid-cols-3 gap-2.5">
          {Array.from({ length: 6 }, (_, i) => (
            <div key={i} className="aspect-square bg-well rounded-[2px] animate-pulse" />
          ))}
        </div>
      ) : (
        <div className="grid grid-cols-3 sm:grid-cols-4 lg:grid-cols-3 gap-2.5">
          {state.parts.map((p) => (
            <PartThumb
              key={p.id}
              part={p}
              selected={state.selected.includes(p.id)}
              mask={masks.has(p.id)}
              onToggle={() => actions.togglePart(p.id)}
              onMask={() =>
                setMasks((m) => {
                  const n = new Set(m)
                  if (n.has(p.id)) n.delete(p.id)
                  else n.add(p.id)
                  return n
                })
              }
            />
          ))}
          <button
            type="button"
            onClick={() => file.current?.click()}
            disabled={state.uploading}
            className="aspect-square rounded-[2px] border border-dashed border-rule-2 text-fg-2 hover:text-fg hover:border-fg-3 flex flex-col items-center justify-center gap-1.5 text-[12px] font-semibold"
          >
            {state.uploading ? (
              <Spinner />
            ) : (
              <svg viewBox="0 0 20 20" className="size-5" aria-hidden>
                <path d="M10 4v12M4 10h12" stroke="currentColor" strokeWidth="1.6" />
              </svg>
            )}
            {state.uploading ? 'Uploading' : 'Add photos'}
          </button>
        </div>
      )}
      <input
        ref={file}
        type="file"
        accept="image/*"
        multiple
        capture="environment"
        className="sr-only"
        tabIndex={-1}
        aria-hidden
        onChange={(e) => {
          const files = Array.from(e.target.files ?? [])
          e.target.value = ''
          void actions.uploadParts(files)
        }}
      />
      {state.partsError && <div className="mt-3"><ErrorLine>{state.partsError}</ErrorLine></div>}
    </section>
  )
}

function ForgeSection() {
  const { state, actions } = useStore()
  const types = state.taxonomy ? state.taxonomy.defects.filter((d) => !state.excluded.includes(d.defect_type)).length : null
  const total = types != null ? types * state.perType : null
  const running = state.streaming === 'run'
  const run = state.run
  const done = run ? run.samples.filter((s) => s.status !== 'forging').length : 0
  const target = state.totalSamples ?? total ?? 0
  return (
    <section className="px-4 lg:px-5 py-5">
      <StepHead n={3} title="Forge" />
      <div className="flex items-center justify-between gap-3">
        <span className="text-[13px] text-fg-2">Defects per type</span>
        <Stepper value={state.perType} onChange={actions.setPerType} label="Defects per type" />
      </div>
      <p className="text-[12px] text-fg-3 mt-2.5">
        {total != null ? (
          <>
            <span className="num text-fg-2">{state.perType}</span> per type × <span className="num text-fg-2">{types}</span> types = <span className="num text-fg">{total}</span> defects on <span className="num text-fg-2">{state.selected.length}</span> parts
          </>
        ) : (
          <>
            <span className="num text-fg-2">{state.perType}</span> per defect type in the spec, on <span className="num text-fg-2">{state.selected.length}</span> parts
          </>
        )}
      </p>
      <div className="mt-4">
        <Checkbox id="stress" checked={state.stress} onChange={actions.setStress} label="Stress-test the inspector after forging" />
      </div>
      <Button
        variant="primary"
        size="lg"
        className="w-full mt-4 relative overflow-hidden"
        onClick={() => void actions.forge()}
        disabled={state.starting || state.streaming !== 'idle' || !state.selected.length}
      >
        {running && <span className="absolute inset-y-0 left-0 bg-black/15" style={{ width: `${target ? (done / target) * 100 : 0}%` }} aria-hidden />}
        <span className="relative inline-flex items-center gap-2">
          {(state.starting || running) && <Spinner />}
          {state.starting ? (state.taxonomyBusy ? 'Reading spec' : 'Starting') : running ? (
            <>
              Forging <span className="num">{done}/{target}</span>
            </>
          ) : state.streaming === 'stress' ? (
            'Stress test running'
          ) : (
            'Forge defects'
          )}
        </span>
      </Button>
      {!state.selected.length && state.partsLoaded && <p className="text-[12px] text-fg-3 mt-2">Select at least one good part.</p>}
      {state.runError && <div className="mt-3"><ErrorLine>{state.runError}</ErrorLine></div>}
    </section>
  )
}

function RunBar({ run }: { run: Run }) {
  const { state } = useStore()
  const running = run.status === 'running'
  const now = useNow(running)
  const acc = run.samples.filter((s) => s.status === 'accepted').length
  const rej = run.samples.filter((s) => s.status === 'rejected').length
  const fail = run.samples.filter((s) => s.status === 'failed').length
  const { calls } = useCalls()
  const callCost = calls.filter((c) => c.run_id === run.id).reduce((a, c) => a + c.cost_usd, 0)
  const cost = run.summary?.cost_usd ?? Math.max(callCost, run.samples.reduce((a, s) => a + (s.cost_usd || 0), 0))
  const elapsed = run.summary ? run.summary.seconds * 1000 : state.runStartedAt ? now - state.runStartedAt : null
  const ious = run.samples.map((s) => s.sam_iou).filter((x): x is number => x != null)
  const iou = run.summary?.mean_sam_iou ?? (ious.length ? ious.reduce((a, b) => a + b, 0) / ious.length : null)
  return (
    <div className="flex flex-wrap items-center gap-x-6 gap-y-2 py-3 border-b border-rule text-[12.5px]">
      <div className="flex items-center gap-2 min-w-0">
        <span className={cx('size-2 rounded-full', running ? 'bg-signal pulse-dot' : run.status === 'failed' ? 'bg-miss' : 'bg-pass')} aria-hidden />
        <span className="font-semibold">{running ? 'Forging live' : run.status === 'failed' ? 'Run failed' : 'Run complete'}</span>
        <span className="num text-fg-3 truncate">{run.id}</span>
      </div>
      <span className="text-fg-3">
        Accepted <span className="num text-pass">{acc}</span>
      </span>
      <span className="text-fg-3">
        Rejected <span className={cx('num', rej ? 'text-miss' : 'text-fg-2')}>{rej}</span>
      </span>
      {fail > 0 && (
        <span className="text-fg-3">
          Failed <span className="num text-miss">{fail}</span>
        </span>
      )}
      <span className="text-fg-3">
        Mean SAM IoU <span className="num text-fg-2">{iou == null ? '–' : iou.toFixed(2)}</span>
      </span>
      <span className="text-fg-3">
        Spend <span className="num text-fg">{usd(cost, 3)}</span>
      </span>
      <span className="text-fg-3">
        Time <span className="num text-fg-2">{elapsed == null ? '–' : dur(elapsed)}</span>
      </span>
      <div className="ml-auto flex items-center gap-2">
        <a href="#/stress" className="h-8 px-3 inline-flex items-center rounded-[3px] border border-rule-2 text-[12.5px] font-semibold hover:bg-raised">
          Stress test
        </a>
        <a
          href={running ? undefined : api.exportUrl(run.id)}
          download={running ? undefined : `${run.id}-coco.zip`}
          aria-disabled={running}
          className={cx('h-8 px-3 inline-flex items-center rounded-[3px] border border-rule-2 text-[12.5px] font-semibold', running ? 'opacity-40 pointer-events-none' : 'hover:bg-raised')}
        >
          Export COCO
        </a>
      </div>
    </div>
  )
}

function EmptyGrid() {
  return (
    <div className="pt-5">
      <div className="max-w-[60ch] mb-5">
        <h2 className="text-[22px] font-bold tracking-[-0.01em]">Forged defects appear here as they are made</h2>
        <p className="text-[14px] text-fg-2 mt-1.5">
          Each card is one defect from your spec, forged onto a good part by Muse Image, labelled to the pixel by SAM 3.1 and checked by the Muse Spark critic. Press Forge defects to start.
        </p>
      </div>
      <div className="grid grid-cols-2 sm:grid-cols-[repeat(auto-fill,minmax(220px,1fr))] gap-3">
        {Array.from({ length: 8 }, (_, i) => (
          <EmptySlot key={i} />
        ))}
      </div>
    </div>
  )
}

export function ForgeScreen() {
  const { state } = useStore()
  const run = state.run
  const [openId, setOpenId] = useState<string | null>(null)
  const types = useMemo(() => run?.taxonomy.defects.map((d) => d.defect_type) ?? [], [run?.taxonomy])
  const samples = run?.samples ?? []
  const openIdx = samples.findIndex((s) => s.id === openId)
  const total = state.totalSamples ?? (run ? run.per_type * run.taxonomy.defects.length : 0)
  const pending = run && run.status === 'running' ? Math.max(0, total - samples.length) : 0
  const accepted = samples.filter((s) => s.status === 'accepted').length

  return (
    <div className="lg:grid lg:grid-cols-[360px_minmax(0,1fr)] 2xl:grid-cols-[400px_minmax(0,1fr)]">
      <aside className="lg:sticky lg:top-14 lg:h-[calc(100vh-56px)] lg:overflow-y-auto lg:border-r border-rule bg-page" aria-label="Forge setup">
        <SpecSection />
        <PartsSection />
        <ForgeSection />
        <div className="h-16 lg:h-4" />
      </aside>

      <main className="px-4 lg:px-6 pb-24 min-w-0 border-t border-rule lg:border-t-0">
        <div className="pt-4 pb-3">
          <StageTimeline stages={state.stages} total={total || null} stress={{ done: run?.severity.length ?? 0, expected: accepted * SEVERITY_VARIANTS }} />
        </div>
        {run ? (
          <>
            <RunBar run={run} />
            <div className="grid grid-cols-2 sm:grid-cols-[repeat(auto-fill,minmax(220px,1fr))] gap-3 pt-4">
              {samples.map((s) => (
                <SampleCard key={s.id} sample={s} types={types} onOpen={() => setOpenId(s.id)} />
              ))}
              {Array.from({ length: pending }, (_, i) => (
                <EmptySlot key={`e${i}`} />
              ))}
            </div>
            {!samples.length && run.status !== 'running' && <p className="text-fg-3 text-[13px] py-6">This run produced no samples.</p>}
          </>
        ) : (
          <EmptyGrid />
        )}
      </main>

      {openIdx >= 0 && (
        <SampleDetail
          sample={samples[openIdx]}
          types={types}
          index={openIdx}
          count={samples.length}
          onClose={() => setOpenId(null)}
          onPrev={openIdx > 0 ? () => setOpenId(samples[openIdx - 1].id) : undefined}
          onNext={openIdx < samples.length - 1 ? () => setOpenId(samples[openIdx + 1].id) : undefined}
        />
      )}
    </div>
  )
}
