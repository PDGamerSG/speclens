import { ArrowLeft, LoaderCircle } from 'lucide-react'
import { cloneElement, useId, type ReactElement, type ReactNode } from 'react'
import { dateTime } from '../workspace/api'

export function Field({ label, children }: { label: string; children: ReactElement<{ id?: string }> }) { const id = useId(); return <div className="field-label"><label htmlFor={id}>{label}</label>{cloneElement(children, { id })}</div> }
export function Panel({ title, children, className = '' }: { title?: string; children: ReactNode; className?: string }) { return <section className={`pilot-panel ${className}`}>{title && <h2>{title}</h2>}{children}</section> }
export function Empty({ title, children, action, onAction }: { title: string; children: ReactNode; action?: string; onAction?: () => void }) { return <div className="pilot-empty"><h2>{title}</h2><p>{children}</p>{action && <button className="button secondary" onClick={onAction}>{action}</button>}</div> }
export function Status({ value }: { value: string }) { return <span className={`pilot-status pilot-status-${value}`}>{value.replaceAll('_', ' ')}</span> }
export function Submit({ busy, children, disabled = false }: { busy: boolean; children: ReactNode; disabled?: boolean }) { return <button className="button primary" type="submit" disabled={busy || disabled}>{busy && <LoaderCircle size={15} className="spin" />}{children}</button> }
export function Back({ children, onClick }: { children: ReactNode; onClick: () => void }) { return <button className="text-link" onClick={onClick}><ArrowLeft size={15} />{children}</button> }
export function Audit({ value, title = 'Record history' }: { value: unknown; title?: string }) { return <details className="pilot-audit"><summary>{title}</summary><pre>{JSON.stringify(value, null, 2)}</pre></details> }
export function Meta({ id, date, version }: { id: string; date: string; version: number }) { return <p className="pilot-meta">{dateTime(date)} · Version {version}<span>{id}</span></p> }
