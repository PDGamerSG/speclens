import { Maximize2, Minus, Plus, ScanLine } from 'lucide-react'
import { useEffect, useRef, useState, type PointerEvent as ReactPointerEvent } from 'react'
import { PencilRing, Stamp } from './marks'
import { motionAllowed, PointScan } from './scan'
import type { Inspection } from './types'

type Phase = 'rest' | 'assemble' | 'scan' | 'settle'
const LOUPE_POWER = 2.4
const LOUPE_RADIUS = 78

export function PartViewer({ url, name, result, busy, generated, onFile }: {
  url: string | null; name: string; result: Inspection | null; busy: boolean; generated: boolean; onFile: (file: File) => void;
}) {
  const [zoom, setZoom] = useState(1)
  const [showBox, setShowBox] = useState(true)
  const [imageError, setImageError] = useState(false)
  const [phase, setPhase] = useState<Phase>('rest')
  const [dropping, setDropping] = useState(false)
  const [shownUrl, setShownUrl] = useState(url)
  if (url !== shownUrl) { setShownUrl(url); setZoom(1); setImageError(false) }

  const stage = useRef<HTMLDivElement>(null)
  const canvas = useRef<HTMLCanvasElement>(null)
  const photo = useRef<HTMLImageElement>(null)
  const loupe = useRef<HTMLDivElement>(null)
  const engine = useRef<PointScan | null>(null)
  const scanning = useRef(false)
  const box = result?.box_px
  const outline = !!result?.overlay_url && showBox

  useEffect(() => {
    if (!canvas.current || !motionAllowed()) return
    const scan = PointScan.create(canvas.current)
    if (!scan) return
    engine.current = scan
    const watcher = new ResizeObserver(() => scan.resize())
    watcher.observe(canvas.current)
    return () => { watcher.disconnect(); scan.dispose(); engine.current = null }
  }, [])

  useEffect(() => {
    const scan = engine.current
    if (!scan || !url) return
    let current = true
    scan.load(url).then(() => {
      if (!current || scanning.current || result) return
      setPhase('assemble')
      scan.play('assemble', () => setPhase('rest'))
    }).catch(() => { /* The <img> below reports a photo that cannot load. */ })
    return () => { current = false }
    // Only a new photo reassembles; a finished result reuses the frame already on screen.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [url])

  useEffect(() => {
    const scan = engine.current
    if (busy) {
      scanning.current = true
      setPhase('scan')
      scan?.play('scan')
      return
    }
    if (!scanning.current) return
    scanning.current = false
    if (!scan) { setPhase('rest'); return }
    setPhase('settle')
    scan.play('settle', () => setPhase('rest'))
  }, [busy])

  const lens = (event: ReactPointerEvent<HTMLDivElement>) => {
    const frame = stage.current?.getBoundingClientRect()
    if (frame) engine.current?.aim((event.clientX - frame.left) / frame.width * 2 - 1, (event.clientY - frame.top) / frame.height * 2 - 1)
    const glass = loupe.current
    const image = photo.current
    if (!glass) return
    if (!frame || !image?.naturalWidth || event.pointerType !== 'mouse' || phase !== 'rest' || zoom !== 1) { glass.style.opacity = '0'; return }
    const area = image.getBoundingClientRect()
    const scale = Math.min(area.width / image.naturalWidth, area.height / image.naturalHeight)
    const width = image.naturalWidth * scale
    const height = image.naturalHeight * scale
    const x = event.clientX - area.left - (area.width - width) / 2
    const y = event.clientY - area.top - (area.height - height) / 2
    if (x < 0 || y < 0 || x > width || y > height) { glass.style.opacity = '0'; return }
    glass.style.opacity = '1'
    glass.style.transform = `translate(${event.clientX - frame.left - LOUPE_RADIUS}px, ${event.clientY - frame.top - LOUPE_RADIUS}px)`
    glass.style.backgroundImage = `url("${image.currentSrc}")`
    glass.style.backgroundSize = `${width * LOUPE_POWER}px ${height * LOUPE_POWER}px`
    glass.style.backgroundPosition = `${LOUPE_RADIUS - x * LOUPE_POWER}px ${LOUPE_RADIUS - y * LOUPE_POWER}px`
  }
  const hideLens = () => { if (loupe.current) loupe.current.style.opacity = '0' }

  return <div className="part-viewer">
    <div ref={stage} className="image-stage" data-phase={phase} aria-busy={busy} onPointerMove={lens} onPointerLeave={hideLens}
      onDragOver={event => { if (!busy && event.dataTransfer.types.includes('Files')) { event.preventDefault(); setDropping(true) } }}
      onDragLeave={() => setDropping(false)}
      onDrop={event => { event.preventDefault(); setDropping(false); const file = event.dataTransfer.files[0]; if (file) onFile(file) }}>
      {url && !imageError ? <div className="part-image-wrap" style={{ transform: `scale(${zoom})` }}>
        <img ref={photo} src={outline && phase === 'rest' ? result!.overlay_url : url} alt={name || 'Part under inspection'} className="part-image" onError={() => setImageError(true)} />
        {result && box && showBox && phase === 'rest' && <PencilRing box={box} width={result.image_width} height={result.image_height} label={result.type} seed={result.id} />}
      </div> : <div className="viewer-empty" role="status">
        <ScanLine size={36} strokeWidth={1.2} />
        <p>{imageError ? 'This part photo could not load' : 'Choose a part to inspect'}</p>
        <span>{imageError ? 'Check the connection or choose another photo.' : 'Upload a photo or pick a sample below.'}</span>
        {imageError && <button className="button secondary" onClick={() => setImageError(false)}>Retry photo</button>}
      </div>}
      <canvas ref={canvas} className="scan-canvas" aria-hidden="true" />
      {busy && !engine.current && <div className="scan-beam" aria-hidden="true" />}
      <div ref={loupe} className="loupe" aria-hidden="true" />
      <span className="stage-tick top-left" /><span className="stage-tick top-right" /><span className="stage-tick bottom-left" /><span className="stage-tick bottom-right" />
      <div className="stage-caption">
        <span className="viewer-label">{name || 'Part image'}</span>
        <span className="viewer-tag">{result && !result.source_kind ? 'Recorded image' : generated ? 'Generated sample' : 'Uploaded image'}</span>
      </div>
      {result && phase === 'rest' && <Stamp key={result.id} verdict={result.verdict} />}
      {dropping && <div className="drop-hint">Drop the photo to use it</div>}
    </div>
    <div className="viewer-footer">
      <button className={'pill-toggle overlay-control' + (showBox && (box || result?.overlay_url) ? ' selected' : '')} onClick={() => setShowBox(!showBox)} aria-pressed={showBox && !!(box || result?.overlay_url)} disabled={!(box || result?.overlay_url) || imageError}><ScanLine size={15} />Defect outline</button>
      <span className="viewer-hint">{busy ? 'Reading the photo against your specification' : zoom === 1 ? 'Hover the photo to magnify' : 'Zoomed view'}</span>
      <div className="zoom-controls">
        <button className="icon-button" aria-label="Zoom out" onClick={() => setZoom(Math.max(1, zoom - 0.25))} disabled={zoom === 1}><Minus size={15} /></button>
        <span>{Math.round(zoom * 100)}%</span>
        <button className="icon-button" aria-label="Zoom in" onClick={() => setZoom(Math.min(2, zoom + 0.25))} disabled={zoom === 2}><Plus size={15} /></button>
        <button className="icon-button" aria-label="Reset zoom" onClick={() => setZoom(1)}><Maximize2 size={14} /></button>
      </div>
    </div>
  </div>
}
