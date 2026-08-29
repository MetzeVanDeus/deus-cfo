import { useState } from 'react'
import { api } from '../lib/helpers'
import { EmptyState, ErrorState } from './ui'

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

  const scoreColor = (score) => {
    if (score >= 80) return 'text-dracula-green'
    if (score >= 60) return 'text-dracula-yellow'
    return 'text-dracula-orange'
  }

  const bestScore = results.length > 0 ? results[0].flipScore : 0

  return (
    <div>
      {/* Search Section */}
      <section className="card animate-fade-in mb-6">
        <h2 className="text-xl font-semibold text-dracula-fg mb-4">Budget Flip Finder</h2>

        <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-5 gap-4">
          <div>
            <label className="block text-sm font-medium text-dracula-comment mb-2">Shared league</label>
            <div className="input w-full" aria-label="Shared league">{selectedLeague || 'Choose shared league above'}</div>
          </div>

          <div>
            <label className="block text-sm font-medium text-dracula-comment mb-2">Category</label>
            <select value={selectedCategory} onChange={(e) => setSelectedCategory(e.target.value)} className="input w-full">
              {categories.map((c) => <option key={c.id} value={c.id}>{c.name}</option>)}
            </select>
          </div>

          <div>
            <label className="block text-sm font-medium text-dracula-comment mb-2">Budget Currency</label>
            <div className="flex rounded-lg overflow-hidden border border-dracula-current">
              <button type="button" onClick={() => setBudgetCurrency('chaos')}
                className={`flex-1 py-3 text-sm font-semibold transition-colors ${budgetCurrency === 'chaos' ? 'bg-dracula-purple text-dracula-bg' : 'bg-dracula-current/50 text-dracula-fg hover:bg-dracula-current'}`}>
                Chaos
              </button>
              <button type="button" onClick={() => setBudgetCurrency('divine')}
                className={`flex-1 py-3 text-sm font-semibold transition-colors ${budgetCurrency === 'divine' ? 'bg-dracula-purple text-dracula-bg' : 'bg-dracula-current/50 text-dracula-fg hover:bg-dracula-current'}`}>
                Divine
              </button>
            </div>
          </div>

          <div>
            <label className="block text-sm font-medium text-dracula-comment mb-2">Budget Amount</label>
            <input type="number" value={budgetAmount} onChange={(e) => setBudgetAmount(e.target.value)}
              className="input w-full" min="0.01" step="0.01" placeholder="10" />
          </div>

          <div className="flex items-end">
            <button onClick={handleSearch} disabled={loading || !selectedLeague}
              className="btn-primary w-full disabled:opacity-50 disabled:cursor-not-allowed">
              {loading ? 'Searching...' : 'Find Flips'}
            </button>
          </div>
        </div>

        {error && <ErrorState message={error} />}
      </section>

      {/* Results */}
      {showResults && results.length > 0 && (
        <section className="animate-slide-up">
          <div className="card mb-4">
            <div className="flex items-center justify-between">
              <div>
                <h3 className="text-lg font-semibold text-dracula-fg">{results.length} Flip Candidates</h3>
                <p className="text-sm text-dracula-comment">
                  {categories.find((c) => c.id === selectedCategory)?.name || selectedCategory}
                  {' · '}Budget: {budgetAmount} {currencyName(budgetCurrency)}
                  {' · '}sorted by flip score
                </p>
              </div>
              <div className="text-right">
                <div className={`text-2xl font-bold ${scoreColor(bestScore)}`}>
                  {bestScore.toFixed(0)}<span className="text-base text-dracula-comment">/100</span>
                </div>
                <div className="text-sm text-dracula-comment">Top Flip Score (/100)</div>
              </div>
            </div>
          </div>

          <div className="card overflow-hidden">
            <div className="overflow-x-auto">
              <table className="w-full">
                <thead>
                  <tr className="border-b border-dracula-current/50">
                    <th className="text-left py-3 px-4 text-sm font-semibold text-dracula-comment">Item</th>
                    <th className="text-right py-3 px-4 text-sm font-semibold text-dracula-comment">Price</th>
                    <th className="text-center py-3 px-4 text-sm font-semibold text-dracula-comment">Flip Score (/100)</th>
                    <th className="text-right py-3 px-4 text-sm font-semibold text-dracula-comment">Dip from Peak</th>
                    <th className="text-right py-3 px-4 text-sm font-semibold text-dracula-comment">Swing</th>
                    <th className="text-right py-3 px-4 text-sm font-semibold text-dracula-comment">Volume</th>
                  </tr>
                </thead>
                <tbody>
                  {results.map((r, i) => (
                    <tr key={r.itemId}
                      className={`border-b border-dracula-current/30 hover:bg-dracula-current/30 transition-colors duration-150 ${i === 0 ? 'bg-dracula-purple/10' : ''}`}>
                      <td className="py-3 px-4">
                        <div className="flex items-center gap-3">
                          <img src={r.icon || ''} alt="" className="w-8 h-8 rounded"
                            onError={(e) => { e.target.style.display = 'none' }} />
                          <div>
                            <div className="font-medium text-dracula-fg">{r.name}</div>
                            {r.variant && <div className="text-xs text-dracula-comment">{r.variant}</div>}
                          </div>
                        </div>
                      </td>
                      <td className="py-3 px-4 text-right text-dracula-fg font-mono whitespace-nowrap">
                        {budgetCurrency === 'divine' ? r.priceInBudget.toFixed(4) + ' div' : r.priceChaos.toFixed(2) + 'c'}
                        <div className="text-xs text-dracula-comment">{r.priceChaos} chaos</div>
                      </td>
                      <td className="py-3 px-4 text-center">
                        <span className={`font-mono font-bold ${scoreColor(r.flipScore)}`}>{r.flipScore.toFixed(0)}</span>
                        {r.monotonicDecline && (
                          <span className="ml-1 text-xs text-dracula-orange" title="Price only fell — dying item, not a dip">⚠</span>
                        )}
                      </td>
                      <td className="py-3 px-4 text-right text-dracula-comment font-mono">{Math.round(r.dipFromPeak * 100)}%</td>
                      <td className="py-3 px-4 text-right text-dracula-comment font-mono">{r.swingDepth.toFixed(0)}%</td>
                      <td className="py-3 px-4 text-right text-dracula-comment font-mono">{r.volume.toLocaleString()}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </div>

          <div className="mt-4 p-4 card text-sm text-dracula-comment">
            <div className="flex items-center gap-4 flex-wrap">
              <span className="flex items-center gap-2"><span className="w-2 h-2 bg-dracula-green rounded-full"></span>Score ≥ 80 (strong flip)</span>
              <span className="flex items-center gap-2"><span className="w-2 h-2 bg-dracula-yellow rounded-full"></span>Score 60–80 (moderate)</span>
              <span className="flex items-center gap-2"><span className="w-2 h-2 bg-dracula-orange rounded-full"></span>Score &lt; 60 / monotonic decline warning</span>
            </div>
            <p className="mt-2">
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
