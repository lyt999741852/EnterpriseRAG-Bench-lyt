"""
LLM interface -- abstract base with OpenAI-compatible stub.
Replace _call_api with your actual provider when ready.
"""

from __future__ import annotations

import os
import socket
import time
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from urllib.error import HTTPError, URLError


@dataclass
class LLMConfig:
    provider: str = "openai_compatible"
    api_base: str = ""
    api_key_env: str = "LLM_API_KEY"
    # Direct keys are supported for isolated/local benchmark configs.  When
    # both are present, the explicit key wins; existing env-based configs are
    # unchanged.
    api_key: str = ""
    model_name: str = ""
    temperature: float = 0.0
    max_tokens: int = 1024
    timeout: int = 60
    retry_attempts: int = 3
    retry_backoff_seconds: float = 1.0
    extra_body: dict = field(default_factory=dict)


class LLMClient(ABC):
    """Abstract LLM client. Implement _call_api for your provider."""

    def __init__(self, config: LLMConfig):
        self.config = config
        self._api_key: str | None = None

    @property
    def api_key(self) -> str:
        if self._api_key is None:
            self._api_key = self.config.api_key or os.environ.get(
                self.config.api_key_env, ""
            )
        return self._api_key

    def generate(self, prompt: str, system_prompt: str = "") -> str:
        """Public entry: call LLM, handle errors gracefully."""
        if not self.config.model_name:
            raise ValueError(
                "LLM model_name is not configured. "
                "Set llm.model_name in configs/default.yaml."
            )
        try:
            return self._call_api(prompt, system_prompt)
        except Exception as e:
            # Keep failures machine-detectable so the pipeline can resume and
            # retry them instead of treating an error string as a valid answer.
            return f"[LLM_ERROR: {type(e).__name__}: {e}]"

    @abstractmethod
    def _call_api(self, prompt: str, system_prompt: str) -> str:
        ...


class OpenAICompatibleClient(LLMClient):
    """OpenAI-compatible API client. Also works with vLLM, Ollama, etc."""

    def _call_api(self, prompt: str, system_prompt: str) -> str:
        import json
        from urllib.request import Request, urlopen

        cfg = self.config
        if not cfg.api_base:
            raise ValueError("LLM api_base is not configured")
        if cfg.api_key_env and not self.api_key and not cfg.api_key:
            raise ValueError(
                f"Environment variable {cfg.api_key_env} is not set"
            )

        messages = []
        if system_prompt:
            messages.append({"role": "system", "content": system_prompt})
        messages.append({"role": "user", "content": prompt})

        payload = {
            "model": cfg.model_name,
            "messages": messages,
            "temperature": cfg.temperature,
            "max_tokens": cfg.max_tokens,
        }
        payload.update(cfg.extra_body or {})
        body = json.dumps(payload).encode("utf-8")

        url = f"{cfg.api_base.rstrip('/')}/chat/completions"
        attempts = max(1, int(cfg.retry_attempts))
        for attempt in range(1, attempts + 1):
            req = Request(url, data=body, headers={
                "Content-Type": "application/json",
                "Authorization": f"Bearer {self.api_key}",
            })
            try:
                with urlopen(req, timeout=cfg.timeout) as resp:
                    data = json.loads(resp.read().decode("utf-8"))
                choice = data["choices"][0]
                message = choice.get("message") or {}
                content = message.get("content")
                if content is None or not str(content).strip():
                    finish = choice.get("finish_reason", "unknown")
                    reasoning_present = bool(message.get("reasoning"))
                    raise RuntimeError(
                        "LLM returned empty content "
                        f"(finish_reason={finish}, reasoning_present={reasoning_present})"
                    )
                return str(content)
            except HTTPError as e:
                detail = e.read().decode("utf-8", errors="replace")[:500]
                retryable = e.code in (408, 409, 429) or e.code >= 500
                if not retryable or attempt == attempts:
                    raise RuntimeError(f"LLM API error {e.code}: {detail}") from e
            except (URLError, TimeoutError, socket.timeout) as e:
                if attempt == attempts:
                    raise RuntimeError(f"LLM request failed: {e}") from e

            delay = max(0.0, cfg.retry_backoff_seconds) * (2 ** (attempt - 1))
            if delay:
                time.sleep(delay)

        raise RuntimeError("LLM request failed after retries")


def create_llm_client(config: LLMConfig) -> LLMClient:
    """Factory: return the right client for the configured provider."""
    if config.provider == "openai_compatible":
        return OpenAICompatibleClient(config)
    raise ValueError(f"Unknown LLM provider: {config.provider}")
