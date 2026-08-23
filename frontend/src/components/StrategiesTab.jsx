import { useEffect, useState } from 'react'
import { api } from '../lib/helpers'
import { ErrorState, LoadingState } from './ui'

const format = (value, suffix = '') => value == null ? '—' : `${typeof value === 'number' ? value.toFixed(2) : value}${suffix}`

export function StrategiesTab({ categories, selectedLeague }) {
  const [category, setCategory] = useState('')
  const [regime, setRegime] = useState('')
  const [percentile, setPercentile] = useState(50)
  const [volumeRatio, setVolumeRatio] = useState('')
  const [horizon, setHorizon] = useState(24)
  const [result, setResult] = useState(null)
  const [performance, setPerformance] = useState(null)
  const [baseline, setBaseline] = useState(null)
  const [loading, setLoading] = useState(false)
  const [baselineLoading, setBaselineLoading] = useState(false)
  const [error, setError] = useState('')

  useEffect(() => {
    if (!selectedLeague) return
    let cancelled = false
    setBaselineLoading(true)
    api.get('/performance', { params: { league: selectedLeague, horizon: 24, signal_window_hours: 24 } })
      .then(({ data }) => { if (!cancelled) setBaseline(data) })
      .catch(() => { if (!cancelled) setBaseline(null) })
      .finally(() => { if (!cancelled) setBaselineLoading(false) })
    return () => { cancelled = true }
  }, [selectedLeague])

  async function run(event) {
    event.preventDefault(); setLoading(true); setError(''); setResult(null); setPerformance(null)
    const conditions = { price_percentile: { lte: Number(percentile) / 100 } }
    if (regime) conditions.regime = regime
    if (volumeRatio !== '') conditions.volume_ratio = { gte: Number(volumeRatio) }
    try {
      const [backtest, history] = await Promise.all([
        api.post('/strategy/backtest', { league: selectedLeague, category: category || null, conditions, horizons: [24], signal_window_hours: 24 }),
        api.get('/performance', { params: { league: selectedLeague, category: category || undefined, horizon: 24, signal_window_hours: 24 } }),
      ])
      setResult(backtest.data); setPerformance(history.data)
    } catch (err) { setError(err.response?.data?.detail || 'Strategy backtest unavailable.') }
    finally { setLoading(false) }
  }

  const rows = Object.entries(result?.horizon_results || {})
  return <div className="terminal-page"><div className="page-head"><div><div className="eyebrow">RESEARCH / VALIDATION</div><h1>Strategies</h1><p className="muted">Test a repeatable market condition against available historical evidence, then compare it with the historical 24h signal baseline. This is evidence for investigation, not a forecast or trade.</p></div></div>
    <Baseline baseline={baseline} loading={baselineLoading} />
    <form className="terminal-panel strategy-form" onSubmit={run}><div className="form-row form-row-main"><Field label="Shared league"><div className="input">{selectedLeague || 'Choose shared league above'}</div></Field><Field label="Category"><select className="input" value={category} onChange={(e) => setCategory(e.target.value)}><option value="">All categories</option>{categories.map((item) => <option key={item.id} value={item.id}>{item.name}</option>)}</select></Field><Field label="Regime"><select className="input" value={regime} onChange={(e) => setRegime(e.target.value)}><option value="">Any regime</option><option value="MEAN_REVERTING">MEAN_REVERTING</option><option value="TRENDING_UP">TRENDING_UP</option><option value="TRENDING_DOWN">TRENDING_DOWN</option><option value="VOLATILE">VOLATILE</option></select></Field><Field label="Horizon (hours)"><select className="input" value={horizon} onChange={(e) => setHorizon(e.target.value)}><option value="24">24</option></select></Field></div><div className="form-row strategy-conditions"><Field label="Price percentile ≤"><input className="input numeric" type="number" min="0" max="100" value={percentile} onChange={(e) => setPercentile(e.target.value)} /></Field><Field label="Volume ratio ≥ (optional)"><input className="input numeric" type="number" min="0" step=".1" placeholder="Any" value={volumeRatio} onChange={(e) => setVolumeRatio(e.target.value)} /></Field><div className="form-actions strategy-action"><button className="btn-primary" disabled={loading || !selectedLeague}>{loading ? 'RUNNING…' : 'RUN BACKTEST'}</button></div></div></form>
    {loading && <LoadingState text="Running historical strategy evaluation…" />}{error && <ErrorState message={error} />}{!loading && !error && result && <Results result={result} performance={performance} rows={rows} />}
  </div>
}
function Baseline({ baseline, loading }) {
  const groups = [...(baseline?.groups || [])].sort((a, b) => (b.horizons?.['24']?.sample_size || 0) - (a.horizons?.['24']?.sample_size || 0)).slice(0, 8)
  return <section className="terminal-panel"><div className="panel-title"><h2>Historical 24h baseline</h2><span>{loading ? 'LOADING…' : `${baseline?.groups?.length || 0} groups`}</span></div><p className="muted">Historical detector outcomes, aligned to the daily sparkline cadence, give you a starting point. Run a condition set below to test whether a narrower pattern has enough occurrences and a better result.</p>{groups.some((group) => Object.keys(group.horizons?.['24']?.evidence_sources || {}).some((source) => source.includes('reconstructed'))) && <p className="muted">PROVENANCE: reconstructed sparkline history is used where available; returns are derived historical outcomes, not direct observations or live quotes.</p>}{groups.length ? <div className="table-wrap"><table className="dense-table"><thead><tr><th>Signal</th><th>Category</th><th>Tier</th><th>Sample</th><th>Win rate</th><th>Median return</th><th>Mean return</th><th>Provenance</th><th>Reconstructed</th></tr></thead><tbody>{groups.map((group, index) => { const data = group.horizons?.['24'] || {}; const sources = Object.keys(data.evidence_sources || {}).join(', '); return <tr key={`${group.signal_type}-${group.category}-${index}`}><td>{group.signal_type || '—'}</td><td>{group.category || '—'}</td><td>{group.liquidity_tier || '—'}</td><td className="numeric">{data.sample_size ?? 0}</td><td className="numeric">{format(data.win_rate != null ? data.win_rate * 100 : null, '%')}</td><td className={`numeric ${(data.median_return || 0) >= 0 ? 'positive' : 'negative'}`}>{format(data.median_return, '%')}</td><td className={`numeric ${(data.mean_return || 0) >= 0 ? 'positive' : 'negative'}`}>{format(data.mean_return, '%')}</td><td>{sources || '—'}</td><td className="numeric">{data.reconstructed_sample_size ?? '—'}</td></tr> })}</tbody></table></div> : !loading && <p className="empty-copy">No historical signal outcomes are available for this league yet.</p>}</section>
}
function Field({ label, children }) { return <label className="field"><span>{label}</span>{children}</label> }
function Results({ result, performance, rows }) { return <div className="strategy-results animate-fade-in"><div className="metric-grid"><Metric label="Occurrences" value={result.occurrences} /><Metric label="Condition" value={`P${result.conditions?.price_percentile?.lte != null ? result.conditions.price_percentile.lte * 100 : '—'}`} /><Metric label="Horizon" value={`${result.horizons?.[0] ?? '—'}h`} /><Metric label="Groups" value={Object.keys(result.category_performance || {}).length} /></div><div className="output-grid"><section className="terminal-panel"><div className="panel-title"><h2>Strategy result</h2></div>{rows.length ? <div className="table-wrap"><table className="dense-table"><thead><tr><th>Horizon</th><th>Occurrences</th><th>Win rate</th><th>Median return</th><th>Mean return (arithmetic)</th><th>Drawdown</th><th>Best / worst</th></tr></thead><tbody>{rows.map(([key,row]) => <tr key={key}><td>{key}h</td><td className="numeric">{row.occurrences ?? row.sample_size ?? 0}</td><td className="numeric positive">{format(row.win_rate != null ? row.win_rate * 100 : null, '%')}</td><td className={`numeric ${(row.median_return || 0) >= 0 ? 'positive' : 'negative'}`}>{format(row.median_return, '%')}</td><td className={`numeric ${row.mean_return >= 0 ? 'positive' : 'negative'}`}>{format(row.mean_return, '%')}</td><td className="numeric negative">{format(row.drawdown, '%')}</td><td className="numeric">{format(row.best_period?.return, '%')} / {format(row.worst_period?.return, '%')}</td></tr>)}</tbody></table></div> : <p className="empty-copy">No matching historical outcomes.</p>}</section><section className="terminal-panel"><div className="panel-title"><h2>Performance groups</h2><span>{performance?.groups?.length || 0}</span></div>{performance?.groups?.length ? <div className="table-wrap"><table className="dense-table"><thead><tr><th>Signal</th><th>Category</th><th>Tier</th><th>Return</th></tr></thead><tbody>{performance.groups.slice(0, 20).map((group, index) => { const horizonData = Object.values(group.horizons || {})[0] || {}; return <tr key={`${group.signal_type}-${index}`}><td>{group.signal_type || '—'}</td><td>{group.category || '—'}</td><td>{group.liquidity_tier || '—'}</td><td className="numeric">{format(horizonData.mean_return, '%')}</td></tr> })}</tbody></table></div> : <p className="empty-copy">No filtered performance groups returned.</p>}</section></div></div> }
function Metric({ label, value }) { return <div className="metric"><span>{label}</span><strong>{value}</strong></div> }
