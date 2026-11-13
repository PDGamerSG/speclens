import { ArrowDownToLine, FolderUp, LoaderCircle, Play } from 'lucide-react'
import { useEffect, useRef, useState } from 'react'
import { decision, workspaceApi as api } from './api'
import { photoError } from './photo'
import type { Batch, BatchJob, Inspection, ScopeSettings } from './types'

const MAX_FILES = 20

// Review first, then the least confident decisions, so the engineer starts where the model is unsure.
function reviewOrder(a: BatchJob, b: BatchJob) {
  const rank = (j: BatchJob) => j.status === 'failed' ? 0 : !j.result ? 3 : j.result.verdict === 'uncertain' ? 1 : 2
  return rank(a) - rank(b) || (a.result?.confidence ?? 1) - (b.result?.confidence ?? 1)
}

function csv(jobs: BatchJob[]) {
  const cell = (value: unknown) => `"${String(value ?? '').replaceAll('"', '""')}"`
  const rows = jobs.map(j => [j.filename, j.status, j.result ? decision(j.result.verdict) : '', j.result?.type, j.result?.confidence,
    j.result?.rationale || j.error?.detail, j.result?.id].map(cell).join(','))
  return ['part,status,decision,class,confidence,reason,inspection_id', ...rows].join('\n')
}

export function BatchSection({ scope, memory, busy, onOpen, onFinished }: {
  scope: ScopeSettings; memory: boolean; busy: boolean;
  onOpen: (item: Inspection) => void; onFinished: () => void;
}) {
  const [files, setFiles] = useState<File[]>([])
  const [batch, setBatch] = useState<Batch | null>(null)
  const [sent, setSent] = useState(0)
  const [sending, setSending] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const picker = useRef<HTMLInputElement>(null)
  const finished = useRef(onFinished)
  useEffect(() => { finished.current = onFinished }, [onFinished])

  useEffect(() => {
    if (!batch || batch.finished) return
    const timer = setTimeout(() => {
      api.batch(batch.batch_id).then(next => {
        setBatch(next)
        if (next.finished) finished.current()
      }).catch(() => { /* The next poll retries. */ })
    }, 1500)
    return () => clearTimeout(timer)
  }, [batch])

  const choose = (list: FileList | null) => {
    const chosen = Array.from(list || [])
    const bad = chosen.map(f => [f, photoError(f)] as const).filter(([, issue]) => issue)
    const good = chosen.filter(f => !photoError(f)).slice(0, MAX_FILES)
    setFiles(good); setBatch(null); setSent(0)
    setError(bad.length ? `${bad.length} file${bad.length === 1 ? ' was' : 's were'} skipped: ${bad[0][1]}`
      : chosen.length > MAX_FILES ? `Only the first ${MAX_FILES} photos are used in one batch.` : null)
  }

  const start = async () => {
    const id = 'batch-' + Array.from(crypto.getRandomValues(new Uint8Array(8)), b => b.toString(16).padStart(2, '0')).join('')
    setSending(true); setError(null); setSent(0)
    try {
      for (const [index, file] of files.entries()) {
        await api.queueInspection(file, scope, memory, id)
        setSent(index + 1)
        if (index === 0) setBatch(await api.batch(id))
      }
      setBatch(await api.batch(id))
    } catch (e) {
      setError(e instanceof Error ? e.message : 'The batch could not be started.')
    } finally {
      setSending(false)
    }
  }

  const jobs = batch ? [...batch.jobs].sort(reviewOrder) : []
  const done = batch ? batch.counts.done + batch.counts.failed : 0
  return <section id="batch" className="page-section" aria-labelledby="batch-title">
    <header className="section-head">
      <div><h2 id="batch-title">Batch inspection</h2><p>Queue up to {MAX_FILES} photos at once. Results arrive as each one finishes, with Review and low-confidence decisions first.</p></div>
      <div className="section-actions">
        <button className="button secondary" onClick={() => picker.current?.click()} disabled={busy || sending}><FolderUp size={15} />Choose photos</button>
        <button className="button primary" onClick={() => void start()} disabled={busy || sending || !files.length || (!!batch && !batch.finished)}>
          {sending ? <LoaderCircle size={15} className="spin" /> : <Play size={15} />}{sending ? `Uploading ${sent} of ${files.length}` : `Inspect ${files.length || ''} photo${files.length === 1 ? '' : 's'}`}
        </button>
        <input ref={picker} type="file" multiple accept="image/jpeg,image/png,image/webp" className="sr-only" tabIndex={-1} aria-label="Batch photos" onChange={e => { choose(e.target.files); e.target.value = '' }} />
      </div>
    </header>
    {error && <p className="spec-error" role="alert">{error}</p>}
    {!batch ? <p className="dash-note">{files.length ? `${files.length} photo${files.length === 1 ? '' : 's'} ready. Memory is ${memory ? 'on' : 'off'}, as on the inspection desk.` : 'No batch yet. Choose photos to start one.'}</p> : <>
      <div className="batch-progress" role="status">
        <progress max={batch.jobs.length} value={done} aria-label="Batch progress" />
        <span>{done} of {batch.jobs.length} finished{batch.counts.failed ? `, ${batch.counts.failed} failed` : ''}</span>
        <button className="button secondary compact" disabled={!batch.finished} onClick={() => {
          const link = document.createElement('a')
          link.href = URL.createObjectURL(new Blob([csv(jobs)], { type: 'text/csv' }))
          link.download = `speclens-${batch.batch_id}.csv`
          link.click()
          URL.revokeObjectURL(link.href)
        }}><ArrowDownToLine size={14} />Export CSV</button>
      </div>
      <div className="table-scroll">
        <table>
          <thead><tr><th>Part</th><th>Status</th><th>Decision</th><th>Confidence</th><th><span className="sr-only">Open</span></th></tr></thead>
          <tbody>{jobs.map(job => <tr key={job.id}>
            <td>{job.filename}</td>
            <td>{job.status === 'failed' ? <span className="state-warn">{job.error?.detail || 'Failed'}</span> : job.status === 'done' ? 'Done' : job.status === 'running' ? 'Inspecting' : 'Queued'}</td>
            <td>{job.result ? <span className={'verdict-text ' + job.result.verdict}>{decision(job.result.verdict)}{job.result.verdict === 'defect' ? ` · ${job.result.type}` : ''}</span> : '–'}</td>
            <td>{job.result ? `${Math.round(job.result.confidence * 100)}%` : '–'}</td>
            <td>{job.result && <button className="text-link" onClick={() => onOpen(job.result!)}>Open</button>}</td>
          </tr>)}</tbody>
        </table>
      </div>
    </>}
  </section>
}
