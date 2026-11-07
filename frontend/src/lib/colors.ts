// Categorical colours for defect types (validated on the graphite surface with the
// dataviz palette checker; the teal/magenta pair relies on marker shape + labels).
const TYPE_COLORS: Record<string, string> = {
  hole: '#3d8be6',
  crack: '#a6923a',
  print: '#cf5aa0',
  cut: '#21a59c',
}
const FALLBACK = ['#3d8be6', '#a6923a', '#cf5aa0', '#21a59c', '#9085e9', '#c8c8c0']

export type Marker = 'circle' | 'square' | 'diamond' | 'triangle'
const TYPE_MARKERS: Record<string, Marker> = { hole: 'circle', crack: 'square', print: 'diamond', cut: 'triangle' }
const MARKERS: Marker[] = ['circle', 'square', 'diamond', 'triangle']

export function typeColor(type: string, all: string[] = []) {
  if (TYPE_COLORS[type]) return TYPE_COLORS[type]
  const i = Math.max(0, all.indexOf(type))
  return FALLBACK[i % FALLBACK.length]
}

export function typeMarker(type: string, all: string[] = []): Marker {
  if (TYPE_MARKERS[type]) return TYPE_MARKERS[type]
  return MARKERS[Math.max(0, all.indexOf(type)) % MARKERS.length]
}

export function modelInfo(model: string): { label: string; color: string } {
  const m = model.toLowerCase()
  if (m.startsWith('muse-image')) return { label: 'Muse Image', color: '#ff8a3d' }
  if (m.startsWith('sam')) return { label: 'SAM 3.1', color: '#3ec7c2' }
  if (m.startsWith('muse-spark')) return { label: 'Muse Spark', color: '#a78bfa' }
  return { label: model, color: '#9aa3ad' }
}
