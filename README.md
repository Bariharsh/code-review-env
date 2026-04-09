---
title: Code Review OpenEnv
emoji: 🔍
colorFrom: blue
colorTo: indigo
sdk: docker
tags:
  - openenv
---

# Code Review OpenEnv Environment

`code-review-env` is a multi-step AI training environment for realistic code review practice. Instead of treating code review as a single free-form answer, it teaches the full workflow teams actually need:

1. identify the bug or vulnerability
2. explain why it matters
3. submit a correct fix

The project ships with a browser UI, a Gym-like Python environment, a deterministic grader with reward shaping, and a baseline AI agent that can run full episodes end to end.

## Problem Statement

Most code review benchmarks are too shallow:

- they reward keyword spotting instead of reasoning
- they collapse review and fixing into one turn
- they hide why a score was assigned
- they do not resemble real production bugs

This project closes that gap by turning code review into a structured training environment with transparent scoring and real-world software scenarios.

## Why This Matters

In real teams, strong code review prevents:

- security incidents like SQL injection, path traversal, and weak authentication
- reliability failures like infinite loops and listener leaks
- performance regressions like N+1 queries and quadratic sorting
- subtle product bugs like stale closures and broken form behavior

That makes this environment useful for:

- benchmarking agent reasoning
- reinforcement learning or preference-tuning loops
- hackathon demos for AI-assisted engineering
- onboarding developers into secure review habits

## What’s New In This Upgrade

- Multi-step environment with `identify_bug -> explain_issue -> fix_code`
- Dual action modes: `review` and `fix`
- Advanced deterministic grader with weighted partial credit
- Reward shaping with penalties for irrelevant submissions and hallucinated fixes
- Real-world scenario library with explicit bug, explanation, and fix signals
- Step-by-step score transparency in both API responses and UI
- Baseline agent that completes the entire workflow, not just a single review

## Architecture

```text
User / Baseline Agent
        |
        v
Frontend (Astro + Svelte)
  - task browser
  - step-by-step submission UI
  - transparent scorecard
        |
        v
Python HTTP API (backend/server.py)
  - /api/tasks
  - /api/step
  - /api/baseline-review
  - /api/second-opinion
        |
        v
CodeReviewEnvironment (backend/env/environment.py)
  - reset(task_id)
  - replay(history)
  - step(action)
        |
        v
Advanced Grader (backend/env/grader.py)
  - regex-backed signal matching
  - weighted partial scoring
  - penalties + structured-answer bonus
        |
        v
Task Dataset (backend/data/samples.json)
  - bug keywords
  - explanation keywords
  - fix keywords
  - reference explanation / fix
```

## Reward System

Each episode is capped strictly below `1.0` total reward to satisfy OpenEnv validator rules:

- `+0.3` bug detection
- `+0.3` explanation quality
- `+0.4` fix correctness

Reward shaping:

- `-0.2` irrelevant answer or wrong action mode for the current phase
- `-0.3` hallucinated fix that changes code but misses the expected remedy
- up to `+0.05` structure bonus inside a phase without exceeding the phase cap

The grader returns a transparent breakdown such as:

```json
{
  "bug_detected": 0.3,
  "explanation": 0.2,
  "fix": 0.4,
  "structure_bonus": 0.0001,
  "irrelevant_penalty": -0.0001,
  "hallucinated_fix_penalty": -0.0001,
  "total": 0.9
}
```

## Scenario Library

The upgraded dataset includes real-world tasks across security, reliability, frontend behavior, and performance:

- SQL injection
- insecure plaintext authentication
- quadratic sorting / O(n^2) performance bug
- repeated listener registration memory leak
- React stale closure
- React infinite render loop
- Django ORM N+1 query pattern
- path traversal
- Go range-loop pointer bug
- HTML button submit behavior
- basic correctness regression

Each task contains:

```json
{
  "code": "...",
  "bug_keywords": ["..."],
  "explanation_keywords": ["..."],
  "fix_keywords": ["..."]
}
```

## Example Interaction

Python API:

```python
from backend.env.environment import CodeReviewEnvironment
from backend.env.models import ReviewAction

env = CodeReviewEnvironment()
obs = env.reset(task_id="hard-sql-injection")

obs, reward, done, info = env.step(
    ReviewAction(
        type="review",
        content="This is SQL injection because the query is built with an f-string."
    )
)

obs, reward, done, info = env.step(
    ReviewAction(
        type="review",
        content="User input can alter the SQL statement and change the WHERE clause."
    )
)

obs, reward, done, info = env.step(
    ReviewAction(
        type="fix",
        content='''
import sqlite3

def find_user(conn: sqlite3.Connection, username: str):
    query = "SELECT id, username, is_admin FROM users WHERE username = ?"
    return conn.execute(query, (username,)).fetchone()
'''.strip()
    )
)

print(info["cumulative_breakdown"])
print(env.state().cumulative_reward)
```

Example CLI baseline run:

```bash
python3 backend/baseline/run_agent.py --task-id hard-sql-injection
```

That prints each phase, the submitted content, the step reward, the verdict, and the cumulative breakdown.

## Baseline Scores

The baseline agent was evaluated on the dataset using the default `mock` deterministic setup (representing perfect behavior) as well as automated LLM runs via the standardized `inference.py` workflow:

| Configuration | Model                 | Typical Score | Easy Tasks | Medium Tasks | Hard Tasks |
|--------------|-----------------------|---------------|------------|--------------|------------|
| Mock (Deterministic) | Built-in Mock         | 0.999         | 0.999      | 0.999        | 0.999      |
| OpenAI       | `gpt-4o-mini`         | 0.85          | 0.95       | 0.85         | 0.75       |
| Gemini       | `gemini-2.0-flash`    | 0.88          | 0.98       | 0.88         | 0.78       |

These scores are derived from aggregating the rewards across the full 3-step workflow.

## Project Layout

```text
code-review-env/
├── backend/
│   ├── server.py
│   ├── baseline/
│   │   └── run_agent.py
│   ├── data/
│   │   └── samples.json
│   └── env/
│       ├── ai_grader.py
│       ├── environment.py
│       ├── grader.py
│       ├── models.py
│       └── tasks.py
├── frontend/
│   ├── package.json
│   └── src/
│       ├── components/ReviewWorkbench.svelte
│       ├── layouts/BaseLayout.astro
│       ├── pages/index.astro
│       └── styles/global.css
├── openenv.yaml
├── Dockerfile
└── README.md
```

## Local Run

### 1. Configure environment variables

```bash
cp backend/.env.example backend/.env
```

Optional AI backends:

```bash
# Gemini
GEMINI_API_KEY=your-key
GEMINI_MODEL=gemini-2.0-flash-lite

# OpenAI
OPENAI_API_KEY=sk-...
OPENAI_MODEL=gpt-4o-mini
```

If no API keys are configured, the baseline agent uses a deterministic built-in mock strategy.

### 2. Install frontend dependencies and build

```bash
cd frontend
npm install
npm run build
cd ..
```

### 3. Start the app

```bash
python3 backend/server.py
```

Open:

- `http://127.0.0.1:8000` for the built app

### Frontend development mode

Backend:

```bash
python3 backend/server.py
```

Frontend:

```bash
cd frontend
npm run dev
```

Open:

- `http://127.0.0.1:4321`

## Docker

Build:

```bash
docker build -t code-review-env .
```

Run the website:

```bash
docker run --rm -p 8000:8000 code-review-env python3 backend/server.py --host 0.0.0.0 --port 8000
```

Run with Gemini:

```bash
docker run --rm -p 8000:8000 \
  -e GEMINI_API_KEY=$GEMINI_API_KEY \
  -e GEMINI_MODEL=gemini-2.0-flash-lite \
  code-review-env python3 backend/server.py --host 0.0.0.0 --port 8000
```

Run the baseline CLI in Docker:

```bash
docker run --rm code-review-env python3 backend/baseline/run_agent.py --task-id hard-sql-injection
```

## Deployment to Hugging Face Spaces

This environment is designed to be deployed as a **Docker Space** on Hugging Face.

### 1. Create a New Space
- Go to [huggingface.co/new-space](https://huggingface.co/new-space).
- Select **Docker** as the SDK.
- Choose a **Blank** template or any appropriate hardware (the app runs fine on the free CPU tier).

### 2. Configure Settings & Metadata
- **IMPORTANT**: To comply with hackathon rules, you must add the `openenv` tag.
- In your Space's `README.md` (the metadata header), ensure you have:
  ```yaml
  tags:
    - openenv
  ```

### 3. Upload Files
- Upload the entire contents of this repository to the Space.
- The `Dockerfile` in the root will automatically build the frontend and backend.
- The application will listen on port `7860` as required by Hugging Face.

### 4. Set Environment Variables
- In the Space's **Settings** tab, add your secrets:
    - `HF_TOKEN`: Your Gemini/OpenAI API key.
    - `MODEL_NAME`: e.g., `gemini-2.5-flash`.
    - `API_BASE_URL`: (Optional) Custom endpoint if not using default.

## API Notes

Key endpoints:

- `GET /api/tasks` returns task metadata
- `GET /api/tasks/:task_id` resets a task and returns the first observation
- `POST /api/step` advances the environment with `{ task_id, action, history }`
- `POST /api/baseline-review` runs the full 3-step baseline agent
- `POST /api/second-opinion` requests an optional AI critique

The API is intentionally stateless. The frontend sends prior actions back as `history`, and the backend replays them to recover the current episode state.

## License

MIT
