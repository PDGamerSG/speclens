import { useEffect, useMemo, useRef, useState } from 'react'
import type { Curve, SeverityKind } from '../api/types'
import { typeColor, typeMarker, type Marker } from '../lib/colors'
import { CAUGHT, headline, orderedCells, threshold, type PlotCell } from '../lib/curves'
import { level, mm, pct, plural, titleCase } from '../lib/format'
import { cx } from './ui'

function useWidth<T extends HTMLElement>() {
  const ref = useRef<T>(null)
  const [w, setW] = useState(0)
  useEffect(() => {
    const el = ref.current
    if (!el) return
    const ro = new ResizeObserver(([e]) => setW(Math.round(e.contentRect.width)))
    ro.observe(el)
    setW(el.clientWidth)
    return () => ro.disconnect()
  }, [])
  return [ref, w] as const
}

export function MarkerShape({ shape, x, y, r = 4.5, color, hollow }: { shape: Marker; x: number; y: number; r?: number; color: string; hollow?: boolean }) {
  const common = { fill: hollow ? 'var(--color-panel)' : color, stroke: hollow ? color : 'var(--color-panel)', strokeWidth: hollow ? 1.5 : 2, paintOrder: 'stroke' as const }
  if (shape === 'square') return <rect x={x - r * 0.88} y={y - r * 0.88} width={r * 1.76} height={r * 1.76} {...common} />
  if (shape === 'diamond') return <path d={`M${x} ${y - r * 1.15}L${x + r * 1.15} ${y}L${x} ${y + r * 1.15}L${x - r * 1.15} ${y}Z`} {...common} />
  if (shape === 'triangle') return <path d={`M${x} ${y - r * 1.15}L${x + r * 1.1} ${y + r * 0.8}L${x - r * 1.1} ${y + r * 0.8}Z`} {...common} />
  return <circle cx={x} cy={y} r={r} {...common} />
}

const KIND_TITLE: Record<SeverityKind, string> = { size: 'Size', opacity: 'Opacity' }
const KIND_SUB: Record<SeverityKind, string> = { size: 'defect shrunk to a share of its forged size', opacity: 'defect faded toward the good part' }

export function CurveChart({ curves, kind }: { curves: Curve[]; kind: SeverityKind }) {
  const [ref, width] = useWidth<HTMLDivElement>()
  const [hover, setHover] = useState<number | null>(null)
  const types = curves.map((c) => c.defect_type)
  const series = useMemo(() => curves.map((c) => ({ curve: c, cells: orderedCells(c, kind) })), [curves, kind])
  const levels = useMemo(() => {
    const set = new Set<number>()
    series.forEach((s) => s.cells.forEach((c) => set.add(c.level)))
    return [...set].sort((a, b) => b - a)
  }, [series])

  const H = 236
  const m = { l: 40, r: 14, t: 14, b: 40 }
  const pw = Math.max(0, width - m.l - m.r)
  const ph = H - m.t - m.b
  const band = levels.length ? pw / levels.length : 0
  const xOf = (lv: number) => m.l + band * (levels.indexOf(lv) + 0.5)
  const yOf = (r: number) => m.t + ph * (1 - r)
  const jitter = (i: number) => (series.length > 1 ? (i - (series.length - 1) / 2) * Math.min(7, band / (series.length * 2.2)) : 0)

  const tipCells = hover == null ? [] : series.map((s, i) => ({ s, i, cell: s.cells.find((c) => c.level === levels[hover]) })).filter((x) => x.cell)

  return (
    <figure className="min-w-0 bg-panel border border-rule rounded-[3px] p-3 pb-2">
      <figcaption className="flex items-baseline gap-2 mb-1">
        <span className="text-[14px] font-bold">{KIND_TITLE[kind]}</span>
        <span className="text-[12px] text-fg-3 truncate">{KIND_SUB[kind]}</span>
      </figcaption>
      <div ref={ref} className="relative" onMouseLeave={() => setHover(null)}>
        {width > 0 && (
          <svg width={width} height={H} role="img" aria-label={`Detection rate by ${kind} level`} className="block overflow-visible">
            {/* grid */}
            {[0, 0.5, 1].map((r) => (
              <g key={r}>
                <line x1={m.l} x2={width - m.r} y1={yOf(r)} y2={yOf(r)} stroke="var(--color-rule)" strokeWidth={1} />
                <text x={m.l - 8} y={yOf(r)} dy="0.32em" textAnchor="end" className="num" fontSize={10.5} fill="var(--color-fg-3)">
                  {pct(r)}
                </text>
              </g>
            ))}
            <line x1={m.l} x2={width - m.r} y1={yOf(CAUGHT)} y2={yOf(CAUGHT)} stroke="var(--color-pass)" strokeOpacity={0.55} strokeDasharray="3 4" strokeWidth={1} />
            <text x={width - m.r} y={yOf(CAUGHT) - 5} textAnchor="end" fontSize={10.5} fill="var(--color-pass)" fillOpacity={0.85}>
              caught ≥ {pct(CAUGHT)}
            </text>
            {/* hover band */}
            {hover != null && <rect x={m.l + band * hover} y={m.t} width={band} height={ph} fill="var(--color-raised)" opacity={0.6} />}
            {/* x labels */}
            {levels.map((lv, i) => (
              <g key={lv}>
                <line x1={xOf(lv)} x2={xOf(lv)} y1={yOf(0)} y2={yOf(0) + 4} stroke="var(--color-rule-2)" />
                <text x={xOf(lv)} y={yOf(0) + 17} textAnchor="middle" className="num" fontSize={11} fill={hover === i ? 'var(--color-fg)' : 'var(--color-fg-2)'}>
                  {level(lv)}
                </text>
              </g>
            ))}
            <text x={m.l + pw / 2} y={H - 4} textAnchor="middle" fontSize={10.5} fill="var(--color-fg-3)">
              full strength to faintest
            </text>
            {/* series */}
            {series.map(({ curve, cells }, si) => {
              const color = typeColor(curve.defect_type, types)
              const pts = cells.filter((c) => c.n > 0)
              const d = pts.map((c, j) => `${j ? 'L' : 'M'}${xOf(c.level) + jitter(si)} ${yOf(c.rate)}`).join('')
              return (
                <g key={curve.defect_type}>
                  {pts.map((c) => (
                    <g key={`ci${c.level}`} stroke={color} strokeOpacity={0.7} strokeWidth={1}>
                      <line x1={xOf(c.level) + jitter(si)} x2={xOf(c.level) + jitter(si)} y1={yOf(c.ci_low)} y2={yOf(c.ci_high)} />
                      <line x1={xOf(c.level) + jitter(si) - 3} x2={xOf(c.level) + jitter(si) + 3} y1={yOf(c.ci_low)} y2={yOf(c.ci_low)} />
                      <line x1={xOf(c.level) + jitter(si) - 3} x2={xOf(c.level) + jitter(si) + 3} y1={yOf(c.ci_high)} y2={yOf(c.ci_high)} />
                    </g>
                  ))}
                  <path d={d} fill="none" stroke={color} strokeWidth={2} strokeLinejoin="round" strokeLinecap="round" />
                  {pts.map((c) => (
                    <MarkerShape key={c.level} shape={typeMarker(curve.defect_type, types)} x={xOf(c.level) + jitter(si)} y={yOf(c.rate)} color={color} hollow={(c as PlotCell).anchor} />
                  ))}
                </g>
              )
            })}
            {/* hit targets */}
            {levels.map((lv, i) => (
              <rect key={`h${lv}`} x={m.l + band * i} y={m.t} width={band} height={ph + 24} fill="transparent" onMouseEnter={() => setHover(i)} onTouchStart={() => setHover(i)} />
            ))}
          </svg>
        )}
        {hover != null && tipCells.length > 0 && (
          <div
            className="absolute z-10 pointer-events-none bg-well border border-rule-2 rounded-[3px] px-2.5 py-2 text-[12px] shadow-xl min-w-[170px]"
            style={{ left: Math.min(Math.max(0, m.l + band * hover + band / 2 - 90), Math.max(0, width - 190)), top: 6 }}
          >
            <div className="font-semibold mb-1">
              {KIND_TITLE[kind]} <span className="num">{level(levels[hover])}</span>
            </div>
            {tipCells.map(({ s, cell }) => (
              <div key={s.curve.defect_type} className="flex items-center gap-2 py-[1px]">
                <span className="size-2 rounded-[1px]" style={{ background: typeColor(s.curve.defect_type, types) }} />
                <span className="text-fg-2 w-12">{titleCase(s.curve.defect_type)}</span>
                <span className="num text-fg">
                  {cell!.detected}/{cell!.n}
                </span>
                <span className="num text-fg-3 ml-auto">
                  {pct(cell!.ci_low)}–{pct(cell!.ci_high)}
                </span>
              </div>
            ))}
            {kind === 'size' && tipCells.some((t) => (t.cell as PlotCell).anchor) && <div className="text-[11px] text-fg-3 mt-1">100% is the forged defect as made.</div>}
          </div>
        )}
      </div>
    </figure>
  )
}

export function CurveLegend({ curves }: { curves: Curve[] }) {
  const types = curves.map((c) => c.defect_type)
  return (
    <ul className="flex flex-wrap items-center gap-x-4 gap-y-1.5 text-[12.5px] text-fg-2" aria-label="Defect types">
      {curves.map((c) => (
        <li key={c.defect_type} className="flex items-center gap-1.5">
          <svg width="22" height="12" aria-hidden>
            <line x1="1" x2="21" y1="6" y2="6" stroke={typeColor(c.defect_type, types)} strokeWidth="2" />
            <MarkerShape shape={typeMarker(c.defect_type, types)} x={11} y={6} r={3.8} color={typeColor(c.defect_type, types)} />
          </svg>
          {titleCase(c.defect_type)}
        </li>
      ))}
      <li className="text-fg-3 text-[12px]">Whiskers: 95% Wilson interval</li>
    </ul>
  )
}

function CurveTable({ curves }: { curves: Curve[] }) {
  return (
    <div className="overflow-x-auto border border-rule rounded-[3px]">
      <table className="w-full text-[12.5px]">
        <thead className="text-fg-3 text-left">
          <tr className="border-b border-rule">
            <th className="font-semibold px-3 py-2">Type</th>
            <th className="font-semibold px-3 py-2">Ladder</th>
            <th className="font-semibold px-3 py-2">Level</th>
            <th className="font-semibold px-3 py-2 text-right">Detected</th>
            <th className="font-semibold px-3 py-2 text-right">Rate</th>
            <th className="font-semibold px-3 py-2 text-right">95% CI</th>
            <th className="font-semibold px-3 py-2 text-right">Mean size</th>
          </tr>
        </thead>
        <tbody>
          {curves.flatMap((c) =>
            c.cells.map((cell) => (
              <tr key={`${c.defect_type}${cell.kind}${cell.level}`} className="border-b border-rule/60 last:border-0">
                <td className="px-3 py-1.5">{titleCase(c.defect_type)}</td>
                <td className="px-3 py-1.5 text-fg-2">{cell.kind}</td>
                <td className="px-3 py-1.5 num">{level(cell.level)}</td>
                <td className="px-3 py-1.5 num text-right">
                  {cell.detected}/{cell.n}
                </td>
                <td className={cx('px-3 py-1.5 num text-right', cell.rate >= CAUGHT ? 'text-pass' : 'text-miss')}>{pct(cell.rate)}</td>
                <td className="px-3 py-1.5 num text-right text-fg-3">
                  {pct(cell.ci_low)}–{pct(cell.ci_high)}
                </td>
                <td className="px-3 py-1.5 num text-right text-fg-2">{mm(cell.mean_size_mm)}</td>
              </tr>
            )),
          )}
        </tbody>
      </table>
    </div>
  )
}

export function CurvesPanel({ curves }: { curves: Curve[] }) {
  const [table, setTable] = useState(false)
  return (
    <div className="flex flex-col gap-3">
      <div className="flex flex-wrap items-center justify-between gap-3">
        <CurveLegend curves={curves} />
        <button type="button" className="text-[12.5px] text-fg-2 hover:text-fg underline underline-offset-4 decoration-rule-2" onClick={() => setTable((t) => !t)}>
          {table ? 'Show charts' : 'Show as table'}
        </button>
      </div>
      {table ? (
        <CurveTable curves={curves} />
      ) : (
        <div className="grid md:grid-cols-2 gap-3">
          <CurveChart curves={curves} kind="size" />
          <CurveChart curves={curves} kind="opacity" />
        </div>
      )}
    </div>
  )
}

/** The big per-type answer: how small / faint before the inspector misses it. */
export function ThresholdCallouts({ curves }: { curves: Curve[] }) {
  const types = curves.map((c) => c.defect_type)
  return (
    <div className="grid sm:grid-cols-2 xl:grid-cols-4 gap-3">
      {curves.map((c) => {
        const sz = threshold(c, 'size')
        const op = threshold(c, 'opacity')
        const worst = sz.missed || op.missed
        return (
          <article key={c.defect_type} className="bg-panel border border-rule rounded-[3px] p-4 flex flex-col gap-2 min-w-0" style={{ borderTop: `2px solid ${typeColor(c.defect_type, types)}` }}>
            <div className="flex items-center justify-between gap-2">
              <svg width="22" height="12" aria-hidden>
                <line x1="1" x2="21" y1="6" y2="6" stroke={typeColor(c.defect_type, types)} strokeWidth="2" />
                <MarkerShape shape={typeMarker(c.defect_type, types)} x={11} y={6} r={3.8} color={typeColor(c.defect_type, types)} />
              </svg>
              <span className={cx('inline-flex items-center gap-1.5 text-[11.5px] font-semibold', worst ? 'text-miss' : 'text-pass')}>
                <span className={cx('size-1.5 rounded-full', worst ? 'bg-miss' : 'bg-pass')} />
                {worst ? 'Blind spot found' : 'No miss found'}
              </span>
            </div>
            <h3 className="text-[19px] leading-snug font-semibold tracking-[-0.01em] text-fg">{headline(c, 'size')}</h3>
            <p className="text-[13px] text-fg-2">{headline(c, 'opacity').replace(/^[^:]+:\s*/, `${plural(c.defect_type)} by opacity: `)}</p>
            {c.threshold_note && <p className="text-[12px] text-fg-3 mt-auto pt-1 border-t border-rule">{c.threshold_note}</p>}
          </article>
        )
      })}
    </div>
  )
}
