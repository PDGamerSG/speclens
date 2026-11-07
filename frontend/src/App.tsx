import { useEffect, useState } from 'react'
import { CallLog } from './components/CallLog'
import { ErrorBoundary } from './components/ErrorBoundary'
import { Header, type Route } from './components/Header'
import { ForgeScreen } from './screens/Forge'
import { InspectScreen } from './screens/Inspect'
import { ResultsScreen } from './screens/Results'
import { StressScreen } from './screens/Stress'
import { StoreProvider } from './state/store'

const ROUTES: Route[] = ['forge', 'stress', 'inspect', 'results']

function readRoute(): Route {
  const r = window.location.hash.replace(/^#\/?/, '').split('/')[0] as Route
  return ROUTES.includes(r) ? r : 'forge'
}

function useHashRoute() {
  const [route, setRoute] = useState<Route>(readRoute)
  useEffect(() => {
    const on = () => {
      setRoute(readRoute())
      window.scrollTo({ top: 0 })
    }
    window.addEventListener('hashchange', on)
    return () => window.removeEventListener('hashchange', on)
  }, [])
  return route
}

export default function App() {
  const route = useHashRoute()
  return (
    <StoreProvider>
      <Header route={route} />
      <ErrorBoundary key={route}>
        {route === 'forge' && <ForgeScreen />}
        {route === 'stress' && <StressScreen />}
        {route === 'inspect' && <InspectScreen />}
        {route === 'results' && <ResultsScreen />}
      </ErrorBoundary>
      <CallLog />
    </StoreProvider>
  )
}
