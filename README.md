# PPT Master Self-hosted Agent

PPT Master Self-hosted Agent is an orchestration layer for generating editable PowerPoint decks from source material. It accepts Markdown, PDF, DOCX, XLSX, PPTX, or URLs, converts content to Markdown when needed, creates a project workspace, plans the deck, generates each slide as SVG, validates the output, runs post-processing, and exports an editable PPTX.

This repository reuses the skills, workflows, scripts, templates, icons, and chart assets from [hugohe3/ppt-master](https://github.com/hugohe3/ppt-master). The main addition in this repo is the self-hosted agent under `agent/`, which drives the upstream `skills/ppt-master` workflow through an OpenAI-compatible LLM endpoint.

## Main Components

- `AGENTS.md`: repository-level behavior instructions for AI agents. It points PPT generation tasks to `skills/ppt-master/SKILL.md`.
- `agent/`: the self-hosted agent implementation.
- `skills/ppt-master/`: the reused upstream skill package, including workflows, references, scripts, templates, icons, and chart assets.
- `projects/`: runtime workspace for generated decks.
- `.env.example`: minimal environment configuration for the agent.
- `requirements.txt`: Python dependencies for the agent and skill package.

## Directory Layout

```text
.
├── agent/
│   ├── main.py              # CLI entry point
│   ├── config.py            # LLM, path, and runtime configuration
│   ├── orchestrator.py      # End-to-end pipeline orchestration
│   ├── schemas.py           # Structured output schemas
│   ├── state.py             # Project state model
│   ├── agents/              # Strategist and Executor agent definitions
│   ├── prompts/             # Prompt loader and context injection
│   └── tools/               # Wrappers around source, project, SVG, and export scripts
├── skills/ppt-master/
│   ├── SKILL.md             # Authoritative PPT Master workflow
│   ├── references/          # Role rules and technical standards
│   ├── workflows/           # Optional workflows such as verify-charts and visual-edit
│   ├── templates/
│   │   ├── icons/           # Icon library and usage guide
│   │   ├── charts/          # Chart templates, index, and style guide
│   │   └── layouts/         # Opt-in layout templates
│   └── scripts/             # Source conversion, SVG validation, finalization, and PPTX export
└── projects/                # Generated project outputs
```

## Pipeline Flow

1. Source processing: non-Markdown inputs are converted through `skills/ppt-master/scripts/source_to_md/`.
2. Project initialization: a workspace is created under `projects/<name>_<format>_<date>/`, and source files are imported into `sources/`.
3. Template option: free design is the default. Layout templates are used only when explicitly requested.
4. Strategist phase: the agent reads the source, AGENTS/SKILL instructions, icon guide, and chart index, then presents the Eight Confirmations. This step blocks until the user confirms or asks for changes.
5. Planning output: after confirmation, the Strategist writes `design_spec.md`, `spec_lock.md`, and `slide_outline.json` using structured output.
6. Executor phase: slides are generated sequentially with `PPT_WINDOW_SIZE=1`. For each slide, the Executor uses the lock file, source content, outline, icon guide, and chart templates when relevant.
7. Quality check: `svg_quality_checker.py` validates generated SVG files.
8. Post-processing: `total_md_split.py` and `finalize_svg.py` normalize notes and SVG assets.
9. Export: `svg_to_pptx.py` exports the final editable PPTX into `exports/`.

For decks with data charts, the optional `skills/ppt-master/workflows/verify-charts.md` workflow can run between Executor and post-processing. For post-export visual edits, `skills/ppt-master/workflows/visual-edit.md` is available when the requested change is visual and ambiguous.

## Setup

Requirements:

- Python 3.12+
- An OpenAI-compatible Chat Completions endpoint

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env
```

Edit `.env` for your LLM server:

```bash
LLM_BASE_URL=http://127.0.0.1:8000/v1
LLM_MODEL=openai/Qwen/Qwen3.6-27B
LLM_API_KEY=sk-dummy
LLM_TEMPERATURE=0.5
LLM_MAX_TOKENS=16384
PPT_DEFAULT_FORMAT=ppt169
PPT_WINDOW_SIZE=1
```

If you use vLLM, expose an OpenAI-compatible endpoint. Example:

```bash
vllm serve Qwen/Qwen3.6-27B \
  --tensor-parallel-size 2 \
  --max-model-len 131072 \
  --gpu-memory-utilization 0.95 \
  --dtype bfloat16 \
  --enable-prefix-caching \
  --enable-chunked-prefill \
  --max-num-seqs 4 \
  --port 8000 \
  --host 0.0.0.0 \
  --trust-remote-code \
  --default-chat-template-kwargs '{"enable_thinking": false}' \
  --enable-auto-tool-choice \
  --tool-call-parser hermes
```

## Running The Pipeline

Load the environment and run the CLI:

```bash
set -a
source .env
set +a

.venv/bin/python -m agent.main input.md
```

You can override runtime options from the command line:

```bash
.venv/bin/python -m agent.main input.md --format ppt169 --base-url http://127.0.0.1:8000/v1
```

At the Eight Confirmations step, press Enter to accept the recommendation or type a change request such as `Reduce to 6 slides`. After confirmation, the pipeline continues automatically through SVG generation, notes, quality checks, post-processing, and PPTX export.

Generated output is stored in:

```text
projects/<project_name>_<format>_<date>/
├── design_spec.md
├── spec_lock.md
├── slide_outline.json
├── sources/
├── svg_output/
├── svg_final/
├── notes/
└── exports/
```

The final PPTX is in `exports/`. Input files are moved into the project's `sources/` directory, following the upstream PPT Master workflow.

## Operating Rules

- `skills/ppt-master/SKILL.md` is the workflow authority for PPT generation tasks.
- The Executor must generate slides sequentially, not in batches.
- Output language should follow the user request and source language. If the user does not specify a language, Vietnamese source material should produce Vietnamese slides and notes.
- Icons and charts should use existing assets in `skills/ppt-master/templates/icons/` and `skills/ppt-master/templates/charts/` whenever possible.
- `projects/` contains runtime output and should not be treated as stable source code.
