"""LLM adapter with OpenAI primary + Claude fallback using Emergent Universal key."""
import asyncio
import os
import json
import logging
import re
import uuid
import base64
from typing import Any

# Disable OpenAI SDK's internal retry-with-60s-backoff so litellm errors
# bubble up to our adapter immediately (we have our own retry layer below
# that's faster and aware of which errors are transient).
os.environ.setdefault("OPENAI_MAX_RETRIES", "0")

from emergentintegrations.llm.chat import LlmChat, UserMessage  # noqa: E402

logger = logging.getLogger(__name__)

EMERGENT_LLM_KEY = os.environ["EMERGENT_LLM_KEY"]

PROVIDER_CHAIN = [
    ("openai", "gpt-5.2"),
    ("anthropic", "claude-sonnet-4-5-20250929"),
]

DIAGRAM_MODEL = "gemini-3.1-flash-image-preview"

# Exponential backoff settings for transient upstream errors.
# We disable litellm's internal retries (num_retries=0) and use these for
# our smart retry layer instead. Each call fails within ~60s so 3 attempts
# × 2 providers worst-case = ~6 minutes (vs ~12-16 mins with internal retries).
RETRY_MAX_ATTEMPTS = 3  # per provider
RETRY_BASE_DELAY_SEC = 2.0
RETRY_BACKOFF = 2.0  # 2s, 4s, 8s


# Substrings that mark a TRANSIENT upstream error worth retrying. Anything
# else (auth, budget, content-policy, malformed request) fails fast so we
# move to the next provider quickly.
_TRANSIENT_MARKERS = (
    "502",
    "503",
    "504",
    "bad gateway",
    "service unavailable",
    "gateway timeout",
    "timed out",
    "timeout",
    "connection error",
    "connection reset",
    "internal server error",
    "remote disconnected",
    "rate limit",
    "rate_limit",
    "429",
    "overloaded",
)


def _is_transient(err: BaseException) -> bool:
    msg = str(err).lower()
    return any(marker in msg for marker in _TRANSIENT_MARKERS)


async def chat_complete(system_message: str, user_text: str) -> str:
    """Run chat completion with retries-per-provider then fall through.

    For each provider in PROVIDER_CHAIN we retry up to RETRY_MAX_ATTEMPTS
    times on TRANSIENT upstream errors (502/503/504/timeout/rate-limit) with
    exponential backoff. Non-transient errors (auth, budget, malformed) fail
    fast and we move to the next provider.

    IMPORTANT: emergentintegrations.LlmChat.send_message() is declared `async`
    but internally calls the SYNC litellm.completion(...) which blocks for
    60-90s on each call. Awaiting it directly freezes the entire FastAPI
    event loop — every other API request queues behind it and the ingress
    proxy 502s after its own 60s timeout. To prevent this we run each
    send_message call in a worker thread so the main loop stays free.
    """
    PER_CALL_TIMEOUT = 75.0
    last_err: Exception | None = None
    loop = asyncio.get_running_loop()

    for provider, model in PROVIDER_CHAIN:
        for attempt in range(1, RETRY_MAX_ATTEMPTS + 1):
            try:
                session_id = f"bodhi-{uuid.uuid4()}"
                chat = (
                    LlmChat(
                        api_key=EMERGENT_LLM_KEY,
                        session_id=session_id,
                        system_message=system_message,
                    )
                    .with_model(provider, model)
                    .with_params(num_retries=0, timeout=60, request_timeout=60)
                )
                msg = UserMessage(text=user_text)

                # Run the (sync-inside-async) call in a worker thread so the
                # main event loop is NOT blocked. The thread spins up its own
                # event loop with asyncio.run().
                def _sync_call(_chat=chat, _msg=msg):
                    return asyncio.run(_chat.send_message(_msg))

                response = await asyncio.wait_for(
                    loop.run_in_executor(None, _sync_call),
                    timeout=PER_CALL_TIMEOUT,
                )
                if response:
                    if attempt > 1:
                        logger.info(
                            f"LLM success with {provider}/{model} on attempt {attempt}"
                        )
                    else:
                        logger.info(f"LLM success with {provider}/{model}")
                    return response if isinstance(response, str) else str(response)
            except asyncio.TimeoutError:
                last_err = TimeoutError(
                    f"LLM call to {provider}/{model} exceeded {PER_CALL_TIMEOUT:.0f}s"
                )
                if attempt < RETRY_MAX_ATTEMPTS:
                    delay = RETRY_BASE_DELAY_SEC * (RETRY_BACKOFF ** (attempt - 1))
                    logger.warning(
                        f"LLM {provider}/{model} attempt {attempt}/{RETRY_MAX_ATTEMPTS} "
                        f"timed out, retry in {delay:.1f}s"
                    )
                    await asyncio.sleep(delay)
                    continue
                logger.warning(
                    f"LLM provider {provider}/{model} timed out (attempt {attempt})"
                )
                break
            except Exception as e:  # noqa: BLE001
                last_err = e
                transient = _is_transient(e)
                if transient and attempt < RETRY_MAX_ATTEMPTS:
                    delay = RETRY_BASE_DELAY_SEC * (RETRY_BACKOFF ** (attempt - 1))
                    logger.warning(
                        f"LLM {provider}/{model} attempt {attempt}/{RETRY_MAX_ATTEMPTS} "
                        f"transient error, retry in {delay:.1f}s: {e}"
                    )
                    await asyncio.sleep(delay)
                    continue
                logger.warning(
                    f"LLM provider {provider}/{model} failed (attempt {attempt}, "
                    f"transient={transient}): {e}"
                )
                break
    raise RuntimeError(f"All LLM providers failed: {last_err}")


async def generate_diagram(description: str) -> bytes | None:
    """Generate a clean B&W line diagram for an exam question. Returns PNG bytes
    or None on failure. Non-raising — diagrams are best-effort.

    Runs in a worker thread so the sync litellm call doesn't block the
    FastAPI event loop (see chat_complete for the same pattern).
    """
    try:
        session_id = f"bodhi-diag-{uuid.uuid4()}"
        chat = LlmChat(
            api_key=EMERGENT_LLM_KEY,
            session_id=session_id,
            system_message=(
                "You generate clean, minimal black-and-white line diagrams "
                "for exam papers. Use clear labels, simple geometric shapes, "
                "no color, white background."
            ),
        ).with_model("gemini", DIAGRAM_MODEL).with_params(
            modalities=["image", "text"], num_retries=0, timeout=60
        )
        prompt = (
            f"Create a simple, clean black-and-white line diagram for a school exam. "
            f"Subject/figure: {description}. "
            f"Requirements: white background, crisp black lines, minimal labels, "
            f"textbook/exam-paper style, no shading, no color, no watermark, no photo. "
            f"Keep it uncluttered and suitable for printing in an exam paper. "
            f"Each label must appear exactly once — never duplicate a label, and do not "
            f"repeat the same element or caption twice in the figure."
        )
        msg = UserMessage(text=prompt)
        loop = asyncio.get_running_loop()

        def _sync_call(_chat=chat, _msg=msg):
            return asyncio.run(_chat.send_message_multimodal_response(_msg))

        _text, images = await asyncio.wait_for(
            loop.run_in_executor(None, _sync_call),
            timeout=75.0,
        )
        if images:
            img_b64 = images[0]["data"]
            return base64.b64decode(img_b64)
        return None
    except Exception as e:  # noqa: BLE001
        logger.warning(f"Diagram generation failed for '{description[:40]}': {e}")
        return None


def parse_json_response(text: str) -> Any:
    """Extract a JSON payload from an LLM response, tolerating code fences,
    prose, and partial/truncated output (will salvage a complete answers array
    from a truncated solution response)."""
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

    # Salvage a truncated `answers` array (common with long step-by-step solutions)
    salvage = re.search(r'"answers"\s*:\s*\[(.*)', text, re.DOTALL)
    if salvage:
        body = salvage.group(1)
        # Split on top-level object boundaries and try parsing each
        items = []
        depth = 0
        start = None
        for i, ch in enumerate(body):
            if ch == "{":
                if depth == 0:
                    start = i
                depth += 1
            elif ch == "}":
                depth -= 1
                if depth == 0 and start is not None:
                    chunk = body[start : i + 1]
                    try:
                        items.append(json.loads(chunk))
                    except json.JSONDecodeError:
                        pass
                    start = None
        if items:
            return {"answers": items}

    raise ValueError(f"Could not parse JSON from: {text[:200]}")
