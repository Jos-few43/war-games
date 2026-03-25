"""OpenCode LLM provider for War Games.

This provider uses OpenCode's built-in LLM tools (ai-tools_ollama_chat, etc.)
to enable LLM inference without external API keys, using existing OpenCode tokens.
"""

import asyncio
import json
from typing import Any, Dict, List

from wargames.models import TeamSettings


class OpenCodeProvider:
    """OpenCode LLM provider that uses built-in tools for inference.

    This provider allows War Games to run using OpenCode's internal
    LLM capabilities instead of external API calls.
    """

    def __init__(self, model: str = 'opencode-go/kimi-k2.5'):
        """Initialize the OpenCode provider.

        Args:
            model: The model identifier to use (informational only,
                  actual model selection happens via OpenCode configuration)
        """
        self.model = model
        self._prompt_tokens = 0
        self._completion_tokens = 0
        self._last_model_used = model

    async def _call_opencode_tool(
        self, tool_name: str, arguments: Dict[str, Any]
    ) -> Dict[str, Any]:
        """Call an OpenCode tool and return the result.

        This is a placeholder implementation. In practice, this would
        use the OpenCode tool-calling mechanism available in the runtime.
        """
        # This implementation assumes we're running in an OpenCode session
        # where we can directly call tools. In practice, this would need
        # to be adapted based on how OpenCode exposes its tools to subprocesses.

        # For now, we'll raise NotImplementedError to indicate this needs
        # to be implemented based on the specific OpenCode integration approach
        raise NotImplementedError(
            'OpenCode tool calling not implemented. '
            'This provider requires running within an OpenCode session '
            'with appropriate tool access.'
        )

    async def chat(self, messages: List[Dict[str, str]], system: str | None = None) -> str:
        """Generate a chat completion using OpenCode tools.

        Args:
            messages: List of message dicts with 'role' and 'content' keys
            system: Optional system prompt

        Returns:
            The generated text response
        """
        # Prepare the full prompt
        full_prompt = ''
        if system:
            full_prompt += f'System: {system}\n\n'

        for message in messages:
            role = message.get('role', 'user')
            content = message.get('content', '')
            full_prompt += f'{role.capitalize()}: {content}\n'

        full_prompt += 'Assistant:'

        # In a real implementation, we would call OpenCode's LLM tool here
        # For example:
        # result = await self._call_opencode_tool(
        #     "ai-tools_ollama_chat",
        #     {
        #         "model": self.model,
        #         "prompt": full_prompt,
        #         "temperature": 0.7,  # Would come from settings
        #     }
        # )
        # response = result.get("response", "")

        # For now, we'll return a placeholder to indicate this needs implementation
        return f'[OpenCodeProvider placeholder response for: {full_prompt[:50]}...]'

    def get_usage(self, reset: bool = False) -> Dict[str, Any]:
        """Get token usage statistics.

        Args:
            reset: Whether to reset the counters after reading

        Returns:
            Dictionary with prompt_tokens, completion_tokens, and model_used
        """
        usage = {
            'prompt_tokens': self._prompt_tokens,
            'completion_tokens': self._completion_tokens,
            'model_used': self._last_model_used,
        }

        if reset:
            self._prompt_tokens = 0
            self._completion_tokens = 0

        return usage
