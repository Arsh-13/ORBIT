const UNITS = ['B', 'KB', 'MB', 'GB', 'TB']

export function formatBytes(bytes: number): string {
  if (bytes < 1024) return `${bytes} B`
  let value = bytes
  let unit = 0
  while (value >= 1024 && unit < UNITS.length - 1) {
    value /= 1024
    unit++
  }
  return `${value.toFixed(value < 10 ? 1 : 0)} ${UNITS[unit]}`
}

const dateFormatter = new Intl.DateTimeFormat(undefined, {
  year: 'numeric',
  month: 'short',
  day: 'numeric',
  hour: '2-digit',
  minute: '2-digit',
})

export function formatDate(iso: string): string {
  const date = new Date(iso)
  return Number.isNaN(date.getTime()) ? iso : dateFormatter.format(date)
}

export function shortHash(hash: string): string {
  return hash.slice(0, 10)
}

/** Duplicate groups cycle through 6 accent colours (defined in index.css). */
export function groupColorClass(groupId: number): string {
  return `group-c${(groupId - 1) % 6}`
}

export function folderOf(relativePath: string): string {
  const i = relativePath.lastIndexOf('/')
  return i === -1 ? '' : relativePath.slice(0, i)
}
