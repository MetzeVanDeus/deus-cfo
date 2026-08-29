import React, { useState, useEffect, useCallback } from 'react'
import { api, isDraftLeagueLive, leagueStatusTone, TABS, adjacentTabId } from './lib/helpers'
import { DashboardTab } from './components/DashboardTab'
import { SignalsTab } from './components/SignalsTab'
import { ExplorerTab } from './components/ExplorerTab'
import { CFOTab } from './components/CFOTab'
import { StrategiesTab } from './components/StrategiesTab'
import { ProfitRoutesTab } from './components/ProfitRoutesTab'
import { ErrorState, LoadingState } from './components/ui'
import { AppFooter, UpdateBadge, UpdateModal, useUpdateCheck } from './components/UpdateNotice'

function App() {
  const [activeTab, setActiveTab] = useState('cfo')
  const [leagues, setLeagues] = useState([])
  const [selectedLeague, setSelectedLeague] = useState('')
  const [leagueDraft, setLeagueDraft] = useState('')
  const [configuredLeague, setConfiguredLeague] = useState('')
  const [migrationRequired, setMigrationRequired] = useState(false)
  const [categories, setCategories] = useState([])
  const [bootErrors, setBootErrors] = useState({})
  const [savingLeague, setSavingLeague] = useState(false)
  const [leagueMessage, setLeagueMessage] = useState('')
  const [historyHours, setHistoryHours] = useState(168)
  const [leagueOpen, setLeagueOpen] = useState(true)
  const update = useUpdateCheck()

  const fetchLeagues = useCallback(async () => {
    try { const response = await api.get('/leagues'); setLeagues(Array.isArray(response.data) ? response.data : []); setBootErrors((current) => ({ ...current, leagues: '' })) }
    catch { setBootErrors((current) => ({ ...current, leagues: 'Market metadata unavailable' })) }
  }, [])
  const fetchConfig = useCallback(async () => {
    try {
      const { data } = await api.get('/config'); const configured = data?.league || ''; const migration = Boolean(data?.migration_required)
      setMigrationRequired(migration); setConfiguredLeague(configured); setLeagueDraft(configured); setSelectedLeague(configured && !migration ? configured : ''); setBootErrors((current) => ({ ...current, config: '' }))
    } catch { setBootErrors((current) => ({ ...current, config: 'Shared league configuration unavailable' })) }
  }, [])
  const fetchCategories = useCallback(async () => {
    try { const response = await api.get('/categories'); setCategories(response.data); setBootErrors((current) => ({ ...current, categories: '' })) }
    catch { setBootErrors((current) => ({ ...current, categories: 'Category metadata unavailable' })) }
  }, [])
  const retryBoot = () => { fetchLeagues(); fetchConfig(); fetchCategories() }
  useEffect(() => { fetchLeagues(); fetchConfig(); fetchCategories() }, [fetchLeagues, fetchConfig, fetchCategories])
  useEffect(() => { const onKey = (event) => { if (event.altKey && !event.ctrlKey && !event.metaKey && /^[1-6]$/.test(event.key)) { event.preventDefault(); setActiveTab(TABS[Number(event.key) - 1].id) } }; window.addEventListener('keydown', onKey); return () => window.removeEventListener('keydown', onKey) }, [])
  useEffect(() => { setLeagueOpen(!selectedLeague || migrationRequired) }, [selectedLeague, migrationRequired])

  const draftIsLive = isDraftLeagueLive(leagues, leagueDraft)
  const bootError = Object.values(bootErrors).some(Boolean)
  const statusTone = leagueStatusTone({ selectedLeague, migrationRequired, bootError })
  const saveLeague = async () => {
    if (!leagueDraft) return
    setSavingLeague(true); setLeagueMessage('')
    try { const { data } = await api.put('/config', { league: leagueDraft }); const saved = data?.league || leagueDraft; setConfiguredLeague(saved); setLeagueDraft(saved); setSelectedLeague(saved); setMigrationRequired(false); setLeagueOpen(false); setLeagueMessage('Shared league saved. Collector will use it on its next cycle.') }
    catch (error) { setLeagueMessage(error.response?.data?.detail || 'League could not be saved') }
    finally { setSavingLeague(false) }
  }


  const onTabKeyDown = (event) => {
    const nextId = adjacentTabId(activeTab, event.key)
    if (!nextId) return
    event.preventDefault()
    setActiveTab(nextId)
    queueMicrotask(() => document.getElementById(`tab-${nextId}`)?.focus())
  }

  return <div className="app-shell">
    <a className="skip-link" href="#main-content">Skip to content</a>
    <header className="topbar">
      <div className="brand"><span className="brand-mark">D</span><strong>DeusCFO</strong><span className="brand-divider" /><span className="brand-context">CAPITAL INTELLIGENCE</span></div>
      <nav className="topnav" role="tablist" aria-label="Primary views">
        {TABS.map((tab) => (
          <button
            key={tab.id}
            id={`tab-${tab.id}`}
            type="button"
            role="tab"
            aria-selected={activeTab === tab.id}
            aria-controls="main-content"
            tabIndex={activeTab === tab.id ? 0 : -1}
            className={activeTab === tab.id ? 'nav-active' : ''}
            onClick={() => setActiveTab(tab.id)}
            onKeyDown={onTabKeyDown}
          >
            {tab.label}
          </button>
        ))}
      </nav>
      <p className="visually-hidden">Alt+1–6 switches views.</p>
      <div className="topbar-end">
        <UpdateBadge status={update.status} onOpen={() => update.setModalOpen(true)} />
        <div className="topbar-status"><span className={`status-dot status-dot-${statusTone}`} />{selectedLeague || (migrationRequired ? configuredLeague || 'MIGRATE LEAGUE' : 'NO LEAGUE')}</div>
      </div>
    </header>
    {Object.values(bootErrors).filter(Boolean).length > 0 && <div className="boot-warning">{Object.values(bootErrors).filter(Boolean).join(' | ')} <button className="text-button" onClick={retryBoot}>RETRY</button></div>}
    <main className="main-shell">
      {selectedLeague && !migrationRequired && !leagueOpen ? (
        <section className="terminal-panel league-panel league-panel-collapsed" aria-labelledby="league-heading">
          <div>
            <div className="eyebrow">SHARED MARKET CONTEXT</div>
            <h2 id="league-heading">Active league <strong>{selectedLeague}</strong></h2>
          </div>
          <button type="button" className="text-button" onClick={() => setLeagueOpen(true)}>CHANGE</button>
        </section>
      ) : (
        <section className="terminal-panel league-panel" aria-labelledby="league-heading"><div><div className="eyebrow">SHARED MARKET CONTEXT</div><h2 id="league-heading">{migrationRequired ? 'League migration' : selectedLeague ? 'Active league' : 'First-run league'}</h2><p className="muted">The UI and collector intentionally use one local league setting. Choose a live league, then save it.</p></div><div className="league-controls"><select className="input" aria-label="Configured league" value={leagueDraft} onChange={(event) => setLeagueDraft(event.target.value)}><option value="">Choose a live league</option>{leagues.map((league) => <option key={league.id} value={league.id}>{league.name || league.text || league.id}</option>)}</select><button className="btn-primary" disabled={!draftIsLive || savingLeague} onClick={saveLeague} title={!draftIsLive ? 'Choose a live league' : undefined}>{savingLeague ? 'SAVING…' : 'SAVE LEAGUE'}</button></div>{leagueMessage && <p className="muted" role="status">{leagueMessage}</p>}</section>
      )}
      {selectedLeague && <ReadinessPanel league={selectedLeague} />}
      {['dashboard', 'signals', 'explorer'].includes(activeTab) && <div className="history-control"><label htmlFor="history-window">History window</label><select id="history-window" className="input" value={historyHours} onChange={(event) => setHistoryHours(Number(event.target.value))}><option value="24">24 hours</option><option value="72">72 hours</option><option value="168">7 days</option></select></div>}
      <ErrorBoundary key={activeTab}><div id="main-content" role="tabpanel" aria-labelledby={`tab-${activeTab}`}>{activeTab === 'cfo' && <div className="cfo-stage"><CFOTab selectedLeague={selectedLeague} /></div>}{activeTab === 'dashboard' && <DashboardTab categories={categories} selectedLeague={selectedLeague} historyHours={historyHours} />}{activeTab === 'signals' && <SignalsTab selectedLeague={selectedLeague} historyHours={historyHours} />}{activeTab === 'explorer' && <ExplorerTab categories={categories} selectedLeague={selectedLeague} historyHours={historyHours} />}{activeTab === 'strategies' && <StrategiesTab categories={categories} selectedLeague={selectedLeague} />}{activeTab === 'profit-routes' && <ProfitRoutesTab categories={categories} selectedLeague={selectedLeague} />}</div></ErrorBoundary>
    </main>
    <UpdateModal status={update.status} open={update.modalOpen} onClose={() => update.setModalOpen(false)} />
    <AppFooter status={update.status} checking={update.checking} message={update.footerMessage} onCheck={update.checkNow} />
  </div>
}

class ErrorBoundary extends React.Component {
  state = { crashed: false }
  static getDerivedStateFromError() { return { crashed: true } }
  render() { return this.state.crashed ? <ErrorState message="This view crashed." onRetry={() => window.location.reload()} /> : this.props.children }
}

function ReadinessPanel({ league }) {
  const [coverage, setCoverage] = useState([])
  const [status, setStatus] = useState(null)
  const [loading, setLoading] = useState(true)
  const [backfilling, setBackfilling] = useState(false)
  const [historyStarting, setHistoryStarting] = useState(false)
  const [message, setMessage] = useState('')
  const [loadError, setLoadError] = useState('')
  const [backfillState, setBackfillState] = useState(null)
  const [historyState, setHistoryState] = useState(null)

  useEffect(() => {
    let cancelled = false
    setLoading(true); setMessage(''); setLoadError('')
    Promise.all([
      api.get('/coverage', { params: { league } }),
      api.get('/snapshot/status'),
      api.get('/cx/status'),
      api.get('/market/history/status'),
    ]).then(async ([coverageResponse, statusResponse, cxResponse, historyResponse]) => {
      if (cancelled) return
      const rows = Array.isArray(coverageResponse.data) ? coverageResponse.data : []
      const samples = rows
        .filter((row) => row.source === 'poe.ninja')
        .reduce((max, row) => Math.max(max, Number(row.hours_present || 0)), 0)
      setCoverage(rows)
      setStatus(statusResponse.data)
      setBackfillState(cxResponse.data)
      setHistoryState(historyResponse.data)
      if (samples < 5 && historyResponse.data?.status === 'idle') {
        setHistoryStarting(true)
        setMessage('Loading real market history for immediate signal analysis…')
        try {
          const { data } = await api.post('/market/history/backfill', { league })
          if (!cancelled) setHistoryState(data)
        } catch (error) {
          if (!cancelled) setMessage(error.response?.data?.detail || 'Market history could not start')
        } finally {
          if (!cancelled) setHistoryStarting(false)
        }
      }
    }).catch(() => {
      if (!cancelled) setLoadError('Readiness data is unavailable; collection may still be starting.')
    }).finally(() => {
      if (!cancelled) setLoading(false)
    })
    return () => { cancelled = true }
  }, [league])

  useEffect(() => {
    if (backfillState?.backfill_status !== 'running') return
    let cancelled = false
    let timer
    const poll = async () => {
      try {
        const { data } = await api.get('/cx/status')
        if (cancelled) return
        if (data?.backfill_status === 'running') {
          setBackfillState(data)
          timer = setTimeout(poll, 1000)
          return
        }
        const response = await api.get('/coverage', { params: { league } })
        if (cancelled) return
        setBackfillState(data)
        setCoverage(Array.isArray(response.data) ? response.data : [])
        setMessage(data?.backfill_status === 'failed'
          ? 'Currency Exchange backfill failed; retry when the upstream is available.'
          : `Currency Exchange backfill processed ${data?.backfill_hours_processed ?? 0} hours; exchange history is stored.`)
      } catch {
        if (!cancelled) timer = setTimeout(poll, 2000)
      }
    }
    timer = setTimeout(poll, 1000)
    return () => { cancelled = true; clearTimeout(timer) }
  }, [backfillState?.backfill_status, league])

  useEffect(() => {
    if (historyState?.status !== 'running' && historyState?.status !== 'started' && historyState?.status !== 'in_progress') return
    let cancelled = false
    let timer
    const poll = async () => {
      try {
        const { data } = await api.get('/market/history/status')
        if (cancelled) return
        if (data?.status === 'running') {
          setHistoryState(data)
          timer = setTimeout(poll, 1000)
          return
        }
        const [coverageResponse, statusResponse] = await Promise.all([
          api.get('/coverage', { params: { league } }),
          api.get('/snapshot/status'),
        ])
        if (cancelled) return
        setHistoryState(data)
        setCoverage(Array.isArray(coverageResponse.data) ? coverageResponse.data : [])
        setStatus(statusResponse.data)
        setMessage(data?.status === 'failed'
          ? `Market history failed: ${data?.error || 'upstream data is unavailable'}`
          : `Loaded ${Number(data?.rows_stored || 0).toLocaleString()} real historical observations for signal analysis.`)
      } catch {
        if (!cancelled) timer = setTimeout(poll, 2000)
      }
    }
    timer = setTimeout(poll, 1000)
    return () => { cancelled = true; clearTimeout(timer) }
  }, [historyState?.status, league])

  const loadMarketHistory = async () => {
    setHistoryStarting(true)
    setMessage('Loading real market history in the background…')
    try {
      const { data } = await api.post('/market/history/backfill', { league })
      setHistoryState(data)
    } catch (error) {
      setMessage(error.response?.data?.detail || 'Market history could not start')
    } finally {
      setHistoryStarting(false)
    }
  }

  const backfillCurrency = async () => {
    setBackfilling(true)
    setMessage('Currency Exchange backfill started in the background; this can take a few minutes and remains local.')
    try {
      const { data } = await api.post('/cx/backfill', { max_hours: 168 })
      setBackfillState((current) => ({ ...current, ...data, backfill_status: data?.status === 'in_progress' || data?.status === 'started' ? 'running' : data?.status }))
      if (data?.status === 'in_progress') setMessage('Currency Exchange backfill is already running in the background.')
    } catch (error) {
      setMessage(error.response?.data?.detail || 'Currency Exchange backfill could not start')
    } finally {
      setBackfilling(false)
    }
  }

  const snapshotSamples = coverage
    .filter((row) => row.source === 'poe.ninja')
    .reduce((max, row) => Math.max(max, Number(row.hours_present || 0)), 0)
  const exchangeHours = Number(coverage.find((row) => row.category === 'Currency Exchange')?.hours_present || 0)
  const historyRunning = ['running', 'started', 'in_progress'].includes(historyState?.status)
  const waiting = snapshotSamples < 5

  return <section className="terminal-panel readiness-panel" aria-labelledby="readiness-heading">
    <div className="panel-title">
      <h2 id="readiness-heading">Data readiness</h2>
      <span>{loading ? 'CHECKING…' : waiting ? 'LOADING HISTORY' : `${snapshotSamples} signal samples · ${exchangeHours} exchange hours`}</span>
    </div>
    {loading ? <LoadingState text={`Checking stored history for ${league}…`} /> : loadError ? <ErrorState message={loadError} /> : <>
      <p className="muted">{waiting
        ? 'Loading real historical poe.ninja observations. Signals become available after five time-separated samples.'
        : 'Signals use real stored observations. Imported daily history makes the most liquid items useful immediately; live snapshots continue expanding coverage. Capital planning applies stricter evidence gates and may correctly remain at WAIT.'}</p>
      <div className="metric-grid">
        <div className="metric"><span>Signal readiness</span><strong>{waiting ? 'SIGNALS WAITING' : 'SIGNALS READY'}</strong></div>
        <div className="metric"><span>Snapshot rows</span><strong>{status?.total_rows?.toLocaleString?.() || '0'}</strong></div>
        <div className="metric"><span>Signal samples</span><strong>{snapshotSamples}</strong></div>
        <div className="metric"><span>Exchange history hours</span><strong>{exchangeHours}</strong></div>
        <div className="metric"><span>Last snapshot</span><strong>{status?.last_snapshot_per_league?.[league] ? new Date(status.last_snapshot_per_league[league]).toLocaleString() : 'Not yet'}</strong></div>
      </div>
      <div className="form-actions">
        <button className="btn-secondary" type="button" disabled={historyStarting || historyRunning} onClick={loadMarketHistory}>{historyStarting || historyRunning ? 'MARKET HISTORY LOADING…' : 'LOAD MARKET HISTORY'}</button>
        <button className="btn-secondary" type="button" disabled={backfilling || backfillState?.backfill_status === 'running'} onClick={backfillCurrency}>{backfilling || backfillState?.backfill_status === 'running' ? 'EXCHANGE BACKFILL RUNNING…' : 'BACKFILL CURRENCY EXCHANGE'}</button>
      </div>
      {message && <p className="paper-note">{message}</p>}
    </>}
  </section>
}

export default App
