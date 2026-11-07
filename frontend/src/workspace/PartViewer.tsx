import { Crosshair, Maximize2, Minus, Plus, ScanLine } from 'lucide-react'
import { useState } from 'react'
import type { Inspection } from './types'

export function PartViewer({ url, name, result, busy, generated }: {
  url: string | null; name: string; result: Inspection | null; busy: boolean; generated: boolean;
}) {
  const [zoom, setZoom] = useState(1)
  const [showBox, setShowBox] = useState(true)
  const box = result?.box_px
  return <div className="part-viewer">
    <div className="viewer-toolbar">
      <span className="viewer-label"><Crosshair size={15} /> {name || 'Part image'}</span>
      <span className="viewer-tag">{result && !result.source_kind ? 'Recorded image' : generated ? 'Generated sample' : 'Uploaded image'}</span>
    </div>
    <div className={'image-stage' + (busy ? ' is-scanning' : '')} aria-busy={busy}>
      <div className="stage-grid" aria-hidden="true" />
      {url ? <div className="part-image-wrap" style={{ transform: `scale(${zoom})` }}>
        <img src={url} alt={name || 'Part under inspection'} className="part-image" />
        {result && box && showBox && <svg className="defect-box" viewBox={`0 0 ${result.image_width} ${result.image_height}`} aria-label="Model defect location">
          <rect x={box[0]} y={box[1]} width={Math.max(0, box[2] - box[0])} height={Math.max(0, box[3] - box[1])} />
        </svg>}
      </div> : <div className="viewer-empty"><ScanLine size={40} strokeWidth={1} /><p>Choose a part to inspect</p><span>Upload a photo or select a sample below.</span></div>}
      <span className="stage-corner top-left" /><span className="stage-corner top-right" /><span className="stage-corner bottom-left" /><span className="stage-corner bottom-right" />
      {busy && <div className="scan-beam" aria-hidden="true" />}
      <div className="image-caption"><span className="capture-dot" />{busy ? 'Inspecting visual evidence…' : 'Top-down inspection'}<span>{result ? `${result.image_width} × ${result.image_height} px` : 'Single part view'}</span></div>
    </div>
    <div className="viewer-footer">
      <button className={'plain-button overlay-control' + (showBox ? ' selected' : '')} onClick={() => setShowBox(!showBox)} aria-pressed={showBox}><ScanLine size={15} /> Defect outline</button>
      <div className="zoom-controls"><button className="icon-button" aria-label="Zoom out" onClick={() => setZoom(Math.max(1, zoom - 0.25))} disabled={zoom === 1}><Minus size={15} /></button><span>{Math.round(zoom * 100)}%</span><button className="icon-button" aria-label="Zoom in" onClick={() => setZoom(Math.min(2, zoom + 0.25))} disabled={zoom === 2}><Plus size={15} /></button><button className="icon-button" aria-label="Reset zoom" onClick={() => setZoom(1)}><Maximize2 size={14} /></button></div>
    </div>
  </div>
}
