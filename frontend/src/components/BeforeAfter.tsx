import { useCallback, useRef, useState } from 'react'

/** Drag (or arrow-key) slider comparing two same-size images. */
export function BeforeAfter({ before, after, beforeLabel = 'Before', afterLabel = 'After' }: { before: string; after: string; beforeLabel?: string; afterLabel?: string }) {
  const [pos, setPos] = useState(32)
  const box = useRef<HTMLDivElement>(null)
  const dragging = useRef(false)

  const fromEvent = useCallback((clientX: number) => {
    const r = box.current?.getBoundingClientRect()
    if (!r) return
    setPos(Math.min(100, Math.max(0, ((clientX - r.left) / r.width) * 100)))
  }, [])

  return (
    <div
      ref={box}
      className="relative aspect-square bg-well select-none touch-none overflow-hidden brackets"
      onPointerDown={(e) => {
        dragging.current = true
        ;(e.target as Element).setPointerCapture?.(e.pointerId)
        fromEvent(e.clientX)
      }}
      onPointerMove={(e) => dragging.current && fromEvent(e.clientX)}
      onPointerUp={() => (dragging.current = false)}
      onPointerCancel={() => (dragging.current = false)}
    >
      <img src={after} alt={afterLabel} className="absolute inset-0 size-full object-contain" draggable={false} />
      <img src={before} alt={beforeLabel} className="absolute inset-0 size-full object-contain" style={{ clipPath: `inset(0 ${100 - pos}% 0 0)` }} draggable={false} />
      <div className="absolute inset-y-0 w-px bg-signal pointer-events-none" style={{ left: `${pos}%` }}>
        <div className="absolute top-1/2 -translate-y-1/2 -translate-x-1/2 w-6 h-10 rounded-[3px] bg-signal text-signal-ink grid place-items-center shadow-[0_0_0_1px_rgba(0,0,0,.5)]">
          <svg viewBox="0 0 12 16" className="w-2.5 h-3.5" aria-hidden>
            <path d="M4 3v10M8 3v10" stroke="currentColor" strokeWidth="1.5" />
          </svg>
        </div>
      </div>
      <span className="absolute top-2.5 left-2.5 text-[11.5px] font-semibold px-1.5 py-0.5 rounded-[2px] bg-well/85 text-fg-2 pointer-events-none">{beforeLabel}</span>
      <span className="absolute top-2.5 right-2.5 text-[11.5px] font-semibold px-1.5 py-0.5 rounded-[2px] bg-well/85 text-signal pointer-events-none">{afterLabel}</span>
      <input
        type="range"
        min={0}
        max={100}
        value={Math.round(pos)}
        onChange={(e) => setPos(Number(e.target.value))}
        aria-label={`Compare ${beforeLabel.toLowerCase()} and ${afterLabel.toLowerCase()}`}
        className="absolute inset-x-0 bottom-0 h-6 opacity-0 cursor-ew-resize focus-visible:opacity-100"
      />
    </div>
  )
}
