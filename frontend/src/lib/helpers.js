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

/**
 * Signal type → semantic color name used by SignalBadge.
 * Red: crashes/supply shocks/bearish.
 * Green: pumps/demand/bullish/recoveries.
 * Cyan: mean-reverting.
 * Yellow: volume spikes.
 */
export const SIGNAL_TYPE_OPTIONS = [
  { id: 'All', label: 'All' },
  { id: 'Supply Shock', label: 'Supply Shock' },
  { id: 'Demand Shock', label: 'Demand Shock' },
  { id: 'Crashing', label: 'Crashing' },
  { id: 'Pumping', label: 'Pumping' },
  { id: 'Recovering', label: 'Recovering' },
  { id: 'Mean-Reverting', label: 'Mean-Reverting' },
  { id: 'Trending Up', label: 'Trending Up' },
  { id: 'Trending Down', label: 'Trending Down' },
  { id: 'Volume Spike', label: 'Volume Spike' },
  { id: 'price_drop', label: 'Price drop' },
  { id: 'price_spike', label: 'Price spike' },
  { id: 'volume_spike', label: 'Volume spike (anomaly)' },
  { id: 'volume_collapse', label: 'Volume collapse' },
  { id: 'divergence', label: 'Divergence' },
  { id: 'recovery', label: 'Recovery' },
]

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

export const fmtPct = (v) => (v != null ? `${v > 0 ? '+' : ''}${Number(v).toFixed(1)}%` : '—')

export const historyWindowLabel = (hours) => Number(hours) === 168 ? '7d' : `${hours}h`

export const isDraftLeagueLive = (leagues, draft) => Boolean(draft) && Array.isArray(leagues) && leagues.some((league) => league.id === draft)

export const leagueStatusTone = ({ selectedLeague = '', migrationRequired = false, bootError = false } = {}) => {
  if (bootError) return 'negative'
  if (!selectedLeague || migrationRequired) return 'warning'
  return 'positive'
}

export const TABS = [
  { id: 'cfo', label: 'CFO' },
  { id: 'dashboard', label: 'Dashboard' },
  { id: 'signals', label: 'Signals' },
  { id: 'explorer', label: 'Explorer' },
  { id: 'strategies', label: 'Strategies' },
  { id: 'profit-routes', label: 'Profit Routes' },
]

export const adjacentTabId = (currentId, key, tabs = TABS) => {
  const index = tabs.findIndex((tab) => tab.id === currentId)
  const last = tabs.length - 1
  if (index < 0) return null
  if (key === 'ArrowRight') return tabs[index === last ? 0 : index + 1].id
  if (key === 'ArrowLeft') return tabs[index === 0 ? last : index - 1].id
  if (key === 'Home') return tabs[0].id
  if (key === 'End') return tabs[last].id
  return null
}

export const hasPositiveChaosPerDivine = (plan) => Number(plan?.chaos_per_divine) > 0

export const LEAGUE_EMPTY_TITLE = 'Select a league'
export const LEAGUE_EMPTY_MESSAGE = 'Save a live league in Shared market context before this view requests market data.'

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

export const formatUpdateBadge = (version) => {
  if (!version) return 'UPDATE AVAILABLE'
  return `UPDATE AVAILABLE · ${version.startsWith('v') ? version : `v${version}`}`
}
