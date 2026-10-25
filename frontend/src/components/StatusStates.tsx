import type { ScanIssue } from '../types'

export function IdleState() {
  return (
    <div className="state-card">
      <div className="state-icon" aria-hidden="true">
        <svg viewBox="0 0 24 24" width="28" height="28" fill="none" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round">
          <path d="M3 7a2 2 0 0 1 2-2h4l2 2h8a2 2 0 0 1 2 2v8a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2z" />
        </svg>
      </div>
      <h2>No scan yet</h2>
      <p className="muted">
        Press <strong>Scan sample workspace</strong> to list the synthetic test files and find exact duplicates.
      </p>
    </div>
  )
}

export function LoadingState() {
  return (
    <div className="state-card" role="status" aria-live="polite">
      <div className="spinner" aria-hidden="true" />
      <h2>Scanning…</h2>
      <p className="muted">Reading files and computing SHA-256 fingerprints.</p>
    </div>
  )
}

export function ErrorState({ message, onRetry }: { message: string; onRetry: () => void }) {
  return (
    <div className="state-card state-error" role="alert">
      <div className="state-icon" aria-hidden="true">!</div>
      <h2>Scan failed</h2>
      <p className="error-text">{message}</p>
      <button className="button" onClick={onRetry}>
        Try again
      </button>
    </div>
  )
}

export function EmptyResultState() {
  return (
    <div className="state-card">
      <h2>The folder is empty</h2>
      <p className="muted">
        No files found. Regenerate the samples with <code>python3 scripts/make_sample_workspace.py</code>.
      </p>
    </div>
  )
}

export function IssueList({ title, issues, tone }: { title: string; issues: ScanIssue[]; tone: 'warn' | 'info' }) {
  if (issues.length === 0) return null
  return (
    <details className={`issues issues-${tone}`}>
      <summary>
        {title} ({issues.length})
      </summary>
      <ul>
        {issues.map((issue) => (
          <li key={issue.relative_path}>
            <code>{issue.relative_path}</code> — {issue.reason}
          </li>
        ))}
      </ul>
    </details>
  )
}
