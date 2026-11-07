import { useCallback, useEffect, useRef, useState } from 'react'
import { api } from '../api'
import type { Inspection } from '../api/types'
import { Button, Checkbox, ErrorLine, Spinner, cx } from '../components/ui'
import { dur, pct, titleCase, usd } from '../lib/format'
import { useStore } from '../state/store'

const VERDICT: Record<Inspection['verdict'], { word: string; cls: string; ring: string; note: string }> = {
  defect: { word: 'DEFECT', cls: 'text-miss', ring: 'border-miss/60 bg-miss/[0.07]', note: 'Reject this part.' },
  good: { word: 'GOOD', cls: 'text-pass', ring: 'border-pass/50 bg-pass/[0.06]', note: 'No defect from the spec was found.' },
  uncertain: { word: 'UNCERTAIN', cls: 'text-signal', ring: 'border-signal/60 bg-signal/[0.07]', note: 'Muse Spark reported a defect, but SAM 3.1 found no mask inside its box. Review by hand.' },
}

interface HistoryItem {
  id: number
  thumb: string
  result: Inspection
}

export function InspectScreen() {
  const { state } = useStore()
  const video = useRef<HTMLVideoElement>(null)
  const stream = useRef<MediaStream | null>(null)
  const file = useRef<HTMLInputElement>(null)
  const [cam, setCam] = useState<'off' | 'starting' | 'on'>('off')
  const [camError, setCamError] = useState<string | null>(null)
  const [preview, setPreview] = useState<string | null>(null)
  const [busy, setBusy] = useState(false)
  const [result, setResult] = useState<Inspection | null>(null)
  const [error, setError] = useState<string | null>(null)
  const [history, setHistory] = useState<HistoryItem[]>([])
  const exampleRuns = state.runs.filter((r) => r.accepted > 0 && r.status === 'completed')
  const [useEx, setUseEx] = useState(false)
  const [exRun, setExRun] = useState('')
  const exId = exRun || exampleRuns[0]?.id || ''

  const stop = useCallback(() => {
    stream.current?.getTracks().forEach((t) => t.stop())
    stream.current = null
    setCam('off')
  }, [])
  useEffect(() => stop, [stop])

  const start = async () => {
    setCamError(null)
    if (!navigator.mediaDevices?.getUserMedia) {
      setCamError(window.isSecureContext ? 'This browser has no camera API. Use Take or upload photo.' : 'The camera needs HTTPS or localhost. Open the tunnel URL, or use Take or upload photo.')
      return
    }
    setCam('starting')
    try {
      const s = await navigator.mediaDevices.getUserMedia({ video: { facingMode: { ideal: 'environment' }, width: { ideal: 1920 }, height: { ideal: 1080 } }, audio: false })
      stream.current = s
      if (video.current) {
        video.current.srcObject = s
        await video.current.play().catch(() => undefined)
      }
      setCam('on')
    } catch (e) {
      setCam('off')
      setCamError(e instanceof Error && e.name === 'NotAllowedError' ? 'Camera permission was denied. Allow it in the browser, or use Take or upload photo.' : 'Could not start the camera. Use Take or upload photo.')
    }
  }

  const send = async (blob: Blob) => {
    const url = URL.createObjectURL(blob)
    setPreview(url)
    setBusy(true)
    setError(null)
    setResult(null)
    try {
      const r = await api.inspect(blob, { spec_text: state.specText || undefined, use_examples_run_id: useEx && exId ? exId : undefined })
      setResult(r)
      setHistory((h) => [{ id: Date.now(), thumb: url, result: r }, ...h].slice(0, 8))
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e))
    } finally {
      setBusy(false)
    }
  }

  const capture = () => {
    const v = video.current
    if (!v || !v.videoWidth) return
    const c = document.createElement('canvas')
    c.width = v.videoWidth
    c.height = v.videoHeight
    c.getContext('2d')!.drawImage(v, 0, 0)
    c.toBlob((b) => b && void send(b), 'image/jpeg', 0.92)
  }

  const v = result ? VERDICT[result.verdict] : null

  return (
    <main className="px-4 lg:px-6 pb-24 pt-5 max-w-[1680px] mx-auto">
      <div className="pb-4 border-b border-rule max-w-[70ch]">
        <h1 className="text-[24px] font-bold tracking-[-0.015em] leading-tight">Inspect a real part</h1>
        <p className="text-[14px] text-fg-2 mt-1.5">Point the camera at a hazelnut on a dark background, or upload a photo. Muse Spark judges it against the spec and SAM 3.1 outlines what it found.</p>
      </div>

      <div className="grid lg:grid-cols-[minmax(0,1.1fr)_minmax(0,0.9fr)] gap-6 mt-5">
        <section className="min-w-0 flex flex-col gap-3" aria-label="Camera">
          <div className="relative aspect-[4/3] bg-well brackets overflow-hidden rounded-[2px]">
            <video ref={video} playsInline muted className={cx('absolute inset-0 size-full object-cover', cam !== 'on' && 'invisible')} />
            {cam === 'on' && (
              <svg className="absolute inset-0 size-full pointer-events-none" aria-hidden>
                <line x1="50%" x2="50%" y1="44%" y2="56%" stroke="rgba(255,255,255,.55)" strokeWidth="1" />
                <line x1="46%" x2="54%" y1="50%" y2="50%" stroke="rgba(255,255,255,.55)" strokeWidth="1" />
                <circle cx="50%" cy="50%" r="31%" fill="none" stroke="rgba(255,255,255,.18)" strokeDasharray="4 6" />
              </svg>
            )}
            {cam !== 'on' && (
              <div className="absolute inset-0 grid place-items-center p-6 text-center">
                <div className="max-w-xs">
                  <p className="text-[14px] text-fg-2">{cam === 'starting' ? 'Starting the camera' : 'The camera is off'}</p>
                  <p className="text-[12px] text-fg-3 mt-1">Phones need the HTTPS tunnel URL for live camera. A photo upload works everywhere.</p>
                  <Button className="mt-4" onClick={() => void start()} disabled={cam === 'starting'}>
                    {cam === 'starting' && <Spinner />}
                    Start camera
                  </Button>
                </div>
              </div>
            )}
          </div>
          <div className="flex flex-wrap items-center gap-2">
            {cam === 'on' && (
              <>
                <Button variant="primary" size="lg" onClick={capture} disabled={busy} className="flex-1 sm:flex-none">
                  {busy && <Spinner />}
                  Capture and inspect
                </Button>
                <Button onClick={stop}>Stop camera</Button>
              </>
            )}
            <Button variant={cam === 'on' ? 'line' : 'primary'} size={cam === 'on' ? 'md' : 'lg'} onClick={() => file.current?.click()} disabled={busy} className={cam === 'on' ? '' : 'flex-1 sm:flex-none'}>
              Take or upload photo
            </Button>
            <input
              ref={file}
              type="file"
              accept="image/*"
              capture="environment"
              className="sr-only"
              tabIndex={-1}
              aria-hidden
              onChange={(e) => {
                const f = e.target.files?.[0]
                e.target.value = ''
                if (f) void send(f)
              }}
            />
          </div>
          {camError && <ErrorLine>{camError}</ErrorLine>}

          <div className="mt-1 p-3 border border-rule rounded-[3px] bg-panel flex flex-col gap-2.5">
            <Checkbox id="use-ex" checked={useEx} onChange={setUseEx} label="Show the inspector forged examples from a run" />
            {useEx && (
              exampleRuns.length ? (
                <label className="flex flex-wrap items-center gap-2 text-[12.5px] text-fg-3 pl-6">
                  Run
                  <select value={exId} onChange={(e) => setExRun(e.target.value)} className="num h-8 max-w-full bg-well border border-rule-2 rounded-[3px] px-2 text-[12px] text-fg">
                    {exampleRuns.map((r) => (
                      <option key={r.id} value={r.id}>
                        {r.id} ({r.accepted} accepted)
                      </option>
                    ))}
                  </select>
                </label>
              ) : (
                <p className="text-[12px] text-fg-3 pl-6">No completed run with accepted samples yet.</p>
              )
            )}
          </div>
        </section>

        <section className="min-w-0 flex flex-col gap-4" aria-label="Inspection result" aria-live="polite">
          {busy && (
            <div className="flex flex-col gap-3">
              <div className="flex items-center gap-2 text-signal text-[14px] font-semibold">
                <Spinner /> Inspecting
              </div>
              {preview && (
                <div className="relative bg-well brackets overflow-hidden rounded-[2px]">
                  <img src={preview} alt="Photo being inspected" className="block w-full h-auto opacity-70" />
                  <div className="absolute inset-0 overflow-hidden"><div className="scanline" /></div>
                </div>
              )}
            </div>
          )}
          {error && <ErrorLine>{error}</ErrorLine>}
          {!busy && result && v && (
            <>
              <div className={cx('border rounded-[3px] px-4 py-4', v.ring)}>
                <div className="flex flex-wrap items-end justify-between gap-x-6 gap-y-3">
                  <div>
                    <div className={cx('text-[44px] leading-none font-[850] tracking-[0.01em] [font-stretch:112%]', v.cls)}>{v.word}</div>
                    <p className="text-[13px] text-fg-2 mt-2 max-w-[44ch]">{v.note}</p>
                  </div>
                  <dl className="flex gap-6">
                    <div>
                      <dt className="text-[11.5px] text-fg-3">Type</dt>
                      <dd className="text-[16px] font-semibold mt-0.5">{result.defect ? titleCase(result.type) : '–'}</dd>
                    </div>
                    <div>
                      <dt className="text-[11.5px] text-fg-3">Confidence</dt>
                      <dd className="num text-[16px] mt-0.5">{pct(result.confidence)}</dd>
                      <div className="h-[3px] w-20 bg-rule mt-1 rounded-[1px] overflow-hidden">
                        <div className={cx('h-full', result.verdict === 'good' ? 'bg-pass' : result.verdict === 'defect' ? 'bg-miss' : 'bg-signal')} style={{ width: `${result.confidence * 100}%` }} />
                      </div>
                    </div>
                  </dl>
                </div>
              </div>
              <p className="text-[14px] leading-relaxed text-fg-2 max-w-[70ch]">{result.rationale}</p>
              <div className="relative bg-well brackets overflow-hidden rounded-[2px]">
                <img src={result.overlay_url ?? result.image_url} alt={result.overlay_url ? 'Photo with the SAM 3.1 mask outlined' : 'Inspected photo'} className="block w-full h-auto" />
                {result.overlay_url && <span className="absolute top-2 left-2 text-[11.5px] font-semibold px-1.5 py-0.5 rounded-[2px] bg-well/85 text-signal">SAM 3.1 mask</span>}
              </div>
              <div className="flex gap-5 text-[12px] text-fg-3">
                <span>
                  Time <span className="num text-fg-2">{dur(result.ms)}</span>
                </span>
                <span>
                  Cost <span className="num text-fg-2">{usd(result.cost_usd)}</span>
                </span>
                {result.box_px && (
                  <span>
                    Box <span className="num text-fg-2">{result.box_px.join(' ')}</span>
                  </span>
                )}
              </div>
            </>
          )}
          {!busy && !result && !error && (
            <div className="border border-dashed border-rule-2 rounded-[3px] p-6 text-[13px] text-fg-3">
              <p className="text-fg-2 font-semibold mb-1">No part inspected yet</p>
              Capture a frame or upload a photo. The verdict, the defect type, the rationale and the mask overlay appear here.
            </div>
          )}

          {history.length > 1 && (
            <div className="mt-2">
              <h2 className="text-[13px] font-bold mb-2">This session</h2>
              <ul className="grid grid-cols-4 sm:grid-cols-8 lg:grid-cols-4 xl:grid-cols-8 gap-2">
                {history.map((h) => (
                  <li key={h.id}>
                    <button type="button" onClick={() => setResult(h.result)} className="block w-full text-left">
                      <div className="relative aspect-square bg-well rounded-[2px] overflow-hidden">
                        <img src={h.thumb} alt="" className="absolute inset-0 size-full object-cover" />
                      </div>
                      <span className={cx('block text-[10.5px] font-bold mt-1', VERDICT[h.result.verdict].cls)}>{VERDICT[h.result.verdict].word}</span>
                    </button>
                  </li>
                ))}
              </ul>
            </div>
          )}
        </section>
      </div>
    </main>
  )
}
