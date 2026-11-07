// Procedural placeholder visuals for mock mode. Everything is drawn with canvas
// gradients and blobs; no real photos are used or bundled.

export const FULL = 768 // full image side, px (mock stand-in for the 1024 px scans)
export const CROP = 384 // crop side, px (mock stand-in for the 512 px crop)
export const PART_WIDTH_MM = 20

export function rng(seed: number) {
  let a = seed >>> 0
  return () => {
    a = (a + 0x6d2b79f5) >>> 0
    let t = a
    t = Math.imul(t ^ (t >>> 15), t | 1)
    t ^= t + Math.imul(t ^ (t >>> 7), t | 61)
    return ((t ^ (t >>> 14)) >>> 0) / 4294967296
  }
}

function canvas(w: number, h = w) {
  const c = document.createElement('canvas')
  c.width = w
  c.height = h
  const ctx = c.getContext('2d')!
  return { c, ctx }
}

export interface NutSpec {
  seed: number
  cx: number
  cy: number
  rx: number
  ry: number
  rot: number
  tone: number // -1..1 shell tone shift
}

export function makeNut(seed: number): NutSpec {
  const r = rng(seed)
  return {
    seed,
    cx: FULL / 2 + (r() - 0.5) * 50,
    cy: FULL / 2 + (r() - 0.5) * 50,
    rx: 232 + r() * 30,
    ry: 262 + r() * 26,
    rot: (r() - 0.5) * 1.4,
    tone: r() * 2 - 1,
  }
}

function shellPath(ctx: CanvasRenderingContext2D, n: NutSpec) {
  ctx.beginPath()
  // Slightly pointed at the tip (bottom): blend an ellipse with a teardrop.
  const steps = 96
  for (let i = 0; i <= steps; i++) {
    const t = (i / steps) * Math.PI * 2
    const x = Math.sin(t) * n.rx * (1 - 0.08 * Math.max(0, Math.cos(t)))
    const y = -Math.cos(t) * n.ry
    if (i === 0) ctx.moveTo(x, y)
    else ctx.lineTo(x, y)
  }
  ctx.closePath()
}

/** Draws a good hazelnut on a dark background. */
export function drawNut(ctx: CanvasRenderingContext2D, n: NutSpec) {
  const r = rng(n.seed * 7 + 3)
  ctx.save()
  ctx.fillStyle = '#0d0e0f'
  ctx.fillRect(0, 0, FULL, FULL)
  const vg = ctx.createRadialGradient(FULL / 2, FULL / 2, 40, FULL / 2, FULL / 2, FULL * 0.75)
  vg.addColorStop(0, '#191a1c')
  vg.addColorStop(1, '#0a0b0c')
  ctx.fillStyle = vg
  ctx.fillRect(0, 0, FULL, FULL)
  // sensor noise
  for (let i = 0; i < 1800; i++) {
    ctx.fillStyle = `rgba(255,255,255,${0.012 + r() * 0.02})`
    ctx.fillRect(r() * FULL, r() * FULL, 1, 1)
  }

  ctx.translate(n.cx, n.cy)
  ctx.rotate(n.rot)

  // contact shadow
  ctx.save()
  ctx.filter = 'blur(18px)'
  ctx.fillStyle = 'rgba(0,0,0,0.75)'
  ctx.beginPath()
  ctx.ellipse(14, 22, n.rx * 0.98, n.ry * 0.98, 0, 0, Math.PI * 2)
  ctx.fill()
  ctx.restore()

  ctx.save()
  shellPath(ctx, n)
  ctx.clip()
  const k = n.tone * 14
  const g = ctx.createRadialGradient(-n.rx * 0.32, -n.ry * 0.22, 10, 0, 0, Math.max(n.rx, n.ry) * 1.15)
  g.addColorStop(0, `rgb(${200 + k},${118 + k * 0.6},${62})`)
  g.addColorStop(0.42, `rgb(${160 + k},${82 + k * 0.5},${36})`)
  g.addColorStop(0.8, `rgb(${112 + k},${52},${22})`)
  g.addColorStop(1, '#3a1808')
  ctx.fillStyle = g
  ctx.fillRect(-n.rx, -n.ry, n.rx * 2, n.ry * 2)

  // meridian striations
  for (let i = 0; i < 64; i++) {
    const th = -Math.PI / 2 + (i / 63) * Math.PI + (r() - 0.5) * 0.03
    const bulge = Math.sin(th) * n.rx * 1.02
    ctx.beginPath()
    ctx.moveTo(0, -n.ry * 1.02)
    ctx.quadraticCurveTo(bulge * 1.32, 0, bulge * 0.15, n.ry * 1.02)
    const dark = r() < 0.6
    ctx.strokeStyle = dark ? `rgba(58,22,6,${0.16 + r() * 0.22})` : `rgba(236,160,96,${0.06 + r() * 0.1})`
    ctx.lineWidth = 0.8 + r() * 2.6
    ctx.stroke()
  }
  // pores
  for (let i = 0; i < 900; i++) {
    const a = r() * Math.PI * 2
    const d = Math.sqrt(r())
    ctx.fillStyle = r() < 0.5 ? 'rgba(40,14,4,0.18)' : 'rgba(255,200,150,0.08)'
    ctx.fillRect(Math.cos(a) * d * n.rx, Math.sin(a) * d * n.ry, 1.4, 1.4)
  }

  // rough cap (attachment scar)
  ctx.save()
  ctx.beginPath()
  const capY = -n.ry * 0.78
  for (let i = 0; i <= 48; i++) {
    const t = (i / 48) * Math.PI * 2
    const wob = 1 + (r() - 0.5) * 0.12
    const x = Math.cos(t) * n.rx * 0.82 * wob
    const y = capY + Math.sin(t) * n.ry * 0.3 * wob
    if (i === 0) ctx.moveTo(x, y)
    else ctx.lineTo(x, y)
  }
  ctx.closePath()
  const cg = ctx.createLinearGradient(0, -n.ry, 0, capY + n.ry * 0.3)
  cg.addColorStop(0, '#6d5139')
  cg.addColorStop(0.6, '#9a7a5a')
  cg.addColorStop(1, '#7a5a3e')
  ctx.fillStyle = cg
  ctx.fill()
  ctx.clip()
  for (let i = 0; i < 1400; i++) {
    const x = (r() - 0.5) * n.rx * 1.8
    const y = capY + (r() - 0.5) * n.ry * 0.7
    ctx.fillStyle = r() < 0.5 ? 'rgba(200,170,130,0.35)' : 'rgba(60,40,24,0.35)'
    ctx.fillRect(x, y, 1 + r() * 2, 1 + r() * 2)
  }
  ctx.restore()
  ctx.strokeStyle = 'rgba(70,40,20,0.5)'
  ctx.lineWidth = 2

  // specular
  const hg = ctx.createRadialGradient(-n.rx * 0.38, -n.ry * 0.1, 4, -n.rx * 0.38, -n.ry * 0.1, n.rx * 0.7)
  hg.addColorStop(0, 'rgba(255,230,200,0.22)')
  hg.addColorStop(1, 'rgba(255,230,200,0)')
  ctx.fillStyle = hg
  ctx.fillRect(-n.rx, -n.ry, n.rx * 2, n.ry * 2)
  // rim darkening
  const rg = ctx.createRadialGradient(0, 0, Math.min(n.rx, n.ry) * 0.7, 0, 0, Math.max(n.rx, n.ry) * 1.02)
  rg.addColorStop(0, 'rgba(0,0,0,0)')
  rg.addColorStop(1, 'rgba(0,0,0,0.55)')
  ctx.fillStyle = rg
  ctx.fillRect(-n.rx, -n.ry, n.rx * 2, n.ry * 2)
  ctx.restore()
  ctx.restore()
}

export function nutImage(n: NutSpec): string {
  const { c, ctx } = canvas(FULL)
  drawNut(ctx, n)
  return c.toDataURL('image/jpeg', 0.86)
}

export function nutMask(n: NutSpec): string {
  const { c, ctx } = canvas(FULL)
  ctx.fillStyle = '#000'
  ctx.fillRect(0, 0, FULL, FULL)
  ctx.translate(n.cx, n.cy)
  ctx.rotate(n.rot)
  shellPath(ctx, n)
  ctx.fillStyle = '#fff'
  ctx.fill()
  return c.toDataURL('image/png')
}

// ---------------------------------------------------------------- defects

export interface DefectSpec {
  type: string
  seed: number
  x: number // image px
  y: number
  angle: number
  text: string
}

export function placeDefect(n: NutSpec, type: string, seed: number): DefectSpec {
  const r = rng(seed)
  const a = r() * Math.PI * 2
  const d = 0.15 + r() * 0.42
  // keep defects on the smooth shell, away from the cap
  const lx = Math.cos(a) * d * n.rx
  const ly = Math.abs(Math.sin(a)) * d * n.ry * 0.9 - n.ry * 0.05
  const x = n.cx + lx * Math.cos(n.rot) - ly * Math.sin(n.rot)
  const y = n.cy + lx * Math.sin(n.rot) + ly * Math.cos(n.rot)
  const texts = ['B7', '4K', 'LOT', 'A3', '12', 'XR']
  return { type, seed, x, y, angle: (r() - 0.5) * 1.2, text: texts[Math.floor(r() * texts.length)] }
}

function blobPoints(r: () => number, radius: number, nPts = 15) {
  const pts: [number, number][] = []
  for (let i = 0; i < nPts; i++) {
    const t = (i / nPts) * Math.PI * 2
    const rr = radius * (0.78 + r() * 0.42)
    pts.push([Math.cos(t) * rr, Math.sin(t) * rr])
  }
  return pts
}

function poly(ctx: CanvasRenderingContext2D, pts: [number, number][], s = 1) {
  ctx.beginPath()
  pts.forEach(([x, y], i) => (i ? ctx.lineTo(x * s, y * s) : ctx.moveTo(x * s, y * s)))
  ctx.closePath()
}

function crackPoints(r: () => number, len: number) {
  const pts: [number, number][] = []
  const segs = 12
  let y = 0
  for (let i = 0; i <= segs; i++) {
    y += (r() - 0.5) * len * 0.06
    pts.push([-len / 2 + (i / segs) * len, y])
  }
  return pts
}

/**
 * Draws a defect. mode 'paint' = photographic look, 'shape' = solid white for masks.
 * opacity and scale implement the severity ladder.
 */
export function drawDefect(
  ctx: CanvasRenderingContext2D,
  d: DefectSpec,
  mode: 'paint' | 'shape',
  opacity = 1,
  scale = 1,
) {
  const r = rng(d.seed * 13 + 1)
  ctx.save()
  ctx.translate(d.x, d.y)
  ctx.rotate(d.angle)
  ctx.globalAlpha = mode === 'paint' ? opacity : 1
  const s = scale
  if (d.type === 'hole') {
    const pts = blobPoints(r, 15)
    if (mode === 'shape') {
      ctx.fillStyle = '#fff'
      poly(ctx, pts, 1.32 * s)
      ctx.fill()
    } else {
      ctx.fillStyle = 'rgba(214,170,118,0.55)'
      poly(ctx, pts, 1.32 * s)
      ctx.fill()
      const g = ctx.createRadialGradient(0, 0, 1, 0, 0, 16 * s)
      g.addColorStop(0, '#030201')
      g.addColorStop(0.7, '#120804')
      g.addColorStop(1, '#3a1a08')
      ctx.fillStyle = g
      poly(ctx, pts, s)
      ctx.fill()
      // torn fibres
      ctx.strokeStyle = 'rgba(230,190,140,0.55)'
      ctx.lineWidth = 1
      for (let i = 0; i < 9; i++) {
        const t = r() * Math.PI * 2
        ctx.beginPath()
        ctx.moveTo(Math.cos(t) * 13 * s, Math.sin(t) * 13 * s)
        ctx.lineTo(Math.cos(t) * 20 * s, Math.sin(t) * 20 * s)
        ctx.stroke()
      }
    }
  } else if (d.type === 'crack') {
    const pts = crackPoints(r, 120)
    ctx.lineJoin = 'round'
    ctx.lineCap = 'round'
    const path = () => {
      ctx.beginPath()
      pts.forEach(([x, y], i) => (i ? ctx.lineTo(x * s, y * s) : ctx.moveTo(x * s, y * s)))
    }
    if (mode === 'shape') {
      path()
      ctx.strokeStyle = '#fff'
      ctx.lineWidth = 9 * Math.max(s, 0.5)
      ctx.stroke()
    } else {
      path()
      ctx.strokeStyle = 'rgba(232,170,110,0.4)'
      ctx.lineWidth = 6 * Math.max(s, 0.5)
      ctx.stroke()
      path()
      ctx.strokeStyle = 'rgba(16,6,2,0.95)'
      ctx.lineWidth = 3.2 * Math.max(s, 0.5)
      ctx.stroke()
    }
  } else if (d.type === 'print') {
    ctx.font = `800 ${Math.round(54 * s)}px Archivo, Arial, sans-serif`
    ctx.textAlign = 'center'
    ctx.textBaseline = 'middle'
    if (mode === 'shape') {
      ctx.fillStyle = '#fff'
      ctx.strokeStyle = '#fff'
      ctx.lineWidth = 7
      ctx.strokeText(d.text, 0, 0)
      ctx.fillText(d.text, 0, 0)
    } else {
      ctx.fillStyle = 'rgba(244,238,226,0.88)'
      ctx.fillText(d.text, 0, 0)
      ctx.fillStyle = 'rgba(244,238,226,0.35)'
      ctx.fillText(d.text, 1.5, 1)
      // ink dropouts
      ctx.globalCompositeOperation = 'source-atop'
      for (let i = 0; i < 90; i++) {
        ctx.fillStyle = 'rgba(150,80,40,0.6)'
        ctx.fillRect((r() - 0.5) * 120 * s, (r() - 0.5) * 50 * s, 2, 2)
      }
    }
  } else {
    // cut: a narrow sliver exposing the pale kernel
    const L = 110
    const pts: [number, number][] = []
    for (let i = 0; i <= 10; i++) pts.push([-L / 2 + (i / 10) * L, -(Math.sin((i / 10) * Math.PI) * 9 + r() * 2)])
    for (let i = 10; i >= 0; i--) pts.push([-L / 2 + (i / 10) * L, Math.sin((i / 10) * Math.PI) * 7 + r() * 2])
    if (mode === 'shape') {
      ctx.fillStyle = '#fff'
      poly(ctx, pts, s)
      ctx.lineWidth = 6
      ctx.strokeStyle = '#fff'
      ctx.fill()
      ctx.stroke()
    } else {
      ctx.fillStyle = '#2a1205'
      poly(ctx, pts, s)
      ctx.fill()
      ctx.fillStyle = 'rgba(214,180,136,0.75)'
      poly(ctx, pts, s * 0.6)
      ctx.fill()
    }
  }
  ctx.restore()
}

export interface ForgedImages {
  original: string
  cropOriginal: string
  cropRaw: string
  cropComposite: string
  composite: string
  mask: string
  overlay: string
  bbox: [number, number, number, number]
  area: number
  sizeMm: number
}

function cropOrigin(d: DefectSpec): [number, number] {
  const x0 = Math.round(Math.min(Math.max(d.x - CROP / 2, 0), FULL - CROP))
  const y0 = Math.round(Math.min(Math.max(d.y - CROP / 2, 0), FULL - CROP))
  return [x0, y0]
}

function cropOf(src: HTMLCanvasElement, d: DefectSpec) {
  const [x0, y0] = cropOrigin(d)
  const { c, ctx } = canvas(CROP)
  ctx.drawImage(src, x0, y0, CROP, CROP, 0, 0, CROP, CROP)
  return c
}

export function mmPerPx(n: NutSpec) {
  return PART_WIDTH_MM / (2 * n.rx)
}

const nutCanvasCache = new Map<number, HTMLCanvasElement>()
function nutCanvas(n: NutSpec) {
  let c = nutCanvasCache.get(n.seed)
  if (!c) {
    const k = canvas(FULL)
    drawNut(k.ctx, n)
    c = k.c
    nutCanvasCache.set(n.seed, c)
  }
  return c
}

export function cropOriginalOnly(n: NutSpec, d: DefectSpec) {
  return cropOf(nutCanvas(n), d).toDataURL('image/jpeg', 0.86)
}

export function forge(n: NutSpec, d: DefectSpec): ForgedImages {
  const base = nutCanvas(n)

  const comp = canvas(FULL)
  comp.ctx.drawImage(base, 0, 0)
  drawDefect(comp.ctx, d, 'paint')

  // alpha shape for mask + outline
  const shape = canvas(FULL)
  drawDefect(shape.ctx, d, 'shape')
  const img = shape.ctx.getImageData(0, 0, FULL, FULL).data
  let area = 0
  let x0 = FULL
  let y0 = FULL
  let x1 = 0
  let y1 = 0
  for (let y = 0; y < FULL; y++) {
    for (let x = 0; x < FULL; x++) {
      if (img[(y * FULL + x) * 4 + 3] > 127) {
        area++
        if (x < x0) x0 = x
        if (x > x1) x1 = x
        if (y < y0) y0 = y
        if (y > y1) y1 = y
      }
    }
  }

  const mask = canvas(FULL)
  mask.ctx.fillStyle = '#000'
  mask.ctx.fillRect(0, 0, FULL, FULL)
  mask.ctx.drawImage(shape.c, 0, 0)

  // outline ring = dilate(shape) minus shape, tinted signal amber
  const ring = canvas(FULL)
  for (let a = 0; a < 16; a++) {
    const t = (a / 16) * Math.PI * 2
    ring.ctx.drawImage(shape.c, Math.cos(t) * 3.5, Math.sin(t) * 3.5)
  }
  ring.ctx.globalCompositeOperation = 'source-in'
  ring.ctx.fillStyle = '#ffb420'
  ring.ctx.fillRect(0, 0, FULL, FULL)
  ring.ctx.globalCompositeOperation = 'destination-out'
  ring.ctx.drawImage(shape.c, 0, 0)

  const over = canvas(FULL)
  over.ctx.drawImage(comp.c, 0, 0)
  over.ctx.drawImage(ring.c, 0, 0)

  const cropC = cropOf(comp.c, d)
  // "raw Muse Image output": same defect but globally shifted and re-toned,
  // which is why the backend composites only the changed pixels.
  const raw = canvas(CROP)
  raw.ctx.filter = 'saturate(1.3) brightness(1.08) contrast(1.06) hue-rotate(-6deg)'
  raw.ctx.drawImage(cropC, -9, -7, CROP * 1.045, CROP * 1.045)
  raw.ctx.filter = 'none'

  const sizeMm = 2 * Math.sqrt(area / Math.PI) * mmPerPx(n)
  return {
    original: nutImage(n),
    cropOriginal: cropOf(base, d).toDataURL('image/jpeg', 0.86),
    cropRaw: raw.c.toDataURL('image/jpeg', 0.86),
    cropComposite: cropC.toDataURL('image/jpeg', 0.88),
    composite: comp.c.toDataURL('image/jpeg', 0.86),
    mask: mask.c.toDataURL('image/png'),
    overlay: over.c.toDataURL('image/jpeg', 0.86),
    bbox: [x0, y0, x1, y1],
    area,
    sizeMm,
  }
}

export function severityVariant(n: NutSpec, d: DefectSpec, kind: 'opacity' | 'size', level: number) {
  const c = canvas(FULL)
  c.ctx.drawImage(nutCanvas(n), 0, 0)
  if (kind === 'opacity') drawDefect(c.ctx, d, 'paint', level, 1)
  else drawDefect(c.ctx, d, 'paint', 1, level)
  return c.c.toDataURL('image/jpeg', 0.84)
}

/** Draws an inspection overlay on an uploaded image for the mock inspector. */
export async function mockInspectOverlay(file: Blob, verdict: string) {
  const url = URL.createObjectURL(file)
  const img = new Image()
  img.src = url
  await img.decode().catch(() => undefined)
  const w = img.naturalWidth || 640
  const h = img.naturalHeight || 480
  const scale = Math.min(1, 1280 / Math.max(w, h))
  const { c, ctx } = canvas(Math.round(w * scale), Math.round(h * scale))
  if (img.naturalWidth) ctx.drawImage(img, 0, 0, c.width, c.height)
  else {
    ctx.fillStyle = '#222'
    ctx.fillRect(0, 0, c.width, c.height)
  }
  const box: [number, number, number, number] = [
    Math.round(c.width * 0.42),
    Math.round(c.height * 0.4),
    Math.round(c.width * 0.54),
    Math.round(c.height * 0.52),
  ]
  if (verdict !== 'good') {
    ctx.strokeStyle = verdict === 'defect' ? '#ffb420' : '#ffb420'
    ctx.lineWidth = Math.max(2, c.width / 300)
    ctx.setLineDash(verdict === 'uncertain' ? [8, 6] : [])
    ctx.beginPath()
    ctx.ellipse((box[0] + box[2]) / 2, (box[1] + box[3]) / 2, (box[2] - box[0]) / 2.6, (box[3] - box[1]) / 2.6, 0.3, 0, Math.PI * 2)
    ctx.stroke()
    ctx.strokeRect(box[0], box[1], box[2] - box[0], box[3] - box[1])
  }
  return { imageUrl: url, overlayUrl: c.toDataURL('image/jpeg', 0.86), box: verdict === 'good' ? null : box }
}
