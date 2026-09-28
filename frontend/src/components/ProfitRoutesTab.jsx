import { useEffect, useMemo, useState } from 'react'
import { api, fmtPrice } from '../lib/helpers'
import { EmptyState, ErrorState, LoadingState, LeagueEmpty } from './ui'

const list = (v) => Array.isArray(v) ? v : v == null ? [] : [v]
const text = (v) => v == null || v === '' ? '—' : typeof v === 'number' ? fmtPrice(v) : Array.isArray(v) ? v.map(text).join(', ') : typeof v === 'object' ? Object.entries(v).map(([k, x]) => `${k}: ${text(x)}`).join(' · ') : String(v)
const percent = (v) => v == null ? '—' : `${(Number(v) * 100).toFixed(1)}%`
const familyNames = { deterministic: 'Deterministic', divination_cards: 'Divination cards', conversions: 'Conversions', bounded_ev: 'Bounded EV', watch_unsupported: 'Watch / unsupported' }
const sectionNames = { best_actionable: 'Best actionable', deterministic: 'Deterministic', divination_cards: 'Divination cards', conversions: 'Conversions', bounded_ev: 'Bounded EV', watch_unsupported: 'Watch / unsupported' }

export function ProfitRoutesTab({ categories = [], selectedLeague }) {
  const [routes, setRoutes] = useState([]);
const [sections, setSections] = useState([]);
const [readiness, setReadiness] = useState(null);
const [planning, setPlanning] = useState(null)
  const [executions, setExecutions] = useState([]);
const [planner, setPlanner] = useState({ amount: '', currency: 'Chaos', horizon: '24', minimumSafeProfit: '', minimumRoi: '', maximumEffort: '', maximumLock: '', executionBias: '', family: '', lifecycle: '', deterministicOnly: false, sort: 'safe_profit_per_active_hour' });
const [requestPlan, setRequestPlan] = useState({ amount: '', currency: 'Chaos', horizon: '24', minimumSafeProfit: '', minimumRoi: '', maximumEffort: '', maximumLock: '', executionBias: '', family: '', lifecycle: '', deterministicOnly: false, sort: 'safe_profit_per_active_hour' })
  const [category, setCategory] = useState('');
const [patch, setPatch] = useState({ status: '', reasons: [] });
const [loading, setLoading] = useState(false);
const [error, setError] = useState('');
const [historyError, setHistoryError] = useState('');
const [historyLoading, setHistoryLoading] = useState(false);
const [historyRefresh, setHistoryRefresh] = useState(0)
  const query = requestPlan || planner
  useEffect(() => { let cancelled = false;
if (!selectedLeague) return () => { cancelled = true };
setLoading(true);
setError('');
const params = makeParams(selectedLeague, category, requestPlan)
    api.get('/profit-routes', { params }).then(({ data }) => { if (cancelled) return;
setRoutes(Array.isArray(data) ? data : data?.routes || []);
setSections(Array.isArray(data?.sections) ? data.sections : []);
setReadiness(data?.deterministic_readiness || null);
setPlanning(data?.planning || null);
setPatch({ status: data?.patch_status || '', reasons: Array.isArray(data?.patch_reasons) ? data.patch_reasons : [] }) }).catch((e) => { if (!cancelled) setError(e.response?.data?.detail || 'Profit routes unavailable.') }).finally(() => { if (!cancelled) setLoading(false) });
return () => { cancelled = true } }, [selectedLeague, category, requestPlan])
  useEffect(() => { let cancelled = false;
if (!selectedLeague) { setExecutions([]);
return () => { cancelled = true } };
setHistoryLoading(true);
setHistoryError('');
api.get('/profit-routes/executions').then(({ data }) => { if (!cancelled) setExecutions(Array.isArray(data) ? data : data?.executions || []) }).catch((e) => { if (!cancelled) { setExecutions([]);
setHistoryError(e.response?.data?.detail || 'Route execution journal unavailable.') } }).finally(() => { if (!cancelled) setHistoryLoading(false) });
return () => { cancelled = true } }, [selectedLeague, historyRefresh])
  // New filters make previous results stale; an in-place refresh keeps them visible.
  const clearResults = () => { setRoutes([]);
setSections([]);
setReadiness(null);
setPlanning(null);
setPatch({ status: '', reasons: [] }) }
  const submit = (e) => { e.preventDefault();
setError('');
clearResults();
setRequestPlan({ ...planner }) }
  const refresh = () => { setHistoryRefresh((x) => x + 1);
setRequestPlan((x) => x ? { ...x } : x) }
  const grouped = useMemo(() => { const map = new Map();
for (const route of routes) { const key = route.section || 'unclassified';
if (!map.has(key)) map.set(key, []);
map.get(key).push(route) } return map }, [routes])
  return <div className="terminal-page">
<div className="page-head">
<div>
<div className="eyebrow">RESEARCH / ROUTES</div>
<h1>Profit Routes</h1>
<p className="muted">Manual, advisory route planning from verified definitions and observed market evidence. No game or trade action is automated.</p>
</div>
</div>
    <form className="terminal-panel strategy-form" onSubmit={submit}>
<div className="form-row form-row-main">
<label className="field">
<span>Category</span>
<select className="input" value={category} onChange={(e) => { clearResults();
setCategory(e.target.value) }}>
<option value="">All registered families</option>{categories.filter((x) => x.id === 'DivinationCard').map((x) => <option key={x.id} value={x.id}>{x.name}</option>)}</select>
</label>
<label className="field">
<span>Budget currency</span>
<select className="input" value={planner.currency} onChange={(e) => setPlanner({ ...planner, currency: e.target.value })}>
<option>Chaos</option>
<option>Divine</option>
</select>
</label>
<label className="field">
<span>Budget amount</span>
<input className="input numeric" type="number" min="0.000001" step="any" value={planner.amount} onChange={(e) => setPlanner({ ...planner, amount: e.target.value })} placeholder="Optional" />
</label>
<label className="field">
<span>Horizon (hours)</span>
<input className="input numeric" type="number" min="0.000001" step="any" value={planner.horizon} onChange={(e) => setPlanner({ ...planner, horizon: e.target.value })} />
</label>
<label className="field">
<span>Min safe profit (Chaos)</span>
<input className="input numeric" type="number" min="0" step="any" value={planner.minimumSafeProfit} onChange={(e) => setPlanner({ ...planner, minimumSafeProfit: e.target.value })} />
</label>
<label className="field">
<span>Min ROI (%)</span>
<input className="input numeric" type="number" min="0" step="any" value={planner.minimumRoi} onChange={(e) => setPlanner({ ...planner, minimumRoi: e.target.value })} />
</label>
<label className="field">
<span>Max active effort (h)</span>
<input className="input numeric" type="number" min="0.000001" step="any" value={planner.maximumEffort} onChange={(e) => setPlanner({ ...planner, maximumEffort: e.target.value })} />
</label>
<label className="field">
<span>Max lock time (h)</span>
<input className="input numeric" type="number" min="0.000001" step="any" value={planner.maximumLock} onChange={(e) => setPlanner({ ...planner, maximumLock: e.target.value })} />
</label>
<label className="field">
<span>Family</span>
<select className="input" value={planner.family} onChange={(e) => setPlanner({ ...planner, family: e.target.value })}>
<option value="">All families</option>{Object.entries(familyNames).map(([k, v]) => <option key={k} value={k}>{v}</option>)}</select>
</label>
<label className="field">
<span>Lifecycle</span>
<select className="input" value={planner.lifecycle} onChange={(e) => setPlanner({ ...planner, lifecycle: e.target.value })}>
<option value="">All lifecycle states</option>
<option value="Validated">Validated</option>
<option value="Experimental">Experimental</option>
<option value="Rejected">Rejected</option>
</select>
</label>
<label className="field">
<span>Sort</span>
<select className="input" value={planner.sort} onChange={(e) => setPlanner({ ...planner, sort: e.target.value })}>
<option value="safe_profit_per_active_hour">Safe profit / active hour</option>
<option value="roi">ROI</option>
<option value="divine_per_hour">Divine / active hour</option>
</select>
</label>
<label className="field">
<span>Execution bias (%)</span>
<input className="input numeric" type="number" min="0" max="99.999999" step="any" value={planner.executionBias} onChange={(e) => setPlanner({ ...planner, executionBias: e.target.value })} />
</label>
<label className="field checkbox-field">
<span>Deterministic only</span>
<input type="checkbox" checked={planner.deterministicOnly} onChange={(e) => setPlanner({ ...planner, deterministicOnly: e.target.checked })} />
</label>
<button className="btn-primary" type="submit">PLAN ROUTES</button>
</div>
<p className="muted small">Budget is normalized only through the observed league-scoped Chaos/Divine rate. Divine planning stays disabled with an explicit blocker when that rate is unavailable.</p>
</form>
    {!selectedLeague && <div className="terminal-panel">
<LeagueEmpty />
</div>}{selectedLeague && loading && <div className="terminal-panel">
<LoadingState text="Loading profit routes…" />
</div>}{selectedLeague && !loading && error && <div className="terminal-panel">
<ErrorState message={error} onRetry={() => setRequestPlan((x) => x ? { ...x } : x)} />
</div>}
    {selectedLeague && !loading && !error && planning && <PlanningSummary planning={planning} filters={requestPlan} />}{selectedLeague && !loading && !error && patch.status !== 'resolved' && patch.reasons.length > 0 && <div className="terminal-panel warning-panel">
<div className="panel-title">
<h2>Patch verification blocked</h2>
<span>STATUS · {patch.status.toUpperCase()}</span>
</div>
<ul className="dense-list">{patch.reasons.map((x, i) => <li key={i}>
<span className="signal-mark" />{x}</li>)}</ul>
</div>}{selectedLeague && !loading && !error && readiness && <DeterministicReadiness readiness={readiness} />}
    {selectedLeague && !loading && !error && routes.length === 0 && sections.length === 0 && <EmptyState title="WAIT — no actionable route" message={sections.find((x) => x.key === 'watch_unsupported')?.reason || 'No route meets the selected budget, evidence, safety, and filter constraints.'} />}{selectedLeague && !error && (sections.length > 0 || routes.length > 0) && <div className="profit-routes">{(sections.length ? sections : Array.from(grouped.keys()).map((key) => ({ key }))).map((section) => <RouteSection key={section.key} section={section} routes={grouped.get(section.key) || []} league={selectedLeague} query={{ category, ...query }} executions={executions} onRefresh={refresh} onRefreshHistory={() => setHistoryRefresh((x) => x + 1)} />)}</div>}
    {selectedLeague && historyLoading && <div className="terminal-panel">
<LoadingState text="Loading route execution journal…" />
</div>}{selectedLeague && !historyLoading && historyError && <ErrorState message={historyError} onRetry={() => setHistoryRefresh((x) => x + 1)} />}{selectedLeague && !historyLoading && !historyError && <ExecutionHistory executions={executions} showIdentity onRefresh={refresh} />}</div>
}
function makeParams(league, category, p) { const params = { league, budget_amount: p.amount ? Number(p.amount) : undefined, budget_currency: p.currency, horizon_hours: p.horizon ? Number(p.horizon) : undefined, category: category || undefined, minimum_safe_profit_chaos: p.minimumSafeProfit ? Number(p.minimumSafeProfit) : undefined, minimum_roi_percent: p.minimumRoi ? Number(p.minimumRoi) : undefined, maximum_active_effort_hours: p.maximumEffort ? Number(p.maximumEffort) : undefined, maximum_lock_time_hours: p.maximumLock ? Number(p.maximumLock) : undefined, family: p.family || undefined, lifecycle: p.lifecycle || undefined, deterministic_only: p.deterministicOnly || undefined, execution_bias_percent: p.executionBias ? Number(p.executionBias) : undefined, sort: p.sort };
return Object.fromEntries(Object.entries(params).filter(([, v]) => v !== undefined && v !== '')) }
function PlanningSummary({ planning, filters }) { return <section className="terminal-panel">
<div className="panel-title">
<h2>Planning context</h2>
<span>{planning.normalization_blocker ? 'WAIT' : 'READY'}</span>
</div>
<div className="metric-grid">
<Metric label="Requested budget" value={`${text(planning.requested_amount)} ${planning.requested_currency || ''}`} />
<Metric label="Budget (Chaos)" value={text(planning.budget_chaos)} />
<Metric label="Chaos / Divine" value={text(planning.chaos_per_divine)} />
<Metric label="Rate provenance" value={planning.rate_provenance ? `${text(planning.rate_provenance.source)} · ${text(planning.rate_provenance.observed_at)} · ${text(planning.rate_provenance.observation_type)} · ${text(planning.rate_provenance.confidence_grade)} · max ${text(planning.rate_provenance.max_age_hours)}h` : "—"} />
</div>{planning.normalization_blocker && <p className="paper-note" role="status">{planning.normalization_blocker}</p>}{planning.applied_filters && <p className="muted small">Applied filters: {text(planning.applied_filters)} · Sort: {filters.sort}</p>}</section> }
function RouteSection({ section, routes, league, query, executions, onRefresh, onRefreshHistory }) { return <section className="terminal-panel route-section">
<div className="panel-title">
<h2>{sectionNames[section.key] || section.label || section.key}</h2>
<span>{routes.length} route{routes.length === 1 ? '' : 's'}</span>
</div>{routes.length ? <div className="table-wrap">
<table className="dense-table">
<thead>
<tr>
<th>Route</th>
<th>Status</th>
<th>Safe profit</th>
<th>ROI</th>
<th>Active h</th>
<th>Lock h</th>
<th>Capacity</th>
<th>Evidence</th>
<th />
</tr>
</thead>
<tbody>{routes.map((route, i) => <RouteRow key={route.transformation_id || i} route={route} league={league} query={query} executions={executions} onRefresh={onRefresh} onRefreshHistory={onRefreshHistory} />)}</tbody>
</table>
</div> : <p className="muted small">{section.reason || 'No route currently meets this section’s readiness and filter requirements.'}</p>}</section> }
function RouteRow({ route, league, query, executions, onRefresh, onRefreshHistory }) { const [open, setOpen] = useState(false);
return <>
<tr>
<td>
<button type="button" className="text-button row-toggle" aria-expanded={open} aria-label={`${open ? 'Collapse' : 'Expand'} ${route.name || 'route'} details`} onClick={() => setOpen((x) => !x)}>{open ? '−' : '+'}</button> <strong>{route.name || route.transformation_id}</strong>
<small>{route.strategy_family || 'transformation'} · {route.lifecycle || route.status || '—'}</small>
</td>
<td>{text(route.status)}</td>
<td className={Number(route.safe_edge_chaos) < 0 ? 'negative' : ''}>{text(route.safe_edge_chaos)} c</td>
<td>{percent(route.roi)}</td>
<td>{text(route.active_execution_time)}</td>
<td>{text(route.capital_lock_time)}</td>
<td>{text(route.recommended_capacity ?? route.capacity)} {route.capacity_units || ''}</td>
<td>{text(route.calibration?.sample_size ?? route.allocator_evidence?.sample_size ?? 0)} samples</td>
<td>
<button type="button" className="text-button" onClick={() => setOpen((x) => !x)}>{open ? 'HIDE' : 'DETAIL'}</button>
</td>
</tr>{open && <tr className="detail-row">
<td colSpan="9">
<RouteDetail route={route} league={league} query={query} executions={executions} onRefresh={onRefresh} onRefreshHistory={onRefreshHistory} />
</td>
</tr>}</> }
function RouteDetail({ route, league, query, executions, onRefresh, onRefreshHistory }) {
  const calibration = route.calibration || {}
  const evidence = route.allocator_evidence || {}
  return <div className="position-detail">
    <div className="metric-grid">
      <Metric label="Theoretical / executable / actual net" value={`${text(route.theoretical_net_profit)} / ${text(route.executable_net_profit)} / ${text(route.actual_net_profit)}`} />
      <Metric label="Safe edge / ROI per lock hour" value={`${text(route.safe_edge_chaos)} c / ${text(route.roi_per_lock_hour)}`} />
      <Metric label="Batch / binding constraint" value={`${text(route.batch_plan?.set_count)} · ${text(route.batch_plan?.binding_constraint)}`} />
      <Metric label="Allocator" value={`${evidence.tier || 'WATCH'} · ${evidence.eligible ? 'eligible' : 'not eligible'}`} />
    </div>
    <p className="small">Calibration: {calibration.applied ? `applied (${calibration.scope}, ${calibration.sample_size} samples)` : (calibration.fallback_reason || 'baseline unchanged')} · factors {text(calibration.factors)} · adjustments {text(calibration.adjustments_chaos)} · duration factor applies to elapsed lock time;
planned active effort is unchanged.</p>
    <p className="small">Safe-edge buffers: {text(route.safe_edge_adjustments)}</p>
    <div className="route-columns">
      <DetailList title="Inputs" items={route.inputs} />
      <DetailList title="Costs" items={route.costs} />
      <DetailList title="Outputs" items={route.outputs} />
    </div>
    <BatchPlan plan={route.batch_plan} />
    <EvidenceLegs legs={route.evidence_legs} />
    <p className="muted small">Reasons: {text(route.reasons)} · Provenance: {text(route.source)} · {text(route.verified_version)} · freshness: {text(route.verification_metadata?.quote_timestamps)}</p>
    <RouteEvidence route={route} league={league} query={query} executions={executions} onRefresh={onRefresh} onRefreshHistory={onRefreshHistory} />
  </div>
}
function DetailList({ title, items }) {
  return <section>
<h3>{title}</h3>{list(items).length ? <ul className="dense-list">{list(items).map((item, index) => <li key={index}>{text(item)}</li>)}</ul> : <p className="muted small">—</p>}</section>
}
function BatchPlan({ plan }) {
  if (!plan) return <p className="muted small">No executable batch plan;
read-only route.</p>
  return <div className="raw-grid route-raw">
    <Raw label="Budget / sets" item={`${text(plan.budget_chaos)} / ${text(plan.set_count)}`} />
    <Raw label="Exact inputs" item={plan.exact_cards_to_buy} />
    <Raw label="Expected outcomes" item={list(plan.expected_outcomes).map((x) => `${x.item || x.market_key}: ${text(x.expected_quantity)}`).join(' · ')} />
    <Raw label="Cost / revenue / net" item={`${text(plan.executable_cost_chaos)} / ${text(plan.executable_revenue_chaos)} / ${text(plan.executable_net_chaos)} c`} />
    <Raw label="Effort / lock" item={`${text(plan.active_effort_hours)}h / ${text(plan.lock_time_min_hours)}–${text(plan.lock_time_max_hours)}h`} />
    <Raw label="Binding constraint" item={plan.binding_constraint} />
    {list(plan.trade_links).map((link) => <p key={`${link.side}-${link.market_key}`}>
<a href={link.url} target="_blank" rel="noreferrer">OPEN {String(link.side || '').toUpperCase()} SEARCH · {link.item || link.market_key}</a>
</p>)}
  </div>
}
function EvidenceLegs({ legs }) {
  const items = list(legs)
  return <details className="progressive">
<summary>Per-leg provenance ({items.length})</summary>{items.length ? <div className="table-wrap">
<table className="dense-table">
<thead>
<tr>
<th>Market key</th>
<th>Role / quote</th>
<th>Source / observation</th>
<th>Quote</th>
<th>Observed / market</th>
<th>Freshness</th>
<th>Confidence</th>
<th>Blocker</th>
</tr>
</thead>
<tbody>{items.map((x, i) => <tr key={i}>
<td>{text(x.market_key)}</td>
<td>{text(x.role)} / {text(x.quote_side)}</td>
<td>{text(x.source)} / {text(x.observation_type)}</td>
<td>{text(x.quote_kind)} · grade {text(x.confidence_grade)}</td>
<td>{text(x.observed_at)} / {text(x.market_timestamp)}</td>
<td>{text(x.freshness_state)}{x.max_age_hours != null ? ` · max ${text(x.max_age_hours)}h` : ''}</td>
<td>{percent(x.confidence)}</td>
<td>{text(x.blocker)}</td>
</tr>)}</tbody>
</table>
</div> : <p className="muted small">No evidence legs supplied.</p>}</details>
}
function RouteEvidence({ route, league, query, executions, onRefresh, onRefreshHistory }) { const [pending, setPending] = useState(null);
const [kind, setKind] = useState('paper');
const [actuals, setActuals] = useState({ cost: route.batch_plan?.executable_cost_chaos ?? '', revenue: route.batch_plan?.executable_revenue_chaos ?? '', duration: route.batch_plan?.lock_time_max_hours ?? '' });
const [message, setMessage] = useState('');
const [busy, setBusy] = useState(false);
const planner = { league, transformation_id: route.transformation_id, snapshot_id: route.snapshot_id, execution_kind: kind, batch_count: route.batch_plan?.set_count, ...makeParams(league, query.category, query) };
async function capture(e) { e.preventDefault();
if (busy) return;
setBusy(true);
setMessage('');
try { const { data } = await api.post('/profit-routes/executions/capture', planner);
setPending(data.execution);
setActuals({ cost: data.execution.predicted_cost_chaos ?? '', revenue: data.execution.predicted_revenue_chaos ?? '', duration: data.execution.predicted_duration_hours ?? '' });
onRefreshHistory();
setMessage('Captured. Complete only after the manual batch is finished.') } catch (err) { setMessage(err.response?.data?.detail || 'Capture failed.') } finally { setBusy(false) } } async function complete(e) { e.preventDefault();
try { await api.post(`/profit-routes/executions/${pending.id}/complete`, { actual_cost_chaos: Number(actuals.cost), actual_revenue_chaos: Number(actuals.revenue), actual_duration_hours: Number(actuals.duration) });
setPending(null);
setMessage('Completed observation recorded.');
onRefresh() } catch (err) { setMessage(err.response?.data?.detail || 'Completion failed.') } } if (!route.batch_plan || !route.snapshot_id) return <p className="muted small">No executable captured batch is available;
this route remains read-only.</p>;
return <section className="route-evidence">
<h3>Empirical evidence · {route.allocator_evidence?.tier || 'WATCH'} · {route.allocator_evidence?.sample_size || 0} samples</h3>{!pending ? <form onSubmit={capture}>
<p className="muted small">Manual confirmation only;
no game or trade request is sent.</p>
<div className="form-row">
<label className="field">
<span>Execution</span>
<select className="input" value={kind} onChange={(e) => setKind(e.target.value)}>
<option value="paper">Paper</option>
<option value="actual">Actual</option>
</select>
</label>
<label className="field">
<span>Selected batch ({route.capacity_units || 'units'})</span>
<strong>{route.batch_plan.set_count}</strong>
</label>
<button className="btn-secondary" disabled={busy} type="submit">{busy ? 'CAPTURING…' : 'CAPTURE BATCH'}</button>
</div>
</form> : <form onSubmit={complete}>
<p className="muted small">
<strong>Pending:</strong> {pending.batch_count} · quoted plan totals prefilled;
confirm actual result.</p>
<div className="form-row">
<label className="field">
<span>Actual cost (Chaos)</span>
<input required className="input numeric" type="number" min="0.000001" step="any" value={actuals.cost} onChange={(e) => setActuals({ ...actuals, cost: e.target.value })} />
</label>
<label className="field">
<span>Actual revenue (Chaos)</span>
<input required className="input numeric" type="number" min="0" step="any" value={actuals.revenue} onChange={(e) => setActuals({ ...actuals, revenue: e.target.value })} />
</label>
<label className="field">
<span>Actual elapsed hours</span>
<input required className="input numeric" type="number" min="0" step="any" value={actuals.duration} onChange={(e) => setActuals({ ...actuals, duration: e.target.value })} />
</label>
<button className="btn-primary" type="submit">CONFIRM COMPLETED RESULT</button>
</div>
</form>}{message && <p className="paper-note" role="status">{message}</p>}<ExecutionHistory executions={(executions || []).filter((x) => x.league === league && x.opportunity_id === route.transformation_id && x.route_version === (route.verification_metadata?.registry_version || route.verified_version) && x.poe_patch === route.poe_patch)} onRefresh={onRefresh} />
</section> }
function ExecutionHistory({ executions = [], showIdentity = false, onRefresh }) { return <section className="execution-history">
<h4>Recent route observations</h4>{executions.length ? <div className="table-wrap">
<table className="dense-table">
<thead>
<tr>
<th>Status</th>
<th>Kind</th>{showIdentity && <>
<th>League</th>
<th>Route</th>
</>}<th>Batch</th>
<th>Actual totals</th>
<th>Duration</th>
<th>Recorded</th>
</tr>
</thead>
<tbody>{executions.map((x) => <ExecutionRow key={x.id} item={x} showIdentity={showIdentity} onRefresh={onRefresh} />)}</tbody>
</table>
</div> : <p className="muted small">No captured or completed observations.</p>}</section> }
function ExecutionRow({ item, showIdentity = false, onRefresh }) { const [editing, setEditing] = useState(false);
const [error, setError] = useState('');
const [form, setForm] = useState({ cost: item.actual_cost_chaos ?? '', revenue: item.actual_revenue_chaos ?? '', duration: item.actual_duration_hours ?? '' });
const save = async (e) => { e.preventDefault();
setError('');
try { await api[editing ? 'patch' : 'post'](`/profit-routes/executions/${item.id}${editing ? '' : '/complete'}`, { actual_cost_chaos: Number(form.cost), actual_revenue_chaos: Number(form.revenue), actual_duration_hours: Number(form.duration) });
setEditing(false);
onRefresh() } catch (err) { setError(err.response?.data?.detail || 'Observation update failed.') } };
const invalidate = async () => { const reason = window.prompt('Why is this observation invalid?');
if (!reason?.trim()) return;
setError('');
try { await api.post(`/profit-routes/executions/${item.id}/invalidate`, { reason: reason.trim() });
onRefresh() } catch (err) { setError(err.response?.data?.detail || 'Invalidation failed.') } };
return <tr>
<td>{item.status || '—'}</td>
<td>{item.execution_kind || '—'}</td>{showIdentity && <>
<td>{item.league}</td>
<td>{item.opportunity_id}</td>
</>}<td>{text(item.batch_count)} {item.quantity_unit || ''}</td>
<td>{item.actual_cost_chaos == null ? '—' : `${text(item.actual_cost_chaos)} → ${text(item.actual_revenue_chaos)} c`}</td>
<td>{text(item.actual_duration_hours)}h</td>
<td>{text(item.completed_at || item.captured_at)} {item.status === 'pending' && <form className="execution-correction" onSubmit={save}>
<input aria-label="Actual cost" required type="number" min="0.000001" step="any" value={form.cost} onChange={(e) => setForm({ ...form, cost: e.target.value })} />
<input aria-label="Actual revenue" required type="number" min="0" step="any" value={form.revenue} onChange={(e) => setForm({ ...form, revenue: e.target.value })} />
<input aria-label="Actual duration" required type="number" min="0" step="any" value={form.duration} onChange={(e) => setForm({ ...form, duration: e.target.value })} />
<button className="text-button" type="submit">COMPLETE</button>
</form>}{!item.invalidated_at && item.status === 'completed' && <>
<button className="text-button" type="button" onClick={() => setEditing(!editing)}>{editing ? 'HIDE' : 'CORRECT'}</button>
<button className="text-button" type="button" onClick={invalidate}>INVALIDATE</button>
</>}{!item.invalidated_at && item.status === 'pending' && <button className="text-button" type="button" onClick={invalidate}>INVALIDATE</button>}{editing && <form className="execution-correction" onSubmit={save}>
<input aria-label="Correct cost" required type="number" min="0.000001" step="any" value={form.cost} onChange={(e) => setForm({ ...form, cost: e.target.value })} />
<input aria-label="Correct revenue" required type="number" min="0" step="any" value={form.revenue} onChange={(e) => setForm({ ...form, revenue: e.target.value })} />
<input aria-label="Correct duration" required type="number" min="0" step="any" value={form.duration} onChange={(e) => setForm({ ...form, duration: e.target.value })} />
<button className="text-button" type="submit">SAVE</button>
</form>}{error && <small className="negative" role="alert">{error}</small>}</td>
</tr> }
function DeterministicReadiness({ readiness }) { const families = readiness.families || {};
return <section className="terminal-panel">
<div className="panel-title">
<h2>Provider readiness</h2>
<span>{readiness.registry?.version || 'BACKEND STATUS'}</span>
</div>
<div className="metric-grid">{Object.entries(families).map(([key, x]) => <div className="metric" key={key}>
<span>{familyNames[key] || key}</span>
<strong>{x.state || '—'}</strong>
<small>{x.accepted_count ?? 0} accepted · {x.rejected_count ?? 0} rejected</small>{list(x.reasons).map((r, i) => <small key={i}>{r}</small>)}</div>)}</div>
</section> }
function Metric({ label, value }) { return <div className="metric">
<span>{label}</span>
<strong>{value}</strong>
</div> };
function Raw({ label, item }) { return <div className="raw-row">
<span>{label}</span>
<strong>{text(item)}</strong>
</div> }
