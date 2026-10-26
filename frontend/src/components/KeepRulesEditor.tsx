import { useState } from 'react'
import type { KeepRules } from '../types'

interface Props {
  rules: KeepRules
  saving: boolean
  onSave: (rules: KeepRules) => void
}

type ListKey = keyof KeepRules

/** Edit the folders ORBIT prefers or avoids. Saving only updates ORBIT's preferences. */
export function KeepRulesEditor({ rules, saving, onSave }: Props) {
  const [draft, setDraft] = useState<KeepRules>(rules)
  const [inputs, setInputs] = useState<Record<ListKey, string>>({ preferred_folders: '', avoid_folders: '' })
  const [lastSaved, setLastSaved] = useState(rules)

  // When fresh rules arrive from the server (after a save or rescan), reset the draft.
  if (rules !== lastSaved) {
    setLastSaved(rules)
    setDraft(rules)
  }

  const dirty = JSON.stringify(draft) !== JSON.stringify(rules)

  const add = (key: ListKey) => {
    const value = inputs[key].trim()
    if (!value) return
    setDraft((d) => (d[key].includes(value) ? d : { ...d, [key]: [...d[key], value] }))
    setInputs((i) => ({ ...i, [key]: '' }))
  }
  const remove = (key: ListKey, folder: string) => setDraft((d) => ({ ...d, [key]: d[key].filter((f) => f !== folder) }))

  const lists: { key: ListKey; title: string; hint: string; tone: 'positive' | 'negative'; placeholder: string }[] = [
    {
      key: 'preferred_folders',
      title: 'Prefer copies in',
      hint: 'Earlier folders win over later ones.',
      tone: 'positive',
      placeholder: 'e.g. documents',
    },
    {
      key: 'avoid_folders',
      title: 'Avoid keeping copies in',
      hint: 'Places that usually hold throwaway copies.',
      tone: 'negative',
      placeholder: 'e.g. downloads',
    },
  ]

  return (
    <details className="panel rules-panel">
      <summary className="rules-summary">
        <span className="panel-title">Keep rules</span>
        <span className="muted small">
          Prefer {rules.preferred_folders.join(', ') || 'nothing'} · Avoid {rules.avoid_folders.join(', ') || 'nothing'}
        </span>
      </summary>

      <p className="muted small rules-intro">
        ORBIT checks these rules in order: <strong>preferred folder</strong>, then <strong>avoided folder</strong>, then{' '}
        <strong>filename</strong> (no “(1)”, “copy”, “scan0001”…), then <strong>oldest copy</strong>. Folder names are
        relative to the sample workspace.
      </p>

      <div className="rules-grid">
        {lists.map(({ key, title, hint, tone, placeholder }) => (
          <div key={key} className="rules-column">
            <h3 className="rec-subtitle">{title}</h3>
            <p className="muted small">{hint}</p>
            <ul className="folder-chips">
              {draft[key].length === 0 && <li className="muted small">None</li>}
              {draft[key].map((folder, index) => (
                <li key={folder} className={`chip chip-${tone}`}>
                  {key === 'preferred_folders' && draft[key].length > 1 && <span className="chip-rank">#{index + 1}</span>}
                  {folder}
                  <button className="chip-remove" onClick={() => remove(key, folder)} aria-label={`Remove ${folder}`}>
                    ×
                  </button>
                </li>
              ))}
            </ul>
            <form
              className="rules-add"
              onSubmit={(e) => {
                e.preventDefault()
                add(key)
              }}
            >
              <input
                className="input"
                value={inputs[key]}
                maxLength={100}
                placeholder={placeholder}
                onChange={(e) => setInputs((i) => ({ ...i, [key]: e.target.value }))}
                aria-label={`Add folder to “${title}”`}
              />
              <button className="button button-small" type="submit" disabled={!inputs[key].trim()}>
                Add
              </button>
            </form>
          </div>
        ))}
      </div>

      <div className="rules-actions">
        {dirty && (
          <button className="button button-small button-ghost" onClick={() => setDraft(rules)} disabled={saving}>
            Discard changes
          </button>
        )}
        <button className="button button-primary button-small" onClick={() => onSave(draft)} disabled={!dirty || saving}>
          {saving ? 'Saving…' : 'Save rules'}
        </button>
      </div>
    </details>
  )
}
