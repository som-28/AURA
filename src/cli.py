"""Simple CLI runner for the agent (demo)."""
from src.agent.planner import Planner
from src.agent.controller import Controller
from src.utils.config import load_config
import asyncio


async def main():
    cfg = load_config()
    planner = Planner(cfg)
    controller = Controller(cfg)

    print("Personal Task Automation Agent (CLI)")
    cmd = input("Enter task: ")
    email = input("Optional email to send results to (leave blank to skip): ") or None
    plan = planner.plan(cmd, target_email=email)
    print("Planned steps:")
    for s in plan["steps"]:
        print(f" - {s}")
    logs = await controller.execute_plan(plan)
    print("\nExecution logs:")
    for line in logs:
        print(line)


if __name__ == "__main__":
    asyncio.run(main())
