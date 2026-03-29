# Code Review Environment

`code-review-env` is an AI-powered code review training platform built with Python, Astro, and Svelte. Each scenario presents buggy code, expects a natural-language review from the user (or an AI agent), and returns a deterministic reward based on how well the review identifies the issue and fix.

The environment follows a Gym-like interface:

- `reset()` selects a task and returns the initial observation.
- `step(action)` grades the review and returns `(observation, reward, done, info)`.
- `state()` returns the typed internal environment state.

## Features

- **10 Real-World Scenarios** — Python bugs, SQL injection, React stale closures, Go pointer leaks, Django N+1 queries, path traversal vulnerabilities, and more
- **AI-Powered Baseline Reviewer** — Integrated with **Google Gemini API** (free tier) for real-time AI code reviews
- **Deterministic Grading** — Keyword-based + semantic overlap scoring (0.0 / 0.5 / 1.0)
- **Gamified Session Tracking** — Live score, accuracy, solved count, and confetti on perfect reviews
- **Premium Dark UI** — Modern SaaS-style workspace built with Astro + Svelte

## Project Layout

```text
code-review-env/
├── backend/
│   ├── server.py              # Python HTTP server (API + static files)
│   ├── .env.example           # Environment variable template
│   ├── env/
│   │   ├── environment.py     # Gym-like environment
│   │   ├── grader.py          # Deterministic grading logic
│   │   ├── models.py          # Typed dataclass models
│   │   └── tasks.py           # Task loader
│   ├── baseline/
│   │   └── run_agent.py       # AI baseline reviewer (Gemini / OpenAI / mock)
│   └── data/
│       └── samples.json       # 10 coding scenarios
├── frontend/
│   ├── package.json
│   ├── astro.config.mjs
│   └── src/
│       ├── components/        # ReviewWorkbench.svelte
│       ├── layouts/           # BaseLayout.astro
│       ├── pages/             # index.astro
│       └── styles/            # global.css
├── openenv.yaml
├── Dockerfile
└── README.md
```

## Quick Start

### 1. Set up the backend

```bash
# Copy the environment template and add your API key
cp backend/.env.example backend/.env
# Edit backend/.env and add your Gemini API key
```

Get a free Gemini API key from: https://aistudio.google.com/apikey

### 2. Build the frontend

```bash
cd frontend
npm install
npm run build
cd ..
```

### 3. Start the server

```bash
python backend/server.py
```

Open http://127.0.0.1:8000

## AI Integration

The baseline reviewer supports multiple AI backends with automatic fallback:

| Priority | Backend | Environment Variables | Cost |
|----------|---------|----------------------|------|
| 1st | **Google Gemini** | `GEMINI_API_KEY` | **Free tier available** |
| 2nd | OpenAI | `OPENAI_API_KEY` + `OPENAI_MODEL` | Paid |
| 3rd | Mock | (none needed) | Free |

### Gemini Setup (Recommended — Free)

```bash
# backend/.env
GEMINI_API_KEY=your-key-from-aistudio
GEMINI_MODEL=gemini-2.0-flash-lite
```

### OpenAI Setup (Optional — Paid)

```bash
# backend/.env
OPENAI_API_KEY=sk-your-key
OPENAI_MODEL=gpt-4o-mini
```

If no API keys are configured, the baseline automatically uses a built-in mock reviewer that returns pattern-matched responses.

## Grading Logic

The grader in [`grader.py`](./backend/env/grader.py) is deterministic:

- **`1.0` (Full Match)** — the review hits every required keyword group
- **`0.5` (Partial Match)** — the review identifies part of the issue or overlaps meaningfully with the reference
- **`0.0` (Miss)** — the review does not identify the core issue

The `info` dictionary includes matched keywords, missing keywords, semantic overlap, and the reference explanation.

## Scenarios

| Difficulty | Title | Language |
|-----------|-------|----------|
| Easy | Broken even-number check | Python |
| Easy | Type-coercion equality bug | JavaScript |
| Easy | Default submit behavior | HTML |
| Medium | Top scores logic bug | Python |
| Medium | React stale closure interval | React/JSX |
| Medium | Django ORM N+1 queries | Python/Django |
| Hard | Unsafe user lookup (SQL injection) | Python/SQL |
| Hard | Go loop variable pointer leak | Go |
| Hard | Path Traversal vulnerability | Python/FastAPI |
| Hard | React layout infinite loop | React/JSX |

## Frontend Development

For hot-reload during frontend development:

**Terminal 1** — Backend:
```bash
python backend/server.py
```

**Terminal 2** — Frontend dev server:
```bash
cd frontend
npm install
npm run dev
```

Open http://127.0.0.1:4321 — the Astro dev server proxies `/api` calls to the Python backend.

## CLI Usage

Run the baseline reviewer from the command line:

```bash
# Run all tasks
python backend/baseline/run_agent.py

# Run a single task
python backend/baseline/run_agent.py --task-id hard-sql-injection

# Custom dataset with multiple steps
python backend/baseline/run_agent.py --data-path backend/data/samples.json --max-steps 2
```

## Python API Example

```python
from backend.env.environment import CodeReviewEnvironment
from backend.env.models import ReviewAction

env = CodeReviewEnvironment()
observation = env.reset(task_id="easy-even-check")
observation, reward, done, info = env.step(
    ReviewAction(review="The modulo condition is reversed; use n % 2 == 0.")
)

print(f"Reward: {reward}")  # 1.0
print(f"Verdict: {info['score_details']['verdict']}")  # full_match
```

## Docker

```bash
# Build
docker build -t code-review-env .

# Run CLI
docker run --rm code-review-env

# Run with Gemini
docker run --rm \
  -e GEMINI_API_KEY=$GEMINI_API_KEY \
  code-review-env

# Run website
docker run --rm -p 8000:8000 \
  -e GEMINI_API_KEY=$GEMINI_API_KEY \
  code-review-env python backend/server.py --host 0.0.0.0 --port 8000
```

## License

MIT
