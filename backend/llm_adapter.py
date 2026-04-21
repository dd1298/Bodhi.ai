"""LLM adapter with OpenAI primary + Claude fallback using Emergent Universal key."""
import os
import json
import logging
import re
import uuid
import base64
from typing import Any

from emergentintegrations.llm.chat import LlmChat, UserMessage

logger = logging.getLogger(__name__)

EMERGENT_LLM_KEY = os.environ["EMERGENT_LLM_KEY"]

PROVIDER_CHAIN = [
    ("openai", "gpt-5.2"),
    ("anthropic", "claude-sonnet-4-5-20250929"),
]

DIAGRAM_MODEL = "gemini-3.1-flash-image-preview"


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


async def generate_diagram(description: str) -> bytes | None:
    """Generate a clean B&W line diagram for an exam question. Returns PNG bytes
    or None on failure. Non-raising — diagrams are best-effort."""
    try:
        session_id = f"qpgen-diag-{uuid.uuid4()}"
        chat = LlmChat(
            api_key=EMERGENT_LLM_KEY,
            session_id=session_id,
            system_message=(
                "You generate clean, minimal black-and-white line diagrams "
                "for exam papers. Use clear labels, simple geometric shapes, "
                "no color, white background."
            ),
        ).with_model("gemini", DIAGRAM_MODEL).with_params(modalities=["image", "text"])
        prompt = (
            f"Create a simple, clean black-and-white line diagram for a school exam. "
            f"Subject/figure: {description}. "
            f"Requirements: white background, crisp black lines, minimal labels, "
            f"textbook/exam-paper style, no shading, no color, no watermark, no photo. "
            f"Keep it uncluttered and suitable for printing in an exam paper."
        )
        msg = UserMessage(text=prompt)
        _text, images = await chat.send_message_multimodal_response(msg)
        if images:
            img_b64 = images[0]["data"]
            return base64.b64decode(img_b64)
        return None
    except Exception as e:  # noqa: BLE001
        logger.warning(f"Diagram generation failed for '{description[:40]}': {e}")
        return None


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
