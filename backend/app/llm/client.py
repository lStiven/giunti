"""The only place that talks to model providers, through LiteLLM.

Messages are provider-neutral (`Message` with text and image parts); `LiteLLMBackend` turns them
into LiteLLM's OpenAI-style format, applies each model's options and maps the response, or the
error, to `Completion` / `ModelCallError`. Retries are not done here: the engine decides them.
"""

import base64
import logging
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from typing import Any, Literal, Protocol

import litellm
from litellm.types.utils import Choices, ModelResponse, Usage

from app.core.config import LLMModelConfig
from app.llm.errors import FailureKind, ModelCallError, classify_exception

# Rough upper bounds used only to skip models whose context window is clearly too small.
CHARS_PER_TOKEN = 3
TOKENS_PER_IMAGE = 1_600

_REFUSAL_FINISH_REASONS = frozenset({"content_filter", "guardrail_intervened"})

logger = logging.getLogger(__name__)


@dataclass(frozen=True, slots=True)
class TextPart:
    text: str


@dataclass(frozen=True, slots=True)
class ImagePart:
    """A PNG image. `required` images carry content that exists nowhere else (a scanned page);
    optional ones only add visual context and are dropped for models without vision."""

    png: bytes
    required: bool = True


type ContentPart = TextPart | ImagePart


@dataclass(frozen=True, slots=True)
class Message:
    role: Literal["system", "user", "assistant"]
    parts: tuple[ContentPart, ...]

    @classmethod
    def text(cls, role: Literal["system", "user", "assistant"], text: str) -> "Message":
        return cls(role, (TextPart(text),))


@dataclass(frozen=True, slots=True)
class Completion:
    text: str
    input_tokens: int = 0
    output_tokens: int = 0


class CompletionBackend(Protocol):
    async def complete(self, model: LLMModelConfig, messages: Sequence[Message]) -> Completion:
        """Returns the model's answer or raises `ModelCallError`."""
        ...


class LiteLLMBackend:
    def __init__(self, *, timeout_s: float, api_keys: Mapping[str, str]) -> None:
        self._timeout_s = timeout_s
        self._api_keys = dict(api_keys)

    async def complete(self, model: LLMModelConfig, messages: Sequence[Message]) -> Completion:
        try:
            response = await litellm.acompletion(**self._request(model, messages))
        except Exception as exc:
            raise classify_exception(exc) from exc
        return _completion_from(response)

    def _request(self, model: LLMModelConfig, messages: Sequence[Message]) -> dict[str, Any]:
        request: dict[str, Any] = {
            "model": model.model,
            "messages": [to_openai_message(message) for message in messages],
            "max_tokens": model.max_output_tokens,
            "timeout": self._timeout_s,
            "num_retries": 0,
            "drop_params": True,
        }
        api_key = self._api_keys.get(model.provider)
        if api_key:
            request["api_key"] = api_key
        if model.temperature is not None:
            request["temperature"] = model.temperature
        if model.reasoning_effort is not None:
            request["reasoning_effort"] = model.reasoning_effort
        if model.json_mode and _supports_json_mode(model.model):
            request["response_format"] = {"type": "json_object"}
        return request


def to_openai_message(message: Message) -> dict[str, Any]:
    if all(isinstance(part, TextPart) for part in message.parts):
        text = "\n\n".join(part.text for part in message.parts if isinstance(part, TextPart))
        return {"role": message.role, "content": text}
    content: list[dict[str, Any]] = []
    for part in message.parts:
        if isinstance(part, TextPart):
            content.append({"type": "text", "text": part.text})
        else:
            encoded = base64.b64encode(part.png).decode("ascii")
            url = f"data:image/png;base64,{encoded}"
            content.append({"type": "image_url", "image_url": {"url": url}})
    return {"role": message.role, "content": content}


def _completion_from(response: object) -> Completion:
    if not isinstance(response, ModelResponse) or not response.choices:
        raise ModelCallError(FailureKind.TRANSIENT, "The provider returned no choices.")
    choice = response.choices[0]
    if not isinstance(choice, Choices):
        raise ModelCallError(FailureKind.TRANSIENT, "Unexpected streaming response.")

    if choice.finish_reason == "length":
        raise ModelCallError(FailureKind.TRUNCATED, "The output token limit was reached.")
    if choice.finish_reason in _REFUSAL_FINISH_REASONS:
        raise ModelCallError(FailureKind.REFUSED, f"Finish reason: {choice.finish_reason}.")
    text = choice.message.content or ""
    if not text.strip():
        detail = f"Empty answer (finish reason: {choice.finish_reason})."
        raise ModelCallError(FailureKind.REFUSED, detail)

    usage = getattr(response, "usage", None)
    if isinstance(usage, Usage):
        return Completion(text, usage.prompt_tokens or 0, usage.completion_tokens or 0)
    return Completion(text)


def _supports_json_mode(model: str) -> bool:
    try:
        return "response_format" in (litellm.get_supported_openai_params(model) or [])
    except Exception:  # noqa: BLE001 - unknown models raise provider-specific errors
        return False


def context_window(model: LLMModelConfig) -> int | None:
    """The model's input token limit, from the configuration or LiteLLM's model map."""
    if model.max_input_tokens is not None:
        return model.max_input_tokens
    try:
        info = litellm.get_model_info(model.model)
    except Exception:  # noqa: BLE001 - LiteLLM raises a generic Exception for unknown models
        return None
    value = info.get("max_input_tokens")
    return value if isinstance(value, int) else None


def estimate_tokens(messages: Sequence[Message]) -> int:
    total = 0
    for message in messages:
        for part in message.parts:
            if isinstance(part, TextPart):
                total += len(part.text) // CHARS_PER_TOKEN
            else:
                total += TOKENS_PER_IMAGE
    return total
