# ORBIT

**ORBIT** is an open-source, local-first personal assistant for your files. The long-term goal
is a cross-device assistant that organises files, catches duplicate downloads, suggests better
filenames, searches documents by content, and accepts authorised commands from your phone.

> **Current status: Milestone 1.** A **read-only** folder scanner with **exact duplicate
> detection**, a FastAPI backend, and a React + TypeScript dashboard. It only ever scans the
> synthetic `sample_workspace/` folder in this repository.

---

## What Milestone 1 does

- Scans `sample_workspace/` recursively and lists each file's name, extension, size,
  modification time, and absolute path.
- Fingerprints every file with **SHA-256**, reading it in 1 MiB chunks so big files don't fill memory.
- Groups **byte-identical files** together, even when their names or folders differ.
- Shows everything in a dashboard with summary cards, colour-coded duplicate groups, a
  filterable and sortable file table, dark/light mode, and a phone-friendly layout.

## Safety model

| Rule | How it's enforced |
| --- | --- |
| Never touch personal files | The scan root is hard-coded to `sample_workspace/` (`backend/orbit/config.py`). There's no setting or API parameter that points it anywhere else. |
| Read-only | Files are opened with `O_RDONLY` only. Nothing is written, renamed, moved, or deleted, and a test checks that file contents and timestamps are unchanged after a scan. The API has no POST/PUT/DELETE routes. |
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
│   │   ├── api.py            FastAPI app: /api/health and /api/scan
│   │   └── __main__.py       `python -m orbit` starts the server on 127.0.0.1
│   ├── tests/                pytest suite (safety, scanner, duplicates, API)
│   └── pyproject.toml        Python dependencies
├── frontend/                 React + TypeScript dashboard (Vite)
│   ├── src/
│   │   ├── App.tsx           Page layout and the idle/loading/error/done state machine
│   │   ├── api.ts            Calls the backend and turns failures into readable messages
│   │   ├── types.ts          TypeScript shapes of the API's JSON
│   │   ├── format.ts         Byte, date, and hash formatting helpers
│   │   ├── components/       Header, SummaryCards, DuplicateGroups, FileTable, StatusStates
│   │   └── index.css         Design tokens, dark/light themes, responsive layout
│   └── vite.config.ts        Dev server (localhost only) + /api proxy to the backend
├── sample_workspace/         Synthetic test files (3 duplicate groups)
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

Stop either server with `Ctrl+C`.

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
| GET | `/api/health` | `{"status": "ok", "version": "0.1.0"}` |
| GET | `/api/scan` | Scan the whole sample workspace |
| GET | `/api/scan?folder=downloads` | Scan a subfolder **inside** the sample workspace |

Error codes: `400` rejected path (traversal or symlink escape), `404` folder not found,
`422` invalid parameter, `503` sample workspace missing.

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

## Roadmap (not yet implemented)

User-defined organisation rules · filename suggestions · annotated-PDF detection · folder
monitoring · approve/reject/undo of file operations · content search · SQLite history ·
optional local AI via Ollama · phone → Mac commands.

## License

To be decided before the first public release.
