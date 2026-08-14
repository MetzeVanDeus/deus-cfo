import { useState, useEffect, useCallback } from 'react'
import { api } from './lib/helpers'
import { DashboardTab } from './components/DashboardTab'
import { SignalsTab } from './components/SignalsTab'
import { ExplorerTab } from './components/ExplorerTab'
import { CFOTab } from './components/CFOTab'
import { StrategiesTab } from './components/StrategiesTab'

const TABS = [
  { id: 'cfo', label: 'CFO' },
  { id: 'dashboard', label: 'Dashboard' },
  { id: 'signals', label: 'Signals' },
  { id: 'explorer', label: 'Explorer' },
  { id: 'strategies', label: 'Strategies' },
]

function App() {
  const [activeTab, setActiveTab] = useState('cfo')
  const [leagues, setLeagues] = useState([])
  const [selectedLeague, setSelectedLeague] = useState('')
  const [categories, setCategories] = useState([])
  const [bootError, setBootError] = useState('')

  const fetchLeagues = useCallback(async () => {
    try {
      const response = await api.get('/leagues')
      setLeagues(response.data)
      if (response.data.length > 0) setSelectedLeague((current) => current || response.data[0].id)
    } catch (error) { setBootError('Market metadata unavailable') }
  }, [])
  const fetchCategories = useCallback(async () => {
    try { const response = await api.get('/categories'); setCategories(response.data) }
    catch (error) { setBootError((current) => current || 'Category metadata unavailable') }
  }, [])
  useEffect(() => { fetchLeagues(); fetchCategories() }, [fetchLeagues, fetchCategories])

  return <div className="app-shell">
    <header className="topbar"><div className="brand"><span className="brand-mark">D</span><strong>DeusCFO</strong><span className="brand-divider" /><span className="brand-context">CAPITAL INTELLIGENCE</span></div><nav className="topnav" aria-label="Primary navigation">{TABS.map((tab) => <button key={tab.id} className={activeTab === tab.id ? 'nav-active' : ''} onClick={() => setActiveTab(tab.id)}>{tab.label}</button>)}</nav><div className="topbar-status"><span className="status-dot" />{selectedLeague || 'NO LEAGUE'}</div></header>
    {bootError && <div className="boot-warning">{bootError} · retrying is safe</div>}
    <main className="main-shell">
      {activeTab === 'cfo' && <CFOTab leagues={leagues} selectedLeague={selectedLeague} setSelectedLeague={setSelectedLeague} />}
      {activeTab === 'dashboard' && <DashboardTab leagues={leagues} categories={categories} selectedLeague={selectedLeague} setSelectedLeague={setSelectedLeague} />}
      {activeTab === 'signals' && <SignalsTab selectedLeague={selectedLeague} />}
      {activeTab === 'explorer' && <ExplorerTab leagues={leagues} categories={categories} selectedLeague={selectedLeague} setSelectedLeague={setSelectedLeague} />}
      {activeTab === 'strategies' && <StrategiesTab leagues={leagues} categories={categories} selectedLeague={selectedLeague} setSelectedLeague={setSelectedLeague} />}
    </main>
    <footer className="footer">DeusCFO <span>·</span> Market data from poe.ninja <span>·</span> Research terminal, not an execution venue</footer>
  </div>
}
export default App
