import test from 'node:test'
import assert from 'node:assert/strict'
import axios from 'axios'
import { api } from '../src/lib/helpers.js'

 test('mutations receive the local session header while reads do not', async () => {
  const requests = []
  const adapter = async (config) => {
    requests.push(config)
    return {
      data: config.url.endsWith('/session') ? { token: 'test-session-token' } : { ok: true },
      status: 200,
      statusText: 'OK',
      headers: {},
      config,
    }
  }
  axios.defaults.adapter = adapter
  api.defaults.adapter = adapter
  await api.get('/read-only')
  await api.post('/mutation', { value: 1 })
  assert.equal(requests[0].headers['X-DeusCFO-Token'], undefined)
  assert.equal(requests.at(-1).headers['X-DeusCFO-Token'], 'test-session-token')
})
