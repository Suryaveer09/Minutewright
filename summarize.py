"""Summarize a transcript with the bundled local LLM (see llm.py).

No external services, no Ollama: the engine runs in-process and the model
weights are downloaded by the app itself on first use.
"""

import llm

MAX_CHARS = 16000  # CPU prompt ingestion is the slow part; keep summaries ~1-2 min.
                   # Chunked (map-reduce) summarization for full-length
                   # transcripts is a documented roadmap item.

SYSTEM = """You write meeting minutes from raw transcripts. The transcript comes
from automatic speech recognition, so ignore small errors and filler.

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

Do not invent details that are not in the transcript."""


def summarize(transcript: str) -> str:
    messages = [
        {"role": "system", "content": SYSTEM},
        {"role": "user", "content": "Transcript:\n" + transcript[:MAX_CHARS]},
    ]
    return llm.chat_completion(messages, max_tokens=800, temperature=0.3)