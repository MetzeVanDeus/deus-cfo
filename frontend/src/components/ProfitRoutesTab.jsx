import { useEffect, useState } from 'react'
import { api, fmtPrice } from '../lib/helpers'
import { EmptyState, ErrorState, LoadingState } from './ui'

const value = (item) => {
  if (item == null || item === '') return '—'
  if (typeof item === 'number') return fmtPrice(item)
  if (Array.isArray(item)) return item.map(value).join(', ')
  if (typeof item === 'object') return Object.entries(item).map(([key, val]) => `${key}: ${value(val)}`).join(' · ')
  return String(item)
}
const percent = (item) => item == null ? '—' : `${(Number(item) <= 1 ? Number(item) * 100 : Number(item)).toFixed(1)}%`
const list = (items) => Array.isArray(items) ? items : items == null ? [] : [items]

export function ProfitRoutesTab({ selectedLeague }) {
  const [routes, setRoutes] = useState([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState('')

  useEffect(() => {
    let cancelled = false
    setLoading(true)
    setError('')
    const config = selectedLeague ? { params: { league: selectedLeague } } : undefined
    api.get('/profit-routes', config)
      .then(({ data }) => { if (!cancelled) setRoutes(Array.isArray(data) ? data : data?.routes || []) })
      .catch((err) => { if (!cancelled) setError(err.response?.data?.detail || 'Profit routes unavailable.') })
      .finally(() => { if (!cancelled) setLoading(false) })
    return () => { cancelled = true }
  }, [selectedLeague])

  return <div className="terminal-page">
    <div className="page-head"><div><div className="eyebrow">MONEY PRINTER / CAPITAL DEPLOYMENT</div><h1>Profit Routes</h1><p className="muted">Backend-evaluated transformations ranked for capital deployment. Economics, confidence, and constraints are reported by the route provider.</p></div></div>
    {loading && <div className="terminal-panel"><LoadingState text="Loading profit routes…" /></div>}
    {!loading && error && <ErrorState message={error} />}
    {!loading && !error && !routes.length && <div className="terminal-panel"><EmptyState title="No investable routes" message="The backend has not published any verified transformations for this market state." /></div>}
    {!loading && !error && routes.length > 0 && <div className="profit-routes">{routes.map((route, index) => <RouteCard key={route.transformation_id || index} route={route} />)}</div>}
  </div>
}

function RouteCard({ route }) {
  const recommendation = route.cfo_recommendation || route.recommendation
  return <article className="terminal-panel profit-route">
    <div className="panel-title"><div><div className="eyebrow">{route.transformation_id || 'TRANSFORMATION'}</div><h2>{route.name || 'Unnamed route'}</h2></div><span>{route.source ? `SOURCE · ${route.source}` : 'BACKEND EVALUATION'}</span></div>
    <div className="route-metrics metric-grid">
      <Metric label="Expected net" value={value(route.expected_net_profit)} tone="positive" />
      <Metric label="ROI" value={percent(route.roi)} tone="positive" />
      <Metric label="Capital required" value={value(route.capital_required)} />
      <Metric label="Profit / hour" value={value(route.profit_per_hour)} tone="positive" />
      <Metric label="Capacity" value={value(route.capacity)} />
      <Metric label="Execution + sale" value={`${value(route.expected_execution_time)} + ${value(route.expected_sale_time)}`} />
    </div>
    <div className="route-columns">
      <RouteSection title="Inputs" items={route.inputs} /><RouteSection title="Costs" items={route.costs} /><RouteSection title="Outputs" items={route.outputs} />
      <section><h3>Economics</h3><div className="raw-grid route-raw"><Raw label="Total input cost" item={route.total_input_cost} /><Raw label="Realistic output value" item={route.realistic_output_value} /><Raw label="Gross profit" item={route.gross_profit} /><Raw label="Divine-hour profit" item={route.profit_per_divine_hour} /></div></section>
      <section><h3>Confidence / risk</h3><div className="raw-grid route-raw"><Raw label="Overall confidence" item={percent(route.confidence)} /><Raw label="Pricing confidence" item={percent(route.pricing_confidence)} /><Raw label="Strategy confidence" item={percent(route.strategy_confidence)} /><Raw label="Execution risk" item={value(route.execution_risk)} /></div></section>
    </div>
    <div className="route-bottom">
      <section><h3>Reasons</h3>{list(route.reasons).length ? <ul className="dense-list">{list(route.reasons).map((reason, i) => <li key={i}><span className="signal-mark" />{value(reason)}</li>)}</ul> : <p className="muted small">No reasons supplied.</p>}</section>
      <section><h3>Execution</h3>{route.execution_steps && <p className="small">{value(route.execution_steps)}</p>}<p className="muted small">Capacity: <strong>{value(route.capacity)}</strong> · Expected execution: <strong>{value(route.expected_execution_time)}</strong> · Expected sale: <strong>{value(route.expected_sale_time)}</strong></p>{(recommendation || route.constraints) && <><h3 className="route-subhead">CFO guidance</h3><p className="small">{recommendation || '—'}</p>{route.constraints && <p className="muted small">Constraints: {value(route.constraints)}</p>}</>}</section>
    </div>
    <div className="route-provenance">PROVENANCE · {route.source || '—'} · VERIFIED VERSION · {route.verified_version || '—'}</div>
  </article>
}
function Metric({ label, value: item, tone }) { return <div className="metric"><span>{label}</span><strong className={tone || ''}>{item}</strong></div> }
function Raw({ label, item }) { return <div className="raw-row"><span>{label}</span><strong>{value(item)}</strong></div> }
function RouteSection({ title, items }) { return <section><h3>{title}</h3>{list(items).length ? <ul className="dense-list">{list(items).map((item, i) => <li key={i}>{value(item)}</li>)}</ul> : <p className="muted small">—</p>}</section> }
