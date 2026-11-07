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
      <main className="crash-screen">
        <h1>This screen hit an error</h1>
        <p>{this.state.error.message}</p>
        <button type="button" className="button secondary" onClick={() => this.setState({ error: null })}>Try again</button>
      </main>
    )
  }
}
