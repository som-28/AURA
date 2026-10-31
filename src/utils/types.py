from typing import TypedDict, Any, List


class Step(TypedDict):
    id: int
    tool: str
    args: dict


class Plan(TypedDict):
    input: str
    steps: List[Step]
