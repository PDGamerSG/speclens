import type { CSSProperties } from 'react'
import { useImageSize } from '../lib/useImageSize'
import { cx } from './ui'

type BBox = [number, number, number, number]

function windowFor(bbox: BBox, W: number, H: number, pad: number, minSide: number) {
  const bw = bbox[2] - bbox[0]
  const bh = bbox[3] - bbox[1]
  const side = Math.min(Math.max(Math.max(bw, bh) * pad, minSide), W, H)
  const cx = (bbox[0] + bbox[2]) / 2
  const cy = (bbox[1] + bbox[3]) / 2
  const x0 = Math.min(Math.max(cx - side / 2, 0), W - side)
  const y0 = Math.min(Math.max(cy - side / 2, 0), H - side)
  return { side, x0, y0 }
}

/**
 * A square window into a full-size image, centred on a bounding box.
 * mode 'mask' tints a white-on-black mask PNG with the defect signal colour.
 */
export function ZoomWindow({
  src,
  bbox,
  size,
  pad = 2.2,
  minSide = 96,
  mode = 'img',
  tint = 'var(--color-signal)',
  className,
  alt = '',
}: {
  src: string
  bbox: BBox | null
  size?: [number, number] | null
  pad?: number
  minSide?: number
  mode?: 'img' | 'mask'
  tint?: string
  className?: string
  alt?: string
}) {
  const natural = useImageSize(src, size ?? null)
  const dims = size ?? natural
  const root = cx(className?.includes('absolute') ? '' : 'relative', 'overflow-hidden bg-well', className)
  if (!bbox || !dims) {
    return (
      <div className={root}>
        {mode === 'img' ? (
          <img src={src} alt={alt} className="absolute inset-0 size-full object-cover" draggable={false} />
        ) : (
          <div className="absolute inset-0 mask-tint" style={{ background: tint, WebkitMaskImage: `url("${src}")`, maskImage: `url("${src}")` } as CSSProperties} />
        )}
      </div>
    )
  }
  const [W, H] = dims
  const { side, x0, y0 } = windowFor(bbox, W, H, pad, minSide)
  const style: CSSProperties = {
    position: 'absolute',
    width: `${(W / side) * 100}%`,
    height: `${(H / side) * 100}%`,
    left: `${(-x0 / side) * 100}%`,
    top: `${(-y0 / side) * 100}%`,
    maxWidth: 'none',
  }
  return (
    <div className={root}>
      {mode === 'img' ? (
        <img src={src} alt={alt} style={style} draggable={false} />
      ) : (
        <div className="mask-tint" style={{ ...style, background: tint, WebkitMaskImage: `url("${src}")`, maskImage: `url("${src}")` } as CSSProperties} />
      )}
    </div>
  )
}
