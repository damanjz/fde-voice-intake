"""Client for the project 1 support agent: POST /chat {session_id, message, confirm}.

P1 keeps any pending action per session_id on its server, so this client never sends one back. A /chat call
is never retried automatically: a retry would repeat the turn (a second ticket, a second return).
"""

from __future__ import annotations

import httpx

from app.config import Settings, settings


class AgentUnavailable(RuntimeError):
    """P1 is down, timed out or answered with an error."""


class AgentClient:
    def __init__(self, cfg: Settings = settings, client: httpx.Client | None = None) -> None:
        self.base_url = cfg.agent_url.rstrip("/")
        self._client = client or httpx.Client(timeout=httpx.Timeout(cfg.agent_timeout_s, connect=5.0))

    def chat(self, session_id: str, message: str, confirm: bool | None = None) -> dict:
        body = {"session_id": session_id, "message": message, "confirm": confirm}
        try:
            resp = self._client.post(f"{self.base_url}/chat", json=body)
            resp.raise_for_status()
            data = resp.json()
        except (httpx.HTTPError, ValueError) as exc:
            raise AgentUnavailable(str(exc)) from exc
        if not isinstance(data, dict) or not isinstance(data.get("text"), str):
            raise AgentUnavailable("unexpected response from the agent")
        return data

    def healthy(self) -> bool:
        try:
            return self._client.get(f"{self.base_url}/health", timeout=3).status_code == 200
        except httpx.HTTPError:
            return False
