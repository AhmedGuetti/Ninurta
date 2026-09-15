# Ninurta ⚡

**Intelligent job-search automation pipeline powered by LLMs.**

Ninurta turns a raw job description into structured data, checks it against jobs you've already logged, scores your resume against it, and keeps everything in a local SQLite database — all driven by a LangGraph pipeline with pluggable LLM backends (Gemini, OpenAI, Anthropic, Ollama, or local HuggingFace models). It ships with both a scriptable CLI and an interactive terminal UI.

## Features

- **Multi-provider LLM support** — Gemini, OpenAI, Anthropic, Ollama, or local HF models
- **LangGraph pipeline** — extraction, duplicate detection, and resume/job matching as composable graphs
- **Duplicate detection** — flags a job as duplicate/similar/new against everything already in your DB, without any external vector store
- **Resume matching** — scores a resume against a job description (overall, skills, experience, education, responsibilities) and stores the report
- **SQLite persistence** — resumes, jobs, and match reports stored locally
- **Interactive terminal UI** — a Node/Ink chat-style interface (`ninurta tui`) talking to the Python backend over JSON-RPC
- **Scriptable CLI** — `ninurta pipeline` runs the same stages non-interactively
- **CSV export** — structured output compatible with spreadsheets

## Quick Start

### Install

```bash
pip install -e .
```

For specific LLM providers:
```bash
pip install -e ".[gemini]"       # Google Gemini
pip install -e ".[openai]"       # OpenAI
pip install -e ".[anthropic]"    # Anthropic Claude
pip install -e ".[transformers]" # Local HuggingFace models
pip install -e ".[all]"          # Everything
```

The terminal UI is a separate Node project:
```bash
cd ninurta/tui-node
npm install
```

### Configure

Create `config.yaml` in the project root (gitignored — never commit it, it holds API keys):
```yaml
llm:
  provider: gemini
  model: gemini-3.6-flash
  gemini_api_key: YOUR_GEMINI_API_KEY_HERE
```

Or use environment variables:
- `GEMINI_API_KEY` / `GOOGLE_API_KEY` — for Gemini
- `OPENAI_API_KEY` — for OpenAI
- `ANTHROPIC_API_KEY` — for Anthropic
- `OLLAMA_BASE_URL` — for Ollama (default: `http://localhost:11434`)

Optional duplicate-detection tuning (also in `config.yaml`):
```yaml
dedup:
  duplicate_threshold: 0.75
  similar_threshold: 0.45
  top_k: 3
```

### Run

```bash
ninurta tui                        # Interactive terminal UI (primary interface)

ninurta extract                    # Interactive mode, saves to jobs.csv
ninurta extract --csv_path=my_jobs.csv
ninurta extract --debug

ninurta resume                     # Paste resume interactively
ninurta resume --file=resume.pdf   # Read resume from a .pdf / .docx / .txt / .md file

ninurta pipeline --stage=full      # extract -> dedup -> load resume -> score
ninurta pipeline --stage=extract   # extract -> dedup -> save job only
ninurta pipeline --stage=match --job_id=3   # score resume against an existing job

ninurta models                     # List available Gemini models with pricing
```

## Interactive TUI

`ninurta tui` launches a chat-style terminal interface (Node + Ink) that talks to a Python gateway subprocess over JSON-RPC. Paste a job description at the prompt to run the full extract → dedup → match pipeline; slash commands are also available:

- `/model` — pick an LLM provider and model interactively
- `/db resumes|jobs|reports` — list what's stored; `/db resume|job|report <id>` for details
- `/clear` — reset the visible transcript
- `/exit` / `/quit` — quit

## Architecture

```
ninurta/
├── cli.py              # Fire-based CLI entry point (extract, resume, pipeline, tui, models)
├── config.py            # YAML config loader
├── state.py              # LangGraph TypedDict state
├── graph.py               # Graph definitions: extract_graph, resume_graph, match_graph, score_graph
├── nodes/                  # Graph node implementations
│   ├── extractor.py         # Job description extraction
│   ├── job_dedup.py          # Duplicate/similar-job detection (bag-of-words cosine similarity)
│   ├── matcher.py              # Resume-vs-job scoring
│   └── resume_reader.py/...      # Resume parsing/validation/review
├── llm/                    # Pluggable LLM backends (Gemini, OpenAI, Anthropic, Ollama, local HF)
├── db/                     # SQLAlchemy ORM: Resume, Job, MatchReport, TailoredResume
├── schemas/                # Pydantic data models
├── prompts/                # Centralized, decorator-registered prompt templates
├── interface/              # stdin/file readers, resume_loader (DB-first, disk-fallback)
├── gateway/                # JSON-RPC server bridging Python backend to the Node TUI
│   ├── entry.py              # `python -m ninurta.gateway.entry`
│   ├── transport.py           # newline-delimited JSON-RPC over stdio
│   ├── methods.py               # RPC method dispatch table
│   └── handlers/                # session.send, db.inspect, model.*, config.*
└── tui-node/                # Node/React(Ink) terminal UI, spawns the gateway as a subprocess
```

## License

MIT
