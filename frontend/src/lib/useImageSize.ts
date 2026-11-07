import { useEffect, useState } from 'react'

const cache = new Map<string, [number, number]>()

/** Natural size of an image URL (cached). */
export function useImageSize(url: string | null | undefined, fallback?: [number, number] | null) {
  const [size, setSize] = useState<[number, number] | null>(() => (url ? cache.get(url) ?? fallback ?? null : null))
  useEffect(() => {
    if (!url) return
    const hit = cache.get(url)
    if (hit) {
      setSize(hit)
      return
    }
    let alive = true
    const img = new Image()
    img.onload = () => {
      const s: [number, number] = [img.naturalWidth, img.naturalHeight]
      cache.set(url, s)
      if (alive) setSize(s)
    }
    img.src = url
    return () => {
      alive = false
    }
  }, [url])
  return size
}
