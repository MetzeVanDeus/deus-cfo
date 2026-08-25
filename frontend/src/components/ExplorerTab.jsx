import { useState, useEffect, useMemo } from 'react'
import { api, fmtPrice, fmtVol, fmtPct, fmtTime } from '../lib/helpers'
import { LoadingState, EmptyState, ErrorState, ConfidenceBar, SignalBadge } from './ui'
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
  // Fetch items when category or league changes
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
  // Fetch detail when item selected
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
    }).catch(e => {
      if (cancelled) return
      setError('Failed to load item data')
      setLoadingDetail(false)
    })
    // Get item info from items list
    const found = items.find(i => i.item_id === selectedItem)
    setItemData(found || null)
    return () => { cancelled = true }
  }, [selectedLeague, selectedCategory, selectedItem, historyHours])
  return (
    <div className="space-y-4">
      {/* Controls */}
      <div className="card !p-4">
        <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
          <div>
            <label className="block text-sm font-medium text-dracula-comment mb-2">Shared league</label>
            <div className="input w-full" aria-label="Shared league">{selectedLeague || 'Choose shared league above'}</div>
          </div>
          <div>
            <label className="block text-sm font-medium text-dracula-comment mb-2">Category</label>
            <select value={selectedCategory} onChange={(e) => { setSelectedCategory(e.target.value); setSelectedItem('') }} className="input w-full">
              {categories.map(c => <option key={c.id} value={c.id}>{c.name}</option>)}
            </select>
          </div>
          <div>
            <label className="block text-sm font-medium text-dracula-comment mb-2">Item</label>
            <select value={selectedItem} onChange={(e) => setSelectedItem(e.target.value)} className="input w-full" disabled={loadingItems || items.length === 0}>
              {loadingItems && <option>Loading items...</option>}
              {!loadingItems && items.length === 0 && <option>No items in category</option>}
              {!loadingItems && items.map(i => <option key={i.item_id} value={i.item_id}>{i.item_name}{i.variant ? ` (${i.variant})` : ''}</option>)}
            </select>
          </div>
        </div>
      </div>
      {itemsError && !loadingItems && <ErrorState message={itemsError} onRetry={() => window.location.reload()} />}
      {!selectedItem && !loadingItems && !itemsError && (
        <EmptyState title="Select an Item" message="Choose a category and item above to see price history, regime, and statistics." />
      )}
      {loadingDetail && <LoadingState text="Loading item data..." />}
      {error && !loadingDetail && <ErrorState message={error} />}
      {selectedItem && !loadingDetail && !error && regime && stats && (
        <div className="space-y-4 animate-fade-in">
          {/* Top Row: Price + Regime */}
          <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
            <PriceCard history={history} itemData={itemData} />
            <RegimeCard regime={regime} />
          </div>
          {/* Statistics */}
          <StatsCard stats={stats} historyHours={historyHours} />
          {/* Price History Chart */}
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
    <div className="card">
      <h3 className="text-sm font-semibold text-dracula-comment uppercase tracking-wide mb-3">Current Price</h3>
      <div className="flex items-end gap-4">
        <div>
          <div className="text-3xl font-bold text-dracula-fg font-mono">{fmtPrice(current)}</div>
          <div className="text-sm text-dracula-comment">chaos</div>
        </div>
        <div className={`flex items-center gap-1 text-lg font-semibold mb-1 ${isUp ? 'text-dracula-green' : 'text-dracula-red'}`}>
          <span>{isUp ? '+' : '-'}</span>
          <span>{fmtPct(changePct)}</span>
        </div>
      </div>
      {itemData && (
        <div className="mt-3 text-sm text-dracula-comment">
          Volume: <span className="text-dracula-fg font-mono">{fmtVol(itemData.volume)}</span>
        </div>
      )}
    </div>
  )
}
function RegimeCard({ regime }) {
  const conf = regime.confidence
  return (
    <div className="card">
      <h3 className="text-sm font-semibold text-dracula-comment uppercase tracking-wide mb-3">Market Regime</h3>
      <div className="flex items-center gap-3 mb-3">
        <SignalBadge type={regime.regime} />
        <span className="text-sm text-dracula-comment">{Math.round(conf * 100)}% confidence</span>
      </div>
      <p className="text-sm text-dracula-fg/90 mb-3">{regime.explanation}</p>
      <div>
        <div className="text-xs text-dracula-comment mb-1">Confidence</div>
        <ConfidenceBar score={conf} />
      </div>
      {regime.signals && (
        <div className="mt-3 grid grid-cols-2 gap-2 text-xs">
          {regime.signals.price_change_pct != null && (
            <div><span className="text-dracula-comment">Price change: </span><span className="text-dracula-fg font-mono">{fmtPct(regime.signals.price_change_pct)}</span></div>
          )}
          {regime.signals.volatility_pct != null && (
            <div><span className="text-dracula-comment">Volatility: </span><span className="text-dracula-fg font-mono">{regime.signals.volatility_pct.toFixed(1)}%</span></div>
          )}
          {regime.signals.trend && (
            <div><span className="text-dracula-comment">Trend: </span><span className="text-dracula-fg">{regime.signals.trend}</span></div>
          )}
          {regime.signals.volume_change != null && (
            <div><span className="text-dracula-comment">Volume change: </span><span className="text-dracula-fg font-mono">{regime.signals.volume_change.toFixed(2)}x</span></div>
          )}
        </div>
      )}
    </div>
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
    <div className="card">
      <h3 className="text-sm font-semibold text-dracula-comment uppercase tracking-wide mb-4">Rolling Statistics ({historyHours}h)</h3>
      <div className="grid grid-cols-2 sm:grid-cols-3 lg:grid-cols-5 gap-4">
        {rows.map(([label, val]) => (
          <div key={label}>
            <div className="stat-label">{label}</div>
            <div className="stat-value">{val}</div>
          </div>
        ))}
      </div>
    </div>
  )
}
function PriceChart({ history, historyHours = 24 }) {
  const points = useMemo(() => {
    const normalized = (Array.isArray(history) ? history : []).flatMap((point) => {
      if (point?.price == null || point.price === '') return []
      const price = Number(point.price)
      return Number.isFinite(price) ? [{ ...point, price }] : []
    })
    if (normalized.length <= 60) return normalized
    const indexes = new Set([0, normalized.length - 1])
    for (let i = 1; i < 59; i += 1) indexes.add(Math.round(i * (normalized.length - 1) / 59))
    return [...indexes].sort((a, b) => a - b).map((index) => normalized[index])
  }, [history])
  if (points.length === 0) {
    return (
      <div className="card">
        <h3 className="text-sm font-semibold text-dracula-comment uppercase tracking-wide mb-4">Price History</h3>
        <p className="text-dracula-comment text-sm">No price history available.</p>
      </div>
    )
  }
  const prices = points.map(p => p.price)
  const min = Math.min(...prices)
  const max = Math.max(...prices)
  const range = max - min || 1
  return (
    <div className="card">
      <div className="flex items-center justify-between mb-4">
        <h3 className="text-sm font-semibold text-dracula-comment uppercase tracking-wide">Price History</h3>
        <span className="text-xs text-dracula-comment">{points.length} data points · {historyHours}h</span>
      </div>
      <svg className="price-chart" viewBox="0 0 600 140" role="img" aria-label="Price history line chart">{(() => { const coords = points.map((p, i) => `${(i / Math.max(1, points.length - 1)) * 590 + 5},${130 - ((p.price - min) / range) * 115}`); return <><polyline fill="none" stroke="var(--brass-bright)" strokeWidth="2" points={coords.join(' ')} />{coords.map((point, i) => <circle key={i} cx={point.split(',')[0]} cy={point.split(',')[1]} r="3" fill="var(--brass-bright)"><title>{`${fmtPrice(points[i].price)}c · ${fmtTime(points[i].timestamp)}`}</title></circle>)}</> })()}</svg>
      {/* Axis labels */}
      <div className="flex justify-between text-xs text-dracula-comment font-mono">
        <span>{fmtPrice(min)}c</span>
        <span>{fmtPrice(max)}c</span>
      </div>
      <div className="flex justify-between text-xs text-dracula-comment">
        <span>{fmtTime(points[0].timestamp)}</span>
        <span>{fmtTime(points.at(-1).timestamp)}</span>
      </div>
    </div>
  )
}
