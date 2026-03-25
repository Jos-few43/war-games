# OpenCode Integration Plan for War Games

## Overview
Integrate War Games with OpenCode's tool-calling infrastructure to use OpenCode Go tokens for LLM inference.

## Architecture

### Current State
- War Games uses `LLMClient` class that makes HTTP POST requests to OpenAI-compatible endpoints
- Expects responses with `choices[0].message.content` and `usage` fields
- Supports fallback models and retry logic

### OpenCode Integration Approach

Since OpenCode doesn't expose a simple HTTP chat completion API like OpenAI, we need to create an adapter layer:

```
War Games Engine
       |
       v
  OpenCodeAdapter (new)
       |
       v
 OpenCode Tools (ai-tools_ollama_chat, etc.)
       |
       v
   LLM Response
```

## Implementation Plan

### Phase 1: Create OpenCodeProvider Class

**File**: `wargames/llm/opencode_provider.py`

```python
class OpenCodeProvider:
    """Adapter to use OpenCode tools as LLM provider for War Games."""
    
    def __init__(self, model: str = "opencode-go/kimi-k2.5"):
        self.model = model
        self._prompt_tokens = 0
        self._completion_tokens = 0
    
    async def chat(self, messages: list[dict], system: str | None = None) -> str:
        """
        Convert War Games chat format to OpenCode tool call.
        
        Steps:
        1. Concatenate system prompt + messages into single prompt
        2. Call ai-tools_ollama_chat tool
        3. Parse response and extract content
        4. Track token usage (estimate if not provided)
        5. Return content string
        """
        pass
    
    def get_usage(self) -> dict:
        """Return token usage statistics."""
        pass
```

### Phase 2: Integration Points

**Modify**: `wargames/llm/client.py`

Option A: Add OpenCode as a provider type
```python
class LLMClient:
    def __init__(self, settings: TeamSettings):
        if settings.model == "opencode":
            self._provider = OpenCodeProvider(settings.model_name)
        else:
            # Existing HTTP client logic
```

Option B: Create parallel client class
```python
class OpenCodeLLMClient:
    """Drop-in replacement for LLMClient using OpenCode."""
    # Implements same interface as LLMClient
```

### Phase 3: Configuration

**Create**: `config/opencode.toml`

```toml
[teams.red]
model = "opencode"  # Special marker
model_name = "opencode-go/kimi-k2.5"
# No api_key needed - uses OpenCode's built-in auth

[teams.blue]
model = "opencode"
model_name = "opencode-go/qwen-2.5-coder-32b"

[teams.judge]
model = "opencode"
model_name = "opencode-go/kimi-k2.5"
```

### Phase 4: Token Usage Tracking

Challenge: OpenCode tools may not return exact token counts.

**Solutions**:
1. Use `ai-tools_stats_llm_calls` to get token counts after each call
2. Estimate tokens using character count / 4 (rough approximation)
3. Store actual usage from OpenCode's tracking system

### Phase 5: Testing

Create tests in `tests/llm/test_opencode_provider.py`:
- Test message formatting
- Test response parsing
- Test token tracking
- Test error handling

## Technical Challenges

### 1. Async vs Sync
OpenCode tools are called synchronously from the tool context. We need to:
- Either make War Games' LLM calls synchronous (bad for performance)
- Or wrap OpenCode tool calls in asyncio.to_thread() or similar

### 2. Response Format
OpenCode returns plain text, not structured JSON with usage stats.
We'll need to:
- Estimate token counts
- Or query OpenCode stats after each call

### 3. Tool Availability
OpenCode tools must be available in the execution context.
This means:
- The game must run within an OpenCode session
- Cannot run standalone like with OpenRouter

## Recommended Approach

**Hybrid Solution**:

1. **Keep OpenRouter as default** for standalone operation
2. **Add OpenCodeProvider** as experimental feature
3. **Detect runtime environment**:
   ```python
   if running_in_opencode():
       use OpenCodeProvider
   else:
       use LLMClient  # HTTP-based
   ```

## Implementation Priority

1. ✅ OpenRouter config (DONE)
2. Create OpenCodeProvider prototype (2-3 hours)
3. Test with single round (1 hour)
4. Add configuration support (1 hour)
5. Document usage (30 min)

## Cost Comparison

| Provider | Model | Input Cost | Output Cost | Notes |
|----------|-------|------------|-------------|-------|
| OpenRouter | gpt-4o-mini | $0.15/1M | $0.60/1M | Pay per use |
| OpenRouter | gemini-flash | $0.075/1M | $0.30/1M | Very cheap |
| OpenRouter | claude-haiku | $0.25/1M | $1.25/1M | Good judge |
| OpenCode | kimi-k2.5 | **FREE** | **FREE** | Uses existing tokens |
| OpenCode | qwen-2.5-coder | **FREE** | **FREE** | Uses existing tokens |

**Estimated savings**: $5-20 per full season (10 rounds × 6 turns × 3 models)

## Next Steps

To implement this:

1. Create `wargames/llm/opencode_provider.py` with basic chat functionality
2. Test in current OpenCode session with a single round
3. If successful, integrate into `LLMClient` as alternative provider
4. Add `config/opencode.toml` for easy switching

Ready to proceed with implementation when you give the go-ahead!
