# Research: recognizing the same PDF, annotated copies, and new editions

**Goal (future milestone):** when you download a PDF you already have, and your existing copy has
your highlights and notes, ORBIT should say *"You already have this, with your annotations. Open
that one instead?"*

**Status:** research and test fixtures only. Milestone 2 deliberately does **not** match
non-identical PDFs. Only byte-identical files are ever called duplicates.

---

## 1. How PDF annotations are stored

A PDF is a collection of numbered *objects* (pages, fonts, text streams...). Annotations are
separate objects attached to a page through the page's `/Annots` array (PDF spec ISO 32000,
§12.5). Each annotation has a `/Subtype`:

| Kind | Subtypes | Made by you? |
| --- | --- | --- |
| Markup | `/Highlight` `/Underline` `/StrikeOut` `/Squiggly` `/Text` (sticky note) `/FreeText` `/Ink` (pen) `/Square` `/Circle` `/Line` `/Polygon` `/PolyLine` `/Stamp` `/Caret` | **Usually yes** |
| Helpers | `/Popup` (the bubble that shows a note's text) | Belongs to a markup annotation |
| Structural | `/Link` (hyperlinks), `/Widget` (form fields) | **No**, the publisher made them |

Markup annotations usually also carry an author (`/T`), text (`/Contents`), and dates
(`/CreationDate`, `/M`). Those are useful for showing "12 highlights by you, last edited Feb 10".

So detection is: open each page, read `/Annots`, and count the markup subtypes, **ignoring
links and form fields**. Our sample `course_reader.pdf` contains a `/Link` on purpose, so a
naive "has any annotation" check would wrongly flag it.

**Pitfall: flattened annotations.** Some apps (and "Print to PDF") burn annotations into
the page drawing itself. They then aren't annotation objects anymore, so the check above sees
nothing. The text and drawing commands still differ from the original, which signal 4 below can
notice, but they can't be reliably labelled as "your annotations".

## 2. How editors save annotations: two styles

1. **Incremental update (appending).** The editor keeps every original byte and adds a small
   section at the end containing only the new or changed objects, plus a pointer (`/Prev`) back
   to the old index. *The original file is an exact prefix of the annotated file.*
   Fixture: `sample_workspace/documents/course_reader_annotated.pdf`.
2. **Full rewrite.** The editor writes a brand-new file. The bytes differ everywhere, even
   though the pages are the same. macOS Preview is commonly reported to save this way. We
   should confirm this with real files before relying on it.
   Fixture: `sample_workspace/archive/course_reader_marked_up.pdf`.

Both fixtures contain the same three annotations (2 highlights + 1 sticky note). They were
checked with the `pypdf` parser in strict mode during development.

## 3. Signals for "same document?" (strongest first)

| # | Signal | What it proves | Cost | Weakness |
| --- | --- | --- | --- | --- |
| 1 | **SHA-256 equal** | Byte-identical (exact duplicate) | Already have it | Any change breaks it |
| 2 | **Prefix match**: file A is the first *N* bytes of B, and B's appended part only adds objects | B = A + edits | Very cheap (hash first *N* bytes) | Only catches incremental saves |
| 3 | **Permanent file ID**: first element of the trailer `/ID` (and XMP `xmpMM:DocumentID`) is equal | Same document lineage | Cheap (read trailer) | Optional in older PDFs; some tools regenerate or copy it |
| 4 | **Content fingerprint**: hash of normalized text per page + page count + page sizes | Same visible content | Moderate (text extraction) | Fails on scanned PDFs (no text); dynamic watermarks change text |
| 5 | **Page-image fingerprint** (render pages, perceptual hash) | Looks the same | Expensive (needs a renderer) | Out of scope for now |

The `/ID` has two parts: **[permanent, changing]**. Editing a document should keep the first
part and change the second. Our fixtures follow that rule:

```
course_reader.pdf               [f8261d27…, f8261d27…]   original
course_reader_annotated.pdf     [f8261d27…, d090a933…]   same document, new revision
course_reader_marked_up.pdf     [f8261d27…, 08fed56d…]   same document, new revision
course_reader_2nd_edition.pdf   [24361559…, 24361559…]   different document
```

## 4. Annotated copy vs. newer edition vs. different document

| Question | Annotated copy | Newer / different edition |
| --- | --- | --- |
| Page text (per page, normalized) | **Identical** | Changed on some pages |
| Page count / page sizes | Same | Often different |
| Permanent `/ID` | Same | Usually new |
| Annotation markup count | Higher than the other copy | Usually 0 (fresh from the publisher) |
| Original is a byte-prefix? | Often (incremental save) | Never |
| Differences limited to... | annotation objects + updated page dictionaries | page content streams, fonts, metadata |

Decision rule (conservative):

- **Annotated copy of X**: same page text fingerprint on every page (or a prefix match), *and*
  more markup annotations than X. If the permanent IDs also match, confidence is high.
- **Different edition of X**: the permanent ID matches *or* the titles are similar, **but** the
  page text differs. Shown as "related", never merged, never suggested as a replacement.
- **Unrelated**: no ID match and different text.
- Anything in between is **"possibly related, please confirm"**, never an automatic decision.

The asymmetry matters. Wrongly saying "these are the same" could make you open an old edition,
or later lose notes. Missing a match only costs a duplicate download. So when in doubt, say
"not the same".

## 5. Proposed safe implementation (next milestone)

1. **Keep exact duplicates separate.** Add a new "Related versions" section rather than changing
   duplicate groups. Exact-duplicate logic and its tests stay untouched.
2. **Parse PDFs defensively.** PDFs are untrusted input. Use `pypdf` (pure Python, it never runs
   embedded JavaScript and doesn't render). Run parsing in a **separate worker process** with a
   timeout, memory limit, file-size cap and page cap, so a malicious or broken PDF can't hang
   or crash ORBIT. Parse failures become "couldn't inspect", never a match.
3. **Extract a small "PDF profile" per file:** permanent/changing ID, page count, page sizes,
   per-page text hashes, markup annotation counts by type (links and widgets excluded), and the
   startxref chain length. Cache it in SQLite keyed by `(sha256)`, so unchanged files are never
   re-parsed.
4. **Find candidates cheaply:** group by permanent ID and by page-text fingerprint. Don't compare
   every PDF with every other.
5. **Classify with the conservative rule in §4**, attaching evidence the UI can show ("same ID,
   identical text on all 2 pages, 3 highlights in this copy, 0 in the download").
6. **Act only on request:** for a fresh download that matches an annotated copy, the dashboard
   offers "Open my annotated copy". Opening a file is read-only, but it still happens only after
   your click, and only inside the allowed workspace. No file is deleted, moved, or replaced.
7. **Test with fixtures:** the five synthetic course-reader PDFs, plus malformed, encrypted,
   huge-page-count and no-text (scanned) PDFs to prove that failures are safe.
8. **Validate against real-world PDFs** you choose to copy into the sandbox (e.g. one annotated
   in Preview, one in Acrobat), to confirm the save-style assumptions in §2.
