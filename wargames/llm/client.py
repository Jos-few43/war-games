import httpx
from wargames.models import TeamSettings

class LLMClient:
    def __init__(self, settings: TeamSettings):
        self.settings = settings
        self._http = httpx.AsyncClient(base_url=settings.model, timeout=120.0)

    async def chat(self, messages: list[dict], system: str | None = None) -> str:
        if system:
            messages = [{"role": "system", "content": system}, *messages]
        response = await self._http.post(
            "/chat/completions",
            json={
                "model": self.settings.model_name,
                "messages": messages,
                "temperature": self.settings.temperature,
            },
        )
        result = response.raise_for_status()
        if hasattr(result, "__await__"):
            await result
        data = response.json()
        if hasattr(data, "__await__"):
            data = await data
        return data["choices"][0]["message"]["content"]

    async def close(self):
        await self._http.aclose()
