# Ninurta ⚡

**Intelligent job-search automation pipeline powered by LLMs.**

Ninurta extracts structured job information from raw job descriptions, stores it in a local SQLite database, and exports it to CSV — all driven by a LangGraph pipeline with pluggable LLM backends (Gemini, OpenAI, Anthropic, Ollama, or local HuggingFace models).

## Features

- **Multi-provider LLM support** — Gemini, OpenAI, Anthropic, Ollama, or local HF models
- **LangGraph pipeline** — Modular graph-based extraction with tool integration
- **SQLite persistence** — All parsed jobs stored locally with deduplication
- **CSV export** — Structured output compatible with spreadsheets and analysis tools
- **Rich terminal UI** — Progress bars, colored tables, and token usage tracking
- **Pydantic validation** — Type-safe job description schemas with coercion

## Quick Start

### Install

```bash
pip install -e .
```

For specific LLM providers:
```bash
pip install -e ".[gemini]"      # Google Gemini
pip install -e ".[openai]"      # OpenAI
pip install -e ".[anthropic]"   # Anthropic Claude
pip install -e ".[transformers]" # Local HuggingFace models
pip install -e ".[all]"         # Everything
```

### Configure

Copy `config.yaml.example` to `config.yaml` (or use the default):
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

### Run

```bash
ninurta extract                    # Interactive mode, saves to jobs.csv
ninurta extract --csv_path=my_jobs.csv  # Custom output path
ninurta extract --debug            # Enable debug logging
ninurta models                     # List available Gemini models

# Resume pipeline — parse → correct → summarize → export markdown
ninurta resume                     # Paste resume interactively
ninurta resume --file=resume.pdf   # Read resume from a .pdf / .docx / .txt / .md file
```

## Architecture

```
ninurta/
├── cli.py              # Fire-based CLI entry point
├── config.py           # YAML config loader
├── state.py            # LangGraph TypedDict state
├── graph.py            # LangGraph graph definition
├── nodes/              # Graph node implementations
│   └── extractor.py    # Job description extraction node
├── llm/                # Pluggable LLM backends
│   ├── base.py         # Abstract base + pricing
│   ├── factory.py      # Model ID → backend resolver
│   ├── gemini_llm.py   # Google Gemini
│   ├── openai_llm.py   # OpenAI / compatible APIs
│   ├── anthropic_llm.py # Anthropic Claude
│   ├── ollama_llm.py   # Local Ollama server
│   └── local.py        # HuggingFace transformers
├── db/                 # SQLAlchemy ORM
│   ├── models.py       # Resume, Job, TailoredResume
│   ├── session.py      # Engine + session management
│   └── operations.py   # CRUD helpers
├── schemas/            # Pydantic data models
│   └── job_description.py
├── tools/              # Agent tool registry
│   ├── registry.py     # @tool decorator
│   └── builtins/       # Built-in tools
├── prompts/            # Centralized prompt templates
│   ├── registry.py     # @prompt decorator
│   └── job_extractor.py
├── utils/
│   └── logger.py       # Rich-based logging
└── interface/
    └── io.py           # stdin reader, CSV writer
```

## License

MIT
