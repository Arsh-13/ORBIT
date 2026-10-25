import { formatBytes, groupColorClass, shortHash } from '../format'
import type { DuplicateGroup } from '../types'

export function DuplicateGroups({ groups }: { groups: DuplicateGroup[] }) {
  if (groups.length === 0) {
    return (
      <section className="panel">
        <h2 className="panel-title">Duplicate groups</h2>
        <p className="muted">No exact duplicates found. Every non-empty file has unique contents.</p>
      </section>
    )
  }

  return (
    <section className="panel">
      <div className="panel-head">
        <h2 className="panel-title">Duplicate groups</h2>
        <span className="muted small">Files with byte-identical contents, whatever their names</span>
      </div>
      <div className="group-grid">
        {groups.map((group) => (
          <article key={group.group_id} className={`group-card ${groupColorClass(group.group_id)}`}>
            <header className="group-card-head">
              <span className="group-badge">Group {group.group_id}</span>
              <span className="muted small">
                {group.file_count} copies · {formatBytes(group.size_bytes)} each
              </span>
            </header>
            <ul className="group-paths">
              {group.relative_paths.map((path) => (
                <li key={path} title={path}>
                  {path}
                </li>
              ))}
            </ul>
            <footer className="group-card-foot">
              <span className="small">
                <strong>{formatBytes(group.wasted_bytes)}</strong> reclaimable
              </span>
              <code className="hash" title={group.sha256}>
                {shortHash(group.sha256)}…
              </code>
            </footer>
          </article>
        ))}
      </div>
    </section>
  )
}
