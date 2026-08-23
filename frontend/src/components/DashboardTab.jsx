import { useState, useEffect } from 'react'
import { api, fmtRelative } from '../lib/helpers'
import { FlipFinder } from './FlipFinder'
import { LoadingState, EmptyState, ErrorState } from './ui'

export function DashboardTab({ categories, selectedLeague }) {
  const [overview, setOverview] = useState(null)
  const [signals, setSignals] = useState([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState('')
  useEffect(() => {
    if (!selectedLeague) return
    let cancelled = false
    const load = () => {
      setError('')
      Promise.all([
        api.get('/snapshot/status'),
        api.get('/signals', { params: { league: selectedLeague, hours: 24 } }),
      ]).then(([status, signalResponse]) => {
        if (!cancelled) {
          setOverview(status.data)
          setSignals(signalResponse.data)
          setLoading(false)
        }
      }).catch(() => {
        if (!cancelled) {
          setError('Dashboard data unavailable')
          setLoading(false)
        }
      })
    }
    load()
    const interval = setInterval(load, 60_000)
    return () => {
      cancelled = true
      clearInterval(interval)
    }
  }, [selectedLeague])
  const snapshot = overview?.last_snapshot_per_league?.[selectedLeague]
  const activeRegimes = signals.filter((signal) => signal.source === 'regime').length
  const anomalies = signals.filter((signal) => signal.source === 'anomaly').length
  return <div className="terminal-page"><div className="page-head"><div><div className="eyebrow">MARKET MONITOR / {selectedLeague || '—'}</div><h1>Dashboard</h1><p className="muted">What changed, what deserves attention, and where to investigate next.</p></div><div className="market-state"><span className="status-dot" /> SNAPSHOT <strong>{fmtRelative(snapshot)}</strong></div></div>
    {loading && <LoadingState text="Loading market monitor…" />}{error && <ErrorState message={error} />}{!loading && !error && <><div className="metric-grid"><Metric label="Signals (24h)" value={signals.length} /><Metric label="Regimes" value={activeRegimes} /><Metric label="Anomalies" value={anomalies} /><Metric label="Items tracked" value={overview?.total_rows?.toLocaleString?.() || '—'} /><Metric label="Last snapshot" value={fmtRelative(snapshot)} /></div><section className="terminal-panel"><div className="panel-title"><h2>Market feed</h2><span>{signals.length} events</span></div>{signals.length ? <div className="table-wrap"><table className="dense-table"><thead><tr><th>Time</th><th>Type</th><th>Item</th><th>Change</th><th>Confidence</th></tr></thead><tbody>{signals.slice(0,12).map((signal,index) => <tr key={`${signal.item}-${index}`}><td>{fmtRelative(signal.timestamp || signal.detected_at)}</td><td>{signal.type || signal.signal_type || '—'}</td><td><strong>{signal.item || signal.item_name || '—'}</strong></td><td className={`numeric ${(signal.change_pct || 0) >= 0 ? 'positive' : 'negative'}`}>{signal.change_pct == null ? '—' : `${signal.change_pct > 0 ? '+' : ''}${Number(signal.change_pct).toFixed(1)}%`}</td><td className="numeric">{signal.confidence == null ? '—' : `${Math.round(signal.confidence * 100)}%`}</td></tr>)}</tbody></table></div> : <EmptyState title="No active market events" message="The selected market has no returned signals in the current period." />}</section><FlipFinder categories={categories} selectedLeague={selectedLeague} /></>}</div>
}
function Metric({ label, value }) { return <div className="metric"><span>{label}</span><strong>{value}</strong></div> }
