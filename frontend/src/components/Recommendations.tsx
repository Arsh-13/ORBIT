import { formatBytes, formatDate, groupColorClass } from '../format'
import type { Confidence, CopyAssessment, DuplicateGroup, Recommendation, Signal } from '../types'

const CONFIDENCE_LABEL: Record<Confidence, string> = {
  user: 'Your choice',
  high: 'High confidence',
  medium: 'Medium confidence',
  low: 'Low confidence: please review',
}

interface Props {
  recommendations: Recommendation[]
  groups: DuplicateGroup[]
  busyGroup: string | null // sha256 of the group whose action is in progress (dimmed)
  disabled: boolean // any preference action is running: wait before allowing another
  onChoose: (sha256: string, relativePath: string) => void
  onReset: (sha256: string) => void
}

export function Recommendations({ recommendations, groups, busyGroup, disabled, onChoose, onReset }: Props) {
  if (recommendations.length === 0) {
    return (
      <section className="panel">
        <h2 className="panel-title">Recommendations</h2>
        <p className="muted">No exact duplicates found. Every non-empty file has unique contents.</p>
      </section>
    )
  }

  const sizeOf = new Map(groups.map((g) => [g.group_id, g.size_bytes]))

  return (
    <section className="panel">
      <div className="panel-head">
        <h2 className="panel-title">Recommendations</h2>
        <span className="muted small">Which copy to keep in each group of identical files. Nothing is changed on disk.</span>
      </div>
      <div className="rec-list">
        {recommendations.map((rec) => (
          <RecommendationCard
            key={rec.sha256}
            rec={rec}
            sizeEach={sizeOf.get(rec.group_id) ?? 0}
            busy={busyGroup === rec.sha256}
            disabled={disabled}
            onChoose={(path) => onChoose(rec.sha256, path)}
            onReset={() => onReset(rec.sha256)}
          />
        ))}
      </div>
    </section>
  )
}

function RecommendationCard({
  rec,
  sizeEach,
  busy,
  disabled,
  onChoose,
  onReset,
}: {
  rec: Recommendation
  sizeEach: number
  busy: boolean
  disabled: boolean
  onChoose: (path: string) => void
  onReset: () => void
}) {
  const [preferred, ...others] = rec.copies

  return (
    <article className={`rec-card ${groupColorClass(rec.group_id)}`} aria-busy={busy}>
      <header className="rec-head">
        <div className="rec-head-left">
          <span className="group-badge">Group {rec.group_id}</span>
          <span className="muted small">
            {rec.copies.length} identical copies · {formatBytes(sizeEach)} each
          </span>
        </div>
        <span className={`confidence confidence-${rec.confidence}`}>{CONFIDENCE_LABEL[rec.confidence]}</span>
      </header>

      <div className="rec-keep">
        <div className="rec-keep-label">
          <span aria-hidden="true">★</span> Keep
        </div>
        <CopyLine copy={preferred} />
      </div>

      <div className="rec-why">
        <h3 className="rec-subtitle">Why this copy</h3>
        <ul className="reason-list">
          {rec.reasons.map((reason) => (
            <li key={reason}>{reason}</li>
          ))}
        </ul>
        {rec.caveats.length > 0 && (
          <ul className="caveat-list">
            {rec.caveats.map((caveat) => (
              <li key={caveat}>{caveat}</li>
            ))}
          </ul>
        )}
      </div>

      <div className="rec-others">
        <h3 className="rec-subtitle">
          Other {others.length === 1 ? 'copy' : `copies (${others.length})`}
          <span className="reclaim">· {formatBytes(rec.reclaimable_bytes)} reclaimable</span>
        </h3>
        <ul className="other-list">
          {others.map((copy) => (
            <li key={copy.relative_path} className="other-item">
              <CopyLine copy={copy} />
              <button
                className="button button-small"
                onClick={() => onChoose(copy.relative_path)}
                disabled={disabled}
                aria-label={`Keep ${copy.relative_path} instead`}
              >
                Keep this instead
              </button>
            </li>
          ))}
        </ul>
      </div>

      <footer className="rec-foot">
        <span className="muted small">
          {rec.source === 'user' ? (
            <>
              ORBIT suggested <code>{rec.suggested_path}</code>
            </>
          ) : (
            <>Decided by: {rec.decided_by.join(' → ')}</>
          )}
        </span>
        {rec.source === 'user' && (
          <button className="button button-small button-ghost" onClick={onReset} disabled={disabled}>
            Use ORBIT's suggestion
          </button>
        )}
      </footer>
    </article>
  )
}

function CopyLine({ copy }: { copy: CopyAssessment }) {
  return (
    <div className="copy-line">
      <code className="copy-path" title={copy.absolute_path}>
        {copy.relative_path}
      </code>
      <div className="copy-meta">
        <span className="muted small">Modified {formatDate(copy.modified_at)}</span>
        {copy.is_suggested && !copy.is_preferred && <span className="chip chip-neutral">ORBIT's suggestion</span>}
        {copy.signals.map((s) => (
          <SignalChip key={s.text} signal={s} />
        ))}
      </div>
    </div>
  )
}

function SignalChip({ signal }: { signal: Signal }) {
  const icon = signal.tone === 'positive' ? '+' : signal.tone === 'negative' ? '−' : '•'
  return (
    <span className={`chip chip-${signal.tone}`}>
      <span aria-hidden="true">{icon}</span> {signal.text}
    </span>
  )
}
