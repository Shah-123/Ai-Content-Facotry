# 🚀 AI Content Factory: Stateful Multi-Agent Content Orchestration & Evaluation Engine
## 🎓 Final Year Project (FYP) — Core System Documentation

[![Python Version](https://img.shields.io/badge/Python-3.11+-blue.svg?logo=python&logoColor=white)](https://www.python.org/)
[![LangGraph](https://img.shields.io/badge/LangGraph-Stateful_Orchestration-orange.svg)](https://langchain-ai.github.io/langgraph/)
[![FastAPI](https://img.shields.io/badge/FastAPI-Backend_API-green.svg?logo=fastapi&logoColor=white)](https://fastapi.tiangolo.com/)
[![React](https://img.shields.io/badge/React_19-TypeScript_&_Vite-blue.svg?logo=react&logoColor=white)](https://react.dev/)
[![Gemini](https://img.shields.io/badge/Gemini_2.5_Flash-Native_Audio-purple.svg)](https://deepmind.google/technologies/gemini/)
[![DeepEval](https://img.shields.io/badge/DeepEval-G--Eval_Metrics-red.svg)](https://github.com/confident-ai/deepeval)
[![License](https://img.shields.io/badge/License-Apache_2.0-lightgrey.svg)](LICENSE)

A stateful, multi-agent AI system for automated research, content synthesis, multi-modal asset generation, and academic-grade evaluation. Built on **LangGraph**, **FastAPI**, and **React**, this project serves as a **Final Year Project (FYP)** demonstrating agent coordination, parallel processing, Human-in-the-Loop (HITL) workflows, Advanced RAG, and automated LLM-as-judge quality assessment.

> **Scope.** This is a research and demonstration system, not a production
> deployment. It runs as a single API worker with a shared-secret access gate
> and no per-user accounts. The **Known Limitations** section at the end of this
> document states these boundaries precisely; read it before deploying anywhere
> reachable by other people.

---

## 🌟 Key Capabilities & Research Pillars

1. **Stateful Graph Orchestration:** Manages complex agent communications, loops, and conditions with [LangGraph](https://langchain-ai.github.io/langgraph/).
2. **Stateful Resumption & Checkpointer:** Employs [LangGraph's SqliteSaver](https://langchain-ai.github.io/langgraph/reference/checkpoints/) to persist state. If the process is halted or the server crashes, the engine can resume execution from the exact last saved step without repeating expensive LLM calls or research operations.
3. **Advanced Document Ingestion (Advanced RAG):** Parses PDFs, DOCX, TXT, and Markdown files. Uses sentence-level embeddings (`text-embedding-3-small`) to construct semantic chunks based on similarity thresholds. It executes cosine-similarity queries to match sections and pull targeted, grounded evidence.
4. **Human-in-the-Loop (HITL) Outline Control:** Pauses the writing process to present a draft outline plan to the user. The user can directly modify titles, goals, word counts, and bullet points via the UI, or write natural language feedback to request the LLM to automatically regenerate the plan.
5. **Parallelized Fan-Out Generation:** Speeds up content generation by writing body sections in parallel. Individual Worker agents are assigned specific sections, receiving only the evidence records matching their topic to prevent redundant text or source-stuffing.
6. **Multi-Modal Generation Studio:**
   - **Gemini Podcast Studio:** Synthesizes conversational, solo podcasts using Gemini 2.5 Flash's native audio capabilities, maintaining natural human pacing and speech elements.
   - **Video Generator:** Generates text-to-speech voiceovers, fetches stock B-roll clips from the Pexels API, matches them to the script, and renders videos with synchronized subtitles using MoviePy.
   - **SEO Keyword Optimizer:** Strategically integrates target keywords into headers, body paragraphs, and meta descriptions.
7. **Academic Evaluation (LLM-as-Judge):** Grades content against academic standards across four dimensions: Coherence, Relevance, Accuracy & Grounding, and Tone Alignment, using both in-house scoring and official [DeepEval](https://github.com/confident-ai/deepeval) GEval metrics.

---

## 📐 System Architecture

The workflow is a stateful, interruptible **cyclic** directed graph — cyclic
because the Quality Control → Revision feedback loop deliberately routes back on
itself, bounded at two attempts. The diagram below mirrors the edges declared in
[`build_graph()`](Agents_backend/main.py):

```mermaid
graph TD
    START([START]) --> B(Router)

    B -->|upload_id set| ING(Document Ingest / RAG)
    B -->|needs research| C(Research Agent)
    B -->|closed book| D(Orchestrator)
    ING -->|closed_book| D
    ING -->|hybrid / auto_topic| C
    C --> D

    D -.->|"interrupt_after — state persisted"| E[/"HITL — Plan Editor UI"/]
    E -.->|"approved, edited, or LLM-revised"| F{{Send fan-out}}

    subgraph PAR [Parallel Writing]
        F --> G0(Worker 0)
        F --> G1(Worker 1)
        F --> GN(Worker N)
    end

    G0 --> H
    G1 --> H
    GN --> H

    subgraph RED [Reducer subgraph]
        H(Merge Sections) -->|generate_images| H2("Plan and Place Images")
    end

    H --> CV(Completion Validator)
    H2 --> CV

    CV -->|generate_qa| I(Quality Control Auditor)
    CV -->|QA disabled| K
    I -->|"critical issues, under limit"| J(Revision Agent)
    J --> I
    I -->|"READY or revision limit reached"| K(Keyword SEO Optimizer)

    K --> P(G-Eval Scorecard)

    P --> L{Asset toggles}
    L -->|campaign| M(Campaign Generator)
    L -->|video| N(Video Synthesis)
    L -->|podcast| O(Gemini Podcast Studio)
    L -->|none enabled| Z

    M --> Z([END])
    N --> Z
    O --> Z

    DE(DeepEval G-Eval):::ondemand -.->|"POST /run-deepeval"| Z
    classDef ondemand stroke-dasharray: 5 5
```

The diagram above is hand-drawn for readability. To render the graph directly
from the compiled workflow — useful as ground truth when the two might drift:

```bash
cd Agents_backend && python -c "from main import build_graph; print(build_graph().get_graph().draw_mermaid())"
```

Two details the diagram makes explicit because they are easy to get wrong:

* **G-Eval runs before the media generators, not after.** Evaluation scores the
  article, so it is sequenced immediately after the SEO optimizer; the campaign,
  video and podcast nodes then fan out in parallel from it.
* **DeepEval is not a graph node.** It runs on demand from its own endpoint
  (dashed above), because adding four chain-of-thought judge calls to every
  generation is not a cost worth paying by default.

---

## 🤖 The Agent Roster

Not every node is an LLM call. Several stages are deterministic Python because
the task does not require judgement — the "Model" column says exactly which is
which, and `None` is a deliberate design choice rather than a missing feature.

> **Temperature is inert on the default model.** Several nodes request a
> specific sampling temperature (the planner asks for 0.7 to vary outlines, the
> writers for 0.3). Reasoning-family models such as `gpt-5-mini` accept only
> their default temperature, and `langchain-openai` drops the parameter silently
> rather than raising — so on the default configuration these values have no
> effect. They do apply when a non-reasoning model such as `gpt-4o-mini` is
> chosen via the model selector. Guarded by
> `tests/test_evaluation.py::TestTemperatureIsInertOnReasoningModels`.

| Graph Node | Model | Code Implementation | Primary Responsibility & Logic |
| :--- | :--- | :--- | :--- |
| **Topic Guard** | `gpt-5-mini` | [topic_guard.py](Agents_backend/Graph/agents/topic_guard.py) | Two tiers: a free deterministic screen rejects malformed input (empty, too short/long, no letters, gibberish); the LLM then judges whether a well-formed topic is semantically unsafe. Runs before a job is created, so rejected topics cost no pipeline tokens. |
| **Router** | `gpt-5-mini` | [routing.py](Agents_backend/Graph/agents/routing.py) | Chooses `closed_book` / `hybrid` / `open_book`, drafts search queries, and sets the recency window Tavily filters on. |
| **Researcher** | `gpt-5-mini` + Tavily | [research.py](Agents_backend/Graph/agents/research.py) | Runs queries in parallel, scrapes results (Jina Reader with a BeautifulSoup fallback), filters near-duplicates by Jaccard overlap, and extracts structured evidence. Downgrades the mode to `closed_book` if nothing usable is found, so an ungrounded post is never reported as grounded. |
| **Ingest / RAG** | `text-embedding-3-small` + `gpt-5-mini` | [document_ingest.py](Agents_backend/Graph/agents/document_ingest.py) | Semantic chunking via sentence-embedding distance, ChromaDB indexing, and topic-scoped retrieval with a three-tier fallback (Chroma → local vectors → persisted evidence). Evidence is extracted only from retrieved chunks. |
| **Orchestrator** | `gpt-5-mini` | [orchestrator.py](Agents_backend/Graph/agents/orchestrator.py) | Plans the outline, then **partitions evidence across sections** so parallel workers cite different sources instead of converging on the same few statistics. A higher temperature is requested to vary outlines between runs, but reasoning-family models such as `gpt-5-mini` ignore the parameter — see the note below the table. |
| **Worker (×N)** | `gpt-5-mini` | [workers.py](Agents_backend/Graph/agents/workers.py) | Writes its assigned section in parallel via LangGraph `Send()`, receiving only its own evidence slice plus sibling section titles for transition context. |
| **Reducer** | **None** (deterministic) | [workers.py](Agents_backend/Graph/agents/workers.py) | Orders sections by task ID, joins them, and builds the references table from the evidence pool — all plain Python. The single LLM call in this module generates SEO metadata, not the merge itself. |
| **Completion Validator** | **None** (deterministic) | [completion_validator.py](Agents_backend/Graph/completion_validator.py) | Regex checks for missing sections and low word count, applies shared auto-repairs, and scores completeness. No model involved. |
| **Quality Control** | `gpt-5-mini` + deterministic check | [quality_control.py](Agents_backend/Graph/agents/quality_control.py) | Audits the draft against evidence for hallucinations and structure. A **non-LLM citation verifier** parses every hyperlink and checks it against the research evidence by URL and domain; any unmatched link forces `NEEDS_REVISION` and caps the score at 6.0 regardless of the model's opinion. |
| **Revision** | `gpt-5-mini` | [revision.py](Agents_backend/Graph/agents/revision.py) | Surgically rewrites only the sections carrying critical issues, falling back to a full-article edit. Bounded at 2 attempts; output shorter than 60% of the original is rejected. |
| **SEO Optimizer** | `gpt-5-mini` + deterministic analysis | [keyword_optimizer.py](Agents_backend/Graph/keyword_optimizer.py) | Keyword density and placement are computed in Python; the model is used only to weave under-represented keywords back into the weakest passages. |
| **Image Planner** | `gpt-5-mini` → DALL·E / Gemini / Flux | [multimedia.py](Agents_backend/Graph/agents/multimedia.py) | Plans placements and prompts, then generates through a three-provider fallback chain (OpenAI → Google Gemini → Pollinations). |
| **Campaign Gen** | `gpt-5-mini` | [campaign.py](Agents_backend/Graph/agents/campaign.py) | Summarises the **full** article into a structured brief, then writes a LinkedIn post and an X/Twitter post in parallel. *Currently these two channels only* — the state carries fields for email, landing page, Facebook and YouTube, but they are not generated. |
| **Podcast Studio** | `gemini-2.5-flash` | [podcast_studio.py](Agents_backend/Graph/podcast_studio.py) | Generates a single-speaker audio podcast using Gemini's native audio output. |
| **Video Gen** | `gpt-5-mini` + Gemini TTS + Whisper | [video.py](Agents_backend/Graph/agents/video.py) | Scripts the voiceover, synthesises speech via Gemini TTS (with backoff), derives word-level timings with Whisper for karaoke captions, pulls portrait B-roll from Pexels, and composites a 9:16 MP4 with MoviePy. |
| **Academic Judge** | `LLM_JUDGE_MODEL` (defaults to `gpt-5-mini`) | [evaluation.py](Agents_backend/Graph/agents/evaluation.py) | In-house G-Eval scorecard (1–5) runs inside the graph; the weighted overall is computed in Python, not by the model. The official `deepeval` G-Eval runs **on demand** via its own endpoint, not as a graph node. |

---

## 🧪 Evidence-Distribution Experiment

The orchestrator partitions the evidence pool across sections so that parallel
workers cite different sources. That exists because of an observed defect: with
9 sections and 5 evidence items, every worker independently gravitated to the
same two or three prominent statistics, and one post repeated the same figure
seven times.

The system ships with the ablation needed to measure whether the fix works.
Setting `assign_evidence=False` skips partitioning, so every worker receives the
full pool — reproducing the pre-fix behaviour exactly.

```bash
cd Agents_backend

# Treatment arm — evidence partitioned across workers
RUN_GOLDEN_TESTS=1 GOLDEN_ASSIGN_EVIDENCE=1 pytest tests/golden -v -s

# Control arm — every worker receives the full pool
RUN_GOLDEN_TESTS=1 GOLDEN_ASSIGN_EVIDENCE=0 pytest tests/golden -v -s

# Aggregate both arms into a comparison + LaTeX table body
python -m tests.golden.report_ablation
```

Artefacts are written to `tests/golden/_runs/<case_id>__{assigned,fullpool}/`,
so the arms never overwrite each other. Two **deterministic** metrics are
recorded per run — no model scores them, so the numbers are not exposed to
judge bias:

| Metric | Meaning | Better |
| :--- | :--- | :--- |
| `repetition.repetition_rate` | Share of distinct statistics that surface in more than one section | Lower |
| `repetition.max_section_spread` | Section count for the single most-repeated statistic | Lower |
| `sources.concentration` | Share of cited sources appearing in more than one section | Lower |

The measurement code is [`tests/golden/metrics.py`](Agents_backend/tests/golden/metrics.py),
which carries its own self-check (`python -m tests.golden.metrics`).

> **On sample size.** One run per topic per arm measures a single sample of a
> stochastic generator, not an effect. Repeat each arm several times per topic
> before reporting a difference, and state `n` alongside any figure.

---

## 📊 Academic Quality & LLM-as-Judge Evaluation

The system evaluates the final content across four academic rubrics, generating scores and explanation logs:

1. **Coherence (Structure & Flow):** Evaluates logical progression, paragraph transitions, and structure.
2. **Relevance (Topic Coverage):** Evaluates how well the text matches user search queries and integrates keywords.
3. **Accuracy & Grounding:** Compares facts, numbers, and references against the source documents or research findings to flag hallucinations.
4. **Tone Alignment:** Evaluates target tone suitability and flags typical AI-generated phrases.

### In-House vs. DeepEval Scoring Modes
The system provides two evaluation workflows:
* **Custom Judge Node (`geval_scores`):** Runs automatically in the graph. Uses structured LLM outputs to rate sections on a **1.0 to 5.0** scale; the overall score is a code-computed weighted average (30% Coherence, 20% Relevance, 30% Accuracy, 20% Tone).
* **DeepEval G-Eval Node (`deepeval_scores`):** Runs **on demand** (the "Run Academic Audit" button → `POST /api/jobs/{job_id}/run-deepeval`), not inside the graph, since it makes 4 extra LLM calls per blog. Leverages Confident AI's `deepeval` library to execute Chain-of-Thought grading based on the G-Eval framework (Liu et al. 2023). Scores are normalized to a **0.0 to 1.0** scale.

Both reports are written to the `reports/` folder of each generated blog for academic audit trails.

---

## 🗂️ Project Directory Map

### 💻 Backend Components
* **Orchestration & Workflow:**
  - [api.py](Agents_backend/api/main.py) — FastAPI web application serving API routes, background tasks, and WebSocket streaming.
  - [main.py](Agents_backend/main.py) — Core CLI execution entry point and LangGraph workflow builder.
  - [db.py](Agents_backend/db.py) — SQLite database interface for jobs, metrics, and files.
  - [event_bus.py](Agents_backend/event_bus.py) — Message broker managing WebSocket connections and stream logs.
* **LangGraph Configuration:**
  - [state.py](Agents_backend/Graph/state.py) — Defines the Graph memory structures using [State TypedDict](Agents_backend/Graph/state.py#L85), [Plan](Agents_backend/Graph/state.py#L51), and [Task](Agents_backend/Graph/state.py#L29) definitions.
  - [nodes.py](Agents_backend/Graph/nodes.py) — Maps graph nodes to corresponding agent functions.
  - [templates.py](Agents_backend/Graph/templates.py) — System instructions, roles, and formatting guidelines.
  - [podcast_studio.py](Agents_backend/Graph/podcast_studio.py) — Script to interface with the `google-genai` SDK and synthesize audio.
* **Specialized Agent Implementation:**
  - [topic_guard.py](Agents_backend/Graph/agents/topic_guard.py) — Evaluates input topic safety.
  - [routing.py](Agents_backend/Graph/agents/routing.py) — Directs work to Tavily Search or closed-book agents.
  - [research.py](Agents_backend/Graph/agents/research.py) — Handles Tavily search processes.
  - [document_ingest.py](Agents_backend/Graph/agents/document_ingest.py) — Manages PDF/Word file parsing, semantic chunking, and retrieval queries.
  - [orchestrator.py](Agents_backend/Graph/agents/orchestrator.py) — Creates draft outline structures.
  - [workers.py](Agents_backend/Graph/agents/workers.py) — Implements parallel workers and merger nodes.
  - [quality_control.py](Agents_backend/Graph/agents/quality_control.py) — Performs fact-checking and consistency audits.
  - [revision.py](Agents_backend/Graph/agents/revision.py) — Refines text based on quality reports.
  - [evaluation.py](Agents_backend/Graph/agents/evaluation.py) — Contains in-house and DeepEval G-Eval nodes.
  - [campaign.py](Agents_backend/Graph/agents/campaign.py) — Creates social media marketing materials.
  - [video.py](Agents_backend/Graph/agents/video.py) — Builds script-to-video pipelines.

### 🎨 Frontend Components
* **Source Files (`frontend/src/`):**
  - [main.tsx](frontend/src/main.tsx) — Main entry point for Vite React.
  - [App.tsx](frontend/src/App.tsx) — Main application layout, sidebar, and tab routes.
  - [ContentView.tsx](frontend/src/ContentView.tsx) — Displays rich-text rendering of articles, evaluation scorecards, and SEO details.
  - [components/PodcastPlayer.tsx](frontend/src/components/PodcastPlayer.tsx) — Player for synthesized podcast audio. Video playback lives in `ContentView`'s media tab. (Replaces the former `MediaView.tsx`.)
  - [api.ts](frontend/src/api.ts) — Handles HTTP request routing and WebSocket connections.
  - [index.css](frontend/src/index.css) — Custom styling variables and theme configurations.
* **Reusable UI Components (`frontend/src/components/`):**
  - [ChatView.tsx](frontend/src/components/ChatView.tsx) — Live monitor displaying event streams and console logs.
  - [PlanEditor.tsx](frontend/src/components/PlanEditor.tsx) — Interface for modifying H2 sections, bullets, and word counts.
  - [Sidebar.tsx](frontend/src/components/Sidebar.tsx) — Navigation menu displaying generated articles.
  - [TopNav.tsx](frontend/src/components/TopNav.tsx) — Controls the header bar and theme toggles.
  - [UploadChip.tsx](frontend/src/components/UploadChip.tsx) — Component for document upload and status updates.

---

## ⚙️ Installation & Configuration

### Prerequisites
* **Python 3.11+**
* **Node.js 18+**
* **ffmpeg:** Required for processing audio and videos. Add the executable to your system's environment `PATH` variable.
* **ImageMagick (Optional):** Required if customizing caption layouts using MoviePy.

### 1. Install Project Dependencies

Clone this repository and run the setup scripts:

```bash
# Clone the repository
git clone <repository_url>
cd Multi_Agent_Blog_generator_FYP

# 1. Install Backend Dependencies
#    Reproducible install — the exact versions this project was developed,
#    tested and demonstrated against (173 pinned packages). Use this one.
pip install -r requirements.lock.txt

# 2. Install Frontend Dependencies
cd frontend
npm install
```

> **`requirements.txt` vs `requirements.lock.txt`**
> `requirements.txt` lists the ~38 direct dependencies as bounded version
> *ranges* (`>=x,<next-major`) and is what CI installs, so the build acts as an
> early warning when a new upstream release breaks the project.
> `requirements.lock.txt` pins the full transitive closure to exact versions and
> is what you should install for a demo, a fresh machine, or an examiner's
> checkout — it removes any chance of a dependency resolving differently today
> than it did when the test suite was last green.
>
> Regenerate the lockfile only from an environment where `pytest tests` passes.

### 2. Configure Environment Variables

Create a `.env` file in the root directory and add the following keys:

```ini
# OpenAI Keys — Used for Reasoning (GPT-4o) and Document Embeddings
OPENAI_API_KEY=sk-...

# Tavily Scraper Key — Used for Web Research
TAVILY_API_KEY=tvly-...

# Google Cloud API Key — Used for Gemini Native Audio TTS and Video TTS
# Note: Set GOOGLE_API_KEY; do not use GEMINI_API_KEY.
GOOGLE_API_KEY=AIzaSy...

# Pexels API Key — Used for B-roll Video Search
PEXELS_API_KEY=...

# ── Optional ────────────────────────────────────────────────────────────────
# Shared-secret API key. When set, all REST routes and the WebSocket require it.
# The frontend must be given the same value as VITE_API_KEY. Unset = open API.
# API_KEY=choose-a-long-random-string

# CORS allowlist (comma-separated). Defaults to the local Vite dev origins.
# ALLOWED_ORIGINS=http://localhost:3000

# Override the default models. LLM_QUALITY_MODEL also sets the G-Eval judge,
# so keep it fixed when comparing writer models across runs.
# LLM_FAST_MODEL=gpt-5-mini
# LLM_QUALITY_MODEL=gpt-5-mini
#
# Evaluation judge only. Defaults to LLM_QUALITY_MODEL. Set this to run an
# independent-judge arm WITHOUT also changing the QA auditor and reviser,
# which read LLM_QUALITY_MODEL:
# LLM_JUDGE_MODEL=gpt-4o

# PostgreSQL instead of SQLite (set automatically by docker-compose).
# DATABASE_URL=postgresql://postgres:postgres@localhost:5432/ai_content_factory
```

---

## 🚀 Usage Guide

This project can be run in two modes:

### Mode A: Full FastAPI + React Web App (Recommended)

This mode runs the complete web app with live WebSocket logs, outline editing, and document uploads.

1. **Start the FastAPI Backend Server:**
   ```bash
   cd Agents_backend
   uvicorn api:app --reload --reload-exclude "data/*" --reload-exclude "blogs/*" --reload-exclude "uploads/*" --reload-exclude "tests/*" --host 0.0.0.0 --port 8000
   ```

   > **It is `api:app`, run from `Agents_backend/`.** Two near-misses produce
   > confusing errors:
   > * `uvicorn main:app` — `main.py` is the pipeline module and defines no
   >   `app`, so uvicorn reports *"Attribute 'app' not found in module 'main'"*.
   > * Running from `Agents_backend/api/` — `main:app` resolves there and the
   >   server does start, but the reloader then watches only that folder.
   >
   > The `--reload-exclude` flags matter: without them, generated blog folders,
   > uploads and the SQLite files under `data/` all trigger reloads, and a
   > reload mid-generation kills the running job.
2. **Start the Vite Frontend Server:**
   ```bash
   cd frontend
   npm run dev
   ```
3. **Open in Browser:** Navigate to `http://localhost:3000`.

### Mode B: CLI Execution Mode
For direct execution and testing via command-line arguments:

```bash
cd Agents_backend
python main.py
```
This CLI walks you through topic checks, research settings, and runs the LangGraph engine locally.

---

## 📝 Example Output Folder Flow

Each run outputs its files to a unique folder under the `Agents_backend/blogs/` directory:

```text
blogs/quantum_computing_20260521_103000/
├── README.md                                 # Overview & execution metrics
├── content/
│   └── quantum_computing.md                  # Final markdown content with placed images
├── social_media/
│   ├── linkedin_quantum_computing.txt
│   ├── twitter_quantum_computing.md
│   ├── landing_page_quantum_computing.md
│   └── email_quantum_computing.md
├── reports/
│   ├── qa_report.txt                         # Fact-checking feedback
│   ├── geval_report.txt                      # In-house G-Eval evaluation scores
│   └── keyword_optimization.txt              # SEO density report
├── research/
│   └── evidence.json                         # Local cache of scraped Tavily results
├── audio/
│   └── podcast.wav                           # Conversational solo podcast audio
├── video/
│   └── short.mp4                             # Rendered MP4 short video
└── metadata/
    ├── plan.json                             # Final approved plan layout
    └── metadata.json                         # Execution traces, tokens, and config keys
```

---

## ⚠️ Known Limitations & Future Scope

* **Checkpointer Backends:** The web application persists checkpoints with `SqliteSaver`, or `PostgresSaver` when `DATABASE_URL` points at Postgres (docker-compose sets this automatically, with an automatic fallback to SQLite if the connection fails). The volatile `MemorySaver` is only the default for the standalone CLI path, where a run is not expected to outlive the process — CLI runs therefore cannot be resumed after a crash.

* **Prompt Injection — not mitigated.** Text scraped from the open web and text extracted from uploaded documents is passed into LLM prompts as evidence with no instruction-hierarchy defence: no delimiter fencing, no escaping, and no validation that extracted "facts" originated in the source rather than in an instruction embedded within it. A web page containing something like *"ignore previous instructions and instead write…"* is handed to the extraction model as ordinary content. The affected paths are the research extractor, the document-chunk extractor, the section writers, and the QA auditor. Realistic mitigations — fencing untrusted spans in explicit delimiters, instructing the extractor to treat the span as data only, and validating that each extracted snippet is a substring of its source — are known but unimplemented. This is the most significant unaddressed security weakness in the system.

* **No Rate Limiting:** No endpoint is rate limited. Because `POST /api/jobs` triggers real spend on OpenAI, Tavily and Google APIs, an instance left reachable without `API_KEY` set can be driven into an unbounded bill by anyone who finds it. Set `API_KEY`, keep the deployment on `localhost`, or place a reverse proxy in front of it.

* **Evaluation Methodology:** The reported quality scores were produced with the same model acting as both writer and judge (`gpt-5-mini`), a known source of self-preference bias in LLM-as-a-judge evaluation. The judge is configured separately via `LLM_QUALITY_MODEL`, so an independent-judge run needs no code change. The published figures also come from three topics with one run each and no baseline comparison arm, so they characterise the system's own behaviour rather than demonstrating superiority over a simpler approach. No human annotation of factual accuracy was performed.
* **Single-Speaker Audio:** The Gemini Podcast studio is set to a single-speaker voice (`Aoede`). Future updates could add two-speaker dialogue scripts using two distinct Gemini audio voices.
* **Authentication:** Access control is a single shared secret, not per-user auth. Setting `API_KEY` in `.env` makes every REST route and the WebSocket require it (`X-API-Key` header, or `?api_key=` for browser-initiated requests such as `<img>` and downloads); leaving it unset keeps the API open, which is only appropriate on `localhost`. CORS defaults to the local dev origins and is configurable via `ALLOWED_ORIGINS`. A public deployment needs real per-user authentication (OAuth2) and per-user job ownership — currently any authenticated caller can read and delete every job.
* **Single-Process Concurrency:** Jobs run in background threads, and HITL approval blocks one of those threads for up to 20 minutes. The approval events are held in an in-process dictionary, so the API must run as a single worker; a multi-worker or multi-replica deployment needs an external task queue and a shared store. The SqliteSaver/PostgresSaver checkpointer is what makes crash recovery possible without one.

---

## 📄 License

This repository is licensed under the Apache 2.0 License. See the [LICENSE](LICENSE) file for details.