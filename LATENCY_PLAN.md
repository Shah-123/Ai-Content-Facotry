# Latency plan — AI Content Factory

How to make every feature faster, ranked. Companion file with line-level detail for 8 of the features: [LATENCY_AUDIT_DETAIL.md](LATENCY_AUDIT_DETAIL.md).

> **Base warning — read first.** Everything in this plan, and the two changesets described in it, was written against `bb234e3` (`main`). The newest *pushed* code is **`origin/fix/fyp-audit-p0-p1` @ `61a819c`**, 13 commits ahead of `main` (2026-09-09 to 2026-09-17). On that branch some line references and findings are stale: the frontend (the agent-graph canvas and the analytics hook were removed; chat, content and sidebar views rewritten; podcast/video progress streaming added), QA scoring (now derived in code; `verify_citations` returns a tuple), video (`make_portrait_frame` rewritten, a render-progress logger, a guard around scene planning), per-user accounts (`api/users.py`) and the exporters. That branch is also not self-consistent: `tests/test_video_normalize.py` imports `_normalize_to_portrait`, which is defined nowhere I can find, so its suite stops at a collection error. Re-validate before acting on any item.

## Read this first (limits of this document)

- **Nothing here is measured.** The repo records no timings (`usage.py` counts tokens only), and the local `web_jobs.db` holds only test fixtures. Every duration below is a reasoned estimate (assumes `gpt-5-mini` at ~100 output tokens/s plus 500–3000 hidden reasoning tokens per call at the default effort). The only measured numbers are the ones the earlier prototype's code comments quote, flagged as such.
- **The multi-agent audit was interrupted.** 8 of 19 features were audited by sub-agents (research, upload/RAG, writers + reducer, QC + revision, SEO/keywords, G-Eval/DeepEval, images, campaign); the skeptic stage that was meant to refute and risk-check each finding never ran. I re-read the cited code for the headline findings (marked ✔ in the detail file) and audited the rest myself (topic guard/router, planning, graph core, API/DB, podcast, video, frontend, infra — IDs `INT-`, `GRP-`, `POD-`, `VID-`, `API-`, `FE-`, `INF-` below). Risk notes on the sub-agent findings are therefore mine, from reading the code.
- **Applied and tested so far:** the earlier prototype (committed as `ab3295d`) and a second batch of five changes (uncommitted; see "Second batch" below). Nothing else in this plan is implemented. Tests ran with the earlier session's virtualenv, which matches `requirements.lock.txt` (173 packages, same pins); no package was installed.

## Earlier prototype — applied and committed here (`ab3295d`, not pushed)

A previous session left **uncommitted** latency changes in a different clone: `D:\Ai-Content-Facotry\.claude\worktrees\effectful-latency-reduction-08e24c` (branch `claude/effectful-latency-reduction-08e24c`, same base commit as `main`). It has been applied here: 9 modified files plus the new `Agents_backend/tests/test_concurrency.py`, byte-identical to the source worktree. Committed as `ab3295d` on `claude/code-version-check-9ddd39`; not pushed. The D: worktree still holds the same changes uncommitted and was left alone.

**What was checked after applying**
- Full offline suite: **215 passed, 3 skipped** (the skips are the golden tests, which need `RUN_GOLDEN_TESTS=1` and real API calls). 208 existing tests + 7 new ones.
- `reasoning_effort` reaches the request payload for `gpt-5-mini` when `LLM_REASONING_EFFORT` is set, and is absent when unset or for `gpt-4o-mini` (checked with `ChatOpenAI._get_request_payload`, no API call).
- Video, real MoviePy 2.2.1, same synthetic inputs through `git HEAD` and the patched compositor (portrait + landscape sources, looped footage, hook card, captions): both give 1080×1920, 2.40 s, 30 fps; every sampled frame is **pixel-identical** (max difference 0) and the files are the same size. Render time **14.7 s → 7.2 s** (order swapped to rule out warm-up bias). That is a tiny 72-frame synthetic render, so treat the ratio as indicative only.
- DeepEval, real deepeval 4.1.0 with a stub judge that sleeps 1 s per call: 8 judge calls either way (this confirms DeepEval makes 8 calls, not 4), **8.1 s serial → 2.0 s** with 4 calls in flight on 4 threads, identical scores, no errors from running `measure()` off the main thread.
- Not checked: any real API call (OpenAI, Gemini, Pexels, DALL·E), the podcast and image paths beyond their unit tests, and real-world speed-ups.

**Not touched by the prototype, and worth knowing:** the DeepEval accuracy rubric raises `MissingTestCaseParamsError` when a job has no evidence (closed-book), so its score is `None` — this happens identically before and after the patch.

| In the prototype (now applied here) | Plan ID |
| :--- | :--- |
| `LLM_REASONING_EFFORT` env knob on every client **except the judge** (unset = identical behaviour; non-reasoning models never receive it) | the effort items in every feature |
| Image generation concurrent, placement still in order | IMG-1 |
| DeepEval's 4 rubrics measured concurrently (its comment: 8.1 s → 2.0 s with a synthetic 1 s/call judge) | DEEP-1 |
| Flagged sections revised concurrently | QC-4 |
| Podcast OpenAI-TTS turns concurrent (4 workers), order kept | POD-3 |
| Upload topic derivation overlapped with embedding/indexing | RAG-3 (part) |
| Video: hook / voiceover+captions / stock-footage chains concurrent; Pexels downloads concurrent; picks the 1080×1920 rendition instead of the first top-scoring (possibly UHD) file; drops a redundant same-size resize and `method="compose"` | VID-1, VID-2, VID-3 (part) |
| Barrier-based tests for all of the above (fail if a loop goes sequential again) | — |

Its code comments quote measurements: 245 ms/frame for a UHD source vs 116 ms/frame for 1080×1920, `compose` ≈ 60% of render time, the redundant resize ≈ 9 ms/frame. Taking 116 ms × 1,800 frames (a 60 s Short at 30 fps) ≈ **3.5 minutes of Python frame work before those fixes**.

**Next:** set `LLM_REASONING_EFFORT` only for an A/B run, then do the items below that the prototype does *not* cover.

## Second batch — five changes, uncommitted

| Change | What it does | Files |
| :--- | :--- | :--- |
| Scrape pool | every page is fetched at once instead of in waves of five; results were already keyed by index, so order is unchanged | `research.py` |
| SEO metadata off the critical path | the SEO call moved out of `merge_content` into node `seo_metadata_generator`, run in the same superstep as QA (or the keyword step when QA is off); same prompt, same input (`merged_body`) | `workers.py`, `main.py`, `state.py`, exports |
| Topic guard ∥ router | `POST /api/jobs` starts the router call beside the guard (never for junk the free screen rejects), never waits for it, and hands the in-flight call to the pipeline, which reuses the answer; failure falls back to the router node's own call | `jobs.py`, `routing.py`, `background.py`, `state.py` |
| Boot-time import warm-up | a daemon thread imports the pipeline at startup; a lock makes the warm-up and the first job load `main.py` once | `api/main.py`, `api/background.py` |
| Two QA bugs | `section_title` is no longer dropped (and bad links name their H2), so revision targets the section instead of rewriting the article; manual "Run QA" loads `research/evidence.json` so real links are no longer reported as fabricated | `quality_control.py`, `manual_tasks.py` |

**Checked**
- Suite: **243 passed, 3 skipped** (the prototype's 215 plus 28 new tests). The behavioural tests (scrape pool, QA/revision targeting, manual-QA evidence, the loader lock, SEO overlapping QA, and the router hand-off) were each run against the old code or a deliberately broken variant in a throwaway copy and failed there; the remaining new tests are plain unit checks.
- **Output equivalence, end to end.** The real compiled graph and real nodes with deterministic fake models, run on `bb234e3` (before any latency work), on `ab3295d` (the prototype) and on this tree, with and without a precomputed router decision: all 14 compared state keys (article, SEO metadata, QA report/verdict/score, G-Eval scores, queries, evidence, plan, …) and all 10 saved files are **identical** (`metadata.json` compared after removing the timestamp and the temp-folder path).
- **Structure, simulated** (every fake model call takes 0.3 s): post-approval phase 1.21 s → 0.91 s (SEO now overlaps QA); with the router decision precomputed the graph's pre-approval phase goes 0.91 s → 0.61 s because the router call has left the graph. This shows the shape, not real seconds.
- **Full stack:** the real FastAPI app, real `_run_pipeline` thread, real graph and real database with fake models and automatic plan approval: job `completed`, 1,234 words, QA `READY`, HTML export saved, and the single router call ran on the speculative `route-guess` thread.

**Costs and caveats**
- A topic that passes the free screen but is rejected by the model wastes one short router call (before, a rejection cost nothing beyond the guard).
- `reports/token_usage.txt` and `metadata.json["usage"]` now include the guard call as well as the router call, because the usage baseline is taken when the request arrives. Previously the guard was outside the run.
- The speculative call needs a free slot in a 4-thread pool; if it fails or never runs, the router node asks the model exactly as before.
- The README graph and roster were updated; the thesis chapters still describe the old topology and were left alone.
- Not checked: real API calls, so the real-world savings (the plan's ranges) are still estimates.

## Bottom line

1. The default job is a chain of ~8 serial reasoning-model stages plus scraping. **No call anywhere sets `reasoning_effort`** (grep confirms; the only token cap in the repo is `max_tokens=3000` on writers), so every call runs at the API default. One env knob is the largest single lever — and the prototype above already adds it, opt-in, leaving the judge untouched so thesis scores stay comparable.
2. **The default UI job generates 2 images.** `App.tsx:25` defaults `numImages` to 2 and `ChatView.tsx` sends `generate_images: numImages > 0`. Image planning + generation sits serially in front of QA.
3. Cheap structural wins that change no output: scrape pool 5→15 (`research.py:261`), SEO-metadata call moved off the critical path (nothing reads it until save time), topic guard ∥ router, startup warm-up (the first request imports the whole `Graph` package **on the event loop**, `api/routes/jobs.py:29`).
4. Two **bugs that cost time**: the manual "Run QA" button never loads evidence, so every link is flagged as fabricated and an article rewrite + re-audit is forced (`manual_tasks.py:85-105`, `quality_control.py:55-109`); and QA issues drop `section_title` (`quality_control.py:266-274`), so revision usually falls back to rewriting the whole article.
5. The UI shows no article text until the whole pipeline ends, though the text is final after the keyword step. Streaming the draft is the biggest *felt* improvement and costs no compute.
6. Frontend: a 15 s poll that returns up to 50 full articles, an un-memoised Markdown render re-parsed on every event/poll, a Vite dev server in Docker.

## Where the time goes — default UI job (all estimates)

7 sections, QA on, 2 images, no keywords, no media, no upload.

| Stage | Calls | Est. now | Note |
| :--- | :--- | :--- | :--- |
| Topic guard (blocks the HTTP response) | 1 LLM | 5–15 s | `jobs.py:30` |
| Router | 1 LLM | 5–15 s | for `hybrid` only queries/mode are used (`routing.py:19-27`) |
| Tavily (≤5 queries, pool 5) | 5 HTTP | 3–8 s | |
| Scrape 15 URLs, pool 5 = 3 waves | 15–30 HTTP | 20–45 s | ~40% Jina timeouts per the author's own comment |
| Evidence extraction | 1 LLM, ~12k tokens in | 25–60 s | nothing shown meanwhile |
| Planner | 1 LLM | 15–40 s | → plan screen at **≈ 75–185 s** |
| *human approval* | | | event-based wait, no polling cost |
| Writers (7 parallel) | 7 LLM | 8–30 s | slowest one sets the time; <80-word output triggers a 2nd serial call |
| SEO metadata (inside `merge_content`) | 1 LLM | 5–25 s | result only read at save time |
| Image planner + 2 images, serial | 1 LLM + 2 DALL·E | 24–70 s | on the critical path |
| QA | 1 LLM, ~10k tokens in | 15–60 s | +60–150 s if the revision loop triggers |
| G-Eval | 1 LLM | 10–40 s | before any media node |
| Save + HTML export | local | <1 s | |
| | | **≈ 100–260 s after approval** | |

## Do next, ranked

Order = impact × confidence ÷ effort, default UI path first. "Out" = changes generated content or scores.

| # | Change | Where | Est. saving | Effort | Safe? / Out? |
| :-- | :--- | :--- | :--- | :--- | :--- |
| 1 | **Done, committed (`ab3295d`):** the D: prototype (see above). Next: A/B `LLM_REASONING_EFFORT=low` with the golden harness | `utils.py` + stages | effort knob: unknown, likely the biggest — measure first (GRP-4) | A/B | safe; effort = **Out** (opt-in, default unset) |
| 2 | **Done (RES-3), uncommitted:** scrape pool 5→15. Still open: deadline/early exit once ~10 pages are in (RES-4) | `research.py:261` | 15–35 s | XS / S | RES-4 **Out** |
| 3 | **Done, uncommitted:** SEO-metadata call → its own node in the same superstep as QA (WRK-2/KWO-3) | `workers.py`, `main.py` | 5–25 s, every job | S | output-identical, checked end to end |
| 4 | **Done, uncommitted:** topic guard ∥ router (INT-1/2) — the router call starts beside the guard and its answer is reused by the pipeline | `jobs.py`, `routing.py`, `background.py` | 5–25 s | S–M | output-identical; token_usage.txt now also counts the guard call |
| 5 | Stream the draft: put section/merged markdown in the `completed` event metrics, render it in ContentView; persist `final_content` right after the keyword step (WRK-3, EVAL-3, FE-6) | `workers.py:257,484`, `background.py:268-322`, `ContentView.tsx` | **perceived**: first text ~10–30 s after approval instead of at the end | M | safe |
| 6 | Overlap images with QA/revision (IMG-2) or plan them from the outline during writing (IMG-4); IMG-1 is already prototyped | `main.py:469-484,541-606` | 8–25 s on top of IMG-1 (default path) | M / L | IMG-4 **Out** (planner no longer reads prose) |
| 7 | **Done (QC-2, QC-3), uncommitted:** manual QA evidence, `section_title` passthrough. Still open: skip re-audit after a no-op revision (QC-5) | `manual_tasks.py`, `quality_control.py` | removes 2 serial calls from manual QA; avoids full-article rewrites | XS–S | bug fixes; revision path **Out** |
| 8 | **Done (INT-4, imports only), uncommitted:** warm the pipeline imports at boot. Not done: Chroma/tiktoken/deepeval warm-up (RAG-8, DEEP-4), which would make network calls | `api/main.py` | measured: the first request paid ~3.1 s (agents package, on the event loop) + ~0.2 s (main.py) | XS–S | safe; `WARMUP_IMPORTS=0` turns it off |
| 9 | Extraction: ask for ~40–90-word snippets, one item per URL (RES-8); optionally extract per source while scraping (RES-2) | `research.py:285-301` | 5–15 s; RES-2 15–45 s | XS; M | **Out** |
| 10 | Upload jobs: doc extraction workers 4→8, ordered `map` (RAG-1); overlap ingest with research (RAG-2/RES-10) | `document_ingest.py:314`, `main.py:517-541` | 8–20 s; up to 40 s | XS; L | RAG-1 safe |
| 11 | Frontend render/poll fixes: batch WS events, memoise the Markdown body, drop the 3 s poll when the WS is up, pause the 15 s poll on a hidden tab (FE-1..4) | `App.tsx:63,89`, `ContentView.tsx:277`, `useJobActions.ts:99` | removes jank, cuts requests | S | safe |
| 12 | Job-list payload: stop returning `final_content`/`plan_json`/social text and skip file healing for the list (API-1) | `db.py:198-206`, `api/utils.py:130` | ~1–3 MB per 15 s poll → a few KB (est.) | S | safe |
| 13 | Serve the built frontend from FastAPI (already supported); drop `--reload` and bind-mounted data dirs outside dev (INF-1/2) | `frontend/Dockerfile`, `docker-compose.yml`, `api/main.py:90` | first-load time; Docker-Desktop file I/O — unmeasured | S | safe |
| 14 | Video render, remaining part (VID-3), podcast fixes (POD-1/2) | below | tens of seconds to minutes per video | M | VID-3 mostly output-preserving |
| 15 | Cache DeepEval steps / results (DEEP-2/3); gate the keyword rewrite and make it an edit list (KWO-2/1); drop the campaign brief round (CAM-2) | detail file | per feature | S each | KWO-2, CAM-2 **Out** |
| 16 | `max_concurrency` on the writer fan-out (WRK-4) and tighter per-stage timeouts (WRK-8, KWO-9, IMG-5) | `background.py:218,269`, `utils.py:135` | tail only | XS | verify WRK-4's claim in the pinned LangGraph first |

## Feature by feature

Detail and exact lines for the starred features are in [LATENCY_AUDIT_DETAIL.md](LATENCY_AUDIT_DETAIL.md).

**Topic guard + router (intake)** — mine.
- INT-1: `POST /api/jobs` awaits a reasoning-model call (`jobs.py:29-30`) before the job id exists; the UI shows nothing until it returns. INT-2: the router then runs another serial call; for the default `hybrid` mode `needs_research` is forced true (`routing.py:19-27`), so only `queries`/`mode` matter. Both use `llm_fast`, so the effort knob covers both; per role they are classification/extraction tasks where `minimal` is the natural setting.
- INT-3: cache guard verdicts per normalised topic (tiny LRU) — resubmitting an edited or retried topic skips the call. XS, fail-open semantics unchanged.
- INT-4: the `from Graph.agents.topic_guard import …` line sits inside the async handler, so the first request after boot imports the whole `Graph` package synchronously on the event loop (all WebSocket streams stall); `_get_pipeline_main()` then executes `main.py` on the first job (`background.py:40-56`). Warm both in `lifespan`.

**Research\*** — pool and structure (RES-3/4/11), extraction call (RES-1/2/8), Tavily wrapper (RES-5: deprecated class, default `search_depth="advanced"`, no timeout; I confirmed the class and that `days=` is passed — the claim that it is then ignored is the auditor's reading of langchain-community 0.4.2), Jina request pattern (RES-6: `Accept: text/event-stream` confirmed at `research.py:157`), `include_raw_content` experiment (RES-7), progress events (RES-9), cache for repeated topics (RES-12).

**Upload / RAG\*** — 8 extraction calls in 2 waves of 4 (RAG-1, confirmed `document_ingest.py:314,734,774`), derive-topic overlap (RAG-3, part prototyped), embed in parallel batches (RAG-5), content-hash dedupe of re-uploads (RAG-6), evidence cache (RAG-7), vectorised distance loop (RAG-11; auditor measured 0.46 s → 0.24 s per 5,000 sentences).

**Planning + plan approval** — one planner call (`orchestrator.py:94-125`, `llm_planner`, default effort) over a Python-repr of 10 evidence dicts; the evidence partition is deterministic Python, not an LLM call. The approval wait is `threading.Event.wait` (`background.py:232`), so approval → writers is instant: there is no polling to remove. Speculatively starting writers during review (WRK-6) reverses the documented cost-control design — not recommended.

**Writers + reducer\*** — effort (WRK-1; do **not** set `verbosity=low` on writers, it shortens articles), SEO metadata off the critical path (WRK-2), streaming (WRK-3), `max_concurrency` (WRK-4), the <80-word retry (WRK-5).

**QC + revision\*** — effort (QC-1), `section_title` (QC-2, confirmed), manual-QA evidence (QC-3, confirmed), concurrent sections (QC-4, prototyped), no-op skip (QC-5), patch-style edits (QC-6), delta re-audit (QC-7, changes what `qa_score` means after revision — opt-in only), deterministic citation re-check (QC-8). Rare path on the thesis fixtures (0, 0 and 2 revisions) but expensive when hit.

**SEO / keywords\*** — a no-op unless keywords are supplied (UI default none). When they are: the "density < 1%" trigger is practically always true (needs ~26 mentions in 2.5k words), so the whole-article rewrite fires every time (KWO-2, confirmed `keyword_optimizer.py:61-66,214`); switch to edit lists (KWO-1); feed keywords to the writers (KWO-6); the node emits no UI events (KWO-7).

**G-Eval / DeepEval\*** — G-Eval is already one call; effort on the *judge* changes scores, so keep it default for thesis-comparable runs (EVAL-1; the prototype agrees). It runs before the media nodes with no data dependency (EVAL-2; only matters for API/CLI jobs — the UI never sets media flags). DeepEval makes **8** judge calls, not the 4 the UI, `jobs.py:346` and the readme say (2 per GEval, per the auditor's reading of deepeval 4.1.0): concurrency (DEEP-1, prototyped), step cache (DEEP-2), result cache by content hash (DEEP-3), import warm-up (DEEP-4).

**Images\*** — default UI path (see above). IMG-1 prototyped; IMG-2/IMG-4 overlap; IMG-5: the OpenAI image client has the SDK's 600 s timeout and 2 retries (the project fixed this for chat clients in `utils.py:122-136` but the guard test only greps `ChatOpenAI(`); IMG-8: `b64_json` skips the second download.

**Campaign\*** — only reachable via the manual button from the UI. Effort (CAM-1), drop the brief round (CAM-2, **Out**), progress text goes stale (CAM-4). The manual path loads no evidence, so supporting stats are empty.

**Podcast** — mine.
- POD-1: `podcast_studio.py:98` calls `gemini-2.5-flash` with an audio response modality, while `video.py:297` uses `gemini-2.5-flash-preview-tts` — the model that actually does TTS. I cannot call the API, so I can't prove the first fails, but the committed sample (`tests/_podcast_test_run/audio/podcast_20260521_113814.wav`) is a valid RIFF WAV at 24 kHz, which is what the OpenAI-fallback `wave` code writes, whereas the Gemini branch writes raw bytes with no header. If it always fails, every podcast pays a failed round trip, then ~20 serial `tts-1-hd` calls. Check the logs for "Gemini native audio generation failed". If Gemini ever *did* succeed, the raw PCM saved under a `.mp3` name would not play.
- POD-2: the prompt asks for 780–910 words total (`:173-174`) **and** 18–20 turns of 70–110 words each (`:176,189`) = 1,260–2,200 words. The model will land near the larger figure, roughly doubling script generation and TTS time versus the stated 6–7 minutes. Pick one (**Out**).
- POD-3: per-turn TTS concurrency is prototyped (4 workers); `tts-1` instead of `tts-1-hd` is a further quality trade; the MP3 conversion goes through MoviePy (`:289-319`) — a direct `ffmpeg` call is leaner.

**Video** — mine; per-stage calls read from `video.py:884-1048`.
- Serial today: brief LLM (whole blog) → script LLM → hook LLM → Gemini TTS → `AudioFileClip` just to read the duration → Whisper API → planner LLM → Pexels → render. VID-1/2/3 (overlap, parallel downloads, rendition choice, `compose`/resize removal) are prototyped.
- Remaining VID-3: per-frame work is `get_frame().copy()`, a float32 gradient over 40% of the frame (`draw_gradient_overlay`, rebuilt every frame), and `draw_caption_on_frame` which round-trips the **whole** frame through PIL (`Image.fromarray` + `np.array`, ~12 MB of copies) to draw one text line. Cache the rendered caption band per (chunk, active word) — highlight only changes on word boundaries, ~150 distinct renders vs ~1,800 frames — and crop to the band instead of converting the full frame; precompute the gradient factor once. Looped footage (`Loop`) re-runs the whole per-frame chain on the repeat. Largest option (L, **Out**): scale/concat/loop in ffmpeg and burn captions as ASS karaoke subtitles so no per-frame Python remains.
- VID-4: fold the brief into the script call — one fewer serial LLM call (**Out**). VID-5: `AudioFileClip(audio_path).duration` spawns an ffmpeg reader that is never closed (`:962`); the TTS output is a WAV the code itself wrote, so `wave` gives the duration instantly. Whisper: the local fallback reloads the model on every call (`:390`); the API path uploads the full 24 kHz WAV — downsample first.

**Graph core / checkpointer / usage** — no large lever beyond the effort knob. Clients are built once at import (`utils.py:157-170`); the graph and `SqliteSaver` are rebuilt per job and `stream_mode="values"` copies state per step, but both are milliseconds against LLM calls — don't spend time there. Worth doing: GRP-1 per-role effort (below), GRP-2 `max_concurrency`, GRP-3 per-stage timeouts (worst case today is 9 min per call, `utils.py:132-136`), GRP-4 instrumentation (`usage.py` has no per-call duration and folds reasoning tokens into output tokens).

**API / DB / event bus** — mine.
- API-1: `list_jobs` is `SELECT *` over up to 50 rows including `final_content`, `plan_json`, social text and score JSON (`db.py:198-206`), then `_verify_and_clean_job_files` opens `metadata.json` and globs the image folder **per job** (`api/utils.py:49-133`). The UI calls this every 15 s (`App.tsx:63`), uncompressed. Return a summary projection and skip healing for the list.
- API-3: no compression. Add gzip for JSON/static, **excluding `/api/files/*`** (video/audio range requests).
- The event bus appends one JSONL line per event under a per-job lock (`event_bus.py:213-221`) — fine at ~100 events/job. DB connections are opened per call with three PRAGMAs and `update_job` re-selects the row it just wrote — milliseconds; ignore.

**Frontend** — mine.
- FE-1: each WebSocket message is its own `setEvents` with an O(n) `prev.some` dedupe (`App.tsx:89-98`), and history is fetched over REST *and* replayed by the socket, so opening a finished job triggers hundreds of renders of every event bubble (`ChatView.tsx:388`). Buffer incoming events and flush once per frame; memoise the bubble.
- FE-2: `ContentView.tsx:277-279` runs `resolveContentImageUrls` and `<ReactMarkdown>` inline on every render, and `currentJob` is replaced every 3 s while a manual task runs (`useJobActions.ts:99`) and on each state event. Wrap the article body in `useMemo`/`React.memo`; add `loading="lazy"` to markdown images.
- FE-3: the 3 s poll is redundant while the WebSocket is up (the handler already refetches on `system:completed/error`, `App.tsx:127-129`); each poll also costs a full `GET /api/jobs/{id}` with healing.
- FE-4: pause the 15 s list poll when `document.visibilityState === 'hidden'`.
- FE-5: `motion/react` is imported eagerly in 14 files; fonts come from a render-blocking third-party stylesheet with five families (`index.html:12`), and `index.css` references only DM Sans, Sora, Space Mono and Inter. Use `LazyMotion`, drop unused families, self-host.

**Infra** — mine.
- INF-1: `frontend/Dockerfile` runs the Vite dev server (unbundled modules, HMR) while `api/main.py:90-97` already serves `frontend/dist` if it exists — build once and serve from the API.
- INF-2: `docker-compose.yml` runs uvicorn with `--reload` and bind-mounts all of `Agents_backend` (SQLite WAL, Chroma, event logs, generated blogs). On Docker Desktop (Windows/macOS) bind mounts are far slower than named volumes. Ignore this if you run natively.

## GRP-1 — effort per role (extension of the prototype's single knob)

One global value is a good start. Once you can measure, differentiate. Suggested starting points, each to be A/B'd:

| Role | Clients | Start at | Why |
| :--- | :--- | :--- | :--- |
| Topic guard, router, evidence/doc extraction, SEO metadata, image planner, campaign, video helper calls | `llm_fast` | `minimal` | classification / copy-and-label tasks |
| Planner, writers, revision, podcast script | `llm_planner`, `get_llm`, `llm_quality` | `low` | creative but bounded |
| QA auditor | `llm_quality` | `low`, compare critical-issue counts | slowest single call |
| G-Eval / DeepEval judge | `llm_judge` | **leave at default** | scores must stay comparable with the thesis |

Hazards: reasoning-only parameter (non-reasoning models return 400 — gate on model name, as the prototype does); a completion-token cap on a reasoning model includes the hidden reasoning (writers' `max_tokens=3000` plus the <80-word retry at `workers.py:197,215` hint at this failure mode), so don't add caps before lowering effort; `ChatOpenAI(` may only be constructed in `utils.py` (`tests/test_utils.py:85-104`).

## Order of work

0. **Measure (30 min).** Run one default job, then:
   ```bash
   python stage_times.py Agents_backend/data/events/<job_id>.jsonl
   ```
   (script below). Add per-call duration and `usage_metadata["output_token_details"]["reasoning"]` to `UsageCallback.on_llm_end` (`usage.py:229`) so reasoning tokens stop being invisible. This turns every estimate above into data.
1. **The D: prototype is applied and committed here (`ab3295d`)**; suite green, see above.
2. **Output-preserving structure:** items 2, 3, 4, 8 are done (second batch, uncommitted); 10 (RAG-1) and 16 remain.
3. **Bug fixes with latency side effects:** item 7 is done (QC-2, QC-3); QC-5 remains.
4. **Perceived latency:** items 5, 11, 12.
5. **Quality-gated changes** (effort per role, RES-2/8, KWO, CAM-2, VID-4, POD-2): one at a time, each compared on the 3 golden topics — `RUN_GOLDEN_TESTS=1 pytest tests/golden -v -s` — judge fixed.
6. **Bigger moves:** IMG-2/4, RAG-2, VID-3 remainder, INF.

Keep every behaviour change opt-in via env with the default unset (the prototype's pattern), so the thesis numbers remain reproducible.

```python
# stage_times.py — per-agent wall-clock from the event log the app already writes
import json, sys
events = [json.loads(l) for l in open(sys.argv[1], encoding="utf-8") if l.strip()]
t0 = events[0]["timestamp"]
spans = {}
for e in events:
    s = spans.setdefault(e["agent_name"], [e["timestamp"], e["timestamp"]])
    s[1] = e["timestamp"]
for agent, (a, b) in sorted(spans.items(), key=lambda kv: kv[1][0]):
    print(f"{agent:<22} starts +{a - t0:6.1f}s   spans {b - a:6.1f}s")
print(f"TOTAL {events[-1]['timestamp'] - t0:.1f}s  (includes your plan-approval time)")
```

## Checked and not worth doing

- DB connection pooling/indexes, checkpointer tuning, per-job graph compile: milliseconds next to LLM calls.
- `verify_citations` and keyword-density analysis: ~1 ms (auditor timed 0.6 ms).
- Writer-prompt layout for prompt caching (WRK-9): ~0.1–0.4 s.
- Mean-pooled chunk vectors / 256-dim sentence embeddings (RAG-9/10): small gain, retrieval-quality risk.
- Speculative writers during plan review (WRK-6): reverses a deliberate cost control.
- Single-user caveat: each running job holds one worker-thread slot, including up to 20 min of plan approval (`background.py:232`). That limits how many jobs can be in flight, not the latency of one.
