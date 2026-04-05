import asyncio
import os
import json
from typing import List, Optional

from openai import AsyncOpenAI
from backend.env.environment import CodeReviewEnvironment
from backend.env.models import ReviewAction, CodeReviewObservation, StepRecord

from dotenv import load_dotenv
load_dotenv()

API_BASE_URL = os.getenv("API_BASE_URL")
MODEL_NAME = os.getenv("MODEL_NAME", "gpt-4o-mini") 
HF_TOKEN = os.getenv("HF_TOKEN")

BENCHMARK = "code-review-env"

def log_start(task: str, env: str, model: str):
    log_data = {"task": task, "env": env, "model": model}
    print(f"[START] {json.dumps(log_data)}", flush=True)

def log_step(step: int, action: str, reward: float, done: bool, error: Optional[str] = None):
    log_data = {
        "step": step,
        "action": action,
        "reward": reward,
        "done": done,
        "error": error
    }
    print(f"[STEP] {json.dumps(log_data)}", flush=True)

def log_end(success: bool, steps: int, score: float, rewards: List[float]):
    log_data = {
        "success": success,
        "steps": steps,
        "score": score,
        "rewards": rewards
    }
    print(f"[END] {json.dumps(log_data)}", flush=True)

def build_prompt(observation: CodeReviewObservation, history: List[StepRecord]) -> str:
    prior_steps = "\n".join(
        f"- Phase: {record.phase}\n  Action type: {record.action.type}\n  Content: {record.action.content}\n  Reward: {record.reward.score}"
        for record in history
    )
    history_block = prior_steps if prior_steps else "- None yet."

    phase = observation.phase
    if phase == "identify_bug":
        instruction = "Goal: Name the core bug, security issue, or faulty behavior. Be specific about the root cause and line number if possible. Focus on what is broken."
    elif phase == "explain_issue":
        instruction = "Goal: Explain why this bug matters. Focus on system impact (e.g., 'This allows SQL injection' or 'This causes an O(N^2) complexity'). Describe the blast radius."
    elif phase == "fix_code":
        instruction = "Goal: Provide the corrected code. It MUST be a complete, runnable replacement. Do not add markdown backticks if possible, just the raw code code snippet."
    else:
        instruction = observation.prompt

    response_style = (
        "Return corrected code ONLY. No prose."
        if observation.expected_action_type == "fix"
        else "Return exactly 1-2 concise, highly technical sentences. No fluff, no 'Sure!', no 'Here is the review'."
    )

    return (
        "You are an elite software auditor acting inside a 3-step OpenEnv training benchmark. Accuracy and conciseness are paramount.\n\n"
        f"SCENARIO TITLE: {observation.title}\n"
        f"DIFFICULTY: {observation.difficulty}\n"
        f"CURRENT PHASE: {phase}\n"
        f"SPECIFIC INSTRUCTION: {instruction}\n"
        f"EXPECTED ACTION TYPE: {observation.expected_action_type}\n\n"
        "CODE TO AUDIT:\n"
        "```\n"
        f"{observation.code}\n"
        "```\n\n"
        f"PRIOR STEPS (for context):\n{history_block}\n\n"
        "--- MANDATORY CONSTRAINT ---\n"
        f"{response_style}\n"
        "Do not mention phase names. Avoid conversational filler."
    )

async def get_model_message(client: AsyncOpenAI, observation: CodeReviewObservation, history: List[StepRecord]) -> str:
    user_prompt = build_prompt(observation, history)
    SYSTEM_PROMPT = (
        "You are a robotic technical auditor. You provide high-density, precise feedback on code vulnerabilities and performance. "
        "You never use conversational filler. You follow instructions to the letter."
    )
    
    try:
        response = await client.chat.completions.create(
            model=MODEL_NAME,
            messages=[
                {"role": "system", "content": SYSTEM_PROMPT},
                {"role": "user", "content": user_prompt}
            ],
            temperature=0.0
        )
        text = response.choices[0].message.content.strip() if response.choices[0].message.content else ""
        
        # Strip markdown code blocks if the model included them in a "fix" action
        if observation.expected_action_type == "fix":
            if text.startswith("```"):
                lines = text.splitlines()
                if lines[0].startswith("```"):
                    lines = lines[1:]
                if lines and lines[-1].startswith("```"):
                    lines = lines[:-1]
                text = "\n".join(lines).strip()
        
        return text if text else "Bug found."
    except Exception as exc:
        print(f"[DEBUG] Model request failed: {exc}", flush=True)
        return "Bug found."

async def main():
    if not HF_TOKEN:
        print("HF_TOKEN (API Key) is missing from environment variables.")
        return

    # Initialize OpenAI client
    # Note: api_key is required. base_url is optional but used by hackathon if provided.
    client = AsyncOpenAI(
        api_key=HF_TOKEN,
        base_url=API_BASE_URL if API_BASE_URL else None
    )
    
    env = CodeReviewEnvironment()
    
    # Iterate over all tasks
    for task_id in env.task_ids():
        rewards: List[float] = []
        steps_taken = 0
        score = 0.0
        success = False

        log_start(task=task_id, env=BENCHMARK, model=MODEL_NAME)
        
        try:
            observation = env.reset(task_id=task_id)
            done = False
            step = 1

            while not done:
                error = None
                try:
                    action_content = await get_model_message(client, observation, env.state().history)
                    action = ReviewAction(type=observation.expected_action_type, content=action_content)
                    
                    next_obs, reward, done, info = env.step(action)
                    
                    rewards.append(reward)
                    steps_taken = step
                    
                    log_step(step=step, action=action_content, reward=reward, done=done, error=error)
                    
                    observation = next_obs
                    step += 1
                except Exception as e:
                    error = str(e)
                    log_step(step=step, action="", reward=0.0, done=True, error=error)
                    break
            
            score = env.state().cumulative_reward
            score = min(max(score, 0.0), 1.0)  # clamp to [0, 1]
            success = score >= 0.7  # Define success threshold

        finally:
            log_end(success=success, steps=steps_taken, score=score, rewards=rewards)

if __name__ == "__main__":
    asyncio.run(main())
