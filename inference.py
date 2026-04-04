import asyncio
import os
import json
from typing import List, Optional

try:
    from google import genai
except ImportError:
    genai = None

from backend.env.environment import CodeReviewEnvironment
from backend.env.models import ReviewAction, CodeReviewObservation, StepRecord

from dotenv import load_dotenv
load_dotenv()

API_BASE_URL = os.getenv("API_BASE_URL", "") # Unused by Gemini natively, kept for hackathon spec
MODEL_NAME = os.getenv("MODEL_NAME", "gemini-2.5-flash") # Use Gemini by default!
HF_TOKEN = os.getenv("HF_TOKEN") # Uses this as Gemini key instead

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

    response_style = (
        "Return corrected code only."
        if observation.expected_action_type == "fix"
        else "Return 1-3 concise sentences focused only on this step."
    )

    return (
        "You are a senior code reviewer acting inside a 3-step training environment.\n"
        f"Current phase: {observation.phase}\n"
        f"Instruction: {observation.prompt}\n"
        f"Expected action type: {observation.expected_action_type}\n"
        f"Code:\n{observation.code}\n\n"
        f"Prior steps:\n{history_block}\n\n"
        f"{response_style}\n"
        "Do not mention the phase names in your answer."
    )

def get_model_message(client, observation: CodeReviewObservation, history: List[StepRecord]) -> str:
    if client is None:
        raise ValueError("GenAI client is missing, cannot generate message")

    user_prompt = build_prompt(observation, history)
    
    SYSTEM_PROMPT = "You are a code review agent."
    
    try:
        response = client.models.generate_content(
            model=MODEL_NAME,
            contents=os.linesep.join([SYSTEM_PROMPT, user_prompt])
        )
        text = response.text.strip() if response.text else "hello"
        return text if text else "hello"
    except Exception as exc:
        print(f"[DEBUG] Model request failed: {exc}", flush=True)
        return "hello"


def main():
    if genai is None:
        print("To run inference, you must install google-genai (e.g. pip install google-genai)")
        return
        
    client = genai.Client(api_key=HF_TOKEN)
    env = CodeReviewEnvironment()
    
    # Iterate over all tasks
    for task_id in env.task_ids():
        history: List[str] = []
        rewards: List[float] = []
        steps_taken = 0
        score = 0.0
        success = False

        log_start(task=task_id, env=BENCHMARK, model=MODEL_NAME)
        
        try:
            observation = env.reset(task_id=task_id)
            done = False
            error = None
            step = 1

            while not done:
                try:
                    action_content = get_model_message(client, observation, env.state().history)
                    action = ReviewAction(type=observation.expected_action_type, content=action_content)
                    
                    next_obs, reward, done, info = env.step(action)
                    
                    rewards.append(reward)
                    steps_taken = step
                    
                    log_step(step=step, action=action_content, reward=reward, done=done, error=error)
                    
                    history.append(f"Step {step}: {action_content!r} -> reward {reward:+.2f}")
                    
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
    main()
