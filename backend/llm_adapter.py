"""LLM adapter with OpenAI primary + Claude fallback using Emergent Universal key."""
import os
import json
import logging
import re
import uuid
from typing import Any

from emergentintegrations.llm.chat import LlmChat, UserMessage

logger = logging.getLogger(__name__)

EMERGENT_LLM_KEY = os.environ["EMERGENT_LLM_KEY"]

PROVIDER_CHAIN = [
    ("openai", "gpt-5.2"),
    ("anthropic", "claude-sonnet-4-5-20250929"),
]


async def chat_complete(system_message: str, user_text: str) -> str:
    """Run chat completion with fallback through provider chain.

    Raises RuntimeError if all providers fail.
    """
    last_err: Exception | None = None
    for provider, model in PROVIDER_CHAIN:
        try:
            session_id = f"qpgen-{uuid.uuid4()}"
            chat = LlmChat(
                api_key=EMERGENT_LLM_KEY,
                session_id=session_id,
                system_message=system_message,
            ).with_model(provider, model)
            msg = UserMessage(text=user_text)
            response = await chat.send_message(msg)
            if response:
                logger.info(f"LLM success with {provider}/{model}")
                return response if isinstance(response, str) else str(response)
        except Exception as e:  # noqa: BLE001
            logger.warning(f"LLM provider {provider}/{model} failed: {e}")
            last_err = e
            continue
    raise RuntimeError(f"All LLM providers failed: {last_err}")


def parse_json_response(text: str) -> Any:
    """Extract a JSON payload from an LLM response, tolerating code fences and prose."""
    if not text:
        raise ValueError("Empty LLM response")

    # Strip code fences
    fenced = re.search(r"```(?:json)?\s*(.*?)```", text, re.DOTALL)
    if fenced:
        text = fenced.group(1)

    text = text.strip()

    # Direct parse
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        pass

    # Greedy object / array match
    for pattern in (r"\{[\s\S]*\}", r"\[[\s\S]*\]"):
        m = re.search(pattern, text)
        if m:
            try:
                return json.loads(m.group(0))
            except json.JSONDecodeError:
                continue

    raise ValueError(f"Could not parse JSON from: {text[:200]}")
