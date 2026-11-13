import { CheckCircle2, FileCheck2, Plus } from 'lucide-react'
import { useState } from 'react'
import { pilotApi } from './api'
import type { Revision, SectionProps } from './types'
import { Empty, Field, Meta, Panel, Status, Submit } from './ui'
import { valueOf } from './utils'

function RevisionDetail({ revision, busy, admin, run }: { revision: Revision; busy: boolean; admin: boolean; run: SectionProps['run'] }) {
  const [confirmed, setConfirmed] = useState(false)
  return <article className="pilot-revision">
    <header className="pilot-row-head"><h3>{revision.label}</h3><Status value={revision.status} /></header>
    <p className="pilot-spec">{revision.spec_text}</p>
    <h4>Parsed defect classes</h4>
    <p className="pilot-help">Check these classes against the specification before approving. A replacement specification needs a new revision.</p>
    {revision.taxonomy?.classes?.length ? <ul className="pilot-taxonomy">{revision.taxonomy.classes.map(item => <li key={item.defect_type}><strong>{item.label}</strong>{item.clause && <span>Clause {item.clause}</span>}<p>{item.description || item.defect_type}{item.limit_mm != null && ` · Limit ${item.limit_mm} mm`}</p></li>)}</ul> : <p className="pilot-help">No classes were parsed. Check the specification before approval.</p>}
    <h4>Capture instructions</h4><p>{revision.capture_instructions || 'No additional instructions recorded.'}</p>
    {revision.status === 'draft' && admin && <div className="pilot-approval"><label className="pilot-check"><input type="checkbox" checked={confirmed} disabled={busy} onChange={event => setConfirmed(event.target.checked)} />I have checked the specification and parsed defect classes</label><button className="button primary" disabled={busy || !confirmed} onClick={() => void run('Approve revision', () => pilotApi.revise(revision.id, revision.version, 'approved'), 'Revision approved. Its specification and taxonomy are frozen.')}><FileCheck2 size={16} />Approve revision</button></div>}
    {revision.status === 'approved' && admin && <button className="button secondary compact" disabled={busy} onClick={() => void run('Retire revision', () => pilotApi.revise(revision.id, revision.version, 'retired'), 'Revision retired. New captures cannot use it.')}>Retire revision</button>}
    {revision.approver && <p className="pilot-help"><CheckCircle2 size={14} />Approved by {revision.approver.name}</p>}
    <Meta id={revision.id} date={revision.created_at} version={revision.version} />
  </article>
}

export function Products({ data, session, busy, run }: SectionProps) {
  const [productId, setProductId] = useState('')
  const [adding, setAdding] = useState(false)
  const product = data.products.find(item => item.id === productId) || data.products[0]
  const canEdit = session.role === 'admin' || session.role === 'engineer'
  const revisions = data.revisions.filter(item => item.product_id === product?.id)
  return <div className="pilot-products">
    <div className="pilot-product-strip">{data.products.map(item => <button key={item.id} className={'pilot-product-tab' + (product?.id === item.id ? ' selected' : '')} aria-pressed={product?.id === item.id} disabled={busy} onClick={() => { setProductId(item.id); setAdding(false) }}><span>{item.code}</span><strong>{item.name}</strong><small>{item.factory}</small></button>)}{canEdit && !!data.products.length && <button className="button secondary compact" disabled={busy} onClick={() => setAdding(!adding)}><Plus size={15} />New product</button>}</div>
    {canEdit && (!data.products.length || adding) && <Panel title="Add a product"><form className="pilot-form" onSubmit={async event => {
      event.preventDefault(); const form = event.currentTarget; const fields = new FormData(form)
      const ok = await run('Add product', async () => { const saved = await pilotApi.product({ code: valueOf(fields, 'code'), name: valueOf(fields, 'name'), factory: valueOf(fields, 'factory'), description: valueOf(fields, 'description') }); setProductId(saved.id) }, 'Product added. Create its first specification revision.')
      if (ok) { form.reset(); setAdding(false) }
    }}><fieldset disabled={busy}><div className="pilot-fields three"><Field label="Product code"><input name="code" required maxLength={64} placeholder="HZ-01" /></Field><Field label="Product name"><input name="name" required maxLength={100} placeholder="Whole hazelnut" /></Field><Field label="Factory"><input name="factory" required maxLength={100} placeholder="Bangalore Foods" /></Field></div><Field label="Product description"><textarea name="description" rows={2} maxLength={2000} /></Field><Submit busy={busy}>Add product</Submit></fieldset></form></Panel>}
    {!product && !canEdit && <Empty title="No products yet">An engineer or admin can add a product and its first specification.</Empty>}
    {product && <><header className="pilot-product-heading"><div><h2>{product.name}</h2><p>{product.factory} / {product.code}</p>{product.description && <p className="pilot-help">{product.description}</p>}</div><span>{revisions.length} revision{revisions.length === 1 ? '' : 's'}</span></header><div className="pilot-columns"><div className="pilot-stack">{revisions.length ? revisions.map(revision => <RevisionDetail key={revision.id} revision={revision} admin={session.role === 'admin'} busy={busy} run={run} />) : <Empty title="Write the first specification">Draft, check and approve a revision before creating a lot.</Empty>}</div>{canEdit && <Panel title="New specification revision" className="pilot-editor"><form className="pilot-form" key={product.id} onSubmit={async event => {
      event.preventDefault(); const form = event.currentTarget; const fields = new FormData(form)
      const ok = await run('Create draft revision', () => pilotApi.revision({ product_id: product.id, label: valueOf(fields, 'label'), spec_text: valueOf(fields, 'spec_text'), capture_instructions: valueOf(fields, 'capture_instructions') }), 'Draft revision saved. Check its parsed classes before approval.')
      if (ok) form.reset()
    }}><fieldset disabled={busy}><Field label="Revision label"><input name="label" required maxLength={64} placeholder="Rev A" /></Field><Field label="Specification text"><textarea name="spec_text" rows={7} required minLength={10} maxLength={12000} placeholder="Define acceptable appearance, defect classes and clause limits." /></Field><Field label="Capture instructions"><textarea name="capture_instructions" rows={3} maxLength={4000} placeholder="Lighting, camera angle and the part’s position." /></Field><p className="pilot-help">The draft is parsed locally. Approval freezes this revision for future captures.</p><Submit busy={busy}>Create draft revision</Submit></fieldset></form></Panel>}</div></>}
  </div>
}
