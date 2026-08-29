import test from 'node:test'
import assert from 'node:assert/strict'
import axios from 'axios'
import { api, formatUpdateBadge, fmtPct, historyWindowLabel, isDraftLeagueLive, leagueStatusTone } from '../src/lib/helpers.js'

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

test('update badge labels a stable version without duplicating the v prefix', () => {
  assert.equal(formatUpdateBadge('0.5.0'), 'UPDATE AVAILABLE · v0.5.0')
  assert.equal(formatUpdateBadge('v0.6.0'), 'UPDATE AVAILABLE · v0.6.0')
  assert.equal(formatUpdateBadge(''), 'UPDATE AVAILABLE')
})

test('fmtPct uses a single sign for positive, negative, and zero', () => {
  assert.equal(fmtPct(5.2), '+5.2%')
  assert.equal(fmtPct(-5.2), '-5.2%')
  assert.equal(fmtPct(0), '0.0%')
  assert.equal(fmtPct(null), '—')
})

test('history window labels map 168 hours to 7d', () => {
  assert.equal(historyWindowLabel(24), '24h')
  assert.equal(historyWindowLabel(72), '72h')
  assert.equal(historyWindowLabel(168), '7d')
})

test('SAVE LEAGUE enablement follows the draft, not the saved league', () => {
  const leagues = [{ id: 'Standard' }, { id: 'Allflame' }]
  assert.equal(isDraftLeagueLive(leagues, ''), false)
  assert.equal(isDraftLeagueLive(leagues, 'Standard'), true)
  assert.equal(isDraftLeagueLive(leagues, 'Expired'), false)
})

test('league status tone is warning until a live league is saved', () => {
  assert.equal(leagueStatusTone({ selectedLeague: '' }), 'warning')
  assert.equal(leagueStatusTone({ selectedLeague: 'Standard', migrationRequired: true }), 'warning')
  assert.equal(leagueStatusTone({ selectedLeague: 'Standard', bootError: true }), 'negative')
  assert.equal(leagueStatusTone({ selectedLeague: 'Standard' }), 'positive')
})
