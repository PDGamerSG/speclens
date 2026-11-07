import type { ButtonHTMLAttributes, ReactNode } from 'react'
import type { SampleStatus } from '../api/types'
import { modelInfo } from '../lib/colors'

export function cx(...c: (string | false | null | undefined)[]) {
  return c.filter(Boolean).join(' ')
}

type BtnProps = ButtonHTMLAttributes<HTMLButtonElement> & { variant?: 'primary' | 'line' | 'quiet'; size?: 'sm' | 'md' | 'lg' }

export function Button({ variant = 'line', size = 'md', className, ...rest }: BtnProps) {
  return (
    <button
      {...rest}
      className={cx(
        'inline-flex items-center justify-center gap-2 font-semibold whitespace-nowrap transition-colors select-none disabled:opacity-45',
        size === 'sm' && 'h-8 px-3 text-[12.5px] rounded-[3px]',
        size === 'md' && 'h-9 px-3.5 text-[13px] rounded-[3px]',
        size === 'lg' && 'h-13 px-5 text-[16px] rounded-[4px]',
        variant === 'primary' && 'bg-signal text-signal-ink hover:bg-[#ffb648] disabled:hover:bg-signal',
        variant === 'line' && 'border border-rule-2 text-fg hover:border-fg-3 hover:bg-raised',
        variant === 'quiet' && 'text-fg-2 hover:text-fg',
        className,
      )}
    />
  )
}

const STATUS: Record<SampleStatus, { label: string; cls: string; dot: string }> = {
  forging: { label: 'Forging', cls: 'text-signal border-signal/50', dot: 'bg-signal pulse-dot' },
  accepted: { label: 'Accepted', cls: 'text-pass border-pass/45', dot: 'bg-pass' },
  rejected: { label: 'Rejected', cls: 'text-miss border-miss/50', dot: 'bg-miss' },
  failed: { label: 'Failed', cls: 'text-fg-2 border-miss/40', dot: 'bg-transparent ring-1 ring-miss' },
}

export function StatusPill({ status, className }: { status: SampleStatus; className?: string }) {
  const s = STATUS[status]
  return (
    <span
      className={cx(
        'inline-flex items-center gap-1.5 h-[22px] px-2 rounded-full border bg-well/85 backdrop-blur-sm text-[11.5px] font-semibold',
        s.cls,
        className,
      )}
    >
      <span className={cx('size-1.5 rounded-full', s.dot)} />
      {s.label}
    </span>
  )
}

export function RealismDots({ value, max = 5 }: { value: number | null | undefined; max?: number }) {
  const v = value ?? 0
  return (
    <span className="inline-flex items-center gap-[3px]" role="img" aria-label={value == null ? 'realism not scored' : `realism ${v} of ${max}`}>
      {Array.from({ length: max }, (_, i) => (
        <span key={i} className={cx('size-[7px] rounded-full', i < v ? 'bg-fg' : 'border border-rule-2')} />
      ))}
    </span>
  )
}

export function Switch({ checked, onChange, label, id }: { checked: boolean; onChange: (b: boolean) => void; label: ReactNode; id: string }) {
  return (
    <label htmlFor={id} className="inline-flex items-center gap-2 cursor-pointer select-none text-[12.5px] text-fg-2">
      <span className="relative inline-flex">
        <input id={id} type="checkbox" className="peer sr-only" checked={checked} onChange={(e) => onChange(e.target.checked)} />
        <span className="w-8 h-[18px] rounded-full border border-rule-2 bg-well transition-colors peer-checked:bg-part/25 peer-checked:border-part/70 peer-focus-visible:outline-2 peer-focus-visible:outline-signal peer-focus-visible:outline-offset-2" />
        <span className="absolute top-[3px] left-[3px] size-3 rounded-full bg-fg-3 transition-transform peer-checked:translate-x-[14px] peer-checked:bg-part" />
      </span>
      {label}
    </label>
  )
}

export function Checkbox({ checked, onChange, label, id }: { checked: boolean; onChange: (b: boolean) => void; label: ReactNode; id: string }) {
  return (
    <label htmlFor={id} className="flex items-start gap-2.5 cursor-pointer select-none text-[13px] text-fg-2">
      <span className="relative mt-[1px] inline-flex">
        <input id={id} type="checkbox" className="peer sr-only" checked={checked} onChange={(e) => onChange(e.target.checked)} />
        <span className="size-4 rounded-[2px] border border-rule-2 bg-well peer-checked:bg-signal peer-checked:border-signal peer-focus-visible:outline-2 peer-focus-visible:outline-signal peer-focus-visible:outline-offset-2" />
        <svg viewBox="0 0 16 16" className="absolute inset-0 size-4 text-signal-ink opacity-0 peer-checked:opacity-100" aria-hidden>
          <path d="M4 8.5l2.5 2.5L12 5.5" fill="none" stroke="currentColor" strokeWidth="2" />
        </svg>
      </span>
      <span>{label}</span>
    </label>
  )
}

export function Stepper({ value, onChange, min = 1, max = 12, label }: { value: number; onChange: (n: number) => void; min?: number; max?: number; label: string }) {
  return (
    <div className="inline-flex items-stretch h-9 border border-rule-2 rounded-[3px] overflow-hidden" role="group" aria-label={label}>
      <button type="button" className="w-9 text-[18px] text-fg-2 hover:bg-raised hover:text-fg disabled:opacity-40" onClick={() => onChange(value - 1)} disabled={value <= min} aria-label="Fewer">
        −
      </button>
      <output className="num w-10 grid place-items-center border-x border-rule text-[14px] text-fg" aria-live="polite">
        {value}
      </output>
      <button type="button" className="w-9 text-[18px] text-fg-2 hover:bg-raised hover:text-fg disabled:opacity-40" onClick={() => onChange(value + 1)} disabled={value >= max} aria-label="More">
        +
      </button>
    </div>
  )
}

export function ModelChip({ model, className }: { model: string; className?: string }) {
  const m = modelInfo(model)
  return (
    <span className={cx('inline-flex items-center gap-1.5 h-5 px-1.5 rounded-[3px] text-[11.5px] font-semibold whitespace-nowrap', className)} style={{ color: m.color, background: `color-mix(in srgb, ${m.color} 14%, transparent)` }}>
      <span className="size-1.5 rounded-[1px]" style={{ background: m.color }} />
      {m.label}
    </span>
  )
}

export function StepHead({ n, title, right }: { n: number; title: string; right?: ReactNode }) {
  return (
    <div className="flex items-center gap-2.5 mb-3">
      <span className="num grid place-items-center size-5 border border-rule-2 rounded-[2px] text-[10.5px] text-fg-2">{n}</span>
      <h2 className="text-[15px] font-bold tracking-[-0.005em]">{title}</h2>
      <div className="ml-auto flex items-center gap-2">{right}</div>
    </div>
  )
}

export function NotRun({ title, children }: { title: string; children?: ReactNode }) {
  return (
    <div className="border border-dashed border-rule-2 rounded-[3px] px-4 py-5 text-fg-3 text-[13px]">
      <div className="text-fg-2 font-semibold mb-1">{title}</div>
      {children}
    </div>
  )
}

export function ErrorLine({ children }: { children: ReactNode }) {
  return (
    <p role="alert" className="text-[12.5px] text-miss border-l-2 border-miss pl-2.5 py-0.5">
      {children}
    </p>
  )
}

export function Spinner({ className }: { className?: string }) {
  return (
    <svg viewBox="0 0 16 16" className={cx('size-4 animate-spin', className)} aria-hidden>
      <circle cx="8" cy="8" r="6" fill="none" stroke="currentColor" strokeOpacity="0.25" strokeWidth="2" />
      <path d="M14 8a6 6 0 0 0-6-6" fill="none" stroke="currentColor" strokeWidth="2" />
    </svg>
  )
}

export function Stat({ label, value, sub, tone }: { label: string; value: ReactNode; sub?: ReactNode; tone?: 'pass' | 'miss' | 'signal' }) {
  return (
    <div className="min-w-0">
      <div className="text-[12px] text-fg-3">{label}</div>
      <div className={cx('num text-[22px] leading-tight mt-0.5', tone === 'pass' && 'text-pass', tone === 'miss' && 'text-miss', tone === 'signal' && 'text-signal')}>{value}</div>
      {sub != null && <div className="num text-[11px] text-fg-3 mt-0.5">{sub}</div>}
    </div>
  )
}
