import asyncio
import httpx
from wargames.models import TeamSettings

class LLMClient:
    MAX_RETRIES = 3
    RETRY_BACKOFF = 2.0

    def __init__(self, settings: TeamSettings):
        self.settings = settings
        self._http = httpx.AsyncClient(base_url=settings.model, timeout=settings.timeout)

    async def chat(self, messages: list[dict], system: str | None = None) -> str:
        if system:
            messages = [{"role": "system", "content": system}, *messages]
        payload = {
            "model": self.settings.model_name,
            "messages": messages,
            "temperature": self.settings.temperature,
        }
        last_exc = None
        for attempt in range(self.MAX_RETRIES):
            try:
                response = await self._http.post("/chat/completions", json=payload)
                result = response.raise_for_status()
                if hasattr(result, "__await__"):
                    await result
                data = response.json()
                if hasattr(data, "__await__"):
                    data = await data
                return data["choices"][0]["message"]["content"]
            except (httpx.RemoteProtocolError, httpx.ConnectError, httpx.ReadTimeout) as exc:
                last_exc = exc
                if attempt < self.MAX_RETRIES - 1:
                    await asyncio.sleep(self.RETRY_BACKOFF * (attempt + 1))
        raise last_exc

    async def close(self):
        await self._http.aclose()
