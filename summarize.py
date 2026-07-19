"""Summarize a transcript with a local LLM served by Ollama (ollama.com).

Fully optional: the app works without it. When Ollama isn't running or has
no models, SummaryError carries an actionable, user-facing message that the
UI shows verbatim - so keep those messages helpful, not technical.

This module is also the Ollama plumbing that Phase 8's chat feature reuses.
"""

import os

import requests

OLLAMA_URL = os.environ.get("OLLAMA_URL", "http://localhost:11434")
PREFERRED = ["llama3.2", "llama3.1", "qwen2.5", "gemma", "mistral", "phi"]
MAX_CHARS = 24000  # keep the prompt within a small local model's context


class SummaryError(Exception):
    """Raised with a user-facing, actionable message."""


PROMPT = """You are writing meeting minutes from a raw transcript. The transcript
comes from automatic speech recognition, so ignore small errors and filler.

Write markdown with exactly these sections:
## Overview
Two or three sentences on what the meeting was about.
## Key points
Bulleted list of the main things discussed.
## Decisions
Bulleted list of decisions that were made. Write "None mentioned." if none.
## Action items
Bulleted list of tasks, with owners and deadlines when they were mentioned.
Write "None mentioned." if none.

Do not invent details that are not in the transcript.

Transcript:
{transcript}
"""


def pick_model() -> str:
    """Find a usable Ollama model, or raise SummaryError telling the user
    exactly what to do about it."""
    override = os.environ.get("SUMMARY_MODEL")
    try:
        resp = requests.get(f"{OLLAMA_URL}/api/tags", timeout=4)
        resp.raise_for_status()
    except requests.RequestException:
        raise SummaryError(
            "Ollama isn't running. Install it from ollama.com, run "
            "'ollama pull llama3.2:3b' once, then try again."
        )
    names = [m.get("name", "") for m in resp.json().get("models", [])]
    if override:
        return override
    if not names:
        raise SummaryError(
            "Ollama is running but has no models. Run 'ollama pull llama3.2:3b' first."
        )
    for prefix in PREFERRED:
        for name in names:
            if name.startswith(prefix):
                return name
    return names[0]


def summarize(transcript: str) -> str:
    model = pick_model()
    try:
        resp = requests.post(
            f"{OLLAMA_URL}/api/generate",
            json={
                "model": model,
                "prompt": PROMPT.format(transcript=transcript[:MAX_CHARS]),
                "stream": False,
            },
            timeout=900,
        )
        resp.raise_for_status()
    except requests.RequestException as exc:
        raise SummaryError(f"Ollama request failed: {exc}")

    result = resp.json().get("response", "").strip()
    if not result:
        raise SummaryError("Ollama returned an empty reply - try a different model.")
    return result