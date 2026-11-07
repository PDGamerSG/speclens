import { ErrorBoundary } from './components/ErrorBoundary'
import Workspace from './workspace/Workspace'

export default function App() {
  return <ErrorBoundary><Workspace /></ErrorBoundary>
}
