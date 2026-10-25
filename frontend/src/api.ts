import type { ScanReport } from './types'

const BACKEND_DOWN =
  'Could not reach the ORBIT backend. Is it running? Start it with: cd backend && .venv/bin/python -m orbit'

/** Ask the backend to scan the sample workspace. Throws an Error with a readable message on failure. */
export async function scanSampleWorkspace(signal?: AbortSignal): Promise<ScanReport> {
  let response: Response
  try {
    response = await fetch('/api/scan', { signal })
  } catch (err) {
    if (err instanceof DOMException && err.name === 'AbortError') throw err
    throw new Error(BACKEND_DOWN)
  }

  if (!response.ok) {
    // FastAPI errors look like {"detail": "..."}; a proxy error (backend down) has no JSON.
    let detail: string | undefined
    try {
      const body = await response.json()
      if (typeof body?.detail === 'string') detail = body.detail
    } catch {
      /* not JSON */
    }
    throw new Error(detail ?? (response.status >= 500 ? BACKEND_DOWN : `Scan failed (HTTP ${response.status})`))
  }

  return (await response.json()) as ScanReport
}
