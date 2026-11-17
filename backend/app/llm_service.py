"""Backend-only provider dispatch for evidence-grounded LLM text generation."""

import logging
import os
from typing import Any, Dict, Optional

import requests
from google import genai
from google.genai import types

from .config import (
    GEMINI_API_KEY,
    GEMINI_MODEL,
    GROQ_API_KEY,
    GROQ_BASE_URL,
    GROQ_ENABLED,
    GROQ_MODEL,
    GROQ_TIMEOUT_SEC,
    OPENAI_API_KEY,
    OPENAI_MODEL,
    OPENAI_TIMEOUT_SEC,
)

logger = logging.getLogger(__name__)


class LLMConfigurationError(Exception):
    pass


class LLMProviderError(Exception):
    def __init__(self, message: str, status_code: int = 502):
        super().__init__(message)
        self.status_code = status_code


def _settings(provider: str) -> tuple[str, str]:
    if provider == "gemini":
        return (
            os.getenv("GEMINI_API_KEY", GEMINI_API_KEY).strip(),
            os.getenv("GEMINI_MODEL", GEMINI_MODEL).strip(),
        )
    if provider == "openai":
        return (
            os.getenv("OPENAI_API_KEY", OPENAI_API_KEY).strip(),
            os.getenv("OPENAI_MODEL", OPENAI_MODEL).strip(),
        )
    if provider == "groq":
        return (
            os.getenv("GROQ_API_KEY", GROQ_API_KEY).strip(),
            os.getenv("GROQ_MODEL", GROQ_MODEL).strip(),
        )
    raise LLMConfigurationError("Unsupported LLM provider.")


def provider_status() -> Dict[str, Dict[str, Any]]:
    statuses: Dict[str, Dict[str, Any]] = {}
    for provider in ("gemini", "openai", "groq"):
        key, model = _settings(provider)
        enabled = provider != "groq" or os.getenv("GROQ_ENABLED", str(GROQ_ENABLED)).strip().lower() in {"1", "true", "yes", "on"}
        configured = bool(enabled and key and model)
        statuses[provider] = {
            "provider": provider,
            "configured": configured,
            "model_configured": bool(model),
            "model": model or None,
            "enabled": enabled,
            "reachable": None,
            "last_success_utc": _last_success_for(provider),
            "detail": ("Configured; connectivity has not been checked." if configured
                       else "Groq is disabled in backend configuration." if provider == "groq" and not enabled
                       else "Provider credentials or model configuration are missing."),
        }
    return statuses


def _last_success_for(provider: str) -> Optional[str]:
    """Use persisted assistant replies as evidence of a prior successful request."""
    try:
        import json
        from .database import get_conn

        conn = get_conn()
        try:
            rows = conn.execute(
                "SELECT evidence_json, created_utc FROM gemini_conversations WHERE role = 'assistant' ORDER BY id DESC LIMIT 500"
            ).fetchall()
        finally:
            conn.close()
        for row in rows:
            try:
                evidence = json.loads(row["evidence_json"] or "{}")
            except (TypeError, ValueError):
                evidence = {}
            message_provider = evidence.get("provider") or "gemini"
            if message_provider == provider:
                return row["created_utc"]
    except Exception:
        return None
    return None


def generate_text(
    provider: str,
    prompt: str,
    *,
    model: Optional[str] = None,
    max_output_tokens: int = 2048,
    temperature: float = 0.2,
) -> Dict[str, str]:
    """Generate one response. Provider selection is explicit; there is no fallback."""
    if provider not in {"gemini", "openai", "groq"}:
        raise LLMConfigurationError("Provider must be 'gemini', 'openai', or 'groq'.")
    if provider == "groq" and os.getenv("GROQ_ENABLED", str(GROQ_ENABLED)).strip().lower() not in {"1", "true", "yes", "on"}:
        raise LLMConfigurationError("Groq is disabled in backend configuration.")
    api_key, configured_model = _settings(provider)
    selected_model = (model or configured_model).strip()
    if not api_key:
        raise LLMConfigurationError(f"{provider.title()} API key is not configured on the backend.")
    if not selected_model:
        raise LLMConfigurationError(f"{provider.title()} model is not configured on the backend.")
    if not prompt or not prompt.strip():
        raise ValueError("Prompt cannot be empty.")

    if provider == "gemini":
        try:
            client = genai.Client(
                api_key=api_key,
                http_options=types.HttpOptions(timeout=90000),
            )
            response = client.models.generate_content(
                model=selected_model,
                contents=prompt,
                config=types.GenerateContentConfig(
                    max_output_tokens=max_output_tokens,
                    temperature=temperature,
                ),
            )
            answer = (response.text or "").strip()
            if not answer:
                raise LLMProviderError("Gemini returned an empty response.")
            return {"provider": "Google Gemini", "provider_key": provider,
                    "model": selected_model, "answer": answer}
        except LLMProviderError:
            raise
        except Exception as exc:
            status_code = getattr(exc, "status_code", None) or getattr(exc, "code", None)
            logger.warning("Gemini request failed (%s; upstream status %s).", type(exc).__name__, status_code or "unknown")
            if status_code == 429:
                raise LLMProviderError("Gemini rate limit reached. Retry later.", 429) from exc
            if status_code in (401, 403):
                raise LLMConfigurationError("Gemini rejected the configured credentials or project access.") from exc
            if status_code and int(status_code) >= 500:
                raise LLMProviderError(f"Gemini is temporarily unavailable (upstream HTTP {status_code}).", 503) from exc
            raise LLMProviderError("Gemini request failed. Check provider status and backend logs.") from exc

    timeout_default = GROQ_TIMEOUT_SEC if provider == "groq" else OPENAI_TIMEOUT_SEC
    timeout_name = "GROQ_TIMEOUT_SEC" if provider == "groq" else "OPENAI_TIMEOUT_SEC"
    timeout = max(1.0, float(os.getenv(timeout_name, str(timeout_default))))
    endpoint = (
        f"{os.getenv('GROQ_BASE_URL', GROQ_BASE_URL).strip().rstrip('/')}/responses"
        if provider == "groq"
        else "https://api.openai.com/v1/responses"
    )
    try:
        request_body = {
            "model": selected_model,
            "input": prompt,
            "max_output_tokens": max_output_tokens,
            "store": False,
        }
        if provider == "groq":
            # GPT-OSS spends some output tokens on reasoning; cap effort so short
            # prompts and the provider health check still leave room for an answer.
            request_body["reasoning"] = {"effort": "low"}
        response = requests.post(
            endpoint,
            headers={"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"},
            json=request_body,
            timeout=timeout,
        )
    except requests.exceptions.Timeout as exc:
        raise LLMProviderError(f"{provider.title()} request timed out.", 504) from exc
    except requests.exceptions.RequestException as exc:
        logger.warning("%s connection failed (%s).", provider.title(), type(exc).__name__)
        raise LLMProviderError(f"{provider.title()} could not be reached.", 503) from exc

    if response.status_code == 429:
        raise LLMProviderError(f"{provider.title()} rate limit reached. Retry later.", 429)
    if response.status_code in (401, 403):
        raise LLMConfigurationError(f"{provider.title()} rejected the configured credentials or project access.")
    if response.status_code >= 500:
        raise LLMProviderError(f"{provider.title()} is temporarily unavailable.", 503)
    if response.status_code >= 400:
        detail = ""
        try:
            error_payload = response.json().get("error", {})
            if isinstance(error_payload, dict):
                detail = str(error_payload.get("message") or "").strip()
        except (ValueError, AttributeError):
            pass
        if provider == "groq" and response.status_code == 413:
            logger.warning("Groq rejected an oversized prompt (%s characters).", len(prompt))
        suffix = f": {detail[:240]}" if detail else ""
        raise LLMProviderError(
            f"{provider.title()} rejected the request (HTTP {response.status_code}){suffix}.",
            response.status_code,
        )
    try:
        payload = response.json()
    except ValueError as exc:
        raise LLMProviderError(f"{provider.title()} returned an invalid response.") from exc

    answer = payload.get("output_text")
    if not answer:
        parts = []
        for item in payload.get("output", []):
            if item.get("type") != "message":
                continue
            for content in item.get("content", []):
                if content.get("type") == "output_text" and content.get("text"):
                    parts.append(content["text"])
        answer = "\n".join(parts)
    if not isinstance(answer, str) or not answer.strip():
        raise LLMProviderError(f"{provider.title()} returned no text output.")
    provider_label = "Groq" if provider == "groq" else "OpenAI"
    return {"provider": provider_label, "provider_key": provider,
            "model": selected_model, "answer": answer.strip()}


def test_provider(provider: str) -> Dict[str, Any]:
    try:
        check_tokens = 128 if provider == "groq" else 16
        result = generate_text(provider, "Respond with exactly OK.", max_output_tokens=check_tokens, temperature=0.0)
        return {"provider": provider, "configured": True, "reachable": True,
                "model": result["model"], "detail": f"{result['provider']} responded successfully."}
    except LLMConfigurationError as exc:
        return {"provider": provider, "configured": False, "reachable": False, "model": _settings(provider)[1] or None,
                "detail": str(exc)}
    except LLMProviderError as exc:
        key, model = _settings(provider)
        return {"provider": provider, "configured": bool(key and model), "reachable": False,
                "model": model or None, "detail": str(exc)}
