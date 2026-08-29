import { LEAGUE_EMPTY_MESSAGE, LEAGUE_EMPTY_TITLE, signalColor } from '../lib/helpers'

export function SignalBadge({ type }) {
  const color = signalColor(type)
  return <span className={`badge badge-${color}`}>{type}</span>
}
export function SourceBadge({ source }) { return <span className="badge">{source === 'regime' ? 'Regime' : 'Anomaly'}</span> }
export function ConfidencePercent({ score }) { const pct = Math.round((score || 0) * 100); return <span className="compact-confidence">{pct}%</span> }
export function StateBlock({ kind = 'empty', eyebrow, title, message, action, compact = false }) {
  const role = kind === 'error' ? 'alert' : kind === 'loading' ? 'status' : undefined
  return <div className={`state state-${kind}${compact ? ' state-compact' : ''}`} role={role}>
    {kind === 'loading' && <span className="spinner" aria-hidden="true" />}
    <div className="state-copy">
      {eyebrow && <div className="eyebrow">{eyebrow}</div>}
      {title && <h3>{title}</h3>}
      {message && <p>{message}</p>}
    </div>
    {action && <div className="state-action">{action}</div>}
  </div>
}
export function LoadingState({ text = 'Loading...' }) { return <StateBlock kind="loading" eyebrow="WORKING" title={text} /> }
export function EmptyState({ eyebrow = 'NO DATA', title, message, action, compact = false }) { return <StateBlock kind="empty" eyebrow={eyebrow} title={title} message={message} action={action} compact={compact} /> }
export function ErrorState({ message, onRetry }) { return <StateBlock kind="error" eyebrow="ERROR" title="Unable to load" message={message} action={onRetry && <button className="text-button" onClick={onRetry}>RETRY</button>} /> }
export function LeagueEmpty() { return <EmptyState title={LEAGUE_EMPTY_TITLE} message={LEAGUE_EMPTY_MESSAGE} /> }
