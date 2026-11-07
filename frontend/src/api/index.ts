import { liveApi } from './client'
import { mockApi } from './mock'
import { staticApi } from './static'
import type { Api } from './types'

/** VITE_MOCK=1 swaps every endpoint and the SSE stream for the in-browser mock.
 *  `vite build --mode static` replays a recorded run from static files, for hosting without a backend. */
export const api: Api = import.meta.env.MODE === 'static' ? staticApi : import.meta.env.VITE_MOCK === '1' ? mockApi : liveApi

export * from './types'
