import axios from 'axios'

export const API_BASE = '/api'
export const api = axios.create({ baseURL: API_BASE })

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
