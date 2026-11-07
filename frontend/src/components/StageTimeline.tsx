import type { StageName } from '../api/types'
import { PIPELINE, stageStatus, type StageState } from '../state/store'
import { cx } from './ui'

const PER_SAMPLE: StageName[] = ['forge', 'composite', 'label', 'critic', 'validate']

export function StageTimeline({ stages, total, stress }: { stages: Partial<Record<StageName, StageState>>; total: number | null; stress?: { done: number; expected: number } }) {
  return (
    <ol className="grid grid-cols-4 md:grid-cols-8 gap-x-[3px] gap-y-3" aria-label="Pipeline stages">
      {PIPELINE.map((p, i) => {
        const st = stages[p.stage]
        const status = stageStatus(st)
        const n = st ? st.done.filter((k) => k !== '_run').length : 0
        const activeN = st ? st.active.filter((k) => k !== '_run').length : 0
        let count: string | null = null
        if (PER_SAMPLE.includes(p.stage) && (n || activeN)) count = total ? `${n}/${total}` : `${n}`
        else if (p.stage === 'stress' && stress && (status !== 'idle' || stress.done)) count = `${stress.done}/${stress.expected || '–'}`
        else if (status === 'done' && st?.detail) count = st.detail
        return (
          <li key={p.stage} className="min-w-0" aria-current={status === 'active' ? 'step' : undefined}>
            <div
              className={cx(
                'h-[3px] rounded-[1px] mb-2 transition-colors',
                status === 'active' && 'bg-signal pulse-dot',
                status === 'done' && 'bg-fg-2',
                status === 'idle' && 'bg-rule',
              )}
            />
            <div className="flex items-baseline gap-1.5 min-w-0">
              <span className="num text-[10px] text-fg-3">{i + 1}</span>
              <span className={cx('text-[13px] font-semibold truncate', status === 'idle' ? 'text-fg-3' : status === 'active' ? 'text-signal' : 'text-fg')}>{p.label}</span>
            </div>
            <div className="text-[11px] text-fg-3 truncate pl-[15px]">{p.by}</div>
            <div className={cx('num text-[11px] truncate pl-[15px] h-4', status === 'active' ? 'text-signal' : 'text-fg-2')} title={count ?? undefined}>
              {count ?? ''}
            </div>
          </li>
        )
      })}
    </ol>
  )
}
