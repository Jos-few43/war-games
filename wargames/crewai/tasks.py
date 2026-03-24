"""
War Games - CrewAI Integration

This module provides task definitions and delegation patterns for CrewAI integration.
Phase 1 focuses on basic maintenance tasks: test fixes, lint corrections, and simple refactors.

Usage:
    from crewai import Task
    from wargames.crewai.tasks import create_task

    task = create_task("fix_test_failure", context={"error": "..."})
"""

from dataclasses import dataclass, field
from enum import Enum
from typing import Any


class TaskType(str, Enum):
    """Available task types for CrewAI delegation."""

    FIX_TEST_FAILURE = "fix_test_failure"
    LINT_FIXES = "lint_fixes"
    UPDATE_DOCS = "update_docs"
    SIMPLE_REFACTOR = "simple_refactor"
    TYPING_FIXES = "typing_fixes"


@dataclass
class TaskDefinition:
    """Definition of a delegatable task."""

    name: str
    description: str
    agent_type: str
    tools: list[str]
    max_retries: int = 3
    timeout_seconds: int = 300
    context: dict[str, Any] = field(default_factory=dict)


# Task definitions registry
TASK_REGISTRY: dict[TaskType, TaskDefinition] = {
    TaskType.FIX_TEST_FAILURE: TaskDefinition(
        name="fix_test_failure",
        description="Auto-fix failing tests by analyzing error and applying corrections",
        agent_type="maintenance",
        tools=["read", "edit", "bash", "grep"],
        max_retries=2,
        timeout_seconds=300,
    ),
    TaskType.LINT_FIXES: TaskDefinition(
        name="lint_fixes",
        description="Fix lint errors and apply code style corrections using ruff",
        agent_type="maintenance",
        tools=["read", "edit", "bash"],
        max_retries=2,
        timeout_seconds=180,
    ),
    TaskType.UPDATE_DOCS: TaskDefinition(
        name="update_docs",
        description="Update documentation for changed code, docstrings, and README",
        agent_type="documentation",
        tools=["read", "write"],
        max_retries=1,
        timeout_seconds=300,
    ),
    TaskType.SIMPLE_REFACTOR: TaskDefinition(
        name="simple_refactor",
        description="Perform simple refactoring: extract methods, rename variables, improve structure",
        agent_type="refactor",
        tools=["read", "edit", "lsp_rename"],
        max_retries=2,
        timeout_seconds=600,
    ),
    TaskType.TYPING_FIXES: TaskDefinition(
        name="typing_fixes",
        description="Fix type annotation errors reported by mypy",
        agent_type="maintenance",
        tools=["read", "edit", "lsp"],
        max_retries=2,
        timeout_seconds=180,
    ),
}


def create_task(
    task_type: TaskType,
    context: dict[str, Any] | None = None,
) -> TaskDefinition:
    """
    Create a task definition for CrewAI execution.

    Args:
        task_type: The type of task to create
        context: Additional context for the task

    Returns:
        TaskDefinition ready for CrewAI execution

    Example:
        >>> task = create_task(TaskType.FIX_TEST_FAILURE, {"error": "NameError: undefined name 'x'"})
        >>> print(task.description)
        Auto-fix failing tests by analyzing error and applying corrections
    """
    definition = TASK_REGISTRY[task_type]
    if context:
        definition.context.update(context)
    return definition


def list_available_tasks() -> list[str]:
    """List all available task names."""
    return [task.name for task in TASK_REGISTRY.values()]


def get_task_definition(task_name: str) -> TaskDefinition | None:
    """Get task definition by name."""
    for task in TASK_REGISTRY.values():
        if task.name == task_name:
            return task
    return None
