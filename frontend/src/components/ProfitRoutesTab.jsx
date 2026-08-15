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
const ratioPercent = (item) => item == null ? '—' : `${(Number(item) * 100).toFixed(1)}%`
const tone = (item) => Number(item) < 0 ? 'negative' : 'positive'
const list = (items) => Array.isArray(items) ? items : items == null ? [] : [items]

export function ProfitRoutesTab({ categories = [], selectedLeague }) {
  const [routes, setRoutes] = useState([])
  const [category, setCategory] = useState('')
  const [patch, setPatch] = useState({ status: '', reasons: [] })
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState('')
  useEffect(() => {
    let cancelled = false
    if (!selectedLeague) {
      setRoutes([])
      setPatch({ status: '', reasons: [] })
      setError('')
      setLoading(false)
      return () => { cancelled = true }
    }
    setLoading(true)
    setError('')
    const params = { league: selectedLeague }
    if (category) params.category = category
    api.get('/profit-routes', { params })
      .then(({ data }) => {
        if (cancelled) return
        setRoutes(Array.isArray(data) ? data : data?.routes || [])
        setPatch({
          status: data?.patch_status || '',
          reasons: Array.isArray(data?.patch_reasons) ? data.patch_reasons : [],
        })
      })
      .catch((err) => { if (!cancelled) setError(err.response?.data?.detail || 'Profit routes unavailable.') })
      .finally(() => { if (!cancelled) setLoading(false) })
    return () => { cancelled = true }
  }, [selectedLeague, category])

  return <div className="terminal-page">
    <div className="page-head"><div><div className="eyebrow">MONEY PRINTER / CAPITAL DEPLOYMENT</div><h1>Profit Routes</h1><p className="muted">Backend-evaluated transformations ranked for capital deployment. Theoretical routes stay visible when executable depth or positive net profit is not verified.</p></div></div>
    <div className="terminal-panel strategy-form"><div className="form-row form-row-main"><label className="field"><span>Category</span><select className="input" value={category} onChange={(event) => setCategory(event.target.value)}><option value="">All categories</option>{categories.map((item) => <option key={item.id} value={item.id}>{item.name}</option>)}</select></label></div></div>
    {!selectedLeague && <div className="terminal-panel"><EmptyState title="Select a league" message="Profit routes wait for a selected league before requesting market data." /></div>}
    {selectedLeague && loading && <div className="terminal-panel"><LoadingState text="Loading profit routes…" /></div>}
    {selectedLeague && !loading && !error && patch.status !== 'resolved' && patch.reasons.length > 0 && <div className="terminal-panel"><div className="panel-title"><h2>Patch verification blocked</h2><span>STATUS · {patch.status.toUpperCase()}</span></div><ul className="dense-list">{patch.reasons.map((reason, index) => <li key={index}><span className="signal-mark" />{reason}</li>)}</ul></div>}
    {selectedLeague && !loading && !error && patch.status === 'resolved' && !routes.length && <div className="terminal-panel"><EmptyState title="No route evidence" message="No registered provider has enough market data to describe a route for this league and category." /></div>}
    {selectedLeague && !loading && !error && routes.length > 0 && <div className="profit-routes">{routes.map((route, index) => <RouteCard key={route.transformation_id || index} route={route} />)}</div>}
  </div>
}

function RouteCard({ route }) {
  const recommendation = route.cfo_recommendation || route.recommendation
  return <article className="terminal-panel profit-route">
    <div className="panel-title"><div><div className="eyebrow">{route.transformation_id || 'TRANSFORMATION'}</div><h2>{route.name || 'Unnamed route'}</h2></div><span>{route.status ? `STATUS · ${route.status.replaceAll('_', ' ').toUpperCase()}` : (route.source ? `SOURCE · ${route.source}` : 'BACKEND EVALUATION')}</span></div>
    <div className="route-metrics metric-grid">
      <Metric label="Status" value={route.status ? route.status.replaceAll('_', ' ') : '—'} />
      <Metric label="Expected net" value={value(route.expected_net_profit)} tone={tone(route.expected_net_profit)} />
      <Metric label="ROI" value={ratioPercent(route.roi)} tone={tone(route.roi)} />
      <Metric label="Theoretical ROI" value={ratioPercent(route.theoretical_roi)} />
      <Metric label="Executable ROI" value={ratioPercent(route.executable_roi)} tone={tone(route.executable_roi)} />
      <Metric label="Capital required" value={value(route.capital_required)} />
      <Metric label="Profit / hour" value={value(route.profit_per_hour)} tone={tone(route.profit_per_hour)} />
      <Metric label={`Capacity (${route.capacity_units || 'capital'})`} value={value(route.capacity)} />
      <Metric label="Sets / hour" value={value(route.estimated_sets_per_hour)} />
      <Metric label="Sets with budget" value={value(route.sets_possible_with_budget)} />
      <Metric label="Market capacity" value={value(route.market_capacity)} />
      <Metric label="Execution + sale" value={`${value(route.expected_execution_time)} + ${value(route.expected_sale_time)}`} />
    </div>
    <div className="route-columns">
      <RouteSection title="Inputs" items={route.inputs} /><RouteSection title="Costs" items={route.costs} /><RouteSection title="Outputs" items={route.outputs} />
      <section><h3>Economics</h3><div className="raw-grid route-raw"><Raw label="Total input cost" item={route.total_input_cost} /><Raw label="Realistic output value" item={route.realistic_output_value} /><Raw label="Gross profit" item={route.gross_profit} /><Raw label="Divine-hour profit" item={route.profit_per_divine_hour} /></div></section>
      <section><h3>Confidence / risk</h3><div className="raw-grid route-raw"><Raw label="Overall confidence" item={percent(route.confidence)} /><Raw label="Pricing confidence" item={percent(route.pricing_confidence)} /><Raw label="Strategy confidence" item={percent(route.strategy_confidence)} /><Raw label="Execution risk" item={value(route.execution_risk)} /></div></section>
    </div>
    <div className="route-bottom">
      <section><h3>Reasons</h3>{list(route.reasons).length ? <ul className="dense-list">{list(route.reasons).map((reason, i) => <li key={i}><span className="signal-mark" />{value(reason)}</li>)}</ul> : <p className="muted small">No reasons supplied.</p>}</section>
      <section><h3>Execution</h3>{route.execution_steps && <p className="small">{value(route.execution_steps)}</p>}<p className="muted small">Capacity: <strong>{value(route.capacity)}</strong> {route.capacity_units ? `(${route.capacity_units})` : ''} · Expected execution: <strong>{value(route.expected_execution_time)}</strong> · Expected sale: <strong>{value(route.expected_sale_time)}</strong></p>{route.capacity_horizon_hours > 0 && <p className="muted small">Repeatability horizon: <strong>{value(route.capacity_horizon_hours)}h</strong> · Assumptions: {value(route.capacity_assumptions)}</p>}{(recommendation || route.constraints) && <><h3 className="route-subhead">CFO guidance</h3><p className="small">{recommendation || '—'}</p>{route.constraints && <p className="muted small">Constraints: {value(route.constraints)}</p>}</>}</section>
    </div>
    <div className="route-provenance">PROVENANCE · {route.source || '—'} · VERIFIED VERSION · {route.verified_version || '—'}</div>
  </article>
}
function Metric({ label, value: item, tone }) { return <div className="metric"><span>{label}</span><strong className={tone || ''}>{item}</strong></div> }
function Raw({ label, item }) { return <div className="raw-row"><span>{label}</span><strong>{value(item)}</strong></div> }
function RouteSection({ title, items }) { return <section><h3>{title}</h3>{list(items).length ? <ul className="dense-list">{list(items).map((item, i) => <li key={i}>{value(item)}</li>)}</ul> : <p className="muted small">—</p>}</section> }
