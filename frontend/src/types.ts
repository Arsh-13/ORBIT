// TypeScript mirrors of the JSON returned by the backend (see backend/orbit/duplicates.py).

export interface FileRecord {
  name: string
  extension: string
  size_bytes: number
  modified_at: string
  absolute_path: string
  relative_path: string
  sha256: string
  duplicate_group: number | null
}

export interface DuplicateGroup {
  group_id: number
  sha256: string
  size_bytes: number
  file_count: number
  wasted_bytes: number
  relative_paths: string[]
}

export interface ScanIssue {
  relative_path: string
  reason: string
}

export interface ScanSummary {
  total_files: number
  total_bytes: number
  duplicate_groups: number
  duplicate_files: number
  redundant_copies: number
  wasted_bytes: number
  skipped_count: number
  error_count: number
}

export interface ScanReport {
  root: string
  truncated: boolean
  summary: ScanSummary
  files: FileRecord[]
  duplicate_groups: DuplicateGroup[]
  skipped: ScanIssue[]
  errors: ScanIssue[]
}
