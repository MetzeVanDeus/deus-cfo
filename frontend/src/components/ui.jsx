import { signalColor } from '../lib/helpers'

export function SignalBadge({ type }) {
  const color = signalColor(type)
  const colorMap = { red: 'bg-dracula-red/20 text-dracula-red', green: 'bg-dracula-green/20 text-dracula-green', cyan: 'bg-dracula-cyan/20 text-dracula-cyan', yellow: 'bg-dracula-yellow/20 text-dracula-yellow', orange: 'bg-dracula-orange/20 text-dracula-orange', purple: 'bg-dracula-purple/20 text-dracula-purple', comment: 'bg-dracula-comment/20 text-dracula-comment' }
  return <span className={`badge ${colorMap[color]}`}>{type}</span>
}
export function SourceBadge({ source }) { return <span className="badge">{source === 'regime' ? 'Regime' : 'Anomaly'}</span> }
export function ConfidenceBar({ score }) { const pct = Math.round((score || 0) * 100); return <span className="compact-confidence">{pct}%</span> }
export function LoadingState({ text = 'Loading...' }) { return <div className="loading-state"><span className="spinner" /><span>{text}</span></div> }
export function EmptyState({ title, message }) { return <div className="empty-state"><div className="eyebrow">NO DATA</div><h3>{title}</h3><p>{message}</p></div> }
export function ErrorState({ message, onRetry }) { return <div className="error-state" role="alert">{message}{onRetry && <button className="text-button" onClick={onRetry}>RETRY</button>}</div> }
