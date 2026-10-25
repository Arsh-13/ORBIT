import { formatBytes } from '../format'
import type { ScanSummary } from '../types'

export function SummaryCards({ summary }: { summary: ScanSummary }) {
  const cards = [
    { label: 'Files', value: summary.total_files.toLocaleString(), hint: formatBytes(summary.total_bytes) + ' total' },
    {
      label: 'Duplicate groups',
      value: summary.duplicate_groups.toLocaleString(),
      hint: `${summary.duplicate_files} files involved`,
      accent: summary.duplicate_groups > 0,
    },
    {
      label: 'Extra copies',
      value: summary.redundant_copies.toLocaleString(),
      hint: 'beyond one copy each',
      accent: summary.redundant_copies > 0,
    },
    {
      label: 'Reclaimable',
      value: formatBytes(summary.wasted_bytes),
      hint: 'if extra copies were removed',
      accent: summary.wasted_bytes > 0,
    },
  ]

  return (
    <section className="summary-grid" aria-label="Scan summary">
      {cards.map((card) => (
        <div key={card.label} className={`stat-card${card.accent ? ' stat-accent' : ''}`}>
          <span className="stat-label">{card.label}</span>
          <span className="stat-value">{card.value}</span>
          <span className="stat-hint">{card.hint}</span>
        </div>
      ))}
    </section>
  )
}
