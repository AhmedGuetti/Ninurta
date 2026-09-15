# Dev Notes

Technical notes on how Ninurta is built, aimed at whoever is (re)touching this code — including future-us. Written from the current working-tree state on `main` (uncommitted changes included), 2026-09-15.

## Big picture

Ninurta is a Python LangGraph pipeline (job-description extraction, duplicate detection, resume matching) with two front ends:

1. **CLI** (`ninurta/cli.py`, Fire-based) — scriptable, synchronous, prints Rich tables.
2. **TUI** (`ninurta/tui-node/`) — a Node/React/Ink chat interface that talks to Python over a JSON-RPC gateway (`ninurta/gateway/`). `ninurta tui` spawns the Node process, which in turn spawns `python -m ninurta.gateway.entry` as its own subprocess. Three processes deep: CLI → tsx/Node → Python gateway.

The gateway/TUI architecture was ported wholesale from a reference project called "hermes-agent" (commit `6d3abef "A full stell[sic] from hermes Agent"`) — method naming, event shapes, and the vendored `@hermes/ink` fork all trace back to that.

## LangGraph pipeline

`ninurta/graph.py` defines four compiled graphs sharing one `State` TypedDict (`ninurta/state.py`):

| Graph | Nodes | Used by |
|---|---|---|
| `extract_graph` | `extractor → job_dedup` | `ninurta extract`, `pipeline --stage=extract`, first phase of `session.send` |
| `resume_graph` | `resume_reader → resume_validator → resume_reviewer → resume_saver` | `ninurta resume` |
| `match_graph` | `extractor → matcher` | gateway `session.send` (extract + score from raw JD text in one graph) |
| `score_graph` | `matcher` only | `pipeline --stage=match` when a job is already extracted — avoids re-extracting |

`graph = extract_graph` is kept as a backward-compat alias.

### Duplicate detection (`ninurta/nodes/job_dedup.py`)

Deliberately **not** embeddings/vector-DB based — comment justifies this at "single-user scale, ~1000 JDs/month, brute-force over the whole table is milliseconds":

- Weighted bag-of-words vector per JD (`_FIELD_WEIGHTS`: `position_title`=3.0, `skills_required`=2.0, `responsibilities`=1.5, `company_name`=1.5, down to 0.5 for location-ish fields). Stopword list deliberately excludes domain terms like "experience"/"requirements"/"python" so they still carry signal.
- Cosine similarity (`_cosine`) against every stored job's vector; legacy rows without `extracted_json` fall back to company+title only.
- Exact company+title match (case-insensitive) always pins the score to the duplicate threshold — a guaranteed fast path independent of the vector math.
- Thresholds configurable via `config.yaml`'s `dedup:` block (`duplicate_threshold` 0.75, `similar_threshold` 0.45, `top_k` 3).
- Read-only — never writes to the DB. Returns `{"dedup_result": {"verdict", "top_score", "top_match_id", "matches": [...]}}`.

### LLM status sink (`ninurta/nodes/_llm_helpers.py`)

`set_llm_status_sink(callback)` / `_emit_llm_status(msg)` — a module-global optional callback `_call_llm()` invokes before/after each LLM call (`"{model_id} · reasoning…"`, `"{model_id} · response received"`). The gateway registers/clears this around each graph `.stream()` call to drive `pipeline.progress` events into the TUI. Nodes stay transport-agnostic; without a registered sink these are no-ops. `_call_llm` still wraps `llm.complete()` in a `ThreadPoolExecutor(max_workers=1)` with a timeout (default 120s) so one stuck call can't hang the whole pipeline.

## Database (`ninurta/db/`)

Four SQLAlchemy tables (`models.py`):

- **`resumes`** — `content` (full text) + `parsed_json` (schema-flexible; sections may be str/list/dict depending on what the LLM produced).
- **`jobs`** — `raw_job_description` + `extracted_json` (~28-field structured JD) + `already_applied`.
- **`match_reports`** (new) — `job_id` FK, `resume_id` FK (nullable), five float scores (overall/skills/experience/education/responsibilities), JSON-text payload columns (keyword_match/strengths/gaps/action_items), truncated summary. One row per scoring run, so re-scoring builds a history rather than overwriting.
- **`tailored_resumes`** — `base_resume_id`/`job_id` FKs, `content`. Model exists but nothing currently writes to it — scaffolded for a future "tailor my resume to this job" feature.

`db/session.py` runs a small additive `_migrate()` on `init_db()` that `ALTER TABLE`s `parsed_json` onto pre-existing SQLite `resumes` tables.

`db/operations.py` additions this round:
- `save_job(job_desc, raw_jd, mark_applied=True)` — new `mark_applied` param. The gateway calls it with `mark_applied=False` because re-extracting a JD to score it isn't the same as applying to it; the CLI's `extract` command keeps the old default (`True`).
- `get_latest_resume_id()` — used to auto-link a `MatchReport` to whichever resume was actually scored, when the caller doesn't pass one.
- `save_match_report(job_id, match_data, resume_id=None)` — defensive coercion: `_score()` swallows non-numeric values to `0.0`, `_as_json()` treats `None`/`""`/`[]` as "nothing to store."

## Gateway (`ninurta/gateway/`)

Newline-delimited JSON-RPC over stdio.

- **`entry.py`** — `python -m ninurta.gateway.entry`. Logging goes to **stderr only** — stdout is reserved for JSON-RPC frames, so a stray print or traceback never corrupts the terminal UI.
- **`transport.py`** (`JSONRPCTransport`) — one JSON object per line in each direction (writes serialized via a `threading.Lock`). Requests with an `id` get a matched response; frames without one are push events. Emits `gateway.ready` on loop start. Dispatches each request onto a `ThreadPoolExecutor(max_workers=4)` so a long LLM call in `session.send` never blocks the stdin read loop. Unknown method → JSON-RPC `-32601`; handler exception → `-32000`.
- **`methods.py`** — `get_dispatch_map()`. Also imports `ninurta.prompts.job_extractor` / `ninurta.prompts.matcher` on module load so `@prompt`-registered templates exist before any RPC call needs them.
- **`handlers/`** — one module per concern (`session.py`, `db.py`, `model.py`, `config.py`). This split is recent: `af19cc9 "[FIX] all bugs"` pulled `methods.py` down from 857 lines to a thin dispatch table by moving the logic here.

### RPC methods

| Method | Handler | Purpose |
|---|---|---|
| `session.send` | `handle_session_send` | Full pipeline for one JD: extract → dedup → load resume → score → stream results |
| `pipeline.cancel` | `handle_pipeline_cancel` | Cooperative cancel via `threading.Event`; sends an immediate `turn.end` |
| `db.inspect` | `handle_db_inspect` | Summary / list / row-detail views over resumes, jobs, match_reports |
| `model.get`/`list`/`set` | `handle_model_*` | Inspect/switch active LLM provider+model; clears LLM cache on switch |
| `config.get`/`set` | `handle_config_*` | Non-secret config; API keys are always masked and never settable over RPC |

Push events: `gateway.ready`, `turn.delta` (streamed text), `turn.end`, `pipeline.progress` (`step`, `message`), `tool.start`/`tool.end` (declared in the event type union, not currently emitted — leftover from the hermes template, likely for future tool-calling).

### `handle_session_send` walkthrough (`gateway/handlers/session.py`)

1. Stream `extract_graph` as running commentary via `turn.delta`.
2. Print extraction stats, then the dedup verdict (duplicate/similar/new) with match IDs and scores.
3. `save_job(..., mark_applied=False)`.
4. Load resume via `_get_resume()` → `ninurta.interface.resume_loader` (DB first, disk fallback; disk-parsed resumes get persisted back to DB).
5. Stream `match_graph`, then stream the match report **one line at a time** with `time.sleep(0.005)` between lines — deliberate workaround for an Ink bug where ~30 lines sent in one `turn.delta` corrupts row layout.
6. `save_match_report`.
7. Diff `llm.usage` before/after, stream a cost table (`gateway/utils.py::_format_cost_table`, fixed 0.926 USD→EUR rate).
8. Emit `turn.end`.

**Hard rule, called out in-code**: never embed raw ANSI SGR codes in streamed text — Ink's `<Text>` doesn't interpret escape codes, and they corrupt string-width math, producing overlapping/mangled rows. Use emoji + markdown markers for visual hierarchy instead.

### `ninurta/interface/resume_loader.py` (new)

Shared DB-first/disk-fallback resume loading used by *both* the gateway and the CLI's `pipeline` command, "so the two entry points never drift" (docstring). `RESUME_DIR` resolves to `<repo root>/resume/`; tries `resume_en.docx` then `resume_fr.docx`, extracting via `interface.documents.extract_text` and parsing heuristically (no LLM) via `nodes.resume_reader.parse_resume`.

## CLI (`ninurta/cli.py`)

Fire-based (`class NinurtaCLI`, entry point `ninurta = ninurta.cli:main`). Bare `ninurta` shows a Rich welcome screen + toy prompt loop; any subcommand dispatches via `fire.Fire`.

- `extract(csv_path="jobs.csv", debug=False)` — paste loop → `extract_graph` → table → `save_job` (`mark_applied=True`) → CSV row → token/cost summary.
- `resume(file="", debug=False)` — runs `resume_graph`.
- `pipeline(stage="full", file="", job_id=0, debug=False)` — unified entry, 4 stages (`full`, `extract`, `resume`, `match`). `match` uses `score_graph` when `job_id` is given (skip re-extraction), otherwise extracts fresh. Shared helpers: `_read_jd_input`, `_extract_jd`, `_load_resume_or_quit`, `_score`.
- `tui()` — locates `tui-node/index.jsx` and `node_modules/.bin/tsx`, errors with an install hint if missing, `subprocess.run([tsx_bin, index_path, model_id, cwd])`.
- `models(provider="gemini")` — live Gemini pricing via `google.genai`; other providers print "not implemented yet".

## TUI (`ninurta/tui-node/`)

Node/React 19 + Ink, ESM (`"type": "module"`), run via `tsx index.jsx`. Uses a **vendored fork** `@hermes/ink` (`vendor/hermes-ink/`, committed to git) instead of stock `ink` — comment says stock `ink-text-input` "never fires" under this fork, hence all input handling is hand-rolled via `useInput`. State lives in `nanostores`/`@nanostores/react`.

### Gateway client (`src/gateway/gatewayClient.ts`)

`GatewayClient extends EventEmitter`. `start()` spawns `python -m ninurta.gateway.entry`, resolving the interpreter: `$VIRTUAL_ENV` → `.venv/bin/python[3]` → `venv/bin/python[3]` → `python3`/`python`. stderr goes to a 200-line ring buffer surfaced via Ctrl+G (never printed directly). stdout parsed line-by-line: frames with `id` resolve/reject pending `request()` promises (120s timeout); frames with `method` are re-emitted as events. `request(method, params)` writes `{jsonrpc:'2.0', id, method, params}\n` to stdin.

### App layout (`src/app/App.tsx`)

Inline (non-alternate-screen), `height = terminal rows - 1` so the last row is never written to — an explicit "anti-scroll" pattern to avoid triggering terminal scroll. Top-to-bottom: `Banner` → `InfoBox` → `ChatArea` (flexGrow, clipped) → connection/error text → `StatusBar` → optional gateway-stderr panel (Ctrl+G) → `Selector` overlay → `InputPrompt` → `CompletionOverlay` (absolute-positioned). Tab cycles focus, Enter toggles focused section, Esc returns focus to input, Ctrl+C cancels/exits, Ctrl+D exits, Ctrl+G toggles stderr log.

### Business logic (`src/app/useMainApp.ts`, `src/app/turnStore.ts`)

`useMainApp` wires gateway push events into `turnStore` atoms and implements slash-command logic: `/clear`, `/model` (two-step selector: provider → model, with a back path, via `model.list`/`model.set`), `/db [resumes|jobs|reports] [id]` (via `db.inspect`), `cancel()` (via `pipeline.cancel`).

`turnStore.ts` atoms: `$turnState` (messages/streaming/step/stepMsg/busy), `$modelId`, `$selector` (generic pick-list state, reusable by any slash command), `$completion` (slash-completion dropdown state).

`src/app/slashCommands.ts` (new) — single source of truth for `SLASH_COMMANDS`, so `InputPrompt.jsx`'s live dropdown and `InfoBox.jsx`'s static help panel can't drift apart. Exports `completeSlash(input)` and `applyCompletion(value, rowText, compReplace)`.

### Components (`ninurta/tui-node/components/`)

- `ChatArea.jsx` — last `MAX_LINES = 20` lines rendered as one `<Text>` per line (multi-line strings split manually — Ink merges embedded `\n` into one row otherwise). Color by role.
- `InputPrompt.jsx` — hand-rolled input via `useInput` (chars, backspace, history ↑↓ 50 entries, Enter submit) plus slash-completion (↑↓ navigate, Tab accept, Enter accept-or-submit, Esc dismiss). Swaps to `RunningLine` when busy; renders nothing when a selector is active.
- `CompletionOverlay.jsx` (new) — deliberately **absolute-positioned**, not in-flow: an earlier in-flow version under the height-clamp corrupted layout (dropped items, stale text bleeding between rows). Up to 8 rows, truncated/no-wrap.
- `RunningLine.jsx` (new) — replaces the input while busy: braille spinner, `STEP_LABELS`-mapped step name, dynamic `stepMsg`, model id, "Ctrl+C to stop" hint.
- `Selector.jsx` (new) — generic arrow-key pick list driven by `$selector`.
- `StatusBar.jsx` — one-line, never-wrapping status (ready/connecting/working+elapsed+spinner, model id, step message, shortened cwd, key hints).
- `InfoBox.jsx` — bordered box with expandable Pipelines/Commands sections; Commands now renders `SLASH_COMMANDS` directly.

### Old Python TUI (`ninurta/tui/`)

`ninurta/tui/app.py` is now a 10-line redirect stub ("The active TUI is the Node/Ink interface... Launch it with: ninurta tui"). It used to hold ~340 lines of a real Python TUI, gutted in `af19cc9`. `ninurta/tui/art.py` and `palette.py` are still live — imported by `cli.py`'s welcome screen and `_print_match_result`'s Rich styling — repurposed as a shared branding module for CLI output. **`tui-node/` fully replaced the Python TUI**, it isn't running alongside it.

## Debugging trail: `scripts/repro-*.py` and `*.tmp.tsx`

Both are scratch artifacts from chasing a cluster of Ink/terminal rendering bugs — not part of the shipped product (nothing in `cli.py`, `pyproject.toml`, or any `__init__.py` references them).

Pattern: `os.pty.fork()` → spawn `tsx` running either the real `tui-node/index.jsx` or a paired `hermes-verify-*.tmp.tsx` harness → feed/read raw PTY bytes on a timer → replay ANSI sequences through `pyte` or a hand-rolled `Screen` class → print the resulting grid or raw byte diffs.

| Script | Target |
|---|---|
| `repro-clamp.py` / `hermes-verify-clamp.tmp.tsx` | Whether a fixed-height clamp around `InputPrompt` breaks slash-completion — led directly to `CompletionOverlay.jsx`'s absolute-positioning fix |
| `repro-completion.py` | End-to-end slash-completion key handling (type `/`, Tab, re-type, backspace) |
| `repro-stream.py` | Streaming-text → finalized-message transition, checking for row overlap |
| `repro-gateway-text.py` | Bypasses the TUI, talks JSON-RPC straight to the Python gateway, scans `turn.delta` text for stray control chars — isolates Python-side vs Ink-side corruption |
| `repro-isolate.py` / `hermes-verify-isolate.tmp.tsx` | `VARIANT`-env-driven bisection of which component causes a bug |
| `repro-raw.py`, `repro-raw-jd.py` | Raw PTY byte capture for manual inspection |
| `repro-after-jd.py`, `repro-second-prompt.py`, `repro-chat-isolated.py`, `repro-full-tui.py`, `repro-screen.py` | Variations on running the full TUI (or `ChatArea` alone) through a submitted JD, chasing the same "overlapping/mangled rows on large streamed output" family of bugs |

Several of the shipped fixes are direct descendants of what these scripts found: line-by-line streaming in `session.py`, the `CompletionOverlay` absolute-overlay pattern, and the "no raw ANSI in streamed text" rule.

The `hermes-verify-*.tmp.tsx` files are throwaway Ink render harnesses (import `render` from `@hermes/ink`, mount a minimal component tree, auto-exit via `setTimeout`), one per bug being isolated.

## Known cleanup items

- **`node_modules/` is tracked in git** — 1,654 files under `ninurta/tui-node/node_modules/` were committed before `ninurta/tui-node/.gitignore` was added (`6794f4b`). The `.gitignore` doesn't retroactively untrack them. Run `git rm -r --cached ninurta/tui-node/node_modules` to fix, or the repo stays noisy forever.
- **`*.tmp.tsx` files and `scripts/repro-*.py`** are untracked debugging scratch, not gitignored. Worth deleting once the rendering bugs they chased are confirmed fixed, or moving under something like `scripts/debug/` with a note that they're throwaway.
- **`config.yaml` is gitignored and untracked** (verified — never committed), but the local copy on this machine has a live Gemini API key in plaintext. Don't `git add -f` it.
- **`tool.start`/`tool.end` gateway events** are declared but never emitted by any handler — either wire them up when tool-calling lands, or drop them from the type union.
- **`TailoredResume`** table exists with no read/write path anywhere in `gateway/` or `cli.py` — scaffolded for a future "tailor resume to job" feature, not yet built.
