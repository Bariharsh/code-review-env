import asyncio
from backend.env.environment import CodeReviewEnvironment
from backend.env.models import ReviewAction

env = CodeReviewEnvironment()
print("Initialized ENV.")

for task_id in env.task_ids():
    env.reset(task_id=task_id)
    print(f"Testing task: {task_id}")
    # Simulate a perfect string of actions
    task = env.current_task
    
    # 1. Identify bug
    action1 = ReviewAction(type="review", content=" ".join(task.rubric.bug_keywords))
    _, rew1, _, _ = env.step(action1)
    
    # 2. Explain issue
    action2 = ReviewAction(type="review", content=" ".join(task.rubric.explanation_keywords))
    _, rew2, _, _ = env.step(action2)
    
    # 3. Fix code
    # try putting the literal fix if present
    content = task.rubric.reference_fix if task.rubric.reference_fix else " ".join(task.rubric.fix_keywords)
    action3 = ReviewAction(type="fix", content=content)
    _, rew3, _, _ = env.step(action3)
    
    print(f"  [{task_id}] rewards: {rew1}, {rew2}, {rew3}. total: {env.state().cumulative_reward}")
    if env.state().cumulative_reward <= 0.0 or env.state().cumulative_reward >= 1.0:
        print("  !!! OUT OF BOUNDS !!!")

