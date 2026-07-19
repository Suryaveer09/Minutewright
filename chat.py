"""Chat with a meeting transcript using the same local LLM as summaries.

Design decision (v1): no RAG. An hour-long meeting transcript is ~8-10k
words and fits in a small local model's context window, so the whole
transcript rides in the system prompt and the conversation follows it.
Embeddings + a vector store only become worth it for cross-meeting search.

The server stays stateless: the UI sends the running history with every
request - consistent with everything else in this app being plain files.
Reuses pick_model / OLLAMA_URL / SummaryError from summarize.py.
"""

import requests

from summarize import MAX_CHARS, OLLAMA_URL, SummaryError, pick_model

SYSTEM = """You are Minutewright's meeting assistant. Answer questions using ONLY
the meeting transcript below. The transcript comes from automatic speech
recognition, so tolerate small errors and filler words.

Rules:
- If the answer is not in the transcript, say plainly that it wasn't discussed.
- Do not invent names, numbers, dates, or decisions.
- Be concise: a short paragraph or a few bullets.

Transcript:
{transcript}
"""

MAX_HISTORY = 12  # keep context bounded on small local models


def chat(transcript: str, history: list, message: str) -> str:
    """history: [{"role": "user"|"assistant", "content": str}, ...]"""
    model = pick_model()

    messages = [
        {"role": "system", "content": SYSTEM.format(transcript=transcript[:MAX_CHARS])}
    ]
    for turn in history[-MAX_HISTORY:]:
        role = turn.get("role")
        content = str(turn.get("content", "")).strip()
        if role in ("user", "assistant") and content:
            messages.append({"role": role, "content": content})
    messages.append({"role": "user", "content": message})

    try:
        resp = requests.post(
            f"{OLLAMA_URL}/api/chat",
            json={"model": model, "messages": messages, "stream": False},
            timeout=900,
        )
        resp.raise_for_status()
    except requests.RequestException as exc:
        raise SummaryError(f"Ollama request failed: {exc}")

    reply = resp.json().get("message", {}).get("content", "").strip()
    if not reply:
        raise SummaryError("Ollama returned an empty reply - try a different model.")
    return reply