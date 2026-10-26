import type { KeepRules, ScanReport } from './types'

const BACKEND_DOWN =
  'Could not reach the ORBIT backend. Is it running? Start it with: cd backend && .venv/bin/python -m orbit'

/** Send a request to the backend. Throws an Error with a readable message on failure. */
async function request<T>(url: string, init?: RequestInit): Promise<T> {
  let response: Response
  try {
    response = await fetch(url, init)
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
      else if (Array.isArray(body?.detail)) detail = 'The server rejected that request (invalid input).'
    } catch {
      /* not JSON */
    }
    throw new Error(detail ?? (response.status >= 500 ? BACKEND_DOWN : `Request failed (HTTP ${response.status})`))
  }

  return response.status === 204 ? (undefined as T) : ((await response.json()) as T)
}

function sendJson(method: 'PUT', body: unknown): RequestInit {
  return { method, headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(body) }
}

/** Ask the backend to scan the sample workspace (read-only). */
export function scanSampleWorkspace(signal?: AbortSignal): Promise<ScanReport> {
  return request<ScanReport>('/api/scan', { signal })
}

// The calls below only change ORBIT's own preference database, never your files.

export function choosePreferredCopy(sha256: string, relativePath: string): Promise<unknown> {
  return request('/api/preferences/choices', sendJson('PUT', { sha256, relative_path: relativePath }))
}

export function resetPreferredCopy(sha256: string): Promise<void> {
  return request<void>(`/api/preferences/choices/${sha256}`, { method: 'DELETE' })
}

export function saveKeepRules(rules: KeepRules): Promise<KeepRules> {
  return request<KeepRules>('/api/preferences/rules', sendJson('PUT', rules))
}
