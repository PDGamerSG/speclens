export function usd(n: number | null | undefined, digits?: number) {
  if (n == null || Number.isNaN(n)) return '–'
  const d = digits ?? (Math.abs(n) >= 1 ? 2 : Math.abs(n) >= 0.1 ? 3 : 4)
  return `$${n.toFixed(d)}`
}

export function dur(ms: number | null | undefined) {
  if (ms == null || Number.isNaN(ms)) return '–'
  if (ms < 1000) return `${Math.round(ms)} ms`
  if (ms < 60_000) return `${(ms / 1000).toFixed(1)} s`
  const m = Math.floor(ms / 60_000)
  const s = Math.round((ms % 60_000) / 1000)
  return `${m}m ${String(s).padStart(2, '0')}s`
}

export function pct(r: number | null | undefined, digits = 0) {
  if (r == null || Number.isNaN(r)) return '–'
  return `${(r * 100).toFixed(digits)}%`
}

export function level(l: number) {
  return `${Math.round(l * 100)}%`
}

export function clock(t: number) {
  const d = new Date(t * 1000)
  const p = (n: number) => String(n).padStart(2, '0')
  return `${p(d.getHours())}:${p(d.getMinutes())}:${p(d.getSeconds())}`
}

export function dateTime(t: number) {
  const d = new Date(t * 1000)
  return d.toLocaleString(undefined, { month: 'short', day: 'numeric', hour: '2-digit', minute: '2-digit' })
}

export function mm(v: number | null | undefined) {
  if (v == null || Number.isNaN(v)) return '–'
  return v < 10 ? `${v.toFixed(1)} mm` : `${Math.round(v)} mm`
}

export function plural(type: string) {
  const t = type.replace(/[_-]+/g, ' ').trim()
  const cap = t.charAt(0).toUpperCase() + t.slice(1)
  return /s$/i.test(cap) ? cap : `${cap}s`
}

export function titleCase(type: string) {
  const t = type.replace(/[_-]+/g, ' ').trim()
  return t.charAt(0).toUpperCase() + t.slice(1)
}
