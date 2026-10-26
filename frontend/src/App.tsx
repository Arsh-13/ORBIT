import { useCallback, useEffect, useMemo, useRef, useState } from 'react'
import { choosePreferredCopy, resetPreferredCopy, saveKeepRules, scanSampleWorkspace } from './api'
import { FileTable } from './components/FileTable'
import { Header } from './components/Header'
import { KeepRulesEditor } from './components/KeepRulesEditor'
import { Recommendations } from './components/Recommendations'
import { EmptyResultState, ErrorState, IdleState, IssueList, LoadingState } from './components/StatusStates'
import { SummaryCards } from './components/SummaryCards'
import { formatDate } from './format'
import type { KeepRules, ScanReport } from './types'

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
  const [busy, setBusy] = useState<string | null>(null) // which action is running: a group's sha256, or 'rules'
  const [actionError, setActionError] = useState<string | null>(null)
  const abortRef = useRef<AbortController | null>(null)

  /** Scan the workspace. `quiet` keeps the current results on screen while refreshing. */
  const runScan = useCallback(async (quiet = false) => {
    abortRef.current?.abort()
    const controller = new AbortController()
    abortRef.current = controller
    if (!quiet) setState({ status: 'loading' })
    try {
      const report = await scanSampleWorkspace(controller.signal)
      setState({ status: 'done', report, scannedAt: new Date().toISOString() })
    } catch (err) {
      if (controller.signal.aborted) return
      setState({ status: 'error', message: err instanceof Error ? err.message : String(err) })
    }
  }, [])

  useEffect(() => () => abortRef.current?.abort(), [])

  /** Run a preference change, then refresh the results so the new recommendation shows. */
  const runAction = useCallback(
    async (key: string, action: () => Promise<unknown>) => {
      setBusy(key)
      setActionError(null)
      try {
        await action()
        await runScan(true)
      } catch (err) {
        setActionError(err instanceof Error ? err.message : String(err))
      } finally {
        setBusy(null)
      }
    },
    [runScan],
  )

  const report = state.status === 'done' ? state.report : null
  const preferredPaths = useMemo(
    () => new Set(report?.recommendations.map((r) => r.preferred_path) ?? []),
    [report],
  )

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
          <button className="button button-primary" onClick={() => runScan()} disabled={state.status === 'loading'}>
            {state.status === 'loading' ? 'Scanning…' : report ? 'Scan again' : 'Scan sample workspace'}
          </button>
        </section>

        {state.status === 'idle' && <IdleState />}
        {state.status === 'loading' && <LoadingState />}
        {state.status === 'error' && <ErrorState message={state.message} onRetry={() => runScan()} />}

        {report && report.files.length === 0 && <EmptyResultState />}
        {report && report.files.length > 0 && (
          <>
            {report.truncated && (
              <div className="notice">This scan stopped at the file limit. Only part of the folder is shown.</div>
            )}
            {actionError && (
              <div className="notice notice-error" role="alert">
                {actionError}
                <button className="chip-remove" onClick={() => setActionError(null)} aria-label="Dismiss">
                  ×
                </button>
              </div>
            )}
            <SummaryCards summary={report.summary} />
            <IssueList title="Files that could not be read" issues={report.errors} tone="warn" />
            <IssueList title="Skipped items (symlinks or special files)" issues={report.skipped} tone="info" />
            <KeepRulesEditor
              rules={report.keep_rules}
              saving={busy === 'rules'}
              onSave={(rules: KeepRules) => runAction('rules', () => saveKeepRules(rules))}
            />
            <Recommendations
              recommendations={report.recommendations}
              groups={report.duplicate_groups}
              busyGroup={busy}
              onChoose={(sha, path) => runAction(sha, () => choosePreferredCopy(sha, path))}
              onReset={(sha) => runAction(sha, () => resetPreferredCopy(sha))}
            />
            <FileTable files={report.files} preferredPaths={preferredPaths} />
          </>
        )}
      </main>

      <footer className="footer muted small">
        ORBIT · Milestone 2 · Read-only recommendations · Runs only on this computer
      </footer>
    </div>
  )
}
