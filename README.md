# AURA

## Autonomous Unified Reasoning & Automation Agent

**Plan. Act. Verify. Recover.**

AURA turns a natural-language goal into an observable, tool-backed workflow. It plans the work, executes registered capabilities, verifies structured outputs, recovers from bounded failures, and keeps a persistent execution trail that can be inspected from the UI or API.

```text
User goal
   -> Plan
   -> Registered tools
   -> Execute
   -> Verify
   -> Recover when needed
   -> Persist and explain
```

## What AURA Does

### Goal execution

- Rule-based planning for deterministic offline operation.
- Optional local Ollama/Qwen or hosted OpenAI-assisted planning.
- Typed plan validation before execution.
- Registered tools only: unknown or unsafe tool names are rejected.
- Dependency-aware task ordering.
- Structured execution events, verification, retries, and failure states.

### Available capabilities

- Live web search when a search provider is configured; reports unavailable instead of showing fake results when no key is set.
- Web scraping through requests or Playwright modes.
- Content summarization.
- Email sending or clearly labelled simulation when SMTP is unavailable.
- Resume parsing for PDF, DOCX, and TXT files.
- Resume analysis with AI or deterministic local fallback.
- Job matching from an analyzed resume.
- Execution logging.

### User interface

The browser-native workspace provides:

- A goal-first Start view.
- Resume analysis and job matching.
- Backend-backed execution History.
- Registered Capabilities with risk and retry metadata.
- Insights calculated from persisted runs.
- Live task events, verification, and recovery details.
- Search result provenance, search timestamps, and an on-demand public-link check that flags confirmed missing pages.
- Journey history search, status/date filters, and newest/oldest sorting.
- Live journey progress streaming, per-step timings, and a process-cached LLM client.
- Fast extractive summaries by default; set `SUMMARY_MODE=llm` to use the configured model for summaries.
- Clear complete, partial, and failed run states, with human-readable plan and event details.
- Screen-reader announcements, keyboard focus treatment, and responsive filter/result layouts.
- Email summaries built from the same captured summary and ordered links shown in the workspace.

The interface is built with HTML, CSS, and JavaScript as a responsive, page-based workspace. It uses an understated graph-paper backdrop, inline numbered navigation, a dark/light theme switch, Space Grotesk headings, and IBM Plex Mono labels. Most sections sit directly on the canvas; the goal composer and resume uploader remain framed as task controls. The frontend has no separate Node, npm, or build-server requirement and calls the existing FastAPI endpoints.

## Architecture

```text
Browser workspace (HTML, CSS, JavaScript)
    |
    v
FastAPI backend
    |
    +--> Planner (rule or LLM)
    |
    +--> Typed plan validation
    |
    +--> Tool registry
    |       +--> Search
    |       +--> Scraper
    |       +--> Summarizer
    |       +--> Resume tools
    |       +--> Job matcher
    |       +--> Email
    |
    +--> Task graph and controller
    |
    +--> Verification and bounded recovery
    |
    +--> Atomic JSON run store
```

The backend owns execution and persistence. The browser UI calls the existing FastAPI endpoints for task execution, run history, resume analysis, job matching, capabilities, memory, and evaluation data.

## Project Structure

```text
web/
├── index.html              # Browser-native AURA workspace
├── styles.css              # Graph-paper themes and responsive layout
└── app.js                  # Navigation and API-backed interactions
src/
├── agent/
│   ├── controller.py       # Dependency-aware execution and events
│   ├── evaluator.py        # Metrics from persisted runs
│   ├── models.py           # Typed plans, tasks, events, and results
│   ├── planner.py          # Deterministic planner
│   ├── planner_llm.py      # Optional Ollama/OpenAI planner
│   ├── recovery.py         # Failure classification and retry policy
│   ├── run_store.py        # Atomic JSON execution history
│   ├── task_graph.py       # Dependency ordering and cycle checks
│   ├── tool_registry.py    # Registered tool metadata
│   └── verifier.py         # Deterministic output verification
├── tools/                  # Independent tool adapters
└── main.py                 # FastAPI entry point
tests/                     # Planner, controller, API, recovery, and verifier tests

```

## Quick Start

### Requirements

- Python 3.10 or newer.
- Ollama running locally for private, key-free Qwen planning and analysis; hosted OpenAI is optional.
- Optional API credentials for live search or SMTP features.
- Optional Playwright browser installation for JavaScript-heavy pages.
- Optional Tesseract and Poppler installations for scanned PDF OCR.

### Install

```bash
git clone <repository-url>
cd AURA
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

On Windows PowerShell:

```powershell
python -m venv .venv
.venv\Scripts\Activate.ps1
pip install -r requirements.txt
```

Copy `.env.example` to `.env` for local Qwen mode. Ollama must be running on this computer at `http://127.0.0.1:11434`. `.env` is ignored by Git, and local Qwen does not need an API key. Set `PLANNER_MODE=rule` if you want deterministic planning instead.

### Run the app locally

```bash
python -m uvicorn src.main:app --reload --host 127.0.0.1 --port 8000
```

This single process serves both the FastAPI API and the browser UI. Open [http://localhost:8000](http://localhost:8000) for AURA, or [http://localhost:8000/docs](http://localhost:8000/docs) for the API documentation. There is no separate frontend server or npm install/build step.

For faster repeated local-model requests, AURA reuses its configured model client and avoids a second model call for summaries by default. The Ollama daemon controls how long a model stays loaded; set `OLLAMA_KEEP_ALIVE=30m` in the Ollama systemd service environment if you want it to remain warm longer than its current setting. This belongs to the Ollama service, not AURA's `.env`.

On Windows PowerShell, activate the virtual environment and run the existing helper:

```powershell
.\.venv\Scripts\Activate.ps1
.\start_gui.ps1
```

`start_gui.ps1` starts the same FastAPI app and expects its Python dependencies to be installed. Alternatively, `run_local.ps1` installs `requirements.txt` into the active Python environment and then starts AURA:

```powershell
.\.venv\Scripts\Activate.ps1
.\run_local.ps1
```

### Run with Docker Compose

The Compose configuration reads a root `.env` file. Create one from the example, then build and start the service:

```bash
cp .env.example .env
docker compose up --build
```

In PowerShell, use `Copy-Item .env.example .env` for the first step. The UI and API are available at [http://localhost:8000](http://localhost:8000). Stop the foreground service with `Ctrl+C`.

### Deploy with Render

The repository includes `render.yaml` and a Dockerfile for a Render Blueprint deployment. Create the service from the Blueprint, then add any optional API or SMTP credentials in the Render environment settings. The deployed service serves the UI and API from the same origin.

## Configuration

| Variable | Purpose | Required |
| --- | --- | --- |
| `PLANNER_MODE` | `rule` or `llm` planner selection | Defaults to `llm` in `.env.example` |
| `LLM_PROVIDER` | `ollama` or `openai` | Defaults to local Ollama in `.env.example` |
| `OLLAMA_BASE_URL` | Ollama OpenAI-compatible endpoint | Defaults to `http://127.0.0.1:11434/v1` |
| `OLLAMA_MODEL` | Local model name | Defaults to `qwen2.5:3b` |
| `LLM_REQUEST_TIMEOUT` | Timeout in seconds for model requests | Defaults to `120` |
| `SUMMARY_MODE` | `extractive` or `llm` | Defaults to fast local extractive summaries |
| `OPENAI_API_KEY` | Optional hosted OpenAI key when `LLM_PROVIDER=openai` | Optional |
| `SERPAPI_KEY` | Live web search | Optional |
| `GOOGLE_SEARCH_API_KEY` | Google Custom Search API key | Optional |
| `GOOGLE_SEARCH_ENGINE_ID` | Google Custom Search engine ID | Optional |
| `SCRAPER_MODE` | `requests` or `playwright` scraping; defaults to `requests` | Optional |
| `SMTP_HOST` | SMTP server for email delivery | Optional |
| `SMTP_PORT` | SMTP server port | Optional |
| `SMTP_USER` | SMTP username | Optional |
| `SMTP_PASSWORD` | SMTP password or app password | Optional |
| `SMTP_FROM` | Verified sender address used in the From header | Optional; falls back to `DEFAULT_FROM`, then `SMTP_USER` |
| `AURA_RUN_STORE` | Custom path for persisted run records | Optional |
| `AURA_MEMORY_STORE` | Custom path for saved preferences and memory | Optional |

When a live service is not configured, AURA reports fallback, simulation, or unavailable status rather than silently claiming live external data.

## API

### Health and discovery

```text
GET /health
GET /tools
GET /metrics
GET /evaluation
```

### Check result links

```http
POST /links/check
Content-Type: application/json
```

```json
{
  "urls": ["https://example.org/jobs/role"]
}
```

Checks up to 15 public HTTP(S) URLs without following redirects or reading page content. Only confirmed `404` and `410` responses are flagged as broken; blocked or unavailable checks remain unverified.

### Run a goal

```http
POST /run
Content-Type: application/json
```

```json
{
  "goal": "Find remote Python internships and summarize the best matches",
  "planner": "rule"
}
```

The browser uses `POST /run/stream` for server-sent progress events and a final result event. Existing API clients can continue using `POST /run` for a single JSON response.

The response includes a `run_id`, final status, validated plan, logs, structured events, task counts, and verification counts.

### Inspect runs

```text
GET /runs
GET /runs/{run_id}
```

### Resume workflows

```text
POST /resume/analyze
POST /resume/match
```

Resume analysis accepts a base64-encoded PDF, DOCX, or TXT payload with a 10 MB limit. The UI uses these endpoints directly, so parsing and matching remain backend-owned operations.

## Testing

Run the complete suite:

```bash
pytest -q
```

The tests cover typed plan validation, dependency ordering, verification, bounded recovery, API validation, run persistence, resume workflows, and evaluation metrics. Tests are deterministic and do not require live API credentials.

## Persistence and Privacy

Execution records are stored in `.aura_runs.json` by default. The file is ignored by Git because it can contain goals, outputs, and execution metadata. Set `AURA_RUN_STORE` to use another local path.

Do not commit `.env` files, API keys, uploaded resumes, personal documents, `.aura_runs.json`, generated reports, or sensitive logs.

External integrations may operate in fallback or simulation mode. Verify the service status before treating a result as live external data.

## Current Limitations

- The default run store is a local JSON file rather than a multi-user database.
- Some search and analysis fallbacks are intentionally lightweight.
- OCR requires system packages that are not installed by Python dependencies alone.
- LLM planner comparison requires a configured Ollama or OpenAI provider and real benchmark runs.
- The browser workspace is served by the FastAPI process and is designed for a local or small-team demonstration.

## Roadmap

- Benchmark suite for rule and LLM planners.
- Richer task graph visualization.
- Persistent user preference memory with secret filtering.
- More task-specific verification evidence.
- Production database and authentication boundary.

