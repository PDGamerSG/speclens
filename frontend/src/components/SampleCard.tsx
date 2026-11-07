import { useState } from 'react'
import type { Sample } from '../api/types'
import { typeColor } from '../lib/colors'
import { dur, mm, titleCase, usd } from '../lib/format'
import { ZoomWindow } from './Zoom'
import { RealismDots, StatusPill, cx } from './ui'

export function ValidatorList({ validators, detailed = false }: { validators: Sample['validators']; detailed?: boolean }) {
  return (
    <ul className={cx('grid', detailed ? 'gap-0 divide-y divide-rule' : 'gap-1')}>
      {validators.map((v) => (
        <li key={v.id} className={cx('flex items-start gap-2', detailed ? 'py-2' : '')} title={detailed ? undefined : v.detail}>
          <span className={cx('mt-[3px] grid place-items-center size-3.5 shrink-0 rounded-[2px]', v.passed ? 'bg-pass/15 text-pass' : 'bg-miss/15 text-miss')} aria-label={v.passed ? 'passed' : 'failed'}>
            <svg viewBox="0 0 12 12" className="size-2.5" aria-hidden>
              {v.passed ? <path d="M2.5 6.2l2.2 2.2L9.5 3.6" fill="none" stroke="currentColor" strokeWidth="1.8" /> : <path d="M3 3l6 6M9 3l-6 6" stroke="currentColor" strokeWidth="1.8" />}
            </svg>
          </span>
          <span className="min-w-0">
            <span className={cx('block', detailed ? 'text-[13px] text-fg' : 'text-[11.5px] text-fg-2 leading-snug')}>
              <span className="num text-fg-3 mr-1.5">{v.id}</span>
              {v.name}
            </span>
            {detailed && <span className="block text-[12px] text-fg-3 mt-0.5">{v.detail}</span>}
          </span>
        </li>
      ))}
    </ul>
  )
}

export function SampleCard({ sample: s, types, onOpen }: { sample: Sample; types: string[]; onOpen: () => void }) {
  const [open, setOpen] = useState(false)
  const passed = s.validators.filter((v) => v.passed).length
  const img = s.crop_composite_url ?? s.crop_original_url
  const forging = s.status === 'forging'
  return (
    <article className={cx('bg-panel border rounded-[3px] overflow-hidden flex flex-col', s.status === 'rejected' || s.status === 'failed' ? 'border-miss/30' : 'border-rule')}>
      <button type="button" onClick={onOpen} className="group relative block aspect-square bg-well brackets text-left" aria-label={`Open ${titleCase(s.defect_type)} sample ${s.id}`}>
        <img
          key={img}
          src={img}
          alt=""
          draggable={false}
          className={cx(
            'absolute inset-0 size-full object-cover',
            s.crop_composite_url ? 'arrive' : 'opacity-55',
            (s.status === 'rejected' || s.status === 'failed') && 'grayscale-[0.7] opacity-60',
          )}
        />
        {forging && (
          <div className="absolute inset-0 overflow-hidden" aria-hidden>
            <div className="scanline" />
          </div>
        )}
        <div className="absolute top-2 left-2 right-2 flex items-start justify-between gap-2">
          <StatusPill status={s.status} />
          {s.attempt > 1 && <span className="num h-[22px] px-1.5 grid place-items-center rounded-[3px] bg-well/85 text-[10.5px] text-fg-2">try {s.attempt}/3</span>}
        </div>
        {s.mask_url && (
          <div className="absolute bottom-2 right-2 w-[30%] aspect-square border border-signal/55 bg-black shadow-[0_0_0_1px_rgba(0,0,0,.6)]">
            <ZoomWindow src={s.mask_url} bbox={s.bbox} mode="mask" pad={1.5} minSide={48} className="absolute inset-0 !bg-black" />
            <span className="absolute left-1 top-0.5 text-[9.5px] font-semibold text-signal/90">mask</span>
          </div>
        )}
        <span className="absolute inset-0 ring-1 ring-inset ring-transparent group-hover:ring-fg-3/60 transition-colors" aria-hidden />
      </button>

      <div className="px-2.5 pt-2 pb-2.5 flex flex-col gap-1.5 text-[12px]">
        <div className="flex items-baseline justify-between gap-2">
          <span className="flex items-center gap-1.5 min-w-0">
            <span className="size-2 shrink-0 rounded-[1px]" style={{ background: typeColor(s.defect_type, types) }} aria-hidden />
            <span className="font-semibold text-[14px] truncate">{titleCase(s.defect_type)}</span>
          </span>
          <span className="num text-fg">{mm(s.size_mm)}</span>
        </div>
        <div className="flex items-center justify-between gap-2">
          <RealismDots value={s.critic?.realism} />
          <span className="text-fg-3">
            IoU <span className="num text-fg-2">{s.sam_iou == null ? '–' : s.sam_iou.toFixed(2)}</span>
          </span>
        </div>
        <div className="flex flex-wrap items-center justify-between gap-x-2 gap-y-1">
          <button
            type="button"
            onClick={() => setOpen((o) => !o)}
            disabled={!s.validators.length}
            aria-expanded={open}
            className={cx('inline-flex items-center gap-1 -ml-0.5 px-0.5 rounded-[2px] hover:text-fg disabled:cursor-default', s.validators.length && passed === s.validators.length ? 'text-pass' : s.validators.length ? 'text-miss' : 'text-fg-3')}
          >
            Validators <span className="num">{s.validators.length ? `${passed}/${s.validators.length}` : '–/8'}</span>
            {s.validators.length > 0 && (
              <svg viewBox="0 0 10 10" className={cx('size-2.5 transition-transform', open && 'rotate-180')} aria-hidden>
                <path d="M2 3.5l3 3 3-3" fill="none" stroke="currentColor" strokeWidth="1.5" />
              </svg>
            )}
          </button>
          <span className="num text-fg-3 flex gap-2">
            <span>{s.cost_usd ? usd(s.cost_usd, 3) : '–'}</span>
            <span>{s.ms ? dur(s.ms) : '–'}</span>
          </span>
        </div>
        {open && (
          <div className="pt-1.5 mt-0.5 border-t border-rule">
            <ValidatorList validators={s.validators} />
          </div>
        )}
      </div>
    </article>
  )
}

export function EmptySlot() {
  return (
    <div className="bg-panel/40 border border-rule/70 rounded-[3px] overflow-hidden flex flex-col" aria-hidden>
      <div className="relative aspect-square brackets [--bc:rgb(255_255_255/0.14)] grid place-items-center">
        <span className="text-[11.5px] text-fg-3/70">queued</span>
      </div>
      <div className="h-[86px]" />
    </div>
  )
}
