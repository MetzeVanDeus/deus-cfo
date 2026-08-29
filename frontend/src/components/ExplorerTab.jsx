import { useState, useEffect, useMemo } from 'react'
import { api, fmtPrice, fmtVol, fmtPct, fmtTime } from '../lib/helpers'
import { LoadingState, EmptyState, ErrorState, ConfidencePercent, SignalBadge, LeagueEmpty } from './ui'

export function ExplorerTab({ categories, selectedLeague, historyHours = 24 }) {
  const [selectedCategory, setSelectedCategory] = useState('Currency')
  const [items, setItems] = useState([])
  const [selectedItem, setSelectedItem] = useState('')
  const [loadingItems, setLoadingItems] = useState(false)
  const [itemsError, setItemsError] = useState('')
  const [history, setHistory] = useState([])
  const [regime, setRegime] = useState(null)
  const [stats, setStats] = useState(null)
  const [itemData, setItemData] = useState(null)
  const [loadingDetail, setLoadingDetail] = useState(false)
  const [error, setError] = useState('')
  useEffect(() => {
    if (!selectedLeague || !selectedCategory) return
    let cancelled = false
    setLoadingItems(true)
    setItemsError('')
    setSelectedItem('')
    setItems([])
    api.get('/market/overview', { params: { league: selectedLeague } }).then(r => {
      if (cancelled) return
      const catItems = r.data.categories?.[selectedCategory] || []
      setItems(catItems)
      setLoadingItems(false)
    }).catch(() => { if (!cancelled) { setItemsError('Failed to load market items'); setLoadingItems(false) } })
    return () => { cancelled = true }
  }, [selectedLeague, selectedCategory])
  useEffect(() => {
    if (!selectedLeague || !selectedCategory || !selectedItem) return
    let cancelled = false
    setLoadingDetail(true)
    setError('')
    const params = { league: selectedLeague, category: selectedCategory, item_id: selectedItem, hours: historyHours }
    Promise.all([
      api.get('/history', { params }),
      api.get('/regime', { params }),
      api.get('/stats', { params }),
    ]).then(([hR, rR, sR]) => {
      if (cancelled) return
      setHistory(hR.data)
      setRegime(rR.data)
      setStats(sR.data)
      setLoadingDetail(false)
    }).catch(() => {
      if (cancelled) return
      setError('Failed to load item data')
      setLoadingDetail(false)
    })
    setItemData(items.find(i => i.item_id === selectedItem) || null)
    return () => { cancelled = true }
  }, [selectedLeague, selectedCategory, selectedItem, historyHours, items])
  return (
    <div className="terminal-page">
      <div className="page-head"><div><div className="eyebrow">ITEM RESEARCH / {selectedLeague || '—'}</div><h1>Explorer</h1><p className="muted">Price history, regime, and rolling statistics for one item.</p></div></div>
      <div className="terminal-panel">
        <div className="form-row explorer-controls">
          <label className="field">
            <span>Category</span>
            <select value={selectedCategory} onChange={(e) => { setSelectedCategory(e.target.value); setSelectedItem('') }} className="input">
              {categories.map(c => <option key={c.id} value={c.id}>{c.name}</option>)}
            </select>
          </label>
          <label className="field">
            <span>Item</span>
            <select value={selectedItem} onChange={(e) => setSelectedItem(e.target.value)} className="input" disabled={loadingItems || items.length === 0 || !selectedLeague}>
              {loadingItems && <option value="">Loading items...</option>}
              {!loadingItems && !selectedLeague && <option value="">Save a live league first</option>}
              {!loadingItems && selectedLeague && items.length === 0 && <option value="">No items in category</option>}
              {!loadingItems && items.length > 0 && <option value="">Select an item</option>}
              {!loadingItems && items.map(i => <option key={i.item_id} value={i.item_id}>{i.item_name}{i.variant ? ` (${i.variant})` : ''}</option>)}
            </select>
          </label>
        </div>
      </div>
      {itemsError && !loadingItems && <ErrorState message={itemsError} onRetry={() => window.location.reload()} />}
      {!selectedLeague && <LeagueEmpty />}
      {selectedLeague && !selectedItem && !loadingItems && !itemsError && (
        <EmptyState title="Select an Item" message="Choose a category and item above to see price history, regime, and statistics." />
      )}
      {loadingDetail && <LoadingState text="Loading item data..." />}
      {error && !loadingDetail && <ErrorState message={error} />}
      {selectedItem && !loadingDetail && !error && regime && stats && (
        <div className="explorer-detail">
          <div className="output-grid">
            <PriceCard history={history} itemData={itemData} />
            <RegimeCard regime={regime} />
          </div>
          <StatsCard stats={stats} historyHours={historyHours} />
          <PriceChart history={history} historyHours={historyHours} />
        </div>
      )}
    </div>
  )
}
function PriceCard({ history, itemData }) {
  const prices = history.map(h => h.price).filter(p => p != null)
  const current = prices.length > 0 ? prices[prices.length - 1] : (itemData?.price_chaos ?? null)
  const first = prices.length > 1 ? prices[0] : current
  const changePct = first && current ? ((current - first) / first) * 100 : 0
  const isUp = changePct >= 0
  return (
    <section className="terminal-panel">
      <div className="panel-title"><h2>Current Price</h2></div>
      <div className="metric-grid">
        <div className="metric"><span>Price (chaos)</span><strong>{fmtPrice(current)}</strong></div>
        <div className="metric"><span>Change</span><strong className={isUp ? 'positive' : 'negative'}>{fmtPct(changePct)}</strong></div>
        {itemData && <div className="metric"><span>Volume</span><strong>{fmtVol(itemData.volume)}</strong></div>}
      </div>
    </section>
  )
}
function RegimeCard({ regime }) {
  const conf = regime.confidence
  return (
    <section className="terminal-panel">
      <div className="panel-title"><h2>Market Regime</h2><span>{Math.round(conf * 100)}% confidence</span></div>
      <div className="regime-head"><SignalBadge type={regime.regime} /><ConfidencePercent score={conf} /></div>
      <p className="muted">{regime.explanation}</p>
      {regime.signals && (
        <div className="metric-grid">
          {regime.signals.price_change_pct != null && (
            <div className="metric"><span>Price change</span><strong>{fmtPct(regime.signals.price_change_pct)}</strong></div>
          )}
          {regime.signals.volatility_pct != null && (
            <div className="metric"><span>Volatility</span><strong>{regime.signals.volatility_pct.toFixed(1)}%</strong></div>
          )}
          {regime.signals.trend && (
            <div className="metric"><span>Trend</span><strong>{regime.signals.trend}</strong></div>
          )}
          {regime.signals.volume_change != null && (
            <div className="metric"><span>Volume change</span><strong>{regime.signals.volume_change.toFixed(2)}x</strong></div>
          )}
        </div>
      )}
    </section>
  )
}
function StatsCard({ stats, historyHours = 24 }) {
  const rows = [
    ['Mean', fmtPrice(stats.mean)],
    ['Median', fmtPrice(stats.median)],
    ['MAD', fmtPrice(stats.mad)],
    ['Std Dev', fmtPrice(stats.std)],
    ['Min', fmtPrice(stats.min)],
    ['Max', fmtPrice(stats.max)],
    ['P25', fmtPrice(stats.p25)],
    ['P75', fmtPrice(stats.p75)],
    ['Percentile Rank', `${Math.round((stats.percentile_rank || 0) * 100)}%`],
    ['Avg Volume', fmtVol(stats.volume_mean)],
  ]
  return (
    <section className="terminal-panel">
      <div className="panel-title"><h2>Rolling Statistics ({historyHours}h)</h2></div>
      <div className="metric-grid">
        {rows.map(([label, val]) => (
          <div className="metric" key={label}><span>{label}</span><strong>{val}</strong></div>
        ))}
      </div>
    </section>
  )
}
function PriceChart({ history, historyHours = 24 }) {
  const points = useMemo(() => {
    const normalized = (Array.isArray(history) ? history : []).flatMap((point) => {
      const rawPrice = point?.price
      if (rawPrice == null || (typeof rawPrice !== 'number' && (typeof rawPrice !== 'string' || rawPrice.trim() === ''))) return []
      const price = Number(rawPrice)
      return Number.isFinite(price) ? [{ ...point, price }] : []
    })
    if (normalized.length <= 60) return normalized
    const indexes = new Set([0, normalized.length - 1])
    for (let i = 1; i < 59; i += 1) indexes.add(Math.round(i * (normalized.length - 1) / 59))
    return [...indexes].sort((a, b) => a - b).map((index) => normalized[index])
  }, [history])
  if (points.length < 2) {
    return (
      <section className="terminal-panel">
        <div className="panel-title"><h2>Price History</h2></div>
        <EmptyState title="Not enough history in this window" message="WAIT is the honest state until at least two observed prices exist. No trend is drawn." compact />
        {points.length === 1 && <p className="muted small">Observed {fmtPrice(points[0].price)}c at {fmtTime(points[0].timestamp)}.</p>}
      </section>
    )
  }
  const prices = points.map(p => p.price)
  const min = Math.min(...prices)
  const max = Math.max(...prices)
  const range = max - min || 1
  return (
    <section className="terminal-panel">
      <div className="panel-title">
        <h2>Price History</h2>
        <span>{points.length} data points · {historyHours}h</span>
      </div>
      <svg className="price-chart" viewBox="0 0 600 140" role="img" aria-label="Price history line chart">{(() => { const coords = points.map((p, i) => `${(i / Math.max(1, points.length - 1)) * 590 + 5},${130 - ((p.price - min) / range) * 115}`); return <><polyline fill="none" stroke="var(--brass-bright)" strokeWidth="2" points={coords.join(' ')} />{coords.map((point, i) => <circle key={i} cx={point.split(',')[0]} cy={point.split(',')[1]} r="3" fill="var(--brass-bright)"><title>{`${fmtPrice(points[i].price)}c · ${fmtTime(points[i].timestamp)}`}</title></circle>)}</> })()}</svg>
      <p className="muted small">Price range {fmtPrice(min)}c – {fmtPrice(max)}c</p>
      <div className="chart-axis">
        <span>{fmtTime(points[0].timestamp)}</span>
        <span>{fmtTime(points.at(-1).timestamp)}</span>
      </div>
    </section>
  )
}
