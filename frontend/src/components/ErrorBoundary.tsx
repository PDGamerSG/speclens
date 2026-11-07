import { Component, type ReactNode } from 'react'

/** Keeps one screen's crash from blanking the whole app during a demo. */
export class ErrorBoundary extends Component<{ children: ReactNode }, { error: Error | null }> {
  state: { error: Error | null } = { error: null }
  static getDerivedStateFromError(error: Error) {
    return { error }
  }
  render() {
    if (!this.state.error) return this.props.children
    return (
      <main className="px-4 lg:px-6 py-10 max-w-2xl">
        <h1 className="text-[20px] font-bold">This screen hit an error</h1>
        <p className="num text-[12.5px] text-miss mt-2 break-words">{this.state.error.message}</p>
        <button type="button" className="mt-4 h-9 px-3.5 rounded-[3px] border border-rule-2 text-[13px] font-semibold hover:bg-raised" onClick={() => this.setState({ error: null })}>
          Try again
        </button>
      </main>
    )
  }
}
