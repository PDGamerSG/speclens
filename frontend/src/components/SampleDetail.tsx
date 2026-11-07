import { useEffect, useRef, useState, type ReactNode } from 'react'
import type { Sample } from '../api/types'
import { typeColor } from '../lib/colors'
import { dur, mm, titleCase, usd } from '../lib/format'
import { BeforeAfter } from './BeforeAfter'
import { ValidatorList } from './SampleCard'
import { RealismDots, StatusPill, cx } from './ui'

function Seg<T extends string>({ value, options, onChange, label }: { value: T; options: { v: T; label: string; disabled?: boolean }[]; onChange: (v: T) => void; label: string }) {
  return (
    <div role="radiogroup" aria-label={label} className="inline-flex border border-rule-2 rounded-[3px] p-0.5 gap-0.5">
      {options.map((o) => (
        <button
          key={o.v}
          type="button"
          role="radio"
          aria-checked={value === o.v}
          disabled={o.disabled}
          onClick={() => onChange(o.v)}
          className={cx('h-7 px-2.5 rounded-[2px] text-[12.5px] font-semibold disabled:opacity-35', value === o.v ? 'bg-raised text-fg' : 'text-fg-3 hover:text-fg-2')}
        >
          {o.label}
        </button>
      ))}
    </div>
  )
}

function Field({ label, children }: { label: string; children: ReactNode }) {
  return (
    <div className="min-w-0">
      <dt className="text-[11.5px] text-fg-3">{label}</dt>
      <dd className="num text-[13.5px] text-fg mt-0.5 truncate">{children}</dd>
    </div>
  )
}

function Block({ title, children }: { title: string; children: ReactNode }) {
  return (
    <section className="border-t border-rule pt-3">
      <h3 className="text-[13px] font-bold mb-2">{title}</h3>
      {children}
    </section>
  )
}

export function SampleDetail({ sample: s, types, onClose, onPrev, onNext, index, count }: { sample: Sample; types: string[]; onClose: () => void; onPrev?: () => void; onNext?: () => void; index: number; count: number }) {
  const [right, setRight] = useState<'composite' | 'raw'>('composite')
  const [full, setFull] = useState<'overlay' | 'composite' | 'mask'>('overlay')
  const closeRef = useRef<HTMLButtonElement>(null)

  useEffect(() => {
    const prev = document.activeElement as HTMLElement | null
    closeRef.current?.focus()
    const onKey = (e: KeyboardEvent) => {
      if (e.key === 'Escape') onClose()
      if (e.key === 'ArrowLeft' && onPrev && !(e.target instanceof HTMLInputElement)) onPrev()
      if (e.key === 'ArrowRight' && onNext && !(e.target instanceof HTMLInputElement)) onNext()
    }
    window.addEventListener('keydown', onKey)
    document.body.style.overflow = 'hidden'
    return () => {
      window.removeEventListener('keydown', onKey)
      document.body.style.overflow = ''
      prev?.focus?.()
    }
  }, [onClose, onNext, onPrev])

  const after = right === 'raw' ? s.crop_raw_url : s.crop_composite_url
  const fullSrc = full === 'overlay' ? s.overlay_url ?? s.composite_url : full === 'composite' ? s.composite_url : s.mask_url
  const passed = s.validators.filter((v) => v.passed).length

  return (
    <div className="fixed inset-0 z-50 flex items-stretch lg:items-center justify-center bg-black/70 backdrop-blur-[2px] lg:p-6" onMouseDown={(e) => e.target === e.currentTarget && onClose()}>
      <div role="dialog" aria-modal="true" aria-label={`${titleCase(s.defect_type)} sample ${s.id}`} className="relative w-full lg:max-w-[1200px] max-h-full overflow-y-auto bg-page border border-rule-2 lg:rounded-[4px] shadow-2xl">
        <header className="sticky top-0 z-10 flex flex-wrap items-center gap-x-3 gap-y-2 px-4 lg:px-5 h-auto min-h-14 py-2.5 bg-page/95 backdrop-blur border-b border-rule">
          <span className="size-2.5 rounded-[1px]" style={{ background: typeColor(s.defect_type, types) }} aria-hidden />
          <h2 className="text-[18px] font-bold">{titleCase(s.defect_type)}</h2>
          <span className="num text-fg-3 text-[12px]">{s.id}</span>
          <StatusPill status={s.status} />
          <span className="text-[12px] text-fg-3 hidden sm:inline">
            attempt <span className="num text-fg-2">{s.attempt}/3</span>
          </span>
          <span className="text-[12px] text-fg-3 hidden md:inline truncate max-w-[260px]">
            part <span className="num text-fg-2">{s.part_id}</span>
          </span>
          <div className="ml-auto flex items-center gap-1">
            <span className="num text-[11.5px] text-fg-3 mr-1">
              {index + 1}/{count}
            </span>
            <button type="button" onClick={onPrev} disabled={!onPrev} className="size-8 grid place-items-center rounded-[3px] text-fg-2 hover:bg-raised disabled:opacity-30" aria-label="Previous sample">
              <svg viewBox="0 0 16 16" className="size-4" aria-hidden><path d="M10 3L5 8l5 5" fill="none" stroke="currentColor" strokeWidth="1.6" /></svg>
            </button>
            <button type="button" onClick={onNext} disabled={!onNext} className="size-8 grid place-items-center rounded-[3px] text-fg-2 hover:bg-raised disabled:opacity-30" aria-label="Next sample">
              <svg viewBox="0 0 16 16" className="size-4" aria-hidden><path d="M6 3l5 5-5 5" fill="none" stroke="currentColor" strokeWidth="1.6" /></svg>
            </button>
            <button ref={closeRef} type="button" onClick={onClose} className="size-8 grid place-items-center rounded-[3px] text-fg-2 hover:bg-raised ml-1" aria-label="Close">
              <svg viewBox="0 0 16 16" className="size-4" aria-hidden><path d="M3.5 3.5l9 9M12.5 3.5l-9 9" stroke="currentColor" strokeWidth="1.6" /></svg>
            </button>
          </div>
        </header>

        <div className="grid lg:grid-cols-[minmax(0,560px)_minmax(0,1fr)] gap-5 lg:gap-7 p-4 lg:p-5">
          <div className="flex flex-col gap-3 min-w-0">
            {after ? (
              <BeforeAfter before={s.crop_original_url} after={after} beforeLabel="Good part" afterLabel={right === 'raw' ? 'Raw Muse Image' : 'Forged composite'} />
            ) : (
              <div className="relative aspect-square bg-well brackets">
                <img src={s.crop_original_url} alt="Good part crop" className="absolute inset-0 size-full object-contain opacity-60" />
                <div className="absolute inset-0 overflow-hidden"><div className="scanline" /></div>
              </div>
            )}
            <div className="flex flex-wrap items-center gap-x-3 gap-y-2">
              <Seg
                label="Right side of the slider"
                value={right}
                onChange={setRight}
                options={[
                  { v: 'composite', label: 'Our composite', disabled: !s.crop_composite_url },
                  { v: 'raw', label: 'Raw Muse Image', disabled: !s.crop_raw_url },
                ]}
              />
              <p className="text-[12.5px] text-fg-2">
                {right === 'composite' ? (
                  <>Pixels outside the mask are byte-identical.</>
                ) : (
                  <>The raw edit shifts and re-tones the whole crop; only the masked change is kept.</>
                )}
              </p>
            </div>

            <section className="mt-2">
              <div className="flex flex-wrap items-center justify-between gap-2 mb-2">
                <h3 className="text-[13px] font-bold">Full image</h3>
                <Seg
                  label="Full image view"
                  value={full}
                  onChange={setFull}
                  options={[
                    { v: 'overlay', label: 'Mask overlay', disabled: !s.overlay_url && !s.composite_url },
                    { v: 'composite', label: 'Composite', disabled: !s.composite_url },
                    { v: 'mask', label: 'Mask', disabled: !s.mask_url },
                  ]}
                />
              </div>
              <div className="relative bg-well brackets">
                {fullSrc ? (
                  <img src={fullSrc} alt={`Full image, ${full}`} className="block w-full h-auto" />
                ) : (
                  <img src={s.original_url} alt="Original good part" className="block w-full h-auto opacity-60" />
                )}
              </div>
            </section>
          </div>

          <div className="flex flex-col gap-4 min-w-0">
            <dl className="grid grid-cols-3 gap-x-4 gap-y-3">
              <Field label="Size">{mm(s.size_mm)}</Field>
              <Field label="Area">{s.area_px ? `${s.area_px.toLocaleString()} px` : '–'}</Field>
              <Field label="SAM IoU">{s.sam_iou == null ? '–' : s.sam_iou.toFixed(3)}</Field>
              <Field label="Box">{s.bbox ? s.bbox.join(' ') : '–'}</Field>
              <Field label="Cost">{s.cost_usd ? usd(s.cost_usd) : '–'}</Field>
              <Field label="Time">{s.ms ? dur(s.ms) : '–'}</Field>
            </dl>

            <Block title="Prompt sent to Muse Image">
              <p className="text-[13px] leading-relaxed text-fg-2 bg-well border border-rule rounded-[3px] px-3 py-2.5 whitespace-pre-wrap">{s.prompt}</p>
            </Block>

            <Block title="Muse Spark critic">
              {s.critic ? (
                <div className="grid gap-2 text-[13px]">
                  <div className="flex flex-wrap items-center gap-x-5 gap-y-1.5">
                    <span className="flex items-center gap-2 text-fg-3">
                      Realism <RealismDots value={s.critic.realism} /> <span className="num text-fg">{s.critic.realism}/5</span>
                    </span>
                    <span className="text-fg-3">
                      Matches type <span className={s.critic.matches_type ? 'text-pass' : 'text-miss'}>{s.critic.matches_type ? 'yes' : 'no'}</span>
                    </span>
                    <span className="text-fg-3">
                      Verdict <span className={cx('font-semibold', s.critic.verdict === 'accept' ? 'text-pass' : 'text-miss')}>{s.critic.verdict}</span>
                    </span>
                  </div>
                  <p className="text-fg-2">
                    <span className="text-fg-3">Artifacts: </span>
                    {s.critic.artifacts || 'none noted'}
                  </p>
                  {s.critic.revised_prompt && (
                    <p className="text-fg-2">
                      <span className="text-fg-3">Revised prompt for the next attempt: </span>
                      {s.critic.revised_prompt}
                    </p>
                  )}
                </div>
              ) : (
                <p className="text-[13px] text-fg-3">Not reviewed yet.</p>
              )}
            </Block>

            <Block title={s.validators.length ? `Deterministic validators, ${passed} of ${s.validators.length} passed` : 'Deterministic validators'}>
              {s.validators.length ? <ValidatorList validators={s.validators} detailed /> : <p className="text-[13px] text-fg-3">Run after the critic accepts.</p>}
            </Block>
          </div>
        </div>
      </div>
    </div>
  )
}
