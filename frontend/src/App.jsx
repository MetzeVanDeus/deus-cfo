import { useState, useEffect, useCallback } from 'react'
import { api } from './lib/helpers'
import { DashboardTab } from './components/DashboardTab'
import { SignalsTab } from './components/SignalsTab'
import { ExplorerTab } from './components/ExplorerTab'
import { CFOTab } from './components/CFOTab'
import { StrategiesTab } from './components/StrategiesTab'
import { ProfitRoutesTab } from './components/ProfitRoutesTab'
import { OracleLens } from './components/OracleLens'

const TABS = [
  { id: 'cfo', label: 'CFO' },
  { id: 'dashboard', label: 'Dashboard' },
  { id: 'signals', label: 'Signals' },
  { id: 'explorer', label: 'Explorer' },
  { id: 'strategies', label: 'Strategies' },
  { id: 'profit-routes', label: 'Profit Routes' },
]

function App() {
  const [activeTab, setActiveTab] = useState('cfo')
  const [leagues, setLeagues] = useState([])
  const [selectedLeague, setSelectedLeague] = useState('')
  const [leagueDraft, setLeagueDraft] = useState('')
  const [configuredLeague, setConfiguredLeague] = useState('')
  const [migrationRequired, setMigrationRequired] = useState(false)
  const [categories, setCategories] = useState([])
  const [bootError, setBootError] = useState('')
  const [savingLeague, setSavingLeague] = useState(false)
  const [leagueMessage, setLeagueMessage] = useState('')

  const fetchLeagues = useCallback(async () => {
    try {
      const response = await api.get('/leagues')
      setLeagues(Array.isArray(response.data) ? response.data : [])
    } catch (error) { setBootError('Market metadata unavailable') }
  }, [])
  const fetchConfig = useCallback(async () => {
    try {
      const { data } = await api.get('/config')
      const configured = data?.league || ''
      const migration = Boolean(data?.migration_required)
      setMigrationRequired(migration)
      setConfiguredLeague(configured)
      setLeagueDraft(configured)
      setSelectedLeague(configured && !migration ? configured : '')
    } catch (error) { setBootError((current) => current || 'Shared league configuration unavailable') }
  }, [])
  const fetchCategories = useCallback(async () => {
    try { const response = await api.get('/categories'); setCategories(response.data) }
    catch (error) { setBootError((current) => current || 'Category metadata unavailable') }
  }, [])
  useEffect(() => { fetchLeagues(); fetchConfig(); fetchCategories() }, [fetchLeagues, fetchConfig, fetchCategories])

  const liveLeague = leagues.some((league) => league.id === configuredLeague)
  const saveLeague = async () => {
    if (!leagueDraft) return
    setSavingLeague(true); setLeagueMessage('')
    try {
      const { data } = await api.put('/config', { league: leagueDraft })
      const saved = data?.league || leagueDraft
      setConfiguredLeague(saved)
      setLeagueDraft(saved)
      setSelectedLeague(saved)
      setMigrationRequired(false)
      setLeagueMessage('Shared league saved. Collector will use it on its next cycle.')
    } catch (error) {
      setLeagueMessage(error.response?.data?.detail || 'League could not be saved')
    } finally { setSavingLeague(false) }
  }

  return <div className="app-shell">
    <header className="topbar"><div className="brand"><span className="brand-mark">D</span><strong>DeusCFO</strong><span className="brand-divider" /><span className="brand-context">CAPITAL INTELLIGENCE</span></div><nav className="topnav" aria-label="Primary navigation">{TABS.map((tab) => <button key={tab.id} className={activeTab === tab.id ? 'nav-active' : ''} aria-current={activeTab === tab.id ? 'page' : undefined} onClick={() => setActiveTab(tab.id)}>{tab.label}</button>)}</nav><div className="topbar-status"><span className="status-dot" />{selectedLeague || 'NO LEAGUE'}</div></header>
    {bootError && <div className="boot-warning">{bootError} · retrying is safe</div>}
    <main className="main-shell">
      <section className="terminal-panel league-panel" aria-labelledby="league-heading"><div><div className="eyebrow">SHARED MARKET CONTEXT</div><h2 id="league-heading">{migrationRequired ? 'League migration' : selectedLeague ? 'Active league' : 'First-run league'}</h2><p className="muted">The UI and collector intentionally use one local league setting. Choose a live league, then save it.</p></div><div className="league-controls"><select className="input" aria-label="Configured league" value={leagueDraft} onChange={(event) => setLeagueDraft(event.target.value)}><option value="">Choose a live league</option>{leagues.map((league) => <option key={league.id} value={league.id}>{league.name || league.text || league.id}</option>)}</select><button className="btn-primary" type="button" disabled={!leagueDraft || savingLeague} onClick={saveLeague}>{savingLeague ? 'SAVING…' : 'SAVE LEAGUE'}</button></div>{(migrationRequired || (configuredLeague && !liveLeague)) && <p className="paper-note">Configured league <strong>{configuredLeague}</strong> is unavailable. Select a current league to migrate intentionally; no data is silently reassigned.</p>}{leagueMessage && <p className="paper-note">{leagueMessage}</p>}</section>
      {selectedLeague && <ReadinessPanel league={selectedLeague} />}
      {activeTab === 'cfo' && <div className="cfo-stage"><OracleLens /><CFOTab selectedLeague={selectedLeague} /></div>}
      {activeTab === 'dashboard' && <DashboardTab categories={categories} selectedLeague={selectedLeague} />}
      {activeTab === 'signals' && <SignalsTab selectedLeague={selectedLeague} />}
      {activeTab === 'explorer' && <ExplorerTab categories={categories} selectedLeague={selectedLeague} />}
      {activeTab === 'strategies' && <StrategiesTab categories={categories} selectedLeague={selectedLeague} />}
      {activeTab === 'profit-routes' && <ProfitRoutesTab categories={categories} selectedLeague={selectedLeague} />}
    </main>
    <footer className="footer">DeusCFO <span>·</span> Market data from poe.ninja and the Currency Exchange CDN <span>·</span> Doctor → Headhunter production route only <span>·</span> Research terminal, not an execution venue <span>·</span> This product isn't affiliated with or endorsed by Grinding Gear Games in any way.</footer>
  </div>
}

function ReadinessPanel({ league }) {
  const [coverage, setCoverage] = useState([])
  const [status, setStatus] = useState(null)
  const [loading, setLoading] = useState(true)
  const [backfilling, setBackfilling] = useState(false)
  const [message, setMessage] = useState('')
  useEffect(() => {
    let cancelled = false
    setLoading(true); setMessage('')
    Promise.all([api.get('/coverage', { params: { league } }), api.get('/snapshot/status')]).then(([coverageResponse, statusResponse]) => {
      if (!cancelled) { setCoverage(Array.isArray(coverageResponse.data) ? coverageResponse.data : []); setStatus(statusResponse.data) }
    }).catch(() => { if (!cancelled) setMessage('Readiness data is unavailable; collection may still be starting.') }).finally(() => { if (!cancelled) setLoading(false) })
    return () => { cancelled = true }
  }, [league])
  const backfill = async () => {
    setBackfilling(true); setMessage('Backfill started; this can take a few minutes and remains local.')
    try {
      const { data } = await api.post('/cx/backfill', { max_hours: 168 })
      setMessage(`Backfill processed ${data?.hours_processed ?? 0} hourly records. Refreshing readiness.`)
      const response = await api.get('/coverage', { params: { league } }); setCoverage(Array.isArray(response.data) ? response.data : [])
    } catch (error) { setMessage(error.response?.data?.detail || 'Backfill could not start') }
    finally { setBackfilling(false) }
  }
  const hours = coverage.reduce((max, row) => Math.max(max, Number(row.hours_present || 0)), 0)
  return <section className="terminal-panel readiness-panel" aria-labelledby="readiness-heading"><div className="panel-title"><h2 id="readiness-heading">Data readiness</h2><span>{loading ? 'CHECKING…' : `${hours} observed hours`}</span></div>{loading ? <p className="muted">Checking stored history for {league}…</p> : <><p className="muted">Current prices arrive on collector cycles. Historical signals and routes need enough observed history; missing history and absent strategy coverage are valid reasons to WAIT.</p><div className="metric-grid"><div className="metric"><span>All stored rows</span><strong>{status?.total_rows?.toLocaleString?.() || '0'}</strong></div><div className="metric"><span>Observed hours</span><strong>{hours}</strong></div><div className="metric"><span>Missing category-hours</span><strong>{coverage.reduce((sum, row) => sum + Number(row.hours_missing || 0), 0)}</strong></div><div className="metric"><span>Last snapshot</span><strong>{status?.last_snapshot_per_league?.[league] ? new Date(status.last_snapshot_per_league[league]).toLocaleString() : 'Not yet'}</strong></div></div><button className="text-button" type="button" disabled={backfilling} onClick={backfill}>{backfilling ? 'BACKFILLING…' : 'BACKFILL CURRENCY EXCHANGE HISTORY'}</button>{message && <p className="paper-note">{message}</p>}</>}</section>
}

export default App
