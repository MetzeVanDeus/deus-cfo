import { Fragment, useEffect, useMemo, useState } from 'react'
import { api, fmtTime } from '../lib/helpers'
import { ErrorState, LoadingState } from './ui'

const initialBankroll = { total_net_worth: 0, liquid_currency: 0, currently_invested: 0, reserved_capital: 0 }
const initialPreferences = { risk_tolerance: 'medium', desired_horizon_hours: 12, minimum_liquidity: 'medium', maximum_effort: 'medium', minimum_reserve_percent: 20, minimum_reserve_amount: 0, max_single_position_percent: 30, max_category_exposure_percent: 50, max_correlated_exposure_percent: 50 }
const presets = {
  conservative: { risk_tolerance: 'low', desired_horizon_hours: 6, minimum_liquidity: 'high', maximum_effort: 'low', minimum_reserve_percent: 30, max_single_position_percent: 15, max_category_exposure_percent: 35, max_correlated_exposure_percent: 25 },
  balanced: initialPreferences,
  opportunistic: { risk_tolerance: 'high', desired_horizon_hours: 24, minimum_liquidity: 'low', maximum_effort: 'high', minimum_reserve_percent: 10, max_single_position_percent: 40, max_category_exposure_percent: 60, max_correlated_exposure_percent: 50 },
}
const divine = (value) => value == null || Number.isNaN(Number(value)) ? '—' : `${Number(value).toFixed(2)}d`
const chaos = (value) => value == null || Number.isNaN(Number(value)) ? '—' : `${Number(value).toFixed(2)}c`
const percent = (value) => value == null || Number.isNaN(Number(value)) ? '—' : `${(Number(value) * 100).toFixed(1)}%`
const plainPercent = (value, digits = 1) => value == null || Number.isNaN(Number(value)) ? '—' : `${Number(value).toFixed(digits)}%`
const title = (value) => String(value || '').replaceAll('_', ' ')
const exitText = (value) => Array.isArray(value) ? value.map(chaos).join('–') : chaos(value)

export function CFOTab({ selectedLeague }) {
  const [bankroll, setBankroll] = useState(() => JSON.parse(localStorage.getItem('deuscfo.bankroll') || 'null') || initialBankroll)
  const [preferences, setPreferences] = useState(() => JSON.parse(localStorage.getItem('deuscfo.preferences') || 'null') || initialPreferences)
  const [mode, setMode] = useState('PAPER')
  const [hours, setHours] = useState(24)
  const [simulations, setSimulations] = useState(2000)
  const [plan, setPlan] = useState(null)
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState('')
  const [advanced, setAdvanced] = useState(false)
  const [portfolioId, setPortfolioId] = useState(() => localStorage.getItem('deuscfo.paperPortfolioId') || '')
  const [usePaperBankroll, setUsePaperBankroll] = useState(() => Boolean(localStorage.getItem('deuscfo.paperPortfolioId')))
  const [portfolio, setPortfolio] = useState(null)
  const [portfolioLoading, setPortfolioLoading] = useState(false)
  const [portfolioError, setPortfolioError] = useState('')
  const [journal, setJournal] = useState([])
  const [journalError, setJournalError] = useState('')
  const [trades, setTrades] = useState([])
  const [manualTrades, setManualTrades] = useState([])
  const [realForm, setRealForm] = useState({ opportunity_id: '', quantity: '', predicted_entry_price: '', actual_entry_price: '', predicted_exit_price: '', actual_exit_price: '', predicted_duration_hours: '', actual_duration_hours: '', confidence: '', chaos_per_divine: '' })
  const [realMessage, setRealMessage] = useState('')
  const [realizeMessage, setRealizeMessage] = useState('')
  const [realizeForms, setRealizeForms] = useState({})

  useEffect(() => { localStorage.setItem('deuscfo.bankroll', JSON.stringify(bankroll)) }, [bankroll])
  useEffect(() => { localStorage.setItem('deuscfo.preferences', JSON.stringify(preferences)) }, [preferences])
  useEffect(() => { loadJournal() }, [])
  useEffect(() => { if (portfolioId) loadPortfolio(portfolioId) }, [portfolioId])
  useEffect(() => { setUsePaperBankroll(Boolean(portfolioId)) }, [portfolioId])

  const updateBankroll = (key, value) => setBankroll((current) => ({ ...current, [key]: value === '' ? '' : Number(value) }))
  const updatePreference = (key, value) => setPreferences((current) => ({ ...current, [key]: ['minimum_reserve_percent', 'max_single_position_percent', 'max_category_exposure_percent', 'max_correlated_exposure_percent'].includes(key) ? Number(value) : value }))
  const applyPreset = (preset) => setPreferences({ ...presets[preset] })

  async function runPlan(event) {
    event.preventDefault(); setLoading(true); setError(''); setPlan(null)
    try {
      const response = await api.post('/capital/plan', {
        league: selectedLeague,
        bankroll: { ...bankroll, currency: 'Divine' },
        ...(usePaperBankroll && portfolioId ? { portfolio_id: Number(portfolioId) } : {}),
        preferences: { ...preferences, minimum_reserve_percent: Number(preferences.minimum_reserve_percent) / 100, max_single_position_percent: Number(preferences.max_single_position_percent) / 100, max_category_exposure_percent: Number(preferences.max_category_exposure_percent) / 100, max_correlated_exposure_percent: Number(preferences.max_correlated_exposure_percent) / 100 },
        mode, hours: Number(hours), seed: 0, simulations: Number(simulations),
      })
      setPlan(response.data)
      if (usePaperBankroll && response.data.bankroll) {
        setBankroll((current) => ({ ...current, ...response.data.bankroll }))
      }
      setRealForm((current) => ({ ...current, chaos_per_divine: response.data.chaos_per_divine ?? '' }))
      loadJournal()
    } catch (err) { setError(err.response?.data?.detail || 'Capital plan unavailable. Check the connection and inputs.') }
    finally { setLoading(false) }
  }

  async function loadJournal() {
    try { const response = await api.get('/journal/recommendations'); setJournal(Array.isArray(response.data) ? response.data : []) }
    catch (err) { setJournalError('Recommendation journal unavailable') }
  }
  async function createPortfolio() {
    setPortfolioLoading(true); setPortfolioError('')
    try {
      if (!(Number(plan?.chaos_per_divine) > 0)) throw new Error('Run a current capital plan before creating a paper portfolio')
      const response = await api.post('/paper/portfolios', { initial_bankroll: Number(bankroll.total_net_worth) || 0, chaos_per_divine: Number(plan.chaos_per_divine), name: 'default' })
      const id = String(response.data.portfolio_id); localStorage.setItem('deuscfo.paperPortfolioId', id); setPortfolioId(id)
    } catch (err) { setPortfolioError(err.response?.data?.detail || err.message || 'Paper portfolio could not be created') }
    finally { setPortfolioLoading(false) }
  }
  async function loadPortfolio(id) {
    setPortfolioLoading(true); setPortfolioError('')
    try {
      const [status, positions, equity, performance] = await Promise.all([api.get(`/paper/portfolios/${id}/status`), api.get(`/paper/portfolios/${id}/positions`), api.get(`/paper/portfolios/${id}/equity`), api.get(`/paper/portfolios/${id}/performance`)])
      const [linked, manual] = await Promise.allSettled([api.get(`/paper/portfolios/${id}/trades`), api.get('/paper/trades/real')])
      setPortfolio({ status: status.data, positions: positions.data, equity: equity.data, performance: performance.data })
      setTrades(linked.status === 'fulfilled' && Array.isArray(linked.value.data) ? linked.value.data : [])
      setManualTrades(manual.status === 'fulfilled' && Array.isArray(manual.value.data) ? manual.value.data : [])
    } catch (err) { if (err.response?.status === 404) { localStorage.removeItem('deuscfo.paperPortfolioId'); setPortfolioId('') } setPortfolioError(err.response?.data?.detail || 'Paper portfolio unavailable') }
    finally { setPortfolioLoading(false) }
  }
  function forgetPortfolio() { localStorage.removeItem('deuscfo.paperPortfolioId'); setPortfolioId(''); setPortfolio(null); setTrades([]); setManualTrades([]) }
  async function addToPaper(position) {
    if (!portfolioId) { setPortfolioError('Create a paper portfolio before adding a recommendation'); return }
    if (!plan?.chaos_per_divine) { setPortfolioError('Plan did not return a chaos-per-Divine conversion; paper entry was not created'); return }
    setPortfolioError('')
    try {
      await api.post(`/paper/portfolios/${portfolioId}/positions`, { opportunity_id: position.opportunity_id, quantity: Number(position.estimated_quantity), entry_price: Number(position.target_entry_chaos), predicted_exit_price: Array.isArray(position.target_exit_chaos) ? Number(position.target_exit_chaos.at(-1)) : (position.target_exit_chaos == null ? null : Number(position.target_exit_chaos)), predicted_duration_hours: position.time_exit_hours || position.expected_duration, predicted_profit: Number(position.expected_profit || 0) * Number(plan.chaos_per_divine), recommendation_id: plan.recommendation_id || null }); await loadPortfolio(portfolioId)
    } catch (err) { setPortfolioError(err.response?.data?.detail || 'Paper position was not added') }
  }
  async function realizePosition(position, values) {
    setRealizeMessage('')
    try {
      await api.post(`/paper/positions/${position.id}/realize`, {
        exit_price: Number(values.exit_price),
        actual_entry_price: Number(values.actual_entry_price),
        quantity: Number(values.quantity),
        ...(values.actual_duration_hours === '' ? {} : { actual_duration_hours: Number(values.actual_duration_hours) }),
        ...(values.confidence === '' ? {} : { confidence: Number(values.confidence) }),
      })
      setRealizeMessage(`Realized ${position.opportunity_id}; portfolio reloaded.`)
      await loadPortfolio(portfolioId)
    } catch (err) { setRealizeMessage(err.response?.data?.detail || 'Position was not realized') }
  }
  async function correctTrade(trade, values) {
    setRealizeMessage('')
    try {
      await api.patch(`/paper/trades/${trade.id}`, {
        quantity: Number(values.quantity),
        actual_entry_price: Number(values.actual_entry_price),
        actual_exit_price: Number(values.actual_exit_price),
        actual_duration_hours: Number(values.actual_duration_hours),
        confidence: values.confidence === '' ? null : Number(values.confidence),
      })
      setRealizeMessage(`Corrected linked trade ${trade.id}; portfolio reloaded.`)
      await loadPortfolio(portfolioId)
      return true
    } catch (err) {
      setRealizeMessage(err.response?.data?.detail || 'Linked trade was not corrected')
      return false
    }
  }
  async function recordReal(event) {
    event.preventDefault(); setRealMessage('')
    if (!(Number(realForm.chaos_per_divine) > 0)) { setRealMessage('Enter a positive chaos-per-Divine rate from the trade timestamp.'); return }
    try {
      await api.post('/paper/trades/real', { ...Object.fromEntries(Object.entries(realForm).map(([key, value]) => [key, key === 'opportunity_id' ? value : Number(value)])), confidence: Number(realForm.confidence) })
      setRealMessage('Recorded for calibration only; no order was placed.')
      if (portfolioId) await loadPortfolio(portfolioId)
    } catch (err) { setRealMessage(err.response?.data?.detail || 'Realized trade was not recorded') }
  }
  const expected = plan?.simulation?.expected_profit
  const probability = plan?.simulation?.probability_profitable
  const allocation = useMemo(() => { if (!plan?.bankroll?.liquid_currency) return { deployed: 0, reserve: 0, free: 100 }; const total = plan.bankroll.liquid_currency; return { deployed: Math.min(100, plan.deployed / total * 100), reserve: Math.min(100, plan.reserve / total * 100), free: Math.max(0, plan.unallocated / total * 100) } }, [plan])

  return <div className="terminal-page">
    <div className="page-head"><div><div className="eyebrow">CAPITAL OFFICE / PLAN</div><h1>CFO</h1><p className="muted">PAPER is the safe default: ideas can be simulated, but DeusCFO never executes trades. Bankroll values are Divine.</p></div><div className="market-state"><span className="status-dot" /> MARKET STATE <strong>{plan ? (plan.positions?.length ? 'SELECTIVE' : 'QUIET') : 'UNASSESSED'}</strong></div></div>
    <PlanForm {...{ selectedLeague, mode, setMode, hours, setHours, simulations, setSimulations, bankroll, updateBankroll, preferences, updatePreference, presets, applyPreset, advanced, setAdvanced, loading, runPlan, portfolioId, usePaperBankroll, setUsePaperBankroll }} />
    {loading && <LoadingState text="Evaluating validated opportunities…" />}{error && <ErrorState message={error} />}{plan && !loading && <PlanView plan={plan} allocation={allocation} expected={expected} probability={probability} portfolioId={portfolioId} addToPaper={addToPaper} />}{!plan && !loading && !error && <div className="terminal-panel empty-panel"><div className="eyebrow">NO PLAN RUN</div><p>Run PAPER after backfill to see exploratory Currency Exchange ideas alongside any validated capital positions.</p></div>}
    <PaperPortfolio {...{ bankroll, portfolioId, portfolio, portfolioLoading, portfolioError, createPortfolio, forgetPortfolio, realForm, setRealForm, recordReal, realMessage, trades, manualTrades, realizePosition, correctTrade, realizeMessage }} />
    <RecommendationJournal journal={journal} error={journalError} />
  </div>
}
function PlanForm({ selectedLeague, mode, setMode, hours, setHours, simulations, setSimulations, bankroll, updateBankroll, preferences, updatePreference, presets, applyPreset, advanced, setAdvanced, loading, runPlan, portfolioId, usePaperBankroll, setUsePaperBankroll }) {
  return <form className="terminal-panel plan-form" onSubmit={runPlan}>
    <div className="form-row form-row-main"><Field label="Shared league"><div className="input">{selectedLeague || 'Choose shared league above'}</div></Field><Field label="Plan mode"><select className="input" value={mode} onChange={(e) => setMode(e.target.value)}><option>OBSERVE</option><option>PAPER</option><option>AGGRESSIVE-PAPER</option><option>LIVE-CANDIDATE</option></select></Field><Field label="Horizon (hours)"><input className="input numeric" type="number" min="1" value={hours} onChange={(e) => setHours(e.target.value)} /></Field><Field label="Simulations"><input className="input numeric" type="number" min="1" max="10000" value={simulations} onChange={(e) => setSimulations(e.target.value)} /></Field></div>
    <div className="form-section-label">BANKROLL · DIVINE {portfolioId && <label className="small"><input type="checkbox" checked={usePaperBankroll} onChange={(e) => setUsePaperBankroll(e.target.checked)} /> Use paper portfolio bankroll</label>}</div>
    <div className="form-row bankroll-grid">{[['total_net_worth','Net worth'],['liquid_currency','Liquid currency'],['currently_invested','Currently invested'],['reserved_capital','Reserved capital']].map(([key,label]) => <Field key={key} label={label}><input className="input numeric" type="number" min="0" step="any" value={bankroll[key]} onChange={(e) => updateBankroll(key, e.target.value)} /></Field>)}</div>
    <div className="form-section-label preference-label"><span>PREFERENCES</span><div className="preset-buttons">{Object.keys(presets).map((preset) => <button type="button" key={preset} className="text-button" onClick={() => applyPreset(preset)}>{preset}</button>)}</div></div>
    <div className="form-row preference-grid"><Field label="Risk"><select className="input" value={preferences.risk_tolerance} onChange={(e) => updatePreference('risk_tolerance', e.target.value)}><option>low</option><option>medium</option><option>high</option></select></Field><Field label="Min liquidity"><select className="input" value={preferences.minimum_liquidity} onChange={(e) => updatePreference('minimum_liquidity', e.target.value)}><option>low</option><option>medium</option><option>high</option></select></Field><Field label="Max effort"><select className="input" value={preferences.maximum_effort} onChange={(e) => updatePreference('maximum_effort', e.target.value)}><option>low</option><option>medium</option><option>high</option></select></Field><Field label="Reserve %"><input className="input numeric" type="number" min="0" max="100" value={preferences.minimum_reserve_percent} onChange={(e) => updatePreference('minimum_reserve_percent', e.target.value)} /></Field></div>
    <details className="advanced" open={advanced} onToggle={(e) => setAdvanced(e.currentTarget.open)}><summary>Advanced constraints</summary><div className="form-row advanced-grid">{[['minimum_reserve_amount','Reserve floor (d)'],['max_single_position_percent','Max single %'],['max_category_exposure_percent','Max category %'],['max_correlated_exposure_percent','Max correlated %']].map(([key,label]) => <Field key={key} label={label}><input className="input numeric" type="number" min="0" max={key.includes('percent') ? '100' : undefined} step="any" value={preferences[key]} onChange={(e) => updatePreference(key, e.target.value)} /></Field>)}</div></details>
    <div className="form-actions"><span className="muted small">{mode === 'OBSERVE' ? 'OBSERVE returns analysis only; positions are never executed.' : mode === 'AGGRESSIVE-PAPER' ? 'AGGRESSIVE-PAPER simulates larger positions from reconstructed evidence; it never authorizes live trades.' : 'Backend may safely downgrade mode when evidence thresholds are unmet.'}</span><button className="btn-primary" disabled={loading || !selectedLeague}>{loading ? 'BUILDING PLAN…' : 'RUN CAPITAL PLAN'}</button></div>
  </form>
}
function Field({ label, children }) { return <label className="field"><span>{label}</span>{children}</label> }

function PlanView({ plan, allocation, expected, probability, portfolioId, addToPaper }) {
  const honest = plan.mode === 'OBSERVE' && plan.recommendation === 'WAIT'
  return <div className="plan-output animate-fade-in">
    <section className={`decision ${plan.recommendation === 'DEPLOY' ? 'decision-deploy' : 'decision-wait'}`}>
      <div><div className="eyebrow">RECOMMENDATION</div><div className="decision-word">{plan.recommendation}</div><p>{honest ? 'No validated opportunity currently clears the evidence and constraint gates.' : plan.reason}</p></div>
      <div className="decision-meta">{plan.mode_downgraded && <span>requested mode <strong>{plan.requested_mode}</strong></span>}<span>effective mode <strong>{plan.mode}</strong></span><span>objective <strong>{title(plan.objective)}</strong></span></div>
    </section>
    <PaperIdeas ideas={plan.paper_ideas} warning={plan.evidence_warning} />
    <section className="metric-grid"><Metric label="Net worth" value={divine(plan.bankroll?.total_net_worth)} /><Metric label="Deployed" value={divine(plan.deployed)} tone={plan.deployed ? 'positive' : ''} /><Metric label="Reserve" value={divine(plan.reserve)} /><Metric label="Expected profit" value={divine(expected)} tone={expected > 0 ? 'positive' : ''} /><Metric label="Portfolio probability" value={percent(probability)} /><Metric label="Market state" value={plan.positions?.length ? 'SELECTIVE' : (plan.paper_ideas?.length ? 'EXPLORATORY' : 'WAIT')} /></section>
    <div className="output-grid"><section className="terminal-panel"><PanelTitle>Recommended actions <span>{plan.positions?.length || 0}</span></PanelTitle>{plan.positions?.length ? <PositionTable positions={plan.positions} portfolioId={portfolioId} addToPaper={addToPaper} /> : <EmptyCopy text="No validated position is recommended. Exploratory paper ideas and rejected records remain separate from deployment decisions." />}</section><section className="terminal-panel"><PanelTitle>Outcome distribution</PanelTitle><OutcomeDistribution simulation={plan.simulation} /></section></div>
    <div className="output-grid"><section className="terminal-panel"><PanelTitle>Allocation · Divine</PanelTitle><div className="allocation-bar"><i className="alloc-deployed" style={{ width: `${allocation.deployed}%` }} /><i className="alloc-reserve" style={{ width: `${allocation.reserve}%` }} /><i className="alloc-free" style={{ width: `${allocation.free}%` }} /></div><div className="allocation-legend"><span><b className="legend deployed" /> Deployed {divine(plan.deployed)}</span><span><b className="legend reserve" /> Reserve {divine(plan.reserve)}</span><span><b className="legend free" /> Unallocated {divine(plan.unallocated)}</span></div></section><Watchlist watchlist={plan.watchlist} /></div>
    <details className="progressive"><summary>Reasoning and raw plan statistics</summary><div className="raw-grid"><div><h3>Objective components</h3>{Object.entries(plan.objective_components || {}).map(([key,value]) => <div className="raw-row" key={key}><span>{title(key)}</span><strong>{typeof value === 'number' ? value.toFixed(4) : value}</strong></div>)}</div><div><h3>Opportunity tiers / rejected</h3>{Object.entries(plan.opportunity_tiers || {}).map(([key,value]) => <div className="raw-row" key={key}><span>{key}</span><strong>{value}</strong></div>)}{Object.entries(plan.rejected || {}).slice(0,8).map(([key,value]) => <div className="raw-row" key={key}><span>{key}</span><strong>{title(value)}</strong></div>)}</div></div></details>
  </div>
}
function PaperIdeas({ ideas = [], warning }) {
  if (!ideas.length) return null
  return <section className="terminal-panel paper-ideas">
    <div className="panel-title"><h2>Currency Exchange paper ideas <span>{ideas.length}</span></h2><span className="confidence-pill">LOW CONFIDENCE</span></div>
    <p className="paper-ideas-warning">{warning || 'Exploratory only. These direct hourly quotes have not passed a validated profitability backtest.'}</p>
    <div className="table-wrap"><table className="dense-table paper-ideas-table">
      <thead><tr><th>Idea</th><th>Current</th><th>Reference</th><th>Gap</th><th>Liquidity</th><th>Evidence</th></tr></thead>
      <tbody>{ideas.map((idea) => <tr key={idea.item_id}>
        <td><strong>{idea.item_name}</strong><small>{idea.action || 'PAPER BUY WATCH'} · against Chaos Orb</small></td>
        <td className="numeric"><strong>{chaos(idea.current_price_chaos)}</strong><small>current direct quote</small></td>
        <td className="numeric">{chaos(idea.reference_price_chaos)}<small>prior hourly median</small></td>
        <td className="numeric warning">{plainPercent(idea.mean_reversion_gap_percent)}<small>potential reversion, not EV</small></td>
        <td className="numeric">{Number(idea.latest_volume || 0).toLocaleString()}<small>{idea.liquidity} · {idea.hourly_samples} samples</small></td>
        <td><span className="evidence-direct">DIRECT</span><small>{idea.reason}</small></td>
      </tr>)}</tbody>
    </table></div>
  </section>
}
function Metric({ label, value, tone = '' }) { return <div className="metric"><span>{label}</span><strong className={tone}>{value}</strong></div> }
function PanelTitle({ children }) { return <div className="panel-title"><h2>{children}</h2></div> }
function EmptyCopy({ text }) { return <p className="empty-copy">{text}</p> }

function PositionTable({ positions, portfolioId, addToPaper }) { return <div className="table-wrap"><table className="dense-table positions-table"><thead><tr><th>Action / item</th><th>Entry / exit</th><th>Allocation</th><th>Quantity</th><th>EV</th><th>Duration</th><th>Win probability</th><th>Samples</th><th /></tr></thead><tbody>{positions.map((position) => <PositionRow key={position.opportunity_id} position={position} portfolioId={portfolioId} addToPaper={addToPaper} />)}</tbody></table></div> }
function PositionRow({ position, portfolioId, addToPaper }) { const [open, setOpen] = useState(false); return <><tr className="expandable" tabIndex="0" role="button" aria-expanded={open} onClick={() => setOpen((value) => !value)} onKeyDown={(event) => { if (event.key === 'Enter' || event.key === ' ') { event.preventDefault(); setOpen((value) => !value) } }}><td><strong>{position.action || 'BUY'} · {position.item || position.entry_item || position.opportunity_id}</strong><small>{position.category} · {position.tier}</small></td><td className="numeric"><span>{chaos(position.target_entry_chaos)} ≤ {chaos(position.maximum_entry_chaos)}</span><small>target {exitText(position.target_exit_chaos)}</small></td><td className="numeric"><strong>{divine(position.capital)}</strong><small>{position.capital_currency || 'Divine'}</small></td><td className="numeric">{Number(position.estimated_quantity || 0).toLocaleString()} units</td><td className="numeric positive">{plainPercent(position.expected_return)}</td><td className="numeric">{position.time_exit_hours || position.expected_duration}h<small>{position.duration_interval?.join('–') || '—'}h</small></td><td className="numeric">{percent(position.probability_profitable)}</td><td className="numeric">{position.historical_sample_size ?? '—'}</td><td>{portfolioId ? <button type="button" className="text-button" onClick={(event) => { event.stopPropagation(); addToPaper(position) }}>ADD TO PAPER</button> : <span className="muted small">PAPER</span>}</td></tr>{open && <tr className="detail-row"><td colSpan="9"><details open><summary>Invalidation / time exit / reason</summary><div className="position-detail"><span>Time exit: {position.time_exit_hours ?? '—'}h</span><span>Invalidation: {position.invalidation_conditions?.length ? position.invalidation_conditions.join(' · ') : '—'}</span><span>Reason: {position.reason || '—'}</span></div></details></td></tr>}</> }
function Watchlist({ watchlist = [] }) { return <section className="terminal-panel"><PanelTitle>Near triggers / watchlist <span>{watchlist.length}</span></PanelTitle>{watchlist.length ? <div className="table-wrap"><table className="dense-table"><thead><tr><th>Item</th><th>Trigger</th><th>Capital range</th><th>Trigger probability</th></tr></thead><tbody>{watchlist.map((watch) => <tr key={watch.opportunity_id}><td><strong>{watch.item || watch.opportunity_id}</strong><small>{watch.category || '—'} · {watch.state || 'WATCHING'}</small></td><td>{watch.trigger || '—'}<small>{watch.reason || '—'}</small></td><td className="numeric">{watch.suggested_capital_range?.map(divine).join('–') || '—'}</td><td className="numeric">{watch.trigger_probability == null ? 'not estimated' : percent(watch.trigger_probability)}</td></tr>)}</tbody></table></div> : <EmptyCopy text="No watchlist entries returned by the current market snapshot." />}</section> }

function OutcomeDistribution({ simulation }) { if (!simulation) return <EmptyCopy text="Simulation statistics unavailable." />; const values = [simulation.p10_profit, simulation.p25_profit, simulation.median_profit, simulation.p75_profit, simulation.p90_profit].map(Number); const max = Math.max(...values.map((v) => Math.abs(v)), 1); return <div className="distribution"><svg viewBox="0 0 300 92" role="img" aria-label="Simulated Divine profit distribution"><line x1="8" y1="76" x2="292" y2="76" stroke="currentColor" opacity=".28" />{values.map((value, index) => { const height = Math.max(4, Math.abs(value) / max * 60); const x = 18 + index * 66; return <g key={index}><rect x={x} y={76 - height} width="38" height={height} rx="2" fill={value >= 0 ? 'var(--positive)' : 'var(--negative)'} opacity={index === 2 ? 1 : .5} /><text x={x + 19} y="90" textAnchor="middle">{['P10','P25','P50','P75','P90'][index]}</text></g> })}</svg><div className="distribution-summary"><span>Median <strong>{divine(simulation.median_profit)}</strong></span><span>Profitable <strong>{percent(simulation.probability_profitable)}</strong></span><span>Completion <strong>{simulation.completion_interval?.join('–') || '—'}h</strong></span></div></div> }

function PaperPortfolio({ bankroll, portfolioId, portfolio, portfolioLoading, portfolioError, createPortfolio, forgetPortfolio, realForm, setRealForm, recordReal, realMessage, trades, manualTrades, realizePosition, correctTrade, realizeMessage }) {
  return <section className="terminal-panel paper-section"><div className="panel-title"><h2>Paper portfolio <span className="muted">· Chaos</span></h2>{portfolioId && <button type="button" className="text-button" onClick={forgetPortfolio}>CLEAR LOCAL ID</button>}</div>{portfolioLoading && <LoadingState text="Loading paper portfolio…" />}{portfolioError && <ErrorState message={portfolioError} />}{!portfolioLoading && !portfolioId && <div className="paper-empty"><p>No paper portfolio selected. Create one from the current Divine bankroll; it is converted to Chaos at the current plan rate.</p><button type="button" className="btn-primary" onClick={createPortfolio} disabled={portfolioLoading}>CREATE PAPER PORTFOLIO · {divine(bankroll.total_net_worth)}</button></div>}{!portfolioLoading && portfolio && <><div className="metric-grid paper-metrics"><Metric label="Equity (c)" value={chaos(portfolio.status?.equity)} /><Metric label="Liquid (c)" value={chaos(portfolio.status?.liquid)} /><Metric label="Open positions" value={portfolio.status?.open_position_count ?? 0} /><><Metric label="Return (c)" value={chaos(portfolio.performance?.total_return)} tone={portfolio.performance?.total_return > 0 ? 'positive' : ''} /><Metric label="Return (%)" value={plainPercent(portfolio.performance?.total_return_percent, 4)} tone={portfolio.performance?.total_return_percent > 0 ? 'positive' : ''} /></><Metric label="Drawdown (c)" value={chaos(portfolio.performance?.max_drawdown)} tone="negative" /><Metric label="Calibration" value={Object.keys(portfolio.performance?.calibration_buckets || {}).length ? 'available' : (Number(portfolio.performance?.realized_trade_count || 0) > 0 ? 'unavailable' : 'empty')} /></div><div className="paper-grid"><div><h3>Open / realized positions · Chaos</h3>{portfolio.positions?.length ? <div className="table-wrap"><table className="dense-table"><thead><tr><th>Opportunity</th><th>Status</th><th>Quantity</th><th>Entry (c)</th><th>Profit (c)</th><th /></tr></thead><tbody>{portfolio.positions.map((position) => <PaperPositionRow key={position.id} position={position} realizePosition={realizePosition} />)}</tbody></table></div> : <p className="empty-copy">No paper positions yet. Use ADD TO PAPER on a recommendation; entry is chaos-denominated.</p>}</div><div><h3>Equity curve · Chaos</h3><EquitySparkline values={(portfolio.equity || []).map((point) => point.equity)} /><div className="paper-note">Baseline availability: {Object.entries(portfolio.performance?.baseline_availability || {}).filter(([,available]) => available).map(([name]) => name).join(', ') || 'none beyond the documented hold-currency baseline'}</div></div></div>{realizeMessage && <p className="paper-note">{realizeMessage}</p>}<TradeHistory trades={trades} manualTrades={manualTrades} correctTrade={correctTrade} /><details className="progressive"><summary>Manual realized trade · no execution · Chaos prices/profit</summary><form className="real-form" onSubmit={recordReal}>{[['opportunity_id','Opportunity ID','text'],['quantity','Quantity','number'],['predicted_entry_price','Predicted entry (c)','number'],['actual_entry_price','Actual entry (c)','number'],['predicted_exit_price','Predicted exit (c)','number'],['actual_exit_price','Actual exit (c)','number'],['predicted_duration_hours','Predicted duration (h)','number'],['actual_duration_hours','Actual duration (h)','number'],['confidence','Confidence (0–1)','number'],['chaos_per_divine','Chaos per Divine at trade','number']].map(([key,label,type]) => <Field key={key} label={label}><input required min={key === 'chaos_per_divine' ? '0.000001' : undefined} className="input numeric" type={type} step="any" value={realForm[key]} onChange={(e) => setRealForm((current) => ({ ...current, [key]: e.target.value }))} /></Field>)}<div className="form-actions"><span className="muted small">Manual prices and realized profit are Chaos; the rate is retained only for calibration metadata.</span><button className="btn-primary">RECORD TRADE</button></div>{realMessage && <p className="paper-note">{realMessage}</p>}</form></details></>}</section>
}
function PaperPositionRow({ position, realizePosition }) {
  const [form, setForm] = useState({
    actual_entry_price: String(position.entry_price),
    quantity: String(position.quantity),
    exit_price: '',
    actual_duration_hours: '',
    confidence: '',
  })
  return <tr><td>{position.opportunity_id}</td><td>{position.status}</td><td className="numeric">{position.quantity}</td><td className="numeric">{chaos(position.entry_price)}</td><td className="numeric">{chaos(position.realized_profit)}</td><td>{position.status === 'open' && <form onSubmit={(event) => { event.preventDefault(); realizePosition(position, form) }} onClick={(event) => event.stopPropagation()}><input required className="input numeric" type="number" min="0.000001" step="any" aria-label="Actual entry (c)" value={form.actual_entry_price} onChange={(e) => setForm({ ...form, actual_entry_price: e.target.value })} /><input required className="input numeric" type="number" min="0.000001" step="any" aria-label="Actual quantity" value={form.quantity} onChange={(e) => setForm({ ...form, quantity: e.target.value })} /><input required className="input numeric" type="number" min="0.000001" step="any" aria-label="Actual exit (c)" placeholder="Exit (c)" value={form.exit_price} onChange={(e) => setForm({ ...form, exit_price: e.target.value })} /><input className="input numeric" type="number" min="0" step="any" aria-label="Actual duration (hours)" placeholder="Hours" value={form.actual_duration_hours} onChange={(e) => setForm({ ...form, actual_duration_hours: e.target.value })} /><input className="input numeric" type="number" min="0" max="1" step="any" aria-label="Confidence" placeholder="Confidence" value={form.confidence} onChange={(e) => setForm({ ...form, confidence: e.target.value })} /><button className="text-button">REALIZE</button></form>}</td></tr>
}
function TradeHistory({ trades = [], manualTrades = [], correctTrade }) {
  const [editing, setEditing] = useState(null)
  const rows = [...trades.map((trade) => ({ ...trade, source: 'LINKED' })), ...manualTrades.map((trade) => ({ ...trade, source: 'MANUAL' }))].sort((a, b) => String(b.recorded_at || '').localeCompare(String(a.recorded_at || '')))
  return <section><h3>Trade history <span className="muted">{rows.length}</span></h3>{rows.length ? <div className="table-wrap"><table className="dense-table"><thead><tr><th>Source</th><th>Opportunity</th><th>Qty</th><th>Entry (c)</th><th>Exit (c)</th><th>Profit (c)</th><th>Duration (h)</th><th>Recorded</th><th /></tr></thead><tbody>{rows.map((trade) => <Fragment key={`${trade.source}-${trade.id}`}><tr><td>{trade.source}</td><td>{trade.opportunity_id}</td><td className="numeric">{Number(trade.quantity).toFixed(4)}</td><td className="numeric">{chaos(trade.actual_entry_price)}</td><td className="numeric">{chaos(trade.actual_exit_price)}</td><td className="numeric">{chaos(trade.realized_profit)}</td><td className="numeric">{trade.actual_duration_hours == null ? '—' : `${Number(trade.actual_duration_hours).toFixed(2)}h`}</td><td>{fmtTime(trade.recorded_at)}</td><td>{trade.source === 'LINKED' && <button type="button" className="text-button" onClick={() => setEditing(editing === trade.id ? null : trade.id)}>EDIT</button>}</td></tr>{editing === trade.id && <TradeCorrectionRow trade={trade} correctTrade={correctTrade} close={() => setEditing(null)} />}</Fragment>)}</tbody></table></div> : <p className="empty-copy">No realized trades recorded yet.</p>}</section>
}
function TradeCorrectionRow({ trade, correctTrade, close }) {
  const [form, setForm] = useState({
    quantity: String(trade.quantity),
    actual_entry_price: String(trade.actual_entry_price),
    actual_exit_price: String(trade.actual_exit_price),
    actual_duration_hours: String(trade.actual_duration_hours ?? 0),
    confidence: trade.confidence == null ? '' : String(trade.confidence),
  })
  return <tr><td colSpan="9"><form className="real-form" onSubmit={async (event) => { event.preventDefault(); if (await correctTrade(trade, form)) close() }}>{[['quantity','Actual quantity'],['actual_entry_price','Actual entry (c)'],['actual_exit_price','Actual exit (c)'],['actual_duration_hours','Actual duration (h)'],['confidence','Confidence (0–1)']].map(([key,label]) => <Field key={key} label={label}><input required={key !== 'confidence'} className="input numeric" type="number" min={key === 'actual_duration_hours' || key === 'confidence' ? '0' : '0.000001'} max={key === 'confidence' ? '1' : undefined} step="any" value={form[key]} onChange={(e) => setForm({ ...form, [key]: e.target.value })} /></Field>)}<div className="form-actions"><button type="button" className="text-button" onClick={close}>CANCEL</button><button className="btn-primary">SAVE CORRECTION</button></div></form></td></tr>
}
function EquitySparkline({ values }) { if (!values.length) return <p className="empty-copy">No equity history yet.</p>; const min = Math.min(...values); const range = Math.max(...values) - min || 1; const points = values.map((value, index) => `${(index / Math.max(1, values.length - 1)) * 100},${38 - ((value - min) / range) * 32}`).join(' '); return <svg className="equity-sparkline" viewBox="0 0 100 42" preserveAspectRatio="none" role="img" aria-label="Paper portfolio equity curve"><polyline fill="none" stroke="var(--purple)" strokeWidth="1.8" points={points} /></svg> }
function RecommendationJournal({ journal, error }) { return <details className="terminal-panel journal-section"><summary><strong>Recent recommendation journal</strong> <span className="muted">{journal.length ? `· ${Math.min(journal.length, 8)} shown` : '· empty'}</span></summary>{error && <p className="paper-note">{error}</p>}{journal.length ? <div className="table-wrap"><table className="dense-table"><thead><tr><th>ID</th><th>Created</th><th>Mode / recommendation</th><th>Positions</th><th>Expected profit</th></tr></thead><tbody>{journal.slice(-8).reverse().map((entry) => <tr key={entry.id}><td>{entry.id}</td><td>{fmtTime(entry.created_at)}</td><td>{entry.mode || '—'} / {entry.recommendation || '—'}</td><td className="numeric">{entry.positions?.length || 0}</td><td className="numeric">{divine(entry.expected_profit)}</td></tr>)}</tbody></table></div> : <p className="empty-copy">No immutable recommendations have been journaled yet.</p>}</details> }
