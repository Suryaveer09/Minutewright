"""In-process LLM engine for summaries and chat (llama-cpp-python).

Replaces Ollama so end users install NOTHING extra: the engine ships
inside the app, and the model weights (~2 GB GGUF) are downloaded BY the
app on first use with a progress bar - the same pattern the Whisper model
already uses. Inference runs on CPU so it works on every machine; GPU
offload is a roadmap enhancement.

States exposed to the UI via get_status():
  missing -> downloading (with %) -> ready   (or error, retryable)
"loading" appears briefly the first time inference actually runs, while
the weights are read into RAM.
"""

import os
import threading
from pathlib import Path

import psutil
import requests

from paths import data_dir

MODEL_NAME = "Llama-3.2-3B-Instruct-Q4_K_M.gguf"
MODEL_URL = (
    "https://huggingface.co/bartowski/Llama-3.2-3B-Instruct-GGUF"
    "/resolve/main/Llama-3.2-3B-Instruct-Q4_K_M.gguf"
)
MODEL_SIZE_BYTES = 2_020_000_000  # ~2.02 GB, fallback if no Content-Length

MODELS_DIR = data_dir() / "models"   # dev: project folder; exe: %LOCALAPPDATA%\Minutewright
MODEL_PATH = MODELS_DIR / MODEL_NAME

N_CTX = 8192          # transcript (~4k tokens) + history + answer fits
MAX_TOKENS = 800


class LLMError(Exception):
    """User-facing, actionable message - the UI shows it verbatim."""


class LLMNotReady(LLMError):
    pass


_state_lock = threading.Lock()
_state = {"state": "missing", "downloaded": 0, "total": MODEL_SIZE_BYTES, "error": None}

_load_lock = threading.Lock()
_infer_lock = threading.Lock()   # llama.cpp instances are not thread-safe
_llm = None
_loading = False


def _set(**kw):
    with _state_lock:
        _state.update(kw)


def get_status() -> dict:
    with _state_lock:
        s = dict(_state)
    if _llm is not None:
        s["state"] = "ready"
    elif _loading:
        s["state"] = "loading"
    elif s["state"] not in ("downloading", "error") and MODEL_PATH.exists():
        s["state"] = "ready"
    total = s["total"] or MODEL_SIZE_BYTES
    s["progress"] = round(min(100.0, s["downloaded"] / total * 100), 1)
    s["model"] = MODEL_NAME
    s["size_mb"] = round(total / 1_000_000)
    return s


def start_download():
    """Idempotent: safe to call when already downloading or already done."""
    with _state_lock:
        if _state["state"] == "downloading":
            return
    if MODEL_PATH.exists():
        _set(state="ready", error=None)
        return
    _set(state="downloading", downloaded=0, error=None)
    threading.Thread(target=_download, daemon=True).start()


def _download():
    MODELS_DIR.mkdir(parents=True, exist_ok=True)
    part = MODEL_PATH.with_suffix(".gguf.part")
    try:
        with requests.get(MODEL_URL, stream=True, timeout=(10, 120)) as resp:
            resp.raise_for_status()
            total = int(resp.headers.get("content-length") or MODEL_SIZE_BYTES)
            _set(total=total)
            done = 0
            with open(part, "wb") as f:
                for chunk in resp.iter_content(chunk_size=1024 * 1024):
                    if chunk:
                        f.write(chunk)
                        done += len(chunk)
                        _set(downloaded=done)
        os.replace(part, MODEL_PATH)  # atomic: half-downloads never count
        _set(state="ready", error=None)
    except Exception as exc:
        part.unlink(missing_ok=True)
        _set(
            state="error",
            error=f"Model download failed ({exc}). Check your internet connection and try again.",
        )


def _ensure_loaded():
    global _llm, _loading
    with _load_lock:
        if _llm is not None:
            return
        if not MODEL_PATH.exists():
            raise LLMNotReady(
                "The AI model isn't downloaded yet - use the download button "
                "in the Summary or Chat tab (one-time, ~2 GB)."
            )
        _loading = True
        try:
            from llama_cpp import Llama

            threads = psutil.cpu_count(logical=False) or (os.cpu_count() or 8) // 2
            _llm = Llama(
                model_path=str(MODEL_PATH),
                n_ctx=N_CTX,
                n_threads=max(2, threads),
                n_gpu_layers=0,   # CPU everywhere for v1; GPU offload is roadmap
                verbose=False,
            )
            try:
                # Cache the constant prefix (system prompt + transcript) so
                # follow-up chat turns don't re-ingest the whole transcript.
                from llama_cpp import LlamaRAMCache

                _llm.set_cache(LlamaRAMCache())
            except Exception:
                pass  # cache is an optimization, never a requirement
        except LLMError:
            raise
        except Exception as exc:
            _llm = None
            raise LLMError(f"Could not load the AI model: {exc}")
        finally:
            _loading = False


def chat_completion(messages: list, max_tokens: int = MAX_TOKENS, temperature: float = 0.4) -> str:
    """messages: [{"role": "system"|"user"|"assistant", "content": str}, ...]"""
    _ensure_loaded()
    try:
        with _infer_lock:   # one request at a time into the single instance
            out = _llm.create_chat_completion(
                messages=messages, max_tokens=max_tokens, temperature=temperature
            )
        reply = out["choices"][0]["message"]["content"].strip()
    except Exception as exc:
        raise LLMError(f"AI generation failed: {exc}")
    if not reply:
        raise LLMError("The AI model returned an empty reply - please try again.")
    return reply