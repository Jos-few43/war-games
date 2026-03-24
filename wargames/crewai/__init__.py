"""CrewAI integration for War Games."""

from wargames.crewai.tasks import (
    TaskDefinition,
    TaskType,
    create_task,
    get_task_definition,
    list_available_tasks,
)

__all__ = [
    "TaskType",
    "TaskDefinition",
    "create_task",
    "list_available_tasks",
    "get_task_definition",
]
