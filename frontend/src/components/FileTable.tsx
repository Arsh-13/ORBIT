import { useMemo, useState } from 'react'
import { folderOf, formatBytes, formatDate, groupColorClass, shortHash } from '../format'
import type { FileRecord } from '../types'

type SortKey = 'name' | 'size' | 'modified'
type Filter = 'all' | 'duplicates'

const SORTERS: Record<SortKey, (a: FileRecord, b: FileRecord) => number> = {
  name: (a, b) => a.relative_path.localeCompare(b.relative_path),
  size: (a, b) => b.size_bytes - a.size_bytes,
  modified: (a, b) => b.modified_at.localeCompare(a.modified_at),
}

export function FileTable({ files, preferredPaths }: { files: FileRecord[]; preferredPaths: Set<string> }) {
  const [query, setQuery] = useState('')
  const [filter, setFilter] = useState<Filter>('all')
  const [sortKey, setSortKey] = useState<SortKey>('name')

  const visible = useMemo(() => {
    const q = query.trim().toLowerCase()
    return files
      .filter((f) => filter === 'all' || f.duplicate_group !== null)
      .filter((f) => !q || f.relative_path.toLowerCase().includes(q))
      .sort(SORTERS[sortKey])
  }, [files, query, filter, sortKey])

  return (
    <section className="panel">
      <div className="panel-head table-toolbar">
        <h2 className="panel-title">
          Files <span className="count">{visible.length}</span>
        </h2>
        <div className="toolbar-controls">
          <input
            className="input"
            type="search"
            placeholder="Filter by name…"
            value={query}
            onChange={(e) => setQuery(e.target.value)}
            aria-label="Filter files by name"
          />
          <div className="segmented" role="group" aria-label="Show">
            <button className={filter === 'all' ? 'active' : ''} onClick={() => setFilter('all')}>
              All
            </button>
            <button className={filter === 'duplicates' ? 'active' : ''} onClick={() => setFilter('duplicates')}>
              Duplicates
            </button>
          </div>
          <select
            className="input select"
            value={sortKey}
            onChange={(e) => setSortKey(e.target.value as SortKey)}
            aria-label="Sort files"
          >
            <option value="name">Sort: Name</option>
            <option value="size">Sort: Largest</option>
            <option value="modified">Sort: Newest</option>
          </select>
        </div>
      </div>

      {visible.length === 0 ? (
        <p className="muted table-empty">No files match this filter.</p>
      ) : (
        <div className="table-wrap">
          <table className="file-table">
            <thead>
              <tr>
                <th>Name</th>
                <th>Type</th>
                <th className="num">Size</th>
                <th>Modified</th>
                <th>Duplicate</th>
                <th>SHA-256</th>
              </tr>
            </thead>
            <tbody>
              {visible.map((file) => {
                const group = file.duplicate_group
                return (
                  <tr key={file.relative_path} className={group !== null ? `dup-row ${groupColorClass(group)}` : ''}>
                    <td data-label="Name" className="name-cell">
                      <span className="file-name" title={file.absolute_path}>
                        {file.name}
                      </span>
                      {folderOf(file.relative_path) && <span className="file-folder">{folderOf(file.relative_path)}/</span>}
                    </td>
                    <td data-label="Type">
                      <span className="ext">{file.extension ? file.extension.slice(1) : '—'}</span>
                    </td>
                    <td data-label="Size" className="num">
                      {formatBytes(file.size_bytes)}
                    </td>
                    <td data-label="Modified" className="nowrap">
                      {formatDate(file.modified_at)}
                    </td>
                    <td data-label="Duplicate">
                      {group !== null ? (
                        <span className="dup-cell">
                          <span className="group-badge">Group {group}</span>
                          {preferredPaths.has(file.relative_path) ? (
                            <span className="role role-keep">★ Keep</span>
                          ) : (
                            <span className="role role-extra">Extra copy</span>
                          )}
                        </span>
                      ) : (
                        <span className="muted">—</span>
                      )}
                    </td>
                    <td data-label="SHA-256">
                      <code className="hash" title={file.sha256}>
                        {shortHash(file.sha256)}…
                      </code>
                    </td>
                  </tr>
                )
              })}
            </tbody>
          </table>
        </div>
      )}
    </section>
  )
}
