"""Quick smoke test for cloud LLM via OpenRouter."""
import asyncio
import os
from wargames.models import TeamSettings
from wargames.llm.client import LLMClient


async def main():
    settings = TeamSettings(
        name="test",
        model="https://openrouter.ai/api/v1",
        model_name="meta-llama/llama-3.3-70b-instruct:free",
        temperature=0.2,
        api_key="$OPENROUTER_API_KEY",
    )
    resolved = settings.api_key and not settings.api_key.startswith("$")
    print(f"API key resolved: {'yes' if resolved else 'NO — set OPENROUTER_API_KEY'}")
    if not resolved:
        return

    client = LLMClient(settings)
    try:
        result = await client.chat([{"role": "user", "content": "Say hello in one word"}])
        print(f"Response: {result[:200]}")
        print("SUCCESS")
    except Exception as e:
        print(f"FAILED: {e}")
    finally:
        await client.close()


if __name__ == "__main__":
    asyncio.run(main())
