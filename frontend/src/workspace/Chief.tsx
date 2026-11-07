import { useEffect, useRef } from 'react'

export type Mood = 'idle' | 'looking' | 'accept' | 'reject' | 'review'

const MOUTH: Record<Mood, string> = {
  idle: 'M20 50.5c2.4 1.8 6 1.8 8.4 0',
  looking: 'M22.5 51a1.8 1.8 0 1 0 3.6 0a1.8 1.8 0 1 0-3.6 0',
  accept: 'M18.5 49c2.6 4.2 9 4.2 11.4 0',
  reject: 'M19 53c2.8-3.4 8-3.4 10.6 0',
  review: 'M19.5 51.5h9.4',
}

/** The inspector character. The lens follows the pointer, and the mouth reports the current decision. */
export function Chief({ mood = 'idle', size = 64, className = '' }: { mood?: Mood; size?: number; className?: string }) {
  const pupil = useRef<SVGCircleElement>(null)
  useEffect(() => {
    const follow = (event: PointerEvent) => {
      const eye = pupil.current
      if (!eye) return
      const box = eye.ownerSVGElement?.getBoundingClientRect()
      if (!box) return
      const dx = event.clientX - (box.left + box.width * 0.64)
      const dy = event.clientY - (box.top + box.height * 0.61)
      const reach = Math.min(1, Math.hypot(dx, dy) / 160)
      const angle = Math.atan2(dy, dx)
      eye.setAttribute('transform', `translate(${(Math.cos(angle) * 3.6 * reach).toFixed(2)} ${(Math.sin(angle) * 3.6 * reach).toFixed(2)})`)
    }
    window.addEventListener('pointermove', follow, { passive: true })
    return () => window.removeEventListener('pointermove', follow)
  }, [])
  return <svg className={'chief ' + className} data-mood={mood} width={size} height={size} viewBox="0 0 64 64" fill="none" aria-hidden="true">
    <g stroke="var(--ink)" strokeWidth="2.3" strokeLinecap="round" strokeLinejoin="round">
      <path d="M11.5 38.5c-1-13 8.2-21.7 20.8-21.4c12.4.3 21 9 20.2 21.6c-.8 12-9.6 19.6-20.6 19.3c-11.2-.3-19.5-7.8-20.4-19.5z" fill="#fff" />
      <path d="M14 27.5c.6-11.3 8.5-18.8 18.2-18.8c9.9 0 17.6 7.6 18.1 18.9c-11.8-3-24.3-3.1-36.3-.1z" fill="var(--marker)" />
      <path d="M8.5 29.5c15.3-4.3 31.9-4.4 47.3-.2" />
      <path d="M28.8 9.3c.5-3.4 6.3-3.5 6.9-.1l.4 6.3h-7.7z" fill="var(--marker)" />
      <circle cx="23.5" cy="39.5" r="2.5" fill="var(--ink)" stroke="none" />
      <circle cx="41" cy="39" r="9.2" fill="#E3F2FB" />
      <path d="M47.8 45.8l7 7.2" strokeWidth="4.2" />
      <circle ref={pupil} cx="41" cy="39" r="3.5" fill="var(--ink)" stroke="none" />
      <path className="chief-mouth" d={MOUTH[mood]} />
    </g>
  </svg>
}
