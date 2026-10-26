# ORBIT

**ORBIT** is an open-source, local-first personal assistant for your files. The long-term goal
is a cross-device assistant that organises files, catches duplicate downloads, suggests better
filenames, searches documents by content, and accepts authorised commands from your phone.

> **Current status: Milestone 2.** A **read-only** folder scanner with **exact duplicate
> detection** and **explainable "which copy to keep" recommendations**, a FastAPI backend, and a
> React + TypeScript dashboard. It only ever scans the synthetic `sample_workspace/` folder in
> this repository.

---

## What Milestone 1 does

- Scans `sample_workspace/` recursively and lists each file's name, extension, size,
  modification time, and absolute path.
- Fingerprints every file with **SHA-256**, reading it in 1 MiB chunks so big files don't fill memory.
- Groups **byte-identical files** together, even when their names or folders differ.
- Shows everything in a dashboard with summary cards, colour-coded duplicate groups, a
  filterable and sortable file table, dark/light mode, and a phone-friendly layout.

## What Milestone 2 adds

- **A recommendation for every duplicate group**: which copy to keep, *why* (one plain-English
  reason per rule that decided), any conflicting signals, a confidence level, and reclaimable space.
- **Transparent rules, applied in priority order:**
  1. **Preferred folder**: in a folder you prefer (earlier in your list wins). Strong.
  2. **Avoided folder**: not in a folder you avoid, such as `downloads`. Strong.
  3. **Filename**: no copy markers like `(1)`, `copy`, `Copy of`, `scan0001`, `IMG_1234`. Medium.
  4. **Oldest copy**: earliest modification time, with a 2-second tolerance. Weak.
  5. **Alphabetical tie-break**, flagged as *low confidence: please review*.
- **"Keep this instead"** lets you pick a different copy, and **"Use ORBIT's suggestion"** undoes
  it. Choices and keep rules are saved in ORBIT's own database (`data/local/orbit.sqlite3`,
  git-ignored, outside the scanned folder). **No scanned file is ever changed.**
- **Synthetic PDFs for future annotated-PDF matching**: an original, an exact re-download, an
  annotated copy saved by appending, an annotated copy saved by full rewrite, and a 2nd edition.
  Only the exact re-download counts as a duplicate. Research and the proposed approach are in
  [`docs/pdf-matching.md`](docs/pdf-matching.md).

## Safety model

| Rule | How it's enforced |
| --- | --- |
| Never touch personal files | The scan root is hard-coded to `sample_workspace/` (`backend/orbit/config.py`). There's no setting or API parameter that points it anywhere else. |
| Read-only | Scanned files are opened with `O_RDONLY` only. Nothing is written, renamed, moved, or deleted, and tests check that file contents and timestamps are unchanged after scans *and* after every preference change. The only write endpoints update ORBIT's own preferences database, which must live outside the scanned folder. |
| No cross-site tricks | Preference writes need JSON (`PUT`/`DELETE`, which browsers won't send cross-site without permission ORBIT never grants), and requests with a foreign `Origin` header are refused (`403`). |
| Choices are verified | Before saving "keep this copy", ORBIT re-checks the path with the sandbox gatekeeper and re-hashes the file to prove it belongs to that group (`409` if not). |
| No path traversal | The optional `folder` parameter is resolved and must stay inside the sandbox (`backend/orbit/safety.py`). `..`, absolute paths, `~`, and NUL bytes are rejected. |
| No symlink escapes | Symlinks are never followed during a scan. Files are opened with `O_NOFOLLOW`, and every folder entered is re-checked against the sandbox. |
| No hangs on special files | FIFOs, sockets, and device files are skipped. Only regular files are read. |
| Local only | The backend binds to `127.0.0.1:8000` and rejects requests with a non-localhost `Host` header. The frontend dev server binds to `127.0.0.1:5173`. |
| Errors don't crash the scan | Unreadable files or folders are listed under "errors", and the scan continues. |

## Project layout

```
ORBIT/
├── backend/                  Python engine + API
│   ├── orbit/
│   │   ├── config.py         Settings: the one allowed folder, chunk size, limits
│   │   ├── safety.py         Gatekeeper that keeps paths inside the sandbox
│   │   ├── scanner.py        Walks folders, collects metadata, hashes files (read-only)
│   │   ├── duplicates.py     Groups identical hashes and builds the summary report
│   │   ├── recommend.py      Rules engine: which copy to keep, with reasons (pure, no I/O)
│   │   ├── preferences.py    Keep rules + your choices, stored in ORBIT's SQLite database
│   │   ├── api.py            FastAPI app: scan, recommendations, preference endpoints
│   │   └── __main__.py       `python -m orbit` starts the server on 127.0.0.1
│   ├── tests/                pytest suite (safety, scanner, duplicates, recommendations, API)
│   └── pyproject.toml        Python dependencies
├── frontend/                 React + TypeScript dashboard (Vite)
│   ├── src/
│   │   ├── App.tsx           Page layout and the idle/loading/error/done state machine
│   │   ├── api.ts            Calls the backend and turns failures into readable messages
│   │   ├── types.ts          TypeScript shapes of the API's JSON
│   │   ├── format.ts         Byte, date, and hash formatting helpers
│   │   ├── components/       Header, SummaryCards, Recommendations, KeepRulesEditor, FileTable, StatusStates
│   │   └── index.css         Design tokens, dark/light themes, responsive layout
│   └── vite.config.ts        Dev server (localhost only) + /api proxy to the backend
├── docs/
│   └── pdf-matching.md       Research: annotated PDFs vs. new editions
├── sample_workspace/         Synthetic test files (6 duplicate groups + PDF versions)
└── scripts/
    └── make_sample_workspace.py   Regenerates the synthetic files
```

## Requirements

- **Python 3.11+** (developed on 3.12)
- **Node.js 20+** (developed on Node 24 LTS) with npm

## Install

```bash
cd ~/Documents/ORBIT

# Backend: create an isolated Python environment and install dependencies
cd backend
python3 -m venv .venv
.venv/bin/pip install -e ".[dev]"
cd ..

# Frontend
cd frontend
npm install
cd ..
```

## Run

Use two terminal windows.

**Terminal 1: backend API**

```bash
cd ~/Documents/ORBIT/backend
.venv/bin/python -m orbit
# → http://127.0.0.1:8000/api/health   (interactive API docs: http://127.0.0.1:8000/docs)
```

**Terminal 2: frontend dashboard**

```bash
cd ~/Documents/ORBIT/frontend
npm run dev
# → open http://127.0.0.1:5173 and click "Scan sample workspace"
```

Stop either server with `Ctrl+C`. After pulling new backend code, restart the backend.

To run a second copy on other ports (e.g. while another one is running):
`.venv/bin/uvicorn orbit.api:app --host 127.0.0.1 --port 8001` and
`ORBIT_API_URL=http://127.0.0.1:8001 npx vite --port 5174`.

## Test

```bash
cd ~/Documents/ORBIT/backend
.venv/bin/pytest -v
```

Frontend type-check, production build, and lint:

```bash
cd ~/Documents/ORBIT/frontend
npm run build
npm run lint
```

## API

| Method | Path | Description |
| --- | --- | --- |
| GET | `/api/health` | `{"status": "ok", "version": "0.2.0"}` |
| GET | `/api/scan` | Scan the whole sample workspace |
| GET | `/api/scan?folder=downloads` | Scan a subfolder **inside** the sample workspace |
| GET | `/api/preferences` | Current keep rules and your preferred-copy choices |
| PUT | `/api/preferences/rules` | `{"preferred_folders": [...], "avoid_folders": [...]}` |
| PUT | `/api/preferences/choices` | `{"sha256": "...", "relative_path": "..."}`: keep this copy |
| DELETE | `/api/preferences/choices/{sha256}` | Go back to ORBIT's suggestion |

The scan response includes `recommendations` (one per duplicate group) and `keep_rules`.

Error codes: `400` rejected path or invalid rule, `403` cross-site request, `404` folder or
file not found, `409` file doesn't belong to that duplicate group, `422` invalid input,
`503` sample workspace missing.

## Design decisions

- **The engine doesn't depend on the web layer.** `scanner.py` and `duplicates.py` don't
  import FastAPI, so a future folder watcher or CLI can reuse them as-is.
- **SHA-256 for exact matches.** Equal hashes mean identical bytes, and a file's name never
  affects its hash. Similar-but-not-identical files (for example an annotated copy of a PDF)
  are a later milestone.
- **Empty files are never grouped as duplicates.** All 0-byte files are technically
  identical, but listing them as duplicates would only be noise.
- **Hidden files are ignored** (`.DS_Store` etc.).
- **No CORS.** The Vite dev server forwards `/api` to the backend, so the browser only ever
  talks to one origin.
- **Rules in priority order, not a points total.** Each rule only breaks ties left by the rules
  above it, so every recommendation can be explained step by step ("avoided folder dropped A,
  filename dropped B"). Lower-priority rules that disagree are shown as caveats.
- **Recommendations are pure functions.** `recommend.py` takes data in and returns data out,
  which makes it easy to test and to reuse later (e.g. from a phone command).
- **Preferences live on the Mac, not in the browser.** They're stored in SQLite by the backend,
  so a future phone client sees the same choices. Choices are keyed by content hash, so they
  survive rescans.

## Roadmap (not yet implemented)

Annotated-PDF / related-version matching (see `docs/pdf-matching.md`) · filename suggestions · folder
monitoring · approve/reject/undo of file operations · content search · SQLite history ·
optional local AI via Ollama · phone → Mac commands.

## License

To be decided before the first public release.
