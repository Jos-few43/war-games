"""CrewAI integration for War Games."""

from wargames.crewai.tasks import (
    TaskType,
    TaskDefinition,
    create_task,
    list_available_tasks,
    get_task_definition,
)

__all__ = [
    "TaskType",
    "TaskDefinition",
    "create_task",
    "list_available_tasks",
    "get_task_definition",
]
