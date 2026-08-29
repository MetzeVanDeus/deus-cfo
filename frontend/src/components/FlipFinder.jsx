import { useState } from 'react'
import { api } from '../lib/helpers'
import { EmptyState, ErrorState } from './ui'

function scoreTone(score) {
  if (score >= 80) return 'score-strong'
  if (score >= 60) return 'score-moderate'
  return 'score-weak'
}

export function FlipFinder({ categories, selectedLeague }) {
  const [selectedCategory, setSelectedCategory] = useState('Currency')
  const [budgetCurrency, setBudgetCurrency] = useState('divine')
  const [budgetAmount, setBudgetAmount] = useState('10')
  const [results, setResults] = useState([])
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState('')
  const [showResults, setShowResults] = useState(false)

  const handleSearch = async () => {
    if (!selectedLeague || !budgetCurrency || !budgetAmount) {
      setError('Please fill in all fields')
      return
    }
    const amount = Number(budgetAmount)
    if (!Number.isFinite(amount) || amount <= 0) {
      setError('Budget amount must be a positive number')
      return
    }
    setLoading(true)
    setError('')
    setShowResults(false)
    try {
      const resp = await api.post('/flips', {
        budgetCurrency,
        budgetAmount: amount,
        leagueId: selectedLeague,
        category: selectedCategory,
      })
      setResults(resp.data)
      setShowResults(true)
    } catch (err) {
      setError(err.response?.data?.detail || 'Failed to fetch flip data')
    } finally {
      setLoading(false)
    }
  }

  const currencyName = (id) => (id === 'chaos' ? 'Chaos Orb' : 'Divine Orb')
  const bestScore = results.length > 0 ? results[0].flipScore : 0

  return (
    <div className="flip-finder">
      <section className="terminal-panel">
        <div className="panel-title"><h2>Budget Flip Finder</h2></div>
        <div className="form-row flip-controls">
          <label className="field">
            <span>Category</span>
            <select value={selectedCategory} onChange={(e) => setSelectedCategory(e.target.value)} className="input">
              {categories.map((c) => <option key={c.id} value={c.id}>{c.name}</option>)}
            </select>
          </label>
          <label className="field">
            <span>Budget currency</span>
            <div className="segmented" role="group" aria-label="Budget currency">
              <button type="button" className="segmented-option" aria-pressed={budgetCurrency === 'chaos'} onClick={() => setBudgetCurrency('chaos')}>Chaos</button>
              <button type="button" className="segmented-option" aria-pressed={budgetCurrency === 'divine'} onClick={() => setBudgetCurrency('divine')}>Divine</button>
            </div>
          </label>
          <label className="field">
            <span>Budget amount</span>
            <input type="number" value={budgetAmount} onChange={(e) => setBudgetAmount(e.target.value)} className="input numeric" min="0.01" step="0.01" placeholder="10" />
          </label>
          <div className="field field-action">
            <span className="visually-hidden">Search</span>
            <button type="button" onClick={handleSearch} disabled={loading || !selectedLeague} className="btn-primary">
              {loading ? 'Searching...' : 'Find Flips'}
            </button>
          </div>
        </div>
        {error && <ErrorState message={error} />}
      </section>

      {showResults && results.length > 0 && (
        <section>
          <div className="terminal-panel">
            <div className="panel-title">
              <div>
                <h2>{results.length} Flip Candidates</h2>
                <p className="muted small">
                  {categories.find((c) => c.id === selectedCategory)?.name || selectedCategory}
                  {' · '}Budget: {budgetAmount} {currencyName(budgetCurrency)}
                  {' · '}sorted by flip score
                </p>
              </div>
              <div className="metric">
                <span>Top Flip Score (/100)</span>
                <strong className={scoreTone(bestScore)}>{bestScore.toFixed(0)}<span className="muted">/100</span></strong>
              </div>
            </div>
          </div>

          <div className="terminal-panel">
            <div className="table-wrap">
              <table className="dense-table">
                <thead>
                  <tr>
                    <th>Item</th>
                    <th>Price</th>
                    <th>Flip Score (/100)</th>
                    <th>Dip from Peak</th>
                    <th>Swing</th>
                    <th>Volume</th>
                  </tr>
                </thead>
                <tbody>
                  {results.map((r, i) => (
                    <tr key={r.itemId} className={i === 0 ? 'row-highlight' : undefined}>
                      <td>
                        {r.icon ? <img src={r.icon} alt="" className="item-icon" onError={(e) => { e.target.style.display = 'none' }} /> : null}
                        <strong>{r.name}</strong>
                        {r.variant && <small>{r.variant}</small>}
                      </td>
                      <td className="numeric">
                        {budgetCurrency === 'divine' ? r.priceInBudget.toFixed(4) + ' div' : r.priceChaos.toFixed(2) + 'c'}
                        <small>{r.priceChaos} chaos</small>
                      </td>
                      <td className="numeric">
                        <span className={scoreTone(r.flipScore)}>{r.flipScore.toFixed(0)}</span>
                        {r.monotonicDecline && (
                          <span className="score-weak" title="Price only fell — dying item, not a dip"> ⚠</span>
                        )}
                      </td>
                      <td className="numeric">{Math.round(r.dipFromPeak * 100)}%</td>
                      <td className="numeric">{r.swingDepth.toFixed(0)}%</td>
                      <td className="numeric">{r.volume.toLocaleString()}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </div>

          <div className="terminal-panel muted small">
            <div className="score-legend">
              <span><i className="score-dot score-strong" />Score ≥ 80 (strong flip)</span>
              <span><i className="score-dot score-moderate" />Score 60–80 (moderate)</span>
              <span><i className="score-dot score-weak" />Score &lt; 60 / monotonic decline warning</span>
            </div>
            <p>
              Flip Score blends how far the item is below its recent peak (dip), how wide its recent price swing is,
              and how liquid it is. Higher is better. Items marked ⚠ only ever fell — they are dying, not dipping,
              so trust them less.
            </p>
          </div>
        </section>
      )}

      {!showResults && !loading && !error && (
        <EmptyState eyebrow="FLIP SCANNER READY" title="Ready to Find Flips" message="Pick a league and category, set your budget, and click Find Flips to see dip-buy candidates." />
      )}

      {showResults && results.length === 0 && !loading && (
        <EmptyState eyebrow="NO MATCHES" title="No Candidates In Budget" message={`Nothing in this category within your ${budgetAmount} ${currencyName(budgetCurrency)} budget cleared the flip signal threshold.`} />
      )}
    </div>
  )
}
