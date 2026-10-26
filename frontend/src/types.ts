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

// ---- Milestone 2: recommendations (see backend/orbit/recommend.py) ----

export interface Signal {
  text: string
  tone: 'positive' | 'negative' | 'neutral'
}

export interface CopyAssessment {
  relative_path: string
  absolute_path: string
  modified_at: string
  is_preferred: boolean
  is_suggested: boolean
  signals: Signal[]
}

export type Confidence = 'user' | 'high' | 'medium' | 'low'

export interface Recommendation {
  group_id: number
  sha256: string
  preferred_path: string
  suggested_path: string
  source: 'rules' | 'user'
  confidence: Confidence
  decided_by: string[]
  reasons: string[]
  caveats: string[]
  reclaimable_bytes: number
  copies: CopyAssessment[]
}

export interface KeepRules {
  preferred_folders: string[]
  avoid_folders: string[]
}

export interface ScanReport {
  root: string
  truncated: boolean
  summary: ScanSummary
  files: FileRecord[]
  duplicate_groups: DuplicateGroup[]
  skipped: ScanIssue[]
  errors: ScanIssue[]
  recommendations: Recommendation[]
  keep_rules: KeepRules
}
