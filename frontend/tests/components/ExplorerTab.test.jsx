import { describe, expect, it } from 'vitest'
import { render, screen, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { ExplorerTab } from '../../src/components/ExplorerTab'
import { installFakeApi } from './fakeApi'

const categories = [{ id: 'Currency', name: 'Currency' }]
const overview = { categories: { Currency: [{ item_id: 'divine', item_name: 'Divine Orb', price_chaos: 180, volume: 50 }] } }

function setup(history) {
  installFakeApi({
    'GET /market/overview': overview,
    'GET /history': history,
    'GET /regime': { regime: 'STABLE', confidence: 0.5, signals: {} },
    'GET /stats': { mean: 180 },
  })
  render(<ExplorerTab categories={categories} selectedLeague="Settlers" historyHours={24} />)
}

async function pickItem(name) {
  const select = screen.getByRole('combobox', { name: 'Item' })
  await screen.findByRole('option', { name: 'Divine Orb' })
  await userEvent.selectOptions(select, name)
}

describe('ExplorerTab honesty contracts', () => {
  it('shows an unknown price change as — instead of +0.0%', async () => {
    setup([{ timestamp: '2026-09-01T00:00:00Z', price: 180 }])
    await pickItem('Divine Orb')
    const card = (await screen.findByText('Current Price')).closest('section')
    const change = within(card).getByText('Change').nextSibling
    expect(change).toHaveTextContent('—')
    expect(card).not.toHaveTextContent('0.0%')
  })

  it('computes change only from observed first and last prices', async () => {
    setup([{ timestamp: '2026-09-01T00:00:00Z', price: 100 }, { timestamp: '2026-09-02T00:00:00Z', price: 110 }])
    await pickItem('Divine Orb')
    const card = (await screen.findByText('Current Price')).closest('section')
    expect(within(card).getByText('Change').nextSibling).toHaveTextContent('+10.0%')
  })

  it('removes item detail when the selection is cleared', async () => {
    setup([{ timestamp: '2026-09-01T00:00:00Z', price: 180 }])
    await pickItem('Divine Orb')
    await screen.findByText('Current Price')
    await userEvent.selectOptions(screen.getByRole('combobox', { name: 'Item' }), 'Select an item')
    expect(screen.queryByText('Current Price')).not.toBeInTheDocument()
    expect(screen.queryByText('Loading item data...')).not.toBeInTheDocument()
  })
})
