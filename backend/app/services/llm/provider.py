import asyncio
import json
from typing import Protocol, Type

import httpx
from pydantic import BaseModel

from app.core.config import get_settings


class LLMProvider(Protocol):
    async def complete(self, messages: list[dict], *, json_schema=None, temperature: float = 0.2) -> str: ...
    async def structured(self, messages: list[dict], schema: Type[BaseModel], temperature: float = 0.2) -> BaseModel: ...


_semaphore: asyncio.Semaphore | None = None


def _sem() -> asyncio.Semaphore:
    global _semaphore
    if _semaphore is None:
        _semaphore = asyncio.Semaphore(get_settings().llm_max_concurrency)
    return _semaphore


class GroqProvider:
    def __init__(self, api_key: str, model: str):
        self.api_key = api_key
        self.model = model

    async def complete(self, messages: list[dict], *, json_schema=None, temperature: float = 0.2) -> str:
        payload = {
            "model": self.model,
            "messages": messages,
            "temperature": temperature,
        }
        if json_schema is not None:
            payload["response_format"] = {"type": "json_object"}
        headers = {"Authorization": f"Bearer {self.api_key}", "Content-Type": "application/json"}
        async with _sem():
            max_retries = 5
            base_delay = 1.0  # seconds
            last_error = None
            for attempt in range(max_retries):
                try:
                    async with httpx.AsyncClient(timeout=60.0) as client:
                        response = await client.post(
                            "https://api.groq.com/openai/v1/chat/completions",
                            headers=headers,
                            json=payload,
                        )
                        if response.status_code == 429:
                            # Respect Retry-After header if present
                            retry_after = response.headers.get("Retry-After")
                            try:
                                wait = float(retry_after) if retry_after is not None else None
                            except (ValueError, TypeError):
                                wait = None
                            if wait is None:
                                # exponential backoff with jitter cap
                                wait = base_delay * (2 ** attempt)
                            import logging
                            logging.getLogger(__name__).warning("Groq 429 rate limit hit. Waiting %s seconds (attempt %s)", wait, attempt)
                            await asyncio.sleep(wait)
                            continue
                        response.raise_for_status()
                        data = response.json()
                        return data["choices"][0]["message"]["content"]
                except httpx.HTTPError as exc:
                    # Non‑rate‑limit errors – backoff then retry
                    last_error = exc
                    await asyncio.sleep(base_delay * (2 ** attempt))
            # Exhausted retries
            raise RuntimeError(str(last_error) if last_error else "LLM request failed")

    async def structured(self, messages: list[dict], schema: Type[BaseModel], temperature: float = 0.2) -> BaseModel:
        """Request structured JSON and safely extract it.

        The LLM may prepend or append harmless text. We first try to parse the
        raw response directly with ``json.loads``. If that fails, we fall back to
        ``json.JSONDecoder().raw_decode`` which scans for the first JSON object
        in the string, correctly handling nested structures and escaped braces
        inside string literals.
        """
        schema_hint = json.dumps(schema.model_json_schema())
        prompted = messages + [
            {"role": "system", "content": f"Respond with JSON matching this schema: {schema_hint}"}
        ]
        # First attempt with normal temperature
        raw = await self.complete(prompted, json_schema=schema, temperature=temperature)
        json_text = self._extract_json(raw)
        try:
            return schema.model_validate_json(json_text)
        except Exception as exc:
            # Fallback: retry with temperature=0 (more deterministic)
            raw2 = await self.complete(prompted, json_schema=schema, temperature=0)
            json_text2 = self._extract_json(raw2)
            return schema.model_validate_json(json_text2)

    @staticmethod
    def _extract_json(text: str) -> str:
        """Extract the first JSON object from *text*.

        1. Try ``json.loads`` on the whole string.
        2. If that fails, use ``json.JSONDecoder().raw_decode`` to locate the
           first JSON object, respecting nesting and escaped characters.
        3. Raise a clear error with a short preview when no JSON is found.
        """
        # Quick path – pure JSON
        try:
            json.loads(text)
            return text
        except Exception:
            pass
        decoder = json.JSONDecoder()
        idx = 0
        length = len(text)
        while idx < length:
            try:
                obj, end = decoder.raw_decode(text, idx)
                # Successfully decoded a JSON value – return the slice
                return text[idx:end]
            except json.JSONDecodeError as e:
                # Move forward one character and try again
                idx = e.pos + 1
        preview = (text[:75] + "...") if len(text) > 75 else text
        raise RuntimeError(f"No JSON object could be extracted from LLM response: {preview!r}")


class HeuristicProvider:
    """Offline extractive fallback when no API key is configured."""

    async def complete(self, messages: list[dict], *, json_schema=None, temperature: float = 0.2) -> str:
        return messages[-1]["content"][:4000]

    async def structured(self, messages: list[dict], schema: Type[BaseModel], temperature: float = 0.2) -> BaseModel:
        from app.services.llm.heuristic import build_heuristic

        return build_heuristic(schema, messages)


def get_provider() -> LLMProvider:
    settings = get_settings()
    if settings.llm_api_key and settings.llm_provider in {"groq", "openai", "mistral", "gemini"}:
        if settings.llm_provider == "groq":
            return GroqProvider(settings.llm_api_key, settings.llm_model)
        if settings.llm_provider == "openai":
            return OpenAICompatibleProvider(
                settings.llm_api_key,
                settings.llm_model,
                "https://api.openai.com/v1/chat/completions",
            )
        if settings.llm_provider == "mistral":
            return OpenAICompatibleProvider(
                settings.llm_api_key,
                settings.llm_model,
                "https://api.mistral.ai/v1/chat/completions",
            )
        if settings.llm_provider == "gemini":
            return OpenAICompatibleProvider(
                settings.llm_api_key,
                settings.llm_model,
                "https://generativelanguage.googleapis.com/v1beta/openai/chat/completions",
            )
    return HeuristicProvider()


class OpenAICompatibleProvider(GroqProvider):
    def __init__(self, api_key: str, model: str, endpoint: str):
        super().__init__(api_key, model)
        self.endpoint = endpoint

    async def complete(self, messages: list[dict], *, json_schema=None, temperature: float = 0.2) -> str:
        payload = {"model": self.model, "messages": messages, "temperature": temperature}
        if json_schema is not None:
            payload["response_format"] = {"type": "json_object"}
        headers = {"Authorization": f"Bearer {self.api_key}", "Content-Type": "application/json"}
        async with _sem():
            async with httpx.AsyncClient(timeout=60.0) as client:
                response = await client.post(self.endpoint, headers=headers, json=payload)
                response.raise_for_status()
                return response.json()["choices"][0]["message"]["content"]
