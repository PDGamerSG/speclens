import type { Curve, CurveCell, SeverityKind } from '../api/types'
import { level, mm, plural } from './format'

/** A level counts as "caught" when the inspector detects at least this share of variants. */
export const CAUGHT = 0.8

export interface PlotCell extends CurveCell {
  /** true when this point is borrowed from opacity 1.0 (the forged defect as made). */
  anchor?: boolean
}

/** Cells of one kind, ordered from full strength to faintest. The size ladder starts
 *  at 0.6, so the unmodified forgery (opacity 1.0 = size 1.0) is used as its 100% point. */
export function orderedCells(curve: Curve, kind: SeverityKind): PlotCell[] {
  const cells: PlotCell[] = curve.cells.filter((c) => c.kind === kind).sort((a, b) => b.level - a.level)
  if (kind === 'size' && cells.length && !cells.some((c) => c.level >= 0.999)) {
    const full = curve.cells.find((c) => c.kind === 'opacity' && c.level >= 0.999)
    if (full) cells.unshift({ ...full, kind: 'size', anchor: true })
  }
  return cells
}

export interface Threshold {
  kind: SeverityKind
  caught: PlotCell | null // faintest level still caught (contiguous from full)
  missed: PlotCell | null // first level below that is missed
}

export function threshold(curve: Curve, kind: SeverityKind): Threshold {
  const cells = orderedCells(curve, kind)
  let caught: PlotCell | null = null
  let missed: PlotCell | null = null
  for (const c of cells) {
    if (c.n === 0) continue
    if (c.rate >= CAUGHT) caught = c
    else {
      missed = c
      break
    }
  }
  return { kind, caught, missed }
}

function at(c: PlotCell, kind: SeverityKind) {
  const base = `${level(c.level)} ${kind}`
  return kind === 'size' && c.mean_size_mm != null ? `${base} (≈${mm(c.mean_size_mm)})` : base
}

/** "Holes: caught down to 35% size (≈0.9 mm). Missed at 20%." */
export function headline(curve: Curve, kind: SeverityKind): string {
  const t = threshold(curve, kind)
  const name = plural(curve.defect_type)
  const cells = orderedCells(curve, kind)
  if (!cells.length) return `${name}: no ${kind} variants inspected yet.`
  if (!t.caught && t.missed) {
    // weak at full strength: say how many were caught, then where detection falls below half
    const half = cells.find((c) => c.n > 0 && c.rate < 0.5)
    const lead = `${name}: only ${Math.round(t.missed.rate * 100)}% caught at ${at(t.missed, kind)}`
    if (!half || half === t.missed) return `${lead}.`
    const miss = kind === 'size' && half.mean_size_mm != null ? `${level(half.level)} (≈${mm(half.mean_size_mm)})` : level(half.level)
    return `${lead}; mostly missed at ${miss}.`
  }
  if (t.caught && !t.missed) return `${name}: caught at every ${kind} tested, down to ${at(t.caught, kind)}.`
  if (t.caught && t.missed) {
    const miss = kind === 'size' && t.missed.mean_size_mm != null ? `${level(t.missed.level)} (≈${mm(t.missed.mean_size_mm)})` : level(t.missed.level)
    if (t.missed.rate >= 0.5) return `${name}: caught down to ${at(t.caught, kind)}. Drops to ${Math.round(t.missed.rate * 100)}% at ${miss}.`
    return `${name}: caught down to ${at(t.caught, kind)}. Missed at ${miss}.`
  }
  return `${name}: not enough data.`
}

const CANON = ['hole', 'crack', 'cut', 'print']

/** Stable display order: the spec's own order when known, else hole, crack, cut, print, then A–Z. */
export function sortCurves(curves: Curve[], order: string[] = CANON): Curve[] {
  const rank = (t: string) => {
    const i = order.indexOf(t)
    if (i >= 0) return i
    const j = CANON.indexOf(t)
    return j >= 0 ? 100 + j : 200
  }
  return curves.slice().sort((a, b) => rank(a.defect_type) - rank(b.defect_type) || a.defect_type.localeCompare(b.defect_type))
}
