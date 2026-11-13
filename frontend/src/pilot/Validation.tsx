import { Download, Upload } from 'lucide-react'
import { useState } from 'react'
import { dateTime } from '../workspace/api'
import { downloadJson } from '../workspace/download'
import { pilotApi } from './api'
import type { EvaluationArm, Prediction, Rate, SectionProps, ValidationCase, ValidationRun } from './types'
import { Audit, Empty, Field, Panel, Submit } from './ui'
import { valueOf } from './utils'

const percent = (value: number | null) => value === null ? 'Not estimable' : `${(value * 100).toFixed(1)}%`
const rateText = (value: Rate) => `${value.count} / ${value.denominator} (${value.rate === null ? 'no denominator' : percent(value.rate)})`
const OUTPUTS: Prediction[] = ['good', 'defect', 'uncertain', 'error']
const outputName = (value: string) => ({ good: 'Accept', defect: 'Reject', uncertain: 'Review', error: 'Error' })[value] || value

function Matrix({ arm, title }: { arm: EvaluationArm; title: string }) {
  return <div className="pilot-validation-matrix"><h3>{title}</h3><div className="pilot-table-wrap"><table><caption>First attempt for each physical part</caption><thead><tr><th>Known truth</th>{OUTPUTS.map(output => <th key={output}>{outputName(output)}</th>)}</tr></thead><tbody>{(['good', 'defect'] as const).map(truth => <tr key={truth}><th>{truth === 'good' ? 'Good part' : 'Defective part'}</th>{OUTPUTS.map(output => <td key={output}>{arm.matrix[truth][output]}</td>)}</tr>)}</tbody></table></div></div>
}

function ValidationResult({ run }: { run: ValidationRun }) {
  const { results } = run
  const metrics: { label: string; key: keyof Omit<EvaluationArm, 'matrix'> }[] = [
    { label: 'Escaped defects', key: 'escaped_defects' }, { label: 'False rejects', key: 'false_rejects' },
    { label: 'Review workload', key: 'review' }, { label: 'Technical errors', key: 'errors' }, { label: 'Decision coverage', key: 'decision_coverage' },
  ]
  return <article className="pilot-validation-result"><header className="pilot-row-head"><div><h2>{run.name}</h2><p className="pilot-help">{dateTime(run.created_at)} / Immutable evaluation</p></div><button className="button secondary compact" onClick={() => downloadJson(`speclens-validation-${run.id}.json`, run)}><Download size={15} />Export validation manifest</button></header><p className="pilot-callout">Imported results are unverified, precomputed model outputs. This evaluation does not run an inspection or establish factory accuracy.</p><div className="pilot-totals"><div><strong>{results.counts.physical_parts}</strong><span>Physical parts</span></div><div><strong>{results.counts.samples}</strong><span>Imported samples</span></div><div><strong>{results.counts.repeated_views}</strong><span>Repeated views</span></div><div><strong>{results.counts.clusters}</strong><span>Connected clusters</span></div></div><p className="pilot-help">{results.counts.truth.defect} defective parts, {results.counts.truth.good} good parts / {results.counts.lots} lots / {results.counts.sessions} capture sessions. Aggregation uses the first input occurrence for each physical part.</p><div className="pilot-table-wrap"><table><caption>Counts / explicit denominator (rate)</caption><thead><tr><th>Measure</th><th>Baseline</th><th>With memory</th></tr></thead><tbody>{metrics.map(metric => <tr key={metric.key}><th>{metric.label}</th><td>{rateText(results.baseline[metric.key])}</td><td>{rateText(results.with_memory[metric.key])}</td></tr>)}</tbody></table></div><p className="pilot-help">Review and error results remain unresolved. They are not counted as successful defect detection.</p><div className="pilot-matrices"><Matrix title="Baseline outputs" arm={results.baseline} /><Matrix title="With-memory outputs" arm={results.with_memory} /></div><div className="pilot-paired"><h3>Paired changes</h3><p>{results.paired.resolved_improvements} resolved improvements / {results.paired.resolved_regressions} resolved regressions / {results.paired.unchanged} unchanged.</p><details><summary>All paired transitions</summary><div className="pilot-table-wrap"><table><caption>Baseline rows; with-memory columns</caption><thead><tr><th>Baseline</th>{OUTPUTS.map(output => <th key={output}>{outputName(output)}</th>)}</tr></thead><tbody>{OUTPUTS.map(baseline => <tr key={baseline}><th>{outputName(baseline)}</th>{OUTPUTS.map(memory => <td key={memory}>{results.paired.transitions[baseline]?.[memory] || 0}</td>)}</tr>)}</tbody></table></div></details></div><section className="pilot-uncertainty"><h3>Uncertainty and independence</h3><p className="pilot-help">{Math.round(results.uncertainty.confidence * 100)}% paired cluster intervals. Parts connected through a lot or capture session are grouped. Rate changes are with memory minus baseline.</p><div className="pilot-table-wrap"><table><thead><tr><th>Rate change</th><th>Estimate</th><th>Lower</th><th>Upper</th></tr></thead><tbody>{Object.entries(results.uncertainty.delta_rates).map(([name, interval]) => <tr key={name}><th>{({ escaped_defects: 'Escaped defects', false_rejects: 'False rejects', review: 'Review workload', errors: 'Technical errors' })[name] || name}</th><td>{percent(interval.estimate)}</td><td>{percent(interval.lower)}</td><td>{percent(interval.upper)}</td></tr>)}</tbody></table></div><ul>{results.limitations.map((limitation, index) => <li key={index}>{limitation}</li>)}</ul></section><Audit value={run.manifest} title="Immutable input manifest and provenance" /></article>
}

export function Validation(props: SectionProps & { runs: ValidationRun[] }) {
  const [json, setJson] = useState('')
  const [fileError, setFileError] = useState('')
  const canImport = props.session.role === 'admin' || props.session.role === 'engineer'
  const [selected, setSelected] = useState('')
  const current = props.runs.find(run => run.id === selected) || props.runs[0]
  return <div className="pilot-stack">{canImport && <Panel title="Evaluate matched results"><p className="pilot-help">Import a JSON array, or an object containing cases and optional configuration. Each case needs sample_id, physical_part_id, lot_id, session_id, truth, baseline and with_memory. Truth is good or defect; predictions are good, defect, uncertain or error. Input order defines the first attempt. Maximum 2,000 samples.</p><form className="pilot-form" onSubmit={event => {
    event.preventDefault(); const fields = new FormData(event.currentTarget)
    void props.run('Evaluate imported results', async () => {
      let parsed: unknown
      try { parsed = JSON.parse(json) } catch { throw new Error('Matched results must be valid JSON. Check quotes, commas and brackets.') }
      const object = parsed && typeof parsed === 'object' && !Array.isArray(parsed) ? parsed as { cases?: unknown; configuration?: unknown } : null
      const cases = Array.isArray(parsed) ? parsed : object?.cases
      if (!Array.isArray(cases) || !cases.length) throw new Error('Include at least one matched result in a JSON array or a cases array.')
      if (cases.length > 2000) throw new Error('Import at most 2,000 matched results per validation run.')
      const configuration = object?.configuration
      if (configuration !== undefined && (!configuration || typeof configuration !== 'object' || Array.isArray(configuration))) throw new Error('The optional configuration field must be a JSON object.')
      const result = await pilotApi.evaluate({ name: valueOf(fields, 'name'), cases: cases as ValidationCase[], ...(configuration ? { configuration: configuration as Record<string, unknown> } : {}) })
      setSelected(result.id)
    }, 'Imported results evaluated. The input manifest is immutable.')
  }}><fieldset disabled={props.busy}><Field label="Validation name"><input name="name" required maxLength={200} placeholder="Matched intake results" /></Field><Field label="Matched results JSON"><textarea value={json} onChange={event => setJson(event.target.value)} required rows={7} spellCheck={false} placeholder={'{"cases":[{"sample_id":"…","physical_part_id":"…","lot_id":"…","session_id":"…","truth":"defect","baseline":"good","with_memory":"defect"}]}'} /></Field><div className="pilot-actions"><label className="button secondary"><Upload size={15} />Load JSON file<input className="sr-only" type="file" accept="application/json,.json" aria-label="Load validation JSON file" onChange={async event => { const file = event.target.files?.[0]; event.target.value = ''; if (!file) return; if (file.size > 4 * 1024 * 1024) { setFileError('Choose a JSON file smaller than 4 MB.'); return } try { setJson(await file.text()); setFileError('') } catch { setFileError('This file could not be read. Try another JSON file.') } }} /></label><Submit busy={props.busy} disabled={!json.trim()}>Evaluate imported results</Submit></div>{fileError && <p role="alert">{fileError}</p>}<p className="pilot-help">Importing precomputed results makes no model calls. Provide configuration and provenance for your own traceability; they are not independently verified.</p></fieldset></form></Panel>}{props.runs.length > 1 && <Field label="Validation run"><select value={current?.id || ''} onChange={event => setSelected(event.target.value)}>{props.runs.map(run => <option key={run.id} value={run.id}>{run.name} / {dateTime(run.created_at)}</option>)}</select></Field>}{current ? <ValidationResult run={current} /> : <Empty title="Measure the unresolved work too">A matched import compares the same physical parts across baseline and memory outputs, with explicit errors, Review workload and cluster limitations.</Empty>}</div>
}
