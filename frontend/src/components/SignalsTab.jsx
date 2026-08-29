import { useState, useEffect, useMemo } from 'react'
import { api, fmtRelative, SIGNAL_TYPE_OPTIONS } from '../lib/helpers'
import { LoadingState, EmptyState, ErrorState, LeagueEmpty } from './ui'
export function SignalsTab({ selectedLeague, historyHours = 24 }) {
  const [signals, setSignals] = useState([]); const [loading, setLoading] = useState(Boolean(selectedLeague)); const [error, setError] = useState(''); const [filterType, setFilterType] = useState('All'); const [sortBy, setSortBy] = useState('confidence')
  useEffect(() => {
    if (!selectedLeague) {
      setSignals([])
      setError('')
      setLoading(false)
      return
    }
    let cancelled = false
    setLoading(true)
    setError('')
    api.get('/signals', { params: { league: selectedLeague, hours: historyHours } }).then((response) => { if (!cancelled) { setSignals(response.data); setLoading(false) } }).catch(() => { if (!cancelled) { setError('Failed to load signals'); setLoading(false) } })
    return () => { cancelled = true }
  }, [selectedLeague, historyHours])
  const filtered = useMemo(() => { const result = filterType === 'All' ? signals : signals.filter((signal) => signal.type === filterType); return [...result].sort((a,b) => sortBy === 'name' ? (a.item || '').localeCompare(b.item || '') : (b.confidence || 0) - (a.confidence || 0)) }, [signals, filterType, sortBy])
  if (!selectedLeague) {
    return <div className="terminal-page"><div className="page-head"><div><div className="eyebrow">EVENT STREAM / —</div><h1>Signals</h1><p className="muted">Compact evidence feed. Open a row for the underlying signal payload.</p></div></div><LeagueEmpty /></div>
  }
  return <div className="terminal-page"><div className="page-head"><div><div className="eyebrow">EVENT STREAM / {historyHours}H</div><h1>Signals</h1><p className="muted">Compact evidence feed. Open a row for the underlying signal payload.</p></div></div><div className="terminal-panel signal-controls"><div className="form-row form-row-main"><label className="field"><span>Type</span><select className="input" value={filterType} onChange={(e) => setFilterType(e.target.value)}>{SIGNAL_TYPE_OPTIONS.map((type) => <option key={type.id} value={type.id}>{type.label}</option>)}</select></label><label className="field"><span>Sort</span><select className="input" value={sortBy} onChange={(e) => setSortBy(e.target.value)}><option value="confidence">Confidence</option><option value="name">Item name</option></select></label><div className="market-state">{filtered.length} signal{filtered.length !== 1 ? 's' : ''}</div></div></div>{loading && <LoadingState text="Loading market signals..." />}{error && <ErrorState message={error} />}{!loading && !error && (filtered.length ? <section className="terminal-panel"><div className="table-wrap"><table className="dense-table"><thead><tr><th>Time</th><th>Signal</th><th>Item</th><th>Move</th><th>Confidence</th><th /></tr></thead><tbody>{filtered.map((signal,index) => <SignalRow key={`${signal.item}-${index}`} signal={signal} />)}</tbody></table></div></section> : <EmptyState title="No signals detected" message="No regime changes or anomalies were returned for the selected period." />)}</div>
}
function SignalRow({ signal }) {
  const [open, setOpen] = useState(false)
  const move = signal.change_pct ?? signal.price_change_pct
  return <>
    <tr>
      <td>{fmtRelative(signal.timestamp || signal.detected_at || signal.created_at)}</td>
      <td><span className="signal-mark" /> {signal.type || signal.signal_type || '-'}</td>
      <td><strong>{signal.item || signal.item_name || '-'}</strong></td>
      <td className={`numeric ${(move || 0) >= 0 ? 'positive' : 'negative'}`}>{move == null ? '-' : `${move > 0 ? '+' : ''}${Number(move).toFixed(1)}%`}</td>
      <td className="numeric">{signal.confidence == null ? '-' : `${Math.round(signal.confidence * 100)}%`}</td>
      <td className="numeric"><button type="button" className="text-button row-toggle" aria-expanded={open} aria-label={`${open ? 'Collapse' : 'Expand'} signal details`} onClick={() => setOpen((current) => !current)}>{open ? '-' : '+'}</button></td>
    </tr>
    {open && <tr className="detail-row"><td colSpan="6"><div className="position-detail"><span>Time: <strong>{fmtRelative(signal.timestamp || signal.detected_at || signal.created_at)}</strong></span><span>Type: <strong>{signal.type || signal.signal_type || '—'}</strong></span><span>Item: <strong>{signal.item || signal.item_name || '—'}</strong></span><span>Change: <strong>{move == null ? '—' : `${Number(move).toFixed(1)}%`}</strong></span><span>Source: <strong>{signal.source || '—'}</strong></span></div><details><summary>Raw payload</summary><pre>{JSON.stringify(signal, null, 2)}</pre></details></td></tr>}
  </>
}
