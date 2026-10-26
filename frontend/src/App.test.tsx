// Regression tests for the frontend bugs found in the Milestone 2 PR review.
// The backend is replaced by a fake `fetch`, so these run without any server.
import { act, cleanup, fireEvent, render, screen, waitFor } from '@testing-library/react'
import { afterEach, describe, expect, it, vi } from 'vitest'
import App from './App'
import { KeepRulesEditor } from './components/KeepRulesEditor'
import type { KeepRules, Recommendation, ScanReport } from './types'

const HASH_A = 'a'.repeat(64)
const HASH_B = 'b'.repeat(64)
const WHEN = '2026-01-15T09:00:00+00:00'

function recommendation(groupId: number, sha256: string, keep: string, other: string): Recommendation {
  const copy = (path: string, preferred: boolean) => ({
    relative_path: path,
    absolute_path: `/sandbox/${path}`,
    modified_at: WHEN,
    is_preferred: preferred,
    is_suggested: preferred,
    signals: [],
  })
  return {
    group_id: groupId,
    sha256,
    preferred_path: keep,
    suggested_path: keep,
    source: 'rules',
    confidence: 'high',
    decided_by: ['Avoided folder'],
    reasons: ['test reason'],
    caveats: [],
    reclaimable_bytes: 10,
    copies: [copy(keep, true), copy(other, false)],
  }
}

function makeReport(): ScanReport {
  const file = (path: string, sha256: string, group: number) => ({
    name: path.split('/').pop()!,
    extension: '.txt',
    size_bytes: 10,
    modified_at: WHEN,
    absolute_path: `/sandbox/${path}`,
    relative_path: path,
    sha256,
    duplicate_group: group,
  })
  return {
    root: '/sandbox',
    truncated: false,
    summary: {
      total_files: 4,
      total_bytes: 40,
      duplicate_groups: 2,
      duplicate_files: 4,
      redundant_copies: 2,
      wasted_bytes: 20,
      skipped_count: 0,
      error_count: 0,
    },
    files: [file('notes/a.txt', HASH_A, 1), file('downloads/a.txt', HASH_A, 1), file('notes/b.txt', HASH_B, 2), file('downloads/b.txt', HASH_B, 2)],
    duplicate_groups: [
      { group_id: 1, sha256: HASH_A, size_bytes: 10, file_count: 2, wasted_bytes: 10, relative_paths: ['downloads/a.txt', 'notes/a.txt'] },
      { group_id: 2, sha256: HASH_B, size_bytes: 10, file_count: 2, wasted_bytes: 10, relative_paths: ['downloads/b.txt', 'notes/b.txt'] },
    ],
    skipped: [],
    errors: [],
    recommendations: [recommendation(1, HASH_A, 'notes/a.txt', 'downloads/a.txt'), recommendation(2, HASH_B, 'notes/b.txt', 'downloads/b.txt')],
    keep_rules: { preferred_folders: ['documents'], avoid_folders: ['downloads'] },
  }
}

const json = (body: unknown, status = 200) =>
  new Response(JSON.stringify(body), { status, headers: { 'Content-Type': 'application/json' } })

type Handler = (url: string, init?: RequestInit) => Promise<Response>

function fakeBackend(handler: Handler) {
  const calls: { url: string; method: string }[] = []
  vi.stubGlobal('fetch', (url: string, init?: RequestInit) => {
    calls.push({ url, method: init?.method ?? 'GET' })
    return handler(url, init)
  })
  return calls
}

async function scanAndWaitForCards() {
  fireEvent.click(screen.getByRole('button', { name: 'Scan sample workspace' }))
  await screen.findByText('Recommendations')
}

afterEach(() => {
  cleanup()
  vi.unstubAllGlobals()
})

describe('KeepRulesEditor (bug 2: unsaved edits were lost on rescan)', () => {
  const rules: KeepRules = { preferred_folders: ['documents'], avoid_folders: ['downloads'] }

  function addPreferred(folder: string) {
    fireEvent.change(screen.getByLabelText('Add folder to “Prefer copies in”'), { target: { value: folder } })
    fireEvent.click(screen.getAllByRole('button', { name: 'Add' })[0])
  }

  it('keeps an unsaved edit when the same rules arrive again as a new object', () => {
    const { rerender } = render(<KeepRulesEditor rules={rules} saving={false} onSave={() => {}} />)
    addPreferred('projects')
    expect(screen.getByText('projects')).toBeTruthy()

    // A rescan delivers equal rules in a brand-new object.
    rerender(<KeepRulesEditor rules={{ ...rules, preferred_folders: [...rules.preferred_folders] }} saving={false} onSave={() => {}} />)
    expect(screen.getByText('projects')).toBeTruthy()
    expect((screen.getByRole('button', { name: 'Save rules' }) as HTMLButtonElement).disabled).toBe(false)
  })

  it('resets the draft when the saved rules really change', () => {
    const { rerender } = render(<KeepRulesEditor rules={rules} saving={false} onSave={() => {}} />)
    addPreferred('projects')
    rerender(<KeepRulesEditor rules={{ preferred_folders: ['school'], avoid_folders: [] }} saving={false} onSave={() => {}} />)
    expect(screen.queryByText('projects')).toBeNull()
    expect(screen.getByText('school')).toBeTruthy()
  })
})

describe('App actions', () => {
  it('bug 3: allows only one preference change at a time', async () => {
    let finishPut: (r: Response) => void = () => {}
    const calls = fakeBackend((_url, init) => {
      if (init?.method === 'PUT') return new Promise<Response>((resolve) => (finishPut = resolve))
      return Promise.resolve(json(makeReport()))
    })
    render(<App />)
    await scanAndWaitForCards()

    const keepA = screen.getByRole('button', { name: 'Keep downloads/a.txt instead' })
    const keepB = screen.getByRole('button', { name: 'Keep downloads/b.txt instead' })
    fireEvent.click(keepA)
    fireEvent.click(keepB) // second click while the first is still running

    expect((keepB as HTMLButtonElement).disabled).toBe(true)
    expect(calls.filter((c) => c.method === 'PUT')).toHaveLength(1)

    await act(async () => finishPut(json({ sha256: HASH_A, relative_path: 'downloads/a.txt' })))
    await waitFor(() =>
      expect((screen.getByRole('button', { name: 'Keep downloads/b.txt instead' }) as HTMLButtonElement).disabled).toBe(false),
    )
  })

  it('bug 4: a failed refresh after a saved change keeps the results on screen', async () => {
    let scans = 0
    fakeBackend((_url, init) => {
      if (init?.method === 'PUT') return Promise.resolve(json({ sha256: HASH_A, relative_path: 'downloads/a.txt' }))
      scans += 1
      return Promise.resolve(scans === 1 ? json(makeReport()) : new Response('Bad Gateway', { status: 502 }))
    })
    render(<App />)
    await scanAndWaitForCards()

    fireEvent.click(screen.getByRole('button', { name: 'Keep downloads/a.txt instead' }))

    const banner = await screen.findByRole('alert')
    expect(banner.textContent).toContain("Your change was saved, but the results couldn't refresh")
    expect(screen.getByText('Recommendations')).toBeTruthy() // results still shown
    expect(screen.queryByText('Scan failed')).toBeNull() // not replaced by the error page
  })

  it('a failed change shows its error without a refresh', async () => {
    let scans = 0
    fakeBackend((_url, init) => {
      if (init?.method === 'PUT') return Promise.resolve(json({ detail: "That file's contents don't match this duplicate group" }, 409))
      scans += 1
      return Promise.resolve(json(makeReport()))
    })
    render(<App />)
    await scanAndWaitForCards()
    fireEvent.click(screen.getByRole('button', { name: 'Keep downloads/a.txt instead' }))
    expect((await screen.findByRole('alert')).textContent).toContain("don't match this duplicate group")
    expect(scans).toBe(1)
  })
})
