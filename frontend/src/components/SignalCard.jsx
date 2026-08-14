import { SignalBadge, SourceBadge, ConfidenceBar } from './ui'

export function SignalCard({ signal }) {
  return (
    <div className="card animate-fade-in hover:border-dracula-purple/50 transition-colors duration-200">
      <div className="flex items-start justify-between gap-3 mb-3">
        <div className="flex items-center gap-2 flex-wrap">
          <SignalBadge type={signal.type} />
          <SourceBadge source={signal.source} />
        </div>
        <div className="text-sm text-dracula-comment whitespace-nowrap">
          {Math.round((signal.confidence || 0) * 100)}%
        </div>
      </div>

      <div className="mb-3">
        <span className="font-semibold text-dracula-fg">{signal.item}</span>
        <span className="text-dracula-comment text-sm ml-2">· {signal.category}</span>
      </div>

      <div className="space-y-2 text-sm">
        <div>
          <span className="text-dracula-comment text-xs uppercase tracking-wide">What happened</span>
          <p className="text-dracula-fg/90">{signal.what_happened}</p>
        </div>
        <div>
          <span className="text-dracula-comment text-xs uppercase tracking-wide">Why it matters</span>
          <p className="text-dracula-fg/90">{signal.why_it_matters}</p>
        </div>
        {signal.possible_action && (
          <div>
            <span className="text-dracula-comment text-xs uppercase tracking-wide">Possible action</span>
            <p className="text-dracula-fg/90">{signal.possible_action}</p>
          </div>
        )}
      </div>

      <div className="mt-4">
        <div className="flex items-center justify-between mb-1">
          <span className="text-xs text-dracula-comment">Confidence</span>
        </div>
        <ConfidenceBar score={signal.confidence} />
      </div>
    </div>
  )
}
