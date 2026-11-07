function random(seed: number) {
  let state = seed >>> 0
  return () => {
    state = (state + 0x6d2b79f5) >>> 0
    let value = Math.imul(state ^ (state >>> 15), 1 | state)
    value = (value + Math.imul(value ^ (value >>> 7), 61 | value)) ^ value
    return ((value ^ (value >>> 14)) >>> 0) / 4294967296
  }
}

function seedOf(text: string) {
  let hash = 2166136261
  for (let index = 0; index < text.length; index++) hash = Math.imul(hash ^ text.charCodeAt(index), 16777619)
  return hash
}

/** One loose pencil loop around a box, with an overshoot like a marked-up part. */
function ringPath(box: number[], seed: string, pad: number) {
  const next = random(seedOf(seed))
  const [x0, y0, x1, y1] = box
  const cx = (x0 + x1) / 2
  const cy = (y0 + y1) / 2
  const rx = (x1 - x0) / 2 * 1.2 + pad
  const ry = (y1 - y0) / 2 * 1.2 + pad
  const start = -2.3 + next() * 0.5
  const steps = 24
  const points: [number, number][] = []
  for (let index = 0; index <= steps * 1.14; index++) {
    const angle = start + (index / steps) * Math.PI * 2
    const wobble = 1 + (next() - 0.5) * 0.05 + (index / steps) * 0.05
    points.push([cx + Math.cos(angle) * rx * wobble, cy + Math.sin(angle) * ry * wobble])
  }
  let path = `M${points[0][0].toFixed(1)} ${points[0][1].toFixed(1)}`
  for (let index = 1; index < points.length - 1; index++) {
    const midX = (points[index][0] + points[index + 1][0]) / 2
    const midY = (points[index][1] + points[index + 1][1]) / 2
    path += `Q${points[index][0].toFixed(1)} ${points[index][1].toFixed(1)} ${midX.toFixed(1)} ${midY.toFixed(1)}`
  }
  return path
}

export function PencilRing({ box, width, height, label, seed }: { box: number[]; width: number; height: number; label: string; seed: string }) {
  const unit = Math.max(width, height)
  const labelY = Math.max(box[1] - unit * 0.075, unit * 0.05)
  return <svg className="defect-box" viewBox={`0 0 ${width} ${height}`} role="img" aria-label="Model defect location">
    <path className="pencil-line" pathLength={1} d={ringPath(box, seed, unit * 0.018)} strokeWidth={unit * 0.0075} />
    <text className="pencil-label" x={Math.min(box[0], width - unit * 0.2)} y={labelY} fontSize={unit * 0.042}>{label}</text>
  </svg>
}

export function Stamp({ verdict }: { verdict: string }) {
  const word = verdict === 'good' ? 'Accept' : verdict === 'defect' ? 'Reject' : 'Review'
  return <div className={'stamp ' + verdict} aria-hidden="true">{word}</div>
}

/** Digits roll to their new value, so a changed count is visible at a glance. */
export function Rolling({ value }: { value: number }) {
  const text = String(value)
  return <span className="rolling">
    <span className="sr-only">{text}</span>
    <span className="rolling-digits" aria-hidden="true">{text.split('').map((digit, index) =>
      <span className="rolling-column" key={text.length - index} style={{ transform: `translateY(${-Number(digit) * 10}%)` }}>
        {[0, 1, 2, 3, 4, 5, 6, 7, 8, 9].map(number => <span key={number}>{number}</span>)}
      </span>)}
    </span>
  </span>
}

export function InkFilter() {
  return <svg className="ink-filter" width="0" height="0" aria-hidden="true">
    <filter id="ink-rough"><feTurbulence type="fractalNoise" baseFrequency="0.85" numOctaves="2" seed="7" result="grain" /><feDisplacementMap in="SourceGraphic" in2="grain" scale="2.4" /></filter>
  </svg>
}
