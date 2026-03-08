"""Antigravity Token Bridge — OpenAI-compatible proxy for Google sandbox Claude API.

Accepts /v1/chat/completions requests, translates to Google's antigravity format,
handles OAuth token refresh, and rotates between accounts on 429s.
"""

import asyncio
import json
import os
import time
import uuid
from pathlib import Path

import httpx
from starlette.applications import Starlette
from starlette.requests import Request
from starlette.responses import JSONResponse
from starlette.routing import Route

# --- Config ---

ACCOUNTS_PATH = Path.home() / ".config/opencode/antigravity-accounts.json"
CLIENT_ID = os.environ.get("ANTIGRAVITY_CLIENT_ID", "")
CLIENT_SECRET = os.environ.get("ANTIGRAVITY_CLIENT_SECRET", "")
TOKEN_URL = "https://oauth2.googleapis.com/token"
API_HOSTS = [
    "https://daily-cloudcode-pa.sandbox.googleapis.com",
    "https://autopush-cloudcode-pa.sandbox.googleapis.com",
    "https://cloudcode-pa.googleapis.com",
]
API_PATH = "/v1internal:generateContent"
TOKEN_TTL = 55 * 60  # 55 minutes
PORT = 4003


# --- Token Manager ---

class Account:
    def __init__(self, email: str, refresh_token: str, project_id: str):
        self.email = email
        self.refresh_token = refresh_token
        self.project_id = project_id
        self.access_token: str | None = None
        self.token_expires: float = 0
        self.rate_limited_until: float = 0

    @property
    def is_rate_limited(self) -> bool:
        return time.time() < self.rate_limited_until

    @property
    def needs_refresh(self) -> bool:
        return self.access_token is None or time.time() >= self.token_expires


class TokenManager:
    def __init__(self):
        self.accounts: list[Account] = []
        self.current_index = 0
        self._client = httpx.AsyncClient(timeout=30)
        self._load_accounts()

    def _load_accounts(self):
        data = json.loads(ACCOUNTS_PATH.read_text())
        for acc in data["accounts"]:
            if "refreshToken" not in acc:
                continue  # skip non-OAuth accounts (e.g. local litellm)
            self.accounts.append(Account(
                email=acc["email"],
                refresh_token=acc["refreshToken"],
                project_id=acc["projectId"],
            ))
        if not self.accounts:
            raise RuntimeError("No OAuth accounts found in antigravity-accounts.json")
        print(f"[bridge] Loaded {len(self.accounts)} accounts: "
              f"{', '.join(a.email for a in self.accounts)}")

    async def refresh_token(self, account: Account):
        resp = await self._client.post(TOKEN_URL, data={
            "client_id": CLIENT_ID,
            "client_secret": CLIENT_SECRET,
            "refresh_token": account.refresh_token,
            "grant_type": "refresh_token",
        })
        resp.raise_for_status()
        token_data = resp.json()
        account.access_token = token_data["access_token"]
        account.token_expires = time.time() + TOKEN_TTL
        print(f"[bridge] Refreshed token for {account.email}")

    async def get_account(self) -> Account:
        """Get next available account, refreshing tokens as needed."""
        start = self.current_index
        for _ in range(len(self.accounts)):
            acc = self.accounts[self.current_index]
            if not acc.is_rate_limited:
                if acc.needs_refresh:
                    await self.refresh_token(acc)
                return acc
            self.current_index = (self.current_index + 1) % len(self.accounts)

        # All rate-limited — wait for the soonest one
        soonest = min(self.accounts, key=lambda a: a.rate_limited_until)
        wait = soonest.rate_limited_until - time.time()
        if wait > 0:
            print(f"[bridge] All accounts rate-limited, waiting {wait:.0f}s")
            await asyncio.sleep(wait)
        soonest.rate_limited_until = 0
        if soonest.needs_refresh:
            await self.refresh_token(soonest)
        return soonest

    def mark_rate_limited(self, account: Account, retry_after: float = 60):
        account.rate_limited_until = time.time() + retry_after
        print(f"[bridge] Rate-limited {account.email} for {retry_after:.0f}s")
        self.current_index = (self.current_index + 1) % len(self.accounts)

    async def close(self):
        await self._client.aclose()


# --- Request/Response Translation ---

def openai_to_antigravity(body: dict, project_id: str) -> dict:
    """Translate OpenAI chat completion request to antigravity format."""
    contents = []
    system_text = None

    for msg in body.get("messages", []):
        role = msg["role"]
        text = msg.get("content", "")

        if role == "system":
            system_text = text
            continue

        # Map OpenAI roles to Gemini roles
        gemini_role = "model" if role == "assistant" else "user"
        contents.append({"role": gemini_role, "parts": [{"text": text}]})

    # Ensure conversation starts with user
    if contents and contents[0]["role"] == "model":
        contents.insert(0, {"role": "user", "parts": [{"text": "(context)"}]})

    generation_config = {}
    if "temperature" in body:
        generation_config["temperature"] = body["temperature"]
    if "max_tokens" in body:
        generation_config["maxOutputTokens"] = body["max_tokens"]

    request_body = {
        "project": project_id,
        "model": body.get("model", "claude-sonnet-4-5"),
        "request": {
            "contents": contents,
            "generationConfig": generation_config,
        },
        "userAgent": "antigravity",
        "requestId": f"wargames-{uuid.uuid4().hex[:12]}",
    }

    if system_text:
        request_body["request"]["systemInstruction"] = {
            "parts": [{"text": system_text}]
        }

    return request_body


def antigravity_to_openai(response_data: dict, model: str) -> dict:
    """Translate antigravity response to OpenAI format."""
    # Navigate: {"response": {"candidates": [{"content": {"parts": [{"text": "..."}]}}]}}
    resp = response_data.get("response", response_data)
    candidates = resp.get("candidates", [])

    content = ""
    if candidates:
        parts = candidates[0].get("content", {}).get("parts", [])
        content = "".join(p.get("text", "") for p in parts)

    return {
        "id": f"chatcmpl-{uuid.uuid4().hex[:12]}",
        "object": "chat.completion",
        "model": model,
        "choices": [{
            "index": 0,
            "message": {"role": "assistant", "content": content},
            "finish_reason": "stop",
        }],
        "usage": {
            "prompt_tokens": 0,
            "completion_tokens": 0,
            "total_tokens": 0,
        },
    }


# --- API Client ---

async def call_antigravity(client: httpx.AsyncClient, account: Account,
                           request_body: dict) -> httpx.Response:
    """Try API hosts in order until one succeeds."""
    headers = {
        "Authorization": f"Bearer {account.access_token}",
        "Content-Type": "application/json",
        "User-Agent": "antigravity/1.11.5",
        "X-Goog-Api-Client": "google-cloud-sdk vscode_cloudshelleditor/0.1",
    }

    last_error = None
    for host in API_HOSTS:
        try:
            resp = await client.post(
                f"{host}{API_PATH}",
                json=request_body,
                headers=headers,
                timeout=180,
            )
            return resp
        except httpx.HTTPError as e:
            last_error = e
            print(f"[bridge] Host {host} failed: {e}, trying next...")
            continue

    raise last_error or RuntimeError("All API hosts failed")


# --- Server ---

token_manager = TokenManager()
http_client = httpx.AsyncClient(timeout=180)


async def chat_completions(request: Request) -> JSONResponse:
    body = await request.json()
    model = body.get("model", "claude-sonnet-4-5")
    max_retries = len(token_manager.accounts)

    for attempt in range(max_retries):
        account = await token_manager.get_account()
        request_body = openai_to_antigravity(body, account.project_id)

        print(f"[bridge] → {account.email} | model={model} | attempt={attempt + 1}")

        resp = await call_antigravity(http_client, account, request_body)

        if resp.status_code == 429:
            retry_after = float(resp.headers.get("Retry-After", "60"))
            print(f"[bridge] 429 body: {resp.text[:300]}")
            token_manager.mark_rate_limited(account, retry_after)
            continue

        if resp.status_code == 401:
            # Token expired mid-flight, force refresh and retry
            account.token_expires = 0
            await token_manager.refresh_token(account)
            continue

        if resp.status_code >= 400:
            error_text = resp.text
            print(f"[bridge] Error {resp.status_code}: {error_text[:200]}")
            return JSONResponse(
                {"error": {"message": error_text, "type": "api_error", "code": resp.status_code}},
                status_code=resp.status_code,
            )

        response_data = resp.json()
        result = antigravity_to_openai(response_data, model)
        content_preview = result["choices"][0]["message"]["content"][:80]
        print(f"[bridge] ← {account.email} | {len(content_preview)}+ chars")
        return JSONResponse(result)

    return JSONResponse(
        {"error": {"message": "All accounts rate-limited after retries", "type": "rate_limit"}},
        status_code=429,
    )


async def health(request: Request) -> JSONResponse:
    accounts_status = [
        {"email": a.email, "rate_limited": a.is_rate_limited, "has_token": a.access_token is not None}
        for a in token_manager.accounts
    ]
    return JSONResponse({"status": "ok", "accounts": accounts_status})


async def on_shutdown():
    await http_client.aclose()
    await token_manager.close()


app = Starlette(
    routes=[
        Route("/v1/chat/completions", chat_completions, methods=["POST"]),
        Route("/health", health, methods=["GET"]),
    ],
    on_shutdown=[on_shutdown],
)

if __name__ == "__main__":
    import uvicorn
    print(f"[bridge] Starting antigravity bridge on port {PORT}")
    uvicorn.run(app, host="0.0.0.0", port=PORT, log_level="info")
