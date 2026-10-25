import { useCallback, useEffect, useRef, useState } from 'react'
import { scanSampleWorkspace } from './api'
import { DuplicateGroups } from './components/DuplicateGroups'
import { FileTable } from './components/FileTable'
import { Header } from './components/Header'
import { EmptyResultState, ErrorState, IdleState, IssueList, LoadingState } from './components/StatusStates'
import { SummaryCards } from './components/SummaryCards'
import { formatDate } from './format'
import type { ScanReport } from './types'

// The screen is always in exactly one of these states.
type ScanState =
  | { status: 'idle' }
  | { status: 'loading' }
  | { status: 'error'; message: string }
  | { status: 'done'; report: ScanReport; scannedAt: string }

type Theme = 'light' | 'dark'

function useTheme(): [Theme, () => void] {
  const [theme, setTheme] = useState<Theme>(() =>
    document.documentElement.dataset.theme === 'light' ? 'light' : 'dark',
  )
  useEffect(() => {
    document.documentElement.dataset.theme = theme
    try {
      localStorage.setItem('orbit-theme', theme)
    } catch {
      /* storage unavailable: theme just won't be remembered */
    }
  }, [theme])
  return [theme, () => setTheme((t) => (t === 'dark' ? 'light' : 'dark'))]
}

export default function App() {
  const [theme, toggleTheme] = useTheme()
  const [state, setState] = useState<ScanState>({ status: 'idle' })
  const abortRef = useRef<AbortController | null>(null)

  const runScan = useCallback(async () => {
    abortRef.current?.abort()
    const controller = new AbortController()
    abortRef.current = controller
    setState({ status: 'loading' })
    try {
      const report = await scanSampleWorkspace(controller.signal)
      setState({ status: 'done', report, scannedAt: new Date().toISOString() })
    } catch (err) {
      if (controller.signal.aborted) return
      setState({ status: 'error', message: err instanceof Error ? err.message : String(err) })
    }
  }, [])

  useEffect(() => () => abortRef.current?.abort(), [])

  const report = state.status === 'done' ? state.report : null

  return (
    <div className="app">
      <Header theme={theme} onToggleTheme={toggleTheme} />

      <main className="main">
        <section className="hero panel">
          <div className="hero-text">
            <h2 className="hero-title">Sample workspace</h2>
            <p className="muted">
              ORBIT scans only the isolated, synthetic <code>sample_workspace/</code> folder inside the project. It
              reads files to fingerprint them and never moves, renames, or deletes anything.
            </p>
            {report && (
              <p className="small muted root-path" title={report.root}>
                <span className="root-label">Folder</span> <code>{report.root}</code>
                {state.status === 'done' && <> · scanned {formatDate(state.scannedAt)}</>}
              </p>
            )}
          </div>
          <button className="button button-primary" onClick={runScan} disabled={state.status === 'loading'}>
            {state.status === 'loading' ? 'Scanning…' : report ? 'Scan again' : 'Scan sample workspace'}
          </button>
        </section>

        {state.status === 'idle' && <IdleState />}
        {state.status === 'loading' && <LoadingState />}
        {state.status === 'error' && <ErrorState message={state.message} onRetry={runScan} />}

        {report && report.files.length === 0 && <EmptyResultState />}
        {report && report.files.length > 0 && (
          <>
            {report.truncated && (
              <div className="notice">This scan stopped at the file limit. Only part of the folder is shown.</div>
            )}
            <SummaryCards summary={report.summary} />
            <IssueList title="Files that could not be read" issues={report.errors} tone="warn" />
            <IssueList title="Skipped items (symlinks or special files)" issues={report.skipped} tone="info" />
            <DuplicateGroups groups={report.duplicate_groups} />
            <FileTable files={report.files} />
          </>
        )}
      </main>

      <footer className="footer muted small">ORBIT · Milestone 1 · Read-only scanner · Runs only on this computer</footer>
    </div>
  )
}
