import axios from 'axios'

export const API_BASE = '/api'
export const api = axios.create({ baseURL: API_BASE })

let sessionToken = ''
let sessionRequest = null

export const getSessionToken = async () => {
  if (sessionToken) return sessionToken
  sessionRequest ||= axios.get(`${API_BASE}/session`).then(({ data }) => {
    sessionToken = data?.token || ''
    if (!sessionToken) throw new Error('Local session token was not returned')
    return sessionToken
  }).catch((error) => {
    sessionRequest = null
    throw error
  })
  return sessionRequest
}

api.interceptors.request.use(async (config) => {
  const method = (config.method || 'get').toUpperCase()
  if (!['GET', 'HEAD', 'OPTIONS'].includes(method)) {
    const token = await getSessionToken()
    config.headers = config.headers || {}
    config.headers['X-DeusCFO-Token'] = token
  }
  return config
})

// Opt-in README walkthrough only. Never default: live collection must still fail closed.
export const SHOWCASE_NON_OBSERVED = typeof window !== 'undefined' && new URLSearchParams(window.location.search).has('showcase')

function showcaseCapitalPlan(requestData) {
  let body = {}
  try { body = typeof requestData === 'string' ? JSON.parse(requestData) : (requestData || {}) } catch { body = {} }
  const bankroll = body.bankroll || {}
  const net = Number(bankroll.total_net_worth) || 25
  const liquid = Number(bankroll.liquid_currency) || 20
  const invested = Number(bankroll.currently_invested) || 0
  const reserved = Number(bankroll.reserved_capital) || 3
  const deployed = 4.8
  const reserve = Math.max(reserved, +(net * 0.2).toFixed(2))
  const unallocated = Math.max(0, +(liquid - reserved - deployed).toFixed(2))
  return {
    mode: 'PAPER',
    requested_mode: body.mode || 'PAPER',
    mode_downgraded: false,
    recommendation: 'DEPLOY',
    reason: 'SHOWCASE / NON-OBSERVED: illustrative PAPER allocation so the portfolio path can be demonstrated. This is not live market evidence.',
    objective: 'expected_profit',
    objective_components: { expected_profit: 0.62, drawdown: 0.11, liquidity: 0.08 },
    opportunity_tiers: { A: 1, B: 1, rejected: 0 },
    rejected: {},
    capital_currency: 'Divine',
    chaos_per_divine: 868.2,
    recommendation_id: null,
    bankroll: { total_net_worth: net, liquid_currency: liquid, currently_invested: invested, reserved_capital: reserved, currency: 'Divine' },
    deployed,
    reserve,
    unallocated,
    simulation: {
      seed: 0, trials: Number(body.simulations) || 2000,
      expected_profit: 0.62, median_profit: 0.48, probability_profitable: 0.71,
      p10_profit: -0.18, p25_profit: 0.12, p75_profit: 0.91, p90_profit: 1.35,
      median_completion_hours: 8, completion_interval: [4, 14], capital_locked: deployed,
    },
    positions: [{
      opportunity_id: 'showcase-the-doctor',
      item: 'The Doctor',
      entry_item: 'The Doctor',
      action: 'BUY',
      category: 'DivinationCard',
      correlation_group: 'divination-hh',
      tier: 'A',
      capital: 4.8,
      capital_currency: 'Divine',
      expected_profit: 0.62,
      expected_return: 0.129,
      probability_profitable: 0.71,
      expected_duration: 8,
      time_exit_hours: 8,
      duration_interval: [4, 14],
      downside_estimate: -0.9,
      target_entry_chaos: 250,
      maximum_entry_chaos: 260,
      estimated_quantity: 16,
      target_exit_chaos: [280, 295],
      historical_sample_size: 42,
      reason: 'Non-observed showcase card-set. Production still requires patch-verified Doctor → Headhunter evidence.',
      invalidation_conditions: ['Exit if buy depth dries up', 'Time-exit at 14h'],
    }],
    watchlist: [{
      opportunity_id: 'showcase-watch-sacred',
      item: 'Sacred Orb',
      category: 'Currency',
      state: 'WATCHING',
      trigger: 'Entry ≤ 95c',
      reason: 'Non-observed watch example.',
      suggested_capital_range: [1.2, 2.4],
      trigger_probability: 0.34,
      capital_currency: 'Divine',
    }],
    paper_ideas: [{
      item_id: 'showcase-exalted',
      item_name: 'Exalted Orb',
      action: 'PAPER BUY WATCH',
      current_price_chaos: 18.4,
      reference_price_chaos: 21.1,
      mean_reversion_gap_percent: 14.7,
      latest_volume: 2400,
      liquidity: 'high',
      hourly_samples: 12,
      reason: 'Non-observed Currency Exchange watch for the README walkthrough.',
    }],
    evidence_warning: 'SHOWCASE / NON-OBSERVED VALUES. Mean-reversion gap is not validated EV. Production DeusCFO does not insert demo opportunities.',
  }
}

if (SHOWCASE_NON_OBSERVED) {
  api.interceptors.response.use((response) => {
    const url = String(response.config?.url || '')
    if (url.includes('/capital/plan') && (response.config?.method || 'get').toLowerCase() === 'post') {
      return { ...response, data: showcaseCapitalPlan(response.config.data) }
    }
    return response
  })
}

/**
 * Signal type → dracula color name.
 * Red: crashes/supply shocks/bearish.
 * Green: pumps/demand/bullish/recoveries.
 * Cyan: mean-reverting.
 * Yellow: volume spikes.
 */
export const SIGNAL_COLORS = {
  'Supply Shock': 'red',
  'Crashing': 'red',
  'Trending Down': 'red',
  'price_drop': 'red',
  'Demand Shock': 'green',
  'Pumping': 'green',
  'Trending Up': 'green',
  'Recovering': 'green',
  'price_spike': 'green',
  'Mean-Reverting': 'cyan',
  'recovery': 'cyan',
  'Volume Spike': 'yellow',
  'volume_spike': 'yellow',
  'volume_collapse': 'comment',
  'divergence': 'orange',
}

export const signalColor = (type) => SIGNAL_COLORS[type] || 'purple'

export const fmtPrice = (v) => {
  if (v == null) return '—'
  if (v >= 1000) return v.toFixed(0)
  if (v >= 1) return v.toFixed(2)
  if (v >= 0.01) return v.toFixed(2)
  return v.toPrecision(3)
}

export const fmtVol = (v) => {
  if (v == null) return '—'
  if (v >= 1e6) return (v / 1e6).toFixed(1) + 'M'
  if (v >= 1e3) return (v / 1e3).toFixed(1) + 'k'
  return v.toFixed(0)
}

export const fmtPct = (v) => (v != null ? `${v > 0 ? '+' : ''}${v.toFixed(1)}%` : '—')

export const fmtTime = (iso) => {
  if (!iso) return '—'
  const d = new Date(iso)
  return d.toLocaleString('en-US', {
    month: 'short', day: 'numeric',
    hour: 'numeric', minute: '2-digit',
  })
}

export const fmtRelative = (iso) => {
  if (!iso) return '—'
  const diff = Date.now() - new Date(iso).getTime()
  const mins = Math.floor(diff / 60000)
  if (mins < 1) return 'just now'
  if (mins < 60) return `${mins}m ago`
  const hrs = Math.floor(mins / 60)
  if (hrs < 24) return `${hrs}h ago`
  return `${Math.floor(hrs / 24)}d ago`
}
