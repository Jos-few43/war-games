import asyncio
import logging
import httpx
from wargames.models import TeamSettings

logger = logging.getLogger(__name__)

RETRYABLE_STATUS = {429, 500, 502, 503, 504}


class LLMClient:
    MAX_RETRIES = 5
    RETRY_BACKOFF = 2.0
    FALLBACK_RETRIES = 2
    MAX_JSON_RETRIES = 3

    def __init__(self, settings: TeamSettings):
        self.settings = settings
        headers = {}
        if settings.api_key:
            headers['Authorization'] = f'Bearer {settings.api_key}'
        self._http = httpx.AsyncClient(
            base_url=settings.model,
            timeout=settings.timeout,
            headers=headers,
        )

        self._fallback_http: httpx.AsyncClient | None = None
        if settings.fallback_model:
            fb_headers = {}
            if settings.fallback_api_key:
                fb_headers['Authorization'] = f'Bearer {settings.fallback_api_key}'
            self._fallback_http = httpx.AsyncClient(
                base_url=settings.fallback_model,
                timeout=settings.timeout,
                headers=fb_headers,
            )

        self._prompt_tokens = 0
        self._completion_tokens = 0
        self._last_model_used = settings.model_name

    async def _attempt(
        self,
        http: httpx.AsyncClient,
        model_name: str,
        messages: list[dict],
        max_retries: int,
    ) -> tuple[str, dict]:
        payload = {
            'model': model_name,
            'messages': messages,
            'temperature': self.settings.temperature,
        }
        last_exc = None
        for attempt in range(max_retries):
            try:
                response = await http.post('/chat/completions', json=payload)
                response.raise_for_status()
                data = response.json()
                content = data['choices'][0]['message']['content']
                usage = data.get('usage', {})
                return content, usage
            except httpx.HTTPStatusError as exc:
                last_exc = exc
                if exc.response.status_code not in RETRYABLE_STATUS:
                    raise
                retry_after = exc.response.headers.get('retry-after')
                delay = float(retry_after) if retry_after else self.RETRY_BACKOFF * (2**attempt)
                logger.warning(
                    'HTTP %d on attempt %d, retrying in %.1fs',
                    exc.response.status_code,
                    attempt + 1,
                    delay,
                )
                if attempt < max_retries - 1:
                    await asyncio.sleep(delay)
            except (httpx.RemoteProtocolError, httpx.ConnectError, httpx.ReadTimeout) as exc:
                last_exc = exc
                if attempt < max_retries - 1:
                    await asyncio.sleep(self.RETRY_BACKOFF * (attempt + 1))
        raise last_exc

    def get_usage(self, reset: bool = False) -> dict:
        usage = {
            'prompt_tokens': self._prompt_tokens,
            'completion_tokens': self._completion_tokens,
            'model_used': self._last_model_used,
        }
        if reset:
            self._prompt_tokens = 0
            self._completion_tokens = 0
        return usage

    async def chat(self, messages: list[dict], system: str | None = None) -> str:
        if system:
            messages = [{'role': 'system', 'content': system}, *messages]

        try:
            content, usage = await self._attempt(
                self._http,
                self.settings.model_name,
                messages,
                self.MAX_RETRIES,
            )
            self._prompt_tokens += usage.get('prompt_tokens', 0)
            self._completion_tokens += usage.get('completion_tokens', 0)
            self._last_model_used = self.settings.model_name
            return content
        except (
            httpx.HTTPStatusError,
            httpx.RemoteProtocolError,
            httpx.ConnectError,
            httpx.ReadTimeout,
        ) as exc:
            if not self._fallback_http:
                raise
            logger.warning(
                'Primary model %s failed after %d retries, falling back to %s',
                self.settings.model_name,
                self.MAX_RETRIES,
                self.settings.fallback_model_name,
            )
            content, usage = await self._attempt(
                self._fallback_http,
                self.settings.fallback_model_name,
                messages,
                self.FALLBACK_RETRIES,
            )
            self._prompt_tokens += usage.get('prompt_tokens', 0)
            self._completion_tokens += usage.get('completion_tokens', 0)
            self._last_model_used = self.settings.fallback_model_name
            return content

    async def close(self):
        await self._http.aclose()
        if self._fallback_http:
            await self._fallback_http.aclose()
