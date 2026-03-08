import asyncio
import logging
import httpx
from wargames.models import TeamSettings

logger = logging.getLogger(__name__)

# HTTP status codes that are safe to retry
RETRYABLE_STATUS = {429, 500, 502, 503, 504}


class LLMClient:
    MAX_RETRIES = 5
    RETRY_BACKOFF = 2.0

    def __init__(self, settings: TeamSettings):
        self.settings = settings
        headers = {}
        if settings.api_key:
            headers["Authorization"] = f"Bearer {settings.api_key}"
        self._http = httpx.AsyncClient(
            base_url=settings.model, timeout=settings.timeout, headers=headers,
        )

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
                response.raise_for_status()
                data = response.json()
                return data["choices"][0]["message"]["content"]
            except httpx.HTTPStatusError as exc:
                last_exc = exc
                if exc.response.status_code not in RETRYABLE_STATUS:
                    raise
                # Respect Retry-After header if present
                retry_after = exc.response.headers.get("retry-after")
                delay = float(retry_after) if retry_after else self.RETRY_BACKOFF * (2 ** attempt)
                logger.warning("HTTP %d on attempt %d, retrying in %.1fs", exc.response.status_code, attempt + 1, delay)
                if attempt < self.MAX_RETRIES - 1:
                    await asyncio.sleep(delay)
            except (httpx.RemoteProtocolError, httpx.ConnectError, httpx.ReadTimeout) as exc:
                last_exc = exc
                if attempt < self.MAX_RETRIES - 1:
                    await asyncio.sleep(self.RETRY_BACKOFF * (attempt + 1))
        raise last_exc

    async def close(self):
        await self._http.aclose()
