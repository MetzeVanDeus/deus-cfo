import { useState, useEffect, useMemo } from 'react'
import { api, fmtRelative } from '../lib/helpers'
import { LoadingState, EmptyState, ErrorState } from './ui'

const SIGNAL_TYPES = ['All', 'Supply Shock', 'Demand Shock', 'Crashing', 'Pumping', 'Recovering', 'Mean-Reverting', 'Trending Up', 'Trending Down', 'Volume Spike', 'price_drop', 'price_spike', 'volume_spike', 'volume_collapse', 'divergence', 'recovery']
export function SignalsTab({ selectedLeague }) {
  const [signals, setSignals] = useState([]); const [loading, setLoading] = useState(true); const [error, setError] = useState(''); const [filterType, setFilterType] = useState('All'); const [sortBy, setSortBy] = useState('confidence')
  useEffect(() => { if (!selectedLeague) return; let cancelled = false; setLoading(true); setError(''); api.get('/signals', { params: { league: selectedLeague, hours: 24 } }).then((response) => { if (!cancelled) { setSignals(response.data); setLoading(false) } }).catch(() => { if (!cancelled) { setError('Failed to load signals'); setLoading(false) } }); return () => { cancelled = true } }, [selectedLeague])
  const filtered = useMemo(() => { const result = filterType === 'All' ? signals : signals.filter((signal) => signal.type === filterType); return [...result].sort((a,b) => sortBy === 'name' ? (a.item || '').localeCompare(b.item || '') : (b.confidence || 0) - (a.confidence || 0)) }, [signals, filterType, sortBy])
  return <div className="terminal-page"><div className="page-head"><div><div className="eyebrow">EVENT STREAM / 24H</div><h1>Signals</h1><p className="muted">Compact evidence feed. Open a row for the underlying signal payload.</p></div></div><div className="terminal-panel signal-controls"><div className="form-row form-row-main"><label className="field"><span>Type</span><select className="input" value={filterType} onChange={(e) => setFilterType(e.target.value)}>{SIGNAL_TYPES.map((type) => <option key={type}>{type}</option>)}</select></label><label className="field"><span>Sort</span><select className="input" value={sortBy} onChange={(e) => setSortBy(e.target.value)}><option value="confidence">Confidence</option><option value="name">Item name</option></select></label><div className="market-state">{filtered.length} signal{filtered.length !== 1 ? 's' : ''}</div></div></div>{loading && <LoadingState text="Loading market signals…" />}{error && <ErrorState message={error} />}{!loading && !error && (filtered.length ? <section className="terminal-panel"><div className="table-wrap"><table className="dense-table"><thead><tr><th>Time</th><th>Signal</th><th>Item</th><th>Move</th><th>Confidence</th><th /></tr></thead><tbody>{filtered.map((signal,index) => <SignalRow key={`${signal.item}-${index}`} signal={signal} />)}</tbody></table></div></section> : <EmptyState title="No signals detected" message="No regime changes or anomalies were returned for the selected period." />)}</div>
}
function SignalRow({ signal }) {
  const [open, setOpen] = useState(false)
  const move = signal.change_pct ?? signal.price_change_pct
  return <>
    <tr onClick={() => setOpen((current) => !current)}>
      <td>{fmtRelative(signal.timestamp || signal.detected_at || signal.created_at)}</td>
      <td><span className="signal-mark" /> {signal.type || signal.signal_type || '—'}</td>
      <td><strong>{signal.item || signal.item_name || '—'}</strong></td>
      <td className={`numeric ${(move || 0) >= 0 ? 'positive' : 'negative'}`}>{move == null ? '—' : `${move > 0 ? '+' : ''}${Number(move).toFixed(1)}%`}</td>
      <td className="numeric">{signal.confidence == null ? '—' : `${Math.round(signal.confidence * 100)}%`}</td>
      <td className="numeric">{open ? '−' : '+'}</td>
    </tr>
    {open && <tr className="detail-row"><td colSpan="6"><details open><summary>Signal detail</summary><pre>{JSON.stringify(signal, null, 2)}</pre></details></td></tr>}
  </>
}
