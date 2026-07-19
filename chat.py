"""Chat with a meeting transcript using the bundled local LLM (see llm.py).

Design decision (v1): no RAG. The transcript rides in the system prompt
and the conversation follows it; the server stays stateless and the UI
sends the running history with every request. llm.py's prefix cache means
follow-up questions don't re-ingest the whole transcript on every turn.
"""

import llm
from summarize import MAX_CHARS

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

MAX_HISTORY = 12  # keep context bounded on a small local model


def chat(transcript: str, history: list, message: str) -> str:
    """history: [{"role": "user"|"assistant", "content": str}, ...]"""
    messages = [
        {"role": "system", "content": SYSTEM.format(transcript=transcript[:MAX_CHARS])}
    ]
    for turn in history[-MAX_HISTORY:]:
        role = turn.get("role")
        content = str(turn.get("content", "")).strip()
        if role in ("user", "assistant") and content:
            messages.append({"role": role, "content": content})
    messages.append({"role": "user", "content": message})

    return llm.chat_completion(messages, max_tokens=500, temperature=0.4)