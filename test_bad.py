import asyncio
from backend.env.environment import CodeReviewEnvironment
from backend.env.models import ReviewAction

env = CodeReviewEnvironment()

for task_id in env.task_ids():
    env.reset(task_id=task_id)
    # Simulate completely bad actions
    action1 = ReviewAction(type="review", content="Completely wrong and irrelevant.")
    _, rew1, _, _ = env.step(action1)
    
    action2 = ReviewAction(type="review", content="Completely wrong and irrelevant.")
    _, rew2, _, _ = env.step(action2)
    
    action3 = ReviewAction(type="fix", content="Completely wrong and irrelevant.")
    _, rew3, _, _ = env.step(action3)
    
    print(f"  [{task_id}] rewards: {rew1}, {rew2}, {rew3}. total: {env.state().cumulative_reward}")
    if env.state().cumulative_reward <= 0.0 or env.state().cumulative_reward >= 1.0:
        print("  !!! OUT OF BOUNDS !!!")

