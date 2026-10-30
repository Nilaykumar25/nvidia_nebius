"""LLM + embedding abstraction — OpenAI-compatible client for Nebius Token Factory / Nemotron.

Configuration (all via environment / config.py, never hardcoded):
  LLM_BASE_URL   — Nebius Token Factory base URL
  LLM_API_KEY    — Nebius Token Factory API key
  LLM_MODEL      — model identifier, e.g. nvidia/Llama-3_1-Nemotron-Ultra-253B-v1
  LLM_TIMEOUT_SECONDS  — per-request timeout (default 60)
  LLM_MAX_RETRIES      — total retry attempts on 429/5xx (default 3)

Nemotron-specific handling:
  - <think>...</think> reasoning blocks are stripped before JSON parsing.
  - JSON is extracted robustly from any surrounding prose or markdown.
  - On parse failure, one retry is issued with a stricter "return ONLY JSON" prompt.
  - response_format=json_object is attempted; falls back to prompt-only if the
    endpoint does not support it (non-200 or missing field).
  - Exponential backoff on 429 and 5xx errors.

Language normalisation:
  - Hindi/Hinglish questions are translated to English via the same LLM.
  - Code identifiers, config keys, and function names are preserved unchanged.
"""
from __future__ import annotations

import hashlib
import json
import logging
import os
import re
import time
from functools import lru_cache

from openai import OpenAI, RateLimitError, APIStatusError, APIConnectionError

from ..config import settings

log = logging.getLogger(__name__)

CACHE_DIR = os.path.join(settings.cache_dir, "llm")

# ──────────────────────────────────────────────────────────────────────────────
# JSON helpers
# ──────────────────────────────────────────────────────────────────────────────

_THINK_RE = re.compile(r"<think>.*?</think>", re.DOTALL | re.IGNORECASE)


def _strip_think(raw: str) -> str:
    """Remove any <think>…</think> reasoning block before JSON parsing."""
    return _THINK_RE.sub("", raw).strip()


def _extract_json(raw: str) -> str:
    """Extract the first valid JSON object or array from raw text.

    Handles:
    - ```json ... ``` fences
    - Prose before/after the JSON
    - Nested braces
    """
    raw = _strip_think(raw)
    # Strip markdown fences
    raw = re.sub(r"^```(?:json)?", "", raw, flags=re.MULTILINE).strip()
    raw = re.sub(r"```$", "", raw, flags=re.MULTILINE).strip()

    # Try to find a JSON object
    start = raw.find("{")
    arr_start = raw.find("[")
    if start == -1 and arr_start == -1:
        raise ValueError(f"no JSON object or array found in LLM output: {raw[:200]!r}")

    # Prefer object unless array starts first
    if start == -1 or (arr_start != -1 and arr_start < start):
        end = raw.rfind("]")
        if end == -1:
            raise ValueError("no closing ] found")
        return raw[arr_start : end + 1]
    else:
        end = raw.rfind("}")
        if end == -1:
            raise ValueError("no closing } found")
        return raw[start : end + 1]


def parse_json(raw: str) -> dict:
    return json.loads(_extract_json(raw))


# ──────────────────────────────────────────────────────────────────────────────
# Cache key helpers
# ──────────────────────────────────────────────────────────────────────────────

def _cache_key(model: str, system: str, user: str) -> str:
    blob = f"nebius|{model}|{system}|{user}"
    return hashlib.sha256(blob.encode()).hexdigest()


# ──────────────────────────────────────────────────────────────────────────────
# Core LLM client
# ──────────────────────────────────────────────────────────────────────────────

class LLM:
    """OpenAI-compatible LLM client targeting Nebius Token Factory."""

    def __init__(self) -> None:
        base_url = settings.llm_base_url
        api_key = settings.llm_api_key
        self.model = settings.llm_model
        self.timeout = float(settings.llm_timeout_seconds)
        self.max_retries = settings.llm_max_retries

        if not base_url or not api_key or not self.model:
            log.warning(
                "LLM_BASE_URL, LLM_API_KEY, or LLM_MODEL is not set. "
                "LLM calls will fail. Configure these from your Nebius dashboard."
            )

        self._client = OpenAI(
            base_url=base_url or "http://placeholder.invalid/v1",
            api_key=api_key or "placeholder",
            timeout=self.timeout,
            max_retries=0,  # We handle retries ourselves with backoff
        )

    # ── low-level call with retry ─────────────────────────────────────────────

    def _call(
        self,
        system: str,
        user: str,
        max_tokens: int,
        json_mode: bool = False,
    ) -> str:
        messages = [
            {"role": "system", "content": system},
            {"role": "user", "content": user},
        ]
        kwargs: dict = {
            "model": self.model,
            "messages": messages,
            "max_tokens": max_tokens,
            "temperature": 0.2,
        }
        if json_mode:
            kwargs["response_format"] = {"type": "json_object"}

        last_exc: Exception | None = None
        for attempt in range(self.max_retries):
            try:
                resp = self._client.chat.completions.create(**kwargs)
                content = resp.choices[0].message.content or ""
                log.debug(
                    "LLM model=%s prompt_tokens=%s completion_tokens=%s",
                    self.model,
                    getattr(getattr(resp, "usage", None), "prompt_tokens", "?"),
                    getattr(getattr(resp, "usage", None), "completion_tokens", "?"),
                )
                return _strip_think(content)

            except RateLimitError as exc:
                last_exc = exc
                wait = (2 ** attempt) + 1
                retry_after = getattr(exc, "response", None)
                if retry_after:
                    ra = retry_after.headers.get("Retry-After")
                    if ra and ra.isdigit():
                        wait = int(ra)
                log.warning("LLM 429 rate-limited; sleeping %ds (attempt %d/%d)", wait, attempt + 1, self.max_retries)
                time.sleep(wait)

            except APIStatusError as exc:
                last_exc = exc
                if exc.status_code < 500:
                    raise  # 4xx that isn't 429 — don't retry
                wait = (2 ** attempt) + 1
                log.warning("LLM %d server error; sleeping %ds (attempt %d/%d)", exc.status_code, wait, attempt + 1, self.max_retries)
                time.sleep(wait)

            except APIConnectionError as exc:
                last_exc = exc
                wait = (2 ** attempt) + 1
                log.warning("LLM connection error; sleeping %ds (attempt %d/%d)", wait, attempt + 1, self.max_retries)
                time.sleep(wait)

        raise last_exc or RuntimeError("LLM call failed after all retries")

    # ── public interface (mirrors the old LLM base class) ─────────────────────

    def complete(self, system: str, user: str, max_tokens: int = 1500, cache: bool = True) -> str:
        key = _cache_key(self.model, system, user)
        path = os.path.join(CACHE_DIR, key + ".txt")
        if cache and os.path.exists(path):
            return open(path, encoding="utf-8").read()
        out = self._call(system, user, max_tokens)
        if cache:
            os.makedirs(CACHE_DIR, exist_ok=True)
            open(path, "w", encoding="utf-8").write(out)
        return out

    def complete_json(self, system: str, user: str, max_tokens: int = 1500) -> dict:
        """Request a JSON response, with robust parsing and one retry on failure.

        Strategy:
        1. Ask with response_format=json_object if the endpoint supports it.
        2. Extract the first valid JSON object from the text.
        3. On parse failure, retry once with a stricter prompt (no json_mode,
           to avoid double-format conflicts on some endpoints).
        """
        sys2 = system + "\nRespond with a single JSON object only. No prose, no markdown fences."
        key = _cache_key(self.model, sys2, user)
        path = os.path.join(CACHE_DIR, key + ".txt")

        if os.path.exists(path):
            raw = open(path, encoding="utf-8").read()
        else:
            # Try json_mode first; fall back silently if endpoint rejects it
            try:
                raw = self._call(sys2, user, max_tokens, json_mode=True)
            except (APIStatusError, Exception) as exc:
                log.debug("json_mode rejected (%s); falling back to prompt-only", exc)
                raw = self._call(sys2, user, max_tokens, json_mode=False)
            os.makedirs(CACHE_DIR, exist_ok=True)
            open(path, "w", encoding="utf-8").write(raw)

        try:
            return parse_json(raw)
        except Exception:
            log.warning("JSON parse failed on first attempt; retrying with stricter prompt")
            repair_user = user + "\n\nReturn ONLY a valid JSON object. No explanation, no markdown, no prose."
            repair_raw = self._call(
                sys2,
                repair_user,
                max_tokens,
                json_mode=False,
            )
            return parse_json(repair_raw)


# ──────────────────────────────────────────────────────────────────────────────
# Language normalisation
# ──────────────────────────────────────────────────────────────────────────────

_TRANSLATE_SYSTEM = (
    "You are a translation assistant. Translate the user's question from Hindi or Hinglish to English. "
    "Preserve all code identifiers, config keys, function names, and technical terms exactly as written. "
    "Output only the English translation. No explanations."
)


def translate_to_english(llm: LLM, question: str) -> str:
    """Translate a Hindi/Hinglish question to English using the LLM.

    Preserves code identifiers, config keys, and function names unchanged.
    Falls back to the original question on any error.
    """
    try:
        return llm.complete(_TRANSLATE_SYSTEM, question, 300, cache=False)
    except Exception as exc:
        log.warning("Language normalisation failed: %s", exc)
        return question


# ──────────────────────────────────────────────────────────────────────────────
# Factory
# ──────────────────────────────────────────────────────────────────────────────

@lru_cache
def get_llm() -> LLM:
    return LLM()


# ──────────────────────────────────────────────────────────────────────────────
# Embeddings (local sentence-transformers, no API key needed)
# ──────────────────────────────────────────────────────────────────────────────

@lru_cache
def _embedder():
    from sentence_transformers import SentenceTransformer
    return SentenceTransformer(settings.embedding_model)


def embed(texts: list[str]) -> list[list[float]]:
    return _embedder().encode(texts, normalize_embeddings=True, show_progress_bar=False).tolist()


def cosine(a: list[float], b: list[float]) -> float:
    return float(sum(x * y for x, y in zip(a, b)))  # vectors are already L2-normalised
