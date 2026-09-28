import { describe, expect, it, vi } from 'vitest'
import { act, render, screen, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import App from '../../src/App'
import { deferred, installFakeApi } from './fakeApi'

// The 3D lens needs WebGL, which jsdom lacks; it carries no market data.
vi.mock('../../src/components/OracleLens', () => ({ OracleLens: () => null }))

const leagues = [{ id: 'Old', name: 'Old League' }, { id: 'New', name: 'New League' }]
const base = (league, extra = {}) => ({
  'GET /leagues': leagues,
  'GET /config': { league, migration_required: false },
  'GET /categories': [{ id: 'Currency', name: 'Currency' }],
  'GET /coverage': [],
  'GET /snapshot/status': { total_rows: 0, last_snapshot_per_league: {} },
  'GET /cx/status': { backfill_status: 'idle' },
  'GET /market/history/status': { status: 'running' },
  'GET /journal/recommendations': [],
  'GET /update/status': {},
  'PUT /config': (config) => ({ league: JSON.parse(config.data).league }),
  ...extra,
})

async function switchLeague(name) {
  await userEvent.click(screen.getByRole('button', { name: 'CHANGE' }))
  await userEvent.selectOptions(screen.getByRole('combobox', { name: 'Configured league' }), name)
  await userEvent.click(screen.getByRole('button', { name: 'SAVE LEAGUE' }))
}

async function runPlanInOldLeague() {
  await screen.findByRole('heading', { name: /Active league Old/ })
  await userEvent.click(screen.getByRole('button', { name: 'RUN CAPITAL PLAN' }))
}

const marketState = () => screen.getByText('MARKET STATE').closest('.market-state')

describe('App shared-league contracts', () => {
  it('first run requires a live league and shows no readiness or results', async () => {
    const calls = installFakeApi(base(''))
    render(<App />)
    expect(await screen.findByRole('heading', { name: 'First-run league' })).toBeInTheDocument()
    expect(screen.getByRole('button', { name: 'SAVE LEAGUE' })).toBeDisabled()
    expect(screen.queryByText('Data readiness')).not.toBeInTheDocument()
    expect(screen.getByRole('button', { name: 'RUN CAPITAL PLAN' })).toBeDisabled()
    expect(calls.some((c) => c.path === '/coverage')).toBe(false)
  })

  it('reports zero stored history as waiting, not ready', async () => {
    installFakeApi(base('Old'))
    render(<App />)
    const panel = (await screen.findByRole('heading', { name: 'Data readiness' })).closest('section')
    expect(await within(panel).findByText('SIGNALS WAITING')).toBeInTheDocument()
    expect(panel).not.toHaveTextContent('SIGNALS READY')
  })

  it('clears a capital plan when the shared league changes', async () => {
    installFakeApi(base('Old', { 'POST /capital/plan': { recommendation: 'WAIT', mode: 'PAPER', positions: [], bankroll: {} } }))
    render(<App />)
    await runPlanInOldLeague()
    expect(await within(marketState()).findByText('QUIET')).toBeInTheDocument()
    await switchLeague('New League')
    expect(await screen.findByRole('heading', { name: /Active league New/ })).toBeInTheDocument()
    expect(within(marketState()).getByText('UNASSESSED')).toBeInTheDocument()
  })

  it('drops a capital plan that resolves after the league changed', async () => {
    const late = deferred()
    installFakeApi(base('Old', { 'POST /capital/plan': () => late.promise }))
    render(<App />)
    await runPlanInOldLeague()
    await switchLeague('New League')
    await screen.findByRole('heading', { name: /Active league New/ })
    await act(async () => late.resolve({ recommendation: 'DEPLOY', mode: 'PAPER', positions: [{}], bankroll: {} }))
    expect(within(marketState()).getByText('UNASSESSED')).toBeInTheDocument()
    expect(screen.queryByText('DEPLOY')).not.toBeInTheDocument()
  })
})
