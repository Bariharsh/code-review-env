# Code Review Environment

`code-review-env` is a small OpenEnv-style Python project for training or evaluating agents on code review tasks. Each episode presents buggy code, expects a natural-language review from the agent, and returns a deterministic reward based on how well the review identifies the issue and fix.

The environment is intentionally simple and Gym-like:

- `reset()` selects a task and returns the initial observation.
- `step(action)` grades the review and returns `(observation, reward, done, info)`.
- `state()` returns the typed internal environment state.

By default, episodes finish after one step. If you want retry-style experiments, you can pass `max_steps > 1` when constructing the environment.

## Project Layout

```text
code-review-env/
├── backend/
│   ├── server.py
│   ├── env/
│   │   ├── environment.py
│   │   ├── grader.py
│   │   ├── models.py
│   │   └── tasks.py
│   ├── baseline/
│   │   └── run_agent.py
│   └── data/
│       └── samples.json
├── frontend/
│   ├── package.json
│   ├── astro.config.mjs
│   ├── svelte.config.js
│   ├── dist/
│   └── src/
│       ├── components/
│       ├── layouts/
│       ├── pages/
│       └── styles/
├── openenv.yaml
├── Dockerfile
└── README.md
```

## Environment Design

The environment loads tasks from `backend/data/samples.json`. Each task includes:

- buggy `code`
- `difficulty`
- `title`
- `expected_output` with an explanation plus deterministic keyword groups for grading

The bundled tasks cover:

- Easy: wrong modulo/operator logic
- Medium: incorrect ranking logic
- Hard: SQL injection risk from string interpolation

## Typed Models

The environment uses Python dataclasses in [`models.py`](./backend/env/models.py):

- `ReviewAction`
- `CodeReviewObservation`
- `RewardState`
- `EnvironmentState`
- `CodeReviewTask`

## Grading Logic

The grader in [`grader.py`](./backend/env/grader.py) is deterministic:

- `1.0` for a full match: the review hits every required keyword group
- `0.5` for a partial match: the review identifies part of the issue, hits partial keywords, or overlaps meaningfully with the reference explanation
- `0.0` for a wrong answer

The `info` dictionary returned by `step()` includes score details such as matched keywords, missing keywords, semantic overlap, and the reference explanation.

## Action and Observation Definitions

Action:

```python
ReviewAction(review="The code is vulnerable to SQL injection...")
```

Observation:

```python
CodeReviewObservation(
    task_id="hard-sql-injection",
    difficulty="hard",
    title="Unsafe user lookup",
    code="...",
    prompt="Review this code and find issues.",
    step_index=0,
)
```

Reward / state:

```python
RewardState(score=1.0, verdict="full_match", ...)
EnvironmentState(task_id="...", step_count=1, done=True, ...)
```

## Quick Start

From the project root:

```bash
python backend/baseline/run_agent.py
```

This runs the baseline across all sample tasks using the built-in mock reviewer.

Run a single task:

```bash
python backend/baseline/run_agent.py --task-id hard-sql-injection
```

Use a custom dataset or allow multiple steps:

```bash
python backend/baseline/run_agent.py --data-path backend/data/samples.json --max-steps 2
```

## Optional OpenAI Integration

The baseline script can use the OpenAI Responses API if the `openai` package is installed and the environment is configured:

```bash
pip install openai
export OPENAI_API_KEY=your_key_here
export OPENAI_MODEL=your_model_here
python backend/baseline/run_agent.py
```

If those values are not available, the script automatically falls back to the mock agent.

The OpenAI client path in the baseline uses the official `OpenAI()` client with `client.responses.create(...)`.

## Website

The project now includes a polished Astro + Svelte frontend in `frontend/` with a professional dark theme, while `backend/` keeps the Python environment, grading API, and baseline agent. Astro builds the UI into static files, and `backend/server.py` serves that built frontend plus the existing `/api/*` routes.

The site lets you:

- browse the bundled tasks
- inspect the current observation/code snippet
- submit your own review text
- see reward details, keyword matches, overlap, and environment state
- run the baseline reviewer directly from the browser

### Run the built website

If the frontend has already been built, start the website from the project root:

```bash
python backend/server.py
```

Then open:

```text
http://127.0.0.1:8000
```

### Build the Astro frontend

When you change anything in `frontend/src`, rebuild the frontend:

```bash
cd frontend
npm install
npm run build
cd ..
```

Then run:

```bash
python backend/server.py
```

### Frontend development mode

For frontend-only iteration with hot reload:

Terminal 1:

```bash
python backend/server.py
```

Terminal 2:

```bash
cd frontend
npm install
npm run dev
```

Open:

```text
http://127.0.0.1:4321
```

The Astro dev server proxies `/api` calls to the Python backend on port `8000`, so the UI still uses the same environment and grading endpoints.

## Minimal Python Example

```python
from backend.env.environment import CodeReviewEnvironment
from backend.env.models import ReviewAction

env = CodeReviewEnvironment()
observation = env.reset(task_id="easy-even-check")
observation, reward, done, info = env.step(
    ReviewAction(review="The modulo condition is reversed; use n % 2 == 0.")
)

print(observation)
print(reward)
print(done)
print(info)
print(env.state())
```

## Docker

Build:

```bash
docker build -t code-review-env .
```

Run:

```bash
docker run --rm code-review-env
```

Run with OpenAI credentials:

```bash
docker run --rm \
  -e OPENAI_API_KEY=$OPENAI_API_KEY \
  -e OPENAI_MODEL=$OPENAI_MODEL \
  code-review-env
```

Run the website in Docker by overriding the default command:

```bash
docker run --rm -p 8000:8000 code-review-env python backend/server.py --host 0.0.0.0 --port 8000
```

## OpenEnv Metadata

[`openenv.yaml`](./openenv.yaml) includes:

- environment name and description
- entrypoint
- action schema
- observation schema
- reward schema

This makes the project easy to inspect and extend in OpenEnv-style tooling while keeping the implementation lightweight and readable.
