import { useState } from 'react'
import { dateTime } from '../workspace/api'
import type { SectionProps } from './types'
import { Audit, Empty, Field } from './ui'

export function Activity(props: SectionProps) {
  const [query, setQuery] = useState('')
  const items = props.data.activity.filter(event => `${event.action} ${event.actor?.name || ''} ${event.target_id} ${JSON.stringify(event.details || {})}`.toLowerCase().includes(query.toLowerCase().trim()))
  return <div className="pilot-stack"><div className="pilot-toolbar"><Field label="Search activity"><input type="search" value={query} placeholder="Action, member or record" onChange={event => setQuery(event.target.value)} /></Field><span>{items.length} of {props.data.activity.length} lifecycle events</span></div>{items.length ? <ol className="pilot-activity">{items.map(event => <li className="pilot-activity-item" key={event.id}><time dateTime={event.created_at}>{dateTime(event.created_at)}</time><div><h2>{event.action.replaceAll('_', ' ').replaceAll('.', ' / ')}</h2><p>{event.actor?.name || 'System'}{event.actor?.role && ` / ${event.actor.role}`}</p><p className="pilot-meta">{event.target_id}</p>{event.details && Object.keys(event.details).length > 0 && <Audit value={event.details} title="Change details" />}</div></li>)}</ol> : <Empty title={props.data.activity.length ? 'No activity matches this search' : 'The team’s work leaves a trail'}>{props.data.activity.length ? 'Search for another action, member or record.' : 'Product approvals, capture, dispositions and other lifecycle changes appear here as your team works.'}</Empty>}<p className="pilot-help">Attributable lifecycle history for this workspace. This is not a tamper-proof security audit.</p></div>
}
