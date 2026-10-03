# AI tools: what we used and for what

The build-phase README must say which AI tools we used and for what. Two parts: AI used **to build** the project, and AI used **inside** the product. Keep this updated as the build goes.

## 1. AI used to build the project

| Tool | Used for | Human check |
|---|---|---|
| **Claude Code** (Anthropic's coding agent, running the Claude Sonnet 5.5 and Claude Opus 5.5 models) in VS Code and the terminal | Turning the design docs, brief and critique into a build plan; scaffolding every layer (Python packages, dbt project, FastAPI routers, React app); the SQL guard, audit log, hardship latch, warehouse publish and tests; Dockerfiles and Compose; documentation | The team member reviews every plan and change; tests, lint, type checks and container runs gate each step |
| **Claude Code subagent** (fresh context, given only the brief and design docs) | An independent black-box spec test suite: unit, integration and system tests, a traceability matrix and open spec questions | Run and checked by us; binding to the code written by us |
| **Figma MCP** (Figma's connector for Claude Code) | Reading the Positivus community landing-page file (screenshots, colour and type variables) as visual inspiration for the frontend | Inspiration only: no Figma assets or copy reused; CIBC colours applied |
| **Claude Code plugin skills**: Render (Blueprint authoring), design (accessibility, UX copy, design system), dataviz, Figma design-to-code | Writing `render.yaml`; planned accessibility and copy reviews; chart design rules | Each output reviewed; deployment only on explicit approval |
| *(add any others used later, e.g. Gemini for an LLM feature, or tools for the deck and video)* | | |

## 2. AI inside the product

The product is **offline-first**: every AI-assisted step has a deterministic fallback, and the demo works with `LLM_PROVIDER=offline`.

| Where | What it does | Model / method | Why AI, and why not rules alone | How it's checked |
|---|---|---|---|---|
| Ask: question → chips | Maps a plain-English question onto a certified metric, dimensions, filters and time range | Offline semantic compiler (no LLM); optional LLM (provider TBC) to widen coverage | Free-text questions | Refusal rules, SQL guard, SQL shown, dev benchmark 0.994 |
| Ask: insight text | 2–3 sentence summary of the result rows | Template offline; optional LLM using **only** the returned rows | Readable summaries | Rows shown alongside; no numbers outside the rows |
| Policy answers (Ask and agent assist) | Answers policy questions with citations | BM25 over current policy sections with precedence (offline); optional LLM for wording | Many documents, some outdated | Citation required or refusal; precedence rules; benchmark policy questions |
| Text features | Hardship signal and reason, delay reason, dispute, complaint, cease request, next step from notes and transcripts | Rules mined from the release's labels (offline); optional LLM | Signals exist only in text | Transcripts: 99.6% hardship accuracy, 98% exact summaries; notes: 95% (500 public labels each) |
| Post-call summary | Structured summary in the gold template | Rule extraction + template (offline); optional LLM | Free speech | 98% exact match on 500 labelled transcripts; promise checked against the record; agent approves |
| Promise-break model | Ranks open promises by break risk | LightGBM (monotone constraints, calibrated) + SHAP reason codes | Many interacting signals | Must beat the bank's v2.1 on the same promises; calibration; top-decile metrics |
| Identity grey band (optional) | Evidence summary for a masked candidate pair | Optional LLM hint | Nicknames, typos | Steward decides; never automatic |

**Deliberately not AI:** the policy gate, treatment ladder, hardship program eligibility, plan simulator arithmetic, explanation text, refusals and the hardship latch. These are plain code, so every outcome is predictable and auditable.
