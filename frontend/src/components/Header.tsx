import { api } from '../api'
import { isDemo, useStore } from '../state/store'
import { cx } from './ui'

export type Route = 'forge' | 'stress' | 'inspect' | 'results'

const TABS: { id: Route; label: string }[] = [
  { id: 'forge', label: 'Forge' },
  { id: 'stress', label: 'Stress test' },
  { id: 'inspect', label: 'Inspect' },
  { id: 'results', label: 'Results' },
]

function Mark() {
  return (
    <svg viewBox="0 0 32 32" className="size-7 shrink-0" aria-hidden>
      <path d="M5 11V5h6M21 5h6v6M27 21v6h-6M11 27H5v-6" fill="none" stroke="var(--color-fg)" strokeWidth="2" />
      <circle cx="18.5" cy="13.5" r="3.8" fill="var(--color-signal)" />
      <path d="M18.5 13.5L13 19" stroke="var(--color-signal)" strokeWidth="1.2" strokeOpacity="0.6" />
    </svg>
  )
}

export function Header({ route }: { route: Route }) {
  const { state } = useStore()
  const demo = isDemo(state)
  const live = state.health && !state.healthError
  return (
    <header className="sticky top-0 z-30 bg-page/95 backdrop-blur border-b border-rule">
      <div className="flex flex-wrap items-center gap-x-6 gap-y-0 px-4 lg:px-6 min-h-14">
        <a href="#/forge" className="flex items-center gap-2.5 py-2 min-w-0 mr-auto lg:mr-0">
          <Mark />
          <span className="min-w-0">
            <span className="block text-[18px] leading-none font-[800] tracking-[-0.01em] [font-stretch:118%]">SpecLens</span>
            <span className="block text-[11px] leading-none mt-1 text-fg-3 whitespace-nowrap">Muse Image × SAM 3.1 × Muse Spark</span>
          </span>
        </a>

        <div className="flex items-center gap-3 lg:order-3 lg:ml-auto">
          {demo && (
            <span className="inline-flex items-center h-6 px-2 rounded-[3px] bg-signal text-signal-ink text-[11px] font-[800] tracking-[0.06em] num" title="Recorded run replayed with its original timing; no live Meta calls.">
              DEMO REPLAY
            </span>
          )}
          {api.mode === 'mock' && <span className="inline-flex items-center h-6 px-2 rounded-[3px] border border-rule-2 text-fg-2 text-[11px] font-semibold">Mock data</span>}
          <span className="hidden sm:inline-flex items-center gap-1.5 text-[12px] text-fg-3" title={state.healthError ?? state.health?.models.join(', ')}>
            <span className={cx('size-1.5 rounded-full', live ? 'bg-pass' : state.healthError ? 'bg-miss' : 'bg-fg-3')} />
            {live ? `${state.health!.models.length} models online` : state.healthError ? 'Backend offline' : 'Connecting'}
          </span>
        </div>

        <nav className="w-full lg:w-auto lg:order-2 -mx-1 lg:mx-0" aria-label="Screens">
          <ul className="flex gap-1">
            {TABS.map((t) => (
              <li key={t.id}>
                <a
                  href={`#/${t.id}`}
                  aria-current={route === t.id ? 'page' : undefined}
                  className={cx(
                    'relative inline-flex items-center h-11 lg:h-14 px-2.5 text-[14px] font-semibold transition-colors',
                    route === t.id ? 'text-fg' : 'text-fg-3 hover:text-fg-2',
                  )}
                >
                  {t.label}
                  <span className={cx('absolute left-2.5 right-2.5 bottom-0 h-[2px]', route === t.id ? 'bg-signal' : 'bg-transparent')} />
                </a>
              </li>
            ))}
          </ul>
        </nav>
      </div>
    </header>
  )
}
