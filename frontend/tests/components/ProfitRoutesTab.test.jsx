import { describe, expect, it } from 'vitest'
import { act, render, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { ProfitRoutesTab } from '../../src/components/ProfitRoutesTab'
import { deferred, installFakeApi } from './fakeApi'

const route = (name, extra = {}) => ({ transformation_id: name, name, section: 'deterministic', status: 'ready', safe_edge_chaos: 12, roi: 0.1, ...extra })
const payload = (routes, extra = {}) => ({ routes, sections: [{ key: 'deterministic' }], ...extra })

describe('ProfitRoutesTab honesty contracts', () => {
  it('shows WAIT instead of an empty table when no route qualifies', async () => {
    installFakeApi({ 'GET /profit-routes': { routes: [], sections: [] }, 'GET /profit-routes/executions': [] })
    render(<ProfitRoutesTab selectedLeague="Settlers" />)
    expect(await screen.findByText('WAIT — no actionable route')).toBeInTheDocument()
    expect(screen.queryByRole('table')).not.toBeInTheDocument()
  })

  it('asks for a league instead of fetching when none is saved', () => {
    const calls = installFakeApi({})
    render(<ProfitRoutesTab selectedLeague="" />)
    expect(screen.getByText('Select a league')).toBeInTheDocument()
    expect(calls.filter((c) => c.path === '/profit-routes')).toHaveLength(0)
  })

  it('surfaces a Chaos/Divine normalization blocker as WAIT', async () => {
    installFakeApi({
      'GET /profit-routes': payload([], { planning: { requested_amount: 5, requested_currency: 'Divine', budget_chaos: null, chaos_per_divine: null, normalization_blocker: 'No fresh observed Chaos/Divine rate' } }),
      'GET /profit-routes/executions': [],
    })
    render(<ProfitRoutesTab selectedLeague="Settlers" />)
    const panel = (await screen.findByText('Planning context')).closest('section')
    expect(panel).toHaveTextContent('WAIT')
    expect(panel).toHaveTextContent('No fresh observed Chaos/Divine rate')
    expect(panel).not.toHaveTextContent('READY')
  })

  it('renders missing route economics as — rather than zero', async () => {
    installFakeApi({ 'GET /profit-routes': payload([route('Blocked route', { status: 'blocked', safe_edge_chaos: null, roi: null })]), 'GET /profit-routes/executions': [] })
    render(<ProfitRoutesTab selectedLeague="Settlers" />)
    const row = (await screen.findByText('Blocked route')).closest('tr')
    const cells = row.querySelectorAll('td')
    expect(cells[2]).toHaveTextContent('—')
    expect(cells[2]).not.toHaveTextContent('0')
    expect(cells[3]).toHaveTextContent('—')
  })

  it('shows patch verification blockers', async () => {
    installFakeApi({ 'GET /profit-routes': payload([], { patch_status: 'unverified', patch_reasons: ['Registry not verified for patch 3.26'] }), 'GET /profit-routes/executions': [] })
    render(<ProfitRoutesTab selectedLeague="Settlers" />)
    expect(await screen.findByText('Patch verification blocked')).toBeInTheDocument()
    expect(screen.getByText('Registry not verified for patch 3.26')).toBeInTheDocument()
  })

  it('ignores a late response for the previous league', async () => {
    const first = deferred()
    const second = deferred()
    installFakeApi({
      'GET /profit-routes': (config) => (config.params.league === 'Old' ? first.promise : second.promise),
      'GET /profit-routes/executions': [],
    })
    const { rerender } = render(<ProfitRoutesTab selectedLeague="Old" />)
    rerender(<ProfitRoutesTab selectedLeague="New" />)
    await act(async () => second.resolve(payload([route('New league route')])))
    expect(await screen.findByText('New league route')).toBeInTheDocument()
    await act(async () => first.resolve(payload([route('Old league route')])))
    expect(screen.queryByText('Old league route')).not.toBeInTheDocument()
    expect(screen.getByText('New league route')).toBeInTheDocument()
  })

  it('does not present previous results as current while a new plan loads', async () => {
    const replan = deferred()
    let call = 0
    installFakeApi({
      'GET /profit-routes': () => (++call === 1 ? payload([route('Unfiltered route')]) : replan.promise),
      'GET /profit-routes/executions': [],
    })
    render(<ProfitRoutesTab selectedLeague="Settlers" />)
    await screen.findByText('Unfiltered route')
    await userEvent.type(screen.getByLabelText('Min ROI (%)'), '50')
    await userEvent.click(screen.getByRole('button', { name: 'PLAN ROUTES' }))
    expect(screen.getByText('Loading profit routes…')).toBeInTheDocument()
    expect(screen.queryByText('Unfiltered route')).not.toBeInTheDocument()
    await act(async () => replan.resolve({ routes: [], sections: [] }))
    await waitFor(() => expect(screen.getByText('WAIT — no actionable route')).toBeInTheDocument())
  })
})
