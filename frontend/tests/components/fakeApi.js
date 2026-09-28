import axios from 'axios'
import { api } from '../../src/lib/helpers'

// Route-keyed fake backend installed as the axios adapter, so the real
// session-token interceptor still runs. Handlers return data or a promise.
export function deferred() {
  let resolve, reject
  const promise = new Promise((res, rej) => { resolve = res; reject = rej })
  return { promise, resolve, reject }
}

export function installFakeApi(routes, { fallback = {} } = {}) {
  const calls = []
  const adapter = async (config) => {
    const method = (config.method || 'get').toUpperCase()
    const path = config.url.replace(/^\/api/, '')
    calls.push({ method, path, params: config.params, data: config.data })
    if (path === '/session') return respond(config, { token: 'test-token' })
    const handler = routes[`${method} ${path}`]
    if (!handler) return respond(config, fallback)
    const result = await (typeof handler === 'function' ? handler(config) : handler)
    if (result instanceof HttpError) {
      const error = new axios.AxiosError(result.detail, 'ERR_BAD_RESPONSE', config)
      error.response = { status: result.status, data: { detail: result.detail }, config, headers: {} }
      throw error
    }
    return respond(config, result)
  }
  api.defaults.adapter = adapter
  axios.defaults.adapter = adapter
  return calls
}

export class HttpError {
  constructor(status, detail) { this.status = status; this.detail = detail }
}

function respond(config, data) {
  return { data, status: 200, statusText: 'OK', headers: {}, config }
}
