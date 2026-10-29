"""
Transformers Local LLM Provider — runs entirely in-process, no server needed.
Loads a model once on first use, then keeps it warm for subsequent turns.
"""
from __future__ import annotations

import asyncio
import json
from importlib.util import find_spec
from typing import Any, AsyncIterator, Optional

try:
    from transformers import AutoModelForCausalLM, AutoTokenizer
    import torch
    HAS_TRANSFORMERS = True
except ImportError:
    HAS_TRANSFORMERS = False

from .base import DEFAULT_CAPS, Field, FunctionCall

# Models that work well on CPU with reasonable memory (~2-4GB)
# Phi-3-mini is the best balance of quality/size for local CPU inference
RECOMMENDED_MODELS = (
    "microsoft/Phi-3-mini-4k-instruct",
    "microsoft/Phi-3.5-mini-instruct",
    "TinyLlama/TinyLlama-1.1B-Chat-v1.0",
    "microsoft/Phi-2",
)

DEFAULT_MODEL = "microsoft/Phi-3-mini-4k-instruct"

# ─────────────────────────────────────────────────────────────────────────────
# Message conversion (same as OpenAI-compat provider)
# ─────────────────────────────────────────────────────────────────────────────
def parts_to_transformers(parts: list) -> str:
    """Gemini parts -> plain text prompt for transformers."""
    texts = []
    for p in parts or []:
        if isinstance(p, str):
            texts.append(p)
        elif isinstance(p, dict):
            if p.get("type") == "text":
                texts.append(p.get("text", ""))
            # Images not supported in this local provider
    return "\n".join(texts)


class _ToolCallBuffer:
    """Reassembles tool calls from streaming deltas (same as openai_compat)."""
    def __init__(self):
        self._slots: dict[int, dict] = {}

    def feed(self, deltas: list) -> None:
        for d in deltas or []:
            idx = d.get("index", 0)
            slot = self._slots.setdefault(idx, {"id": "", "name": "", "args": ""})
            if d.get("id"):
                slot["id"] = d["id"]
            fn = d.get("function") or {}
            if fn.get("name"):
                slot["name"] += fn["name"]
            if fn.get("arguments"):
                slot["args"] += fn["arguments"]

    def drain(self) -> list[FunctionCall]:
        calls = []
        for idx in sorted(self._slots):
            slot = self._slots[idx]
            if not slot["name"]:
                continue
            raw = slot["args"].strip() or "{}"
            try:
                args = json.loads(raw)
            except Exception:
                args = {}
                if "{" in raw and "}" in raw:
                    try:
                        args = json.loads(raw[raw.find("{"):raw.rfind("}") + 1])
                    except Exception:
                        args = {"value": raw}
            if not isinstance(args, dict):
                args = {"value": args}
            calls.append(FunctionCall(
                id=slot["id"] or f"call_{idx}",
                name=slot["name"],
                args=args
            ))
        self._slots.clear()
        return calls


# ─────────────────────────────────────────────────────────────────────────────
# The provider
# ─────────────────────────────────────────────────────────────────────────────
class TransformersLLM:
    def __init__(self, cfg: dict):
        if not HAS_TRANSFORMERS:
            raise RuntimeError("transformers/torch not installed. pip install transformers torch accelerate")

        self.model_id = (cfg.get("model_id") or DEFAULT_MODEL).strip()
        self._model = None
        self._tokenizer = None
        self._device = "cuda" if torch.cuda.is_available() else "cpu"
        self._load_lock = asyncio.Lock()
        self._loaded = False

        # Capabilities
        self.caps = dict(DEFAULT_CAPS)
        self.caps.update({
            "tools": True,
            "tool_format": "prompt",  # We use prompt-based tool calling
            "max_tools": 14,
            "max_tool_chars": 12000,
        })

        # System prompt + tool declarations (set via config)
        self._system = ""
        self._declarations: list = []
        self._tool_names: set = set()

    # ── Configuration from pipeline engine ─────────────────────────────────────
    def _read_config(self, config) -> None:
        """Read system prompt and tool declarations from the Live config."""
        si = getattr(config, "system_instruction", None)
        if si:
            self._system = si if isinstance(si, str) else str(si)

        decls: list = []
        for group in (getattr(config, "tools", None) or []):
            fd = (group.get("function_declarations") if isinstance(group, dict)
                  else getattr(group, "function_declarations", None))
            if fd:
                decls.extend(fd)

        # Store declarations for prompt-based tool calling
        self._declarations = decls
        self._tool_names = {d.get("name") for d in decls if isinstance(d, dict)}

        # Build tool descriptions for the system prompt
        if decls:
            tool_desc = self._build_tool_prompt(decls)
            self._system = (self._system + "\n\n" + tool_desc).strip()

    def _build_tool_prompt(self, decls: list) -> str:
        """Build tool descriptions for prompt-based calling."""
        lines = [
            "You have access to the following tools. When you need to use a tool,",
            "respond with a JSON object in this exact format:",
            '{"tool": "tool_name", "args": {"arg1": "value1", "arg2": "value2"}}',
            "Only output the JSON, nothing else. Wait for the tool result before continuing.",
            "",
            "Available tools:"
        ]
        for d in decls:
            if not isinstance(d, dict):
                continue
            name = d.get("name", "")
            desc = d.get("description", "")
            params = d.get("parameters", {})
            props = params.get("properties", {}) if isinstance(params, dict) else {}
            required = params.get("required", []) if isinstance(params, dict) else []
            prop_strs = []
            for pname, pinfo in props.items():
                if not isinstance(pinfo, dict):
                    continue
                ptype = pinfo.get("type", "string")
                pdesc = pinfo.get("description", "")
                req = " (required)" if pname in required else ""
                prop_strs.append(f"  {pname} ({ptype}){req}: {pdesc}")
            lines.append(f"  • {name}: {desc}")
            lines.extend(prop_strs)
            lines.append("")
        return "\n".join(lines)

    # ── Model loading ──────────────────────────────────────────────────────────
    async def _ensure_loaded(self, log=None) -> None:
        if self._loaded:
            return
        async with self._load_lock:
            if self._loaded:
                return
            if log:
                log(f"SYS: loading {self.model_id} on {self._device} (first time downloads ~2.7 GB)")
            try:
                # Load in thread to not block event loop
                await asyncio.to_thread(self._load_blocking)
                self._loaded = True
                if log:
                    log(f"SYS: {self.model_id} loaded on {self._device}")
            except Exception as e:
                if log:
                    log(f"SYS: failed to load model: {e}")
                raise

    def _load_blocking(self) -> None:
        self._tokenizer = AutoTokenizer.from_pretrained(self.model_id, trust_remote_code=True)

        # Use eager attention implementation to avoid flash-attention issues
        # Don't pass a custom config - let the model load its own
        model_kwargs = {
            "torch_dtype": torch.float16 if self._device == "cuda" else torch.float32,
            "device_map": "auto",
            "trust_remote_code": True,
            "low_cpu_mem_usage": True,
            "attn_implementation": "eager",  # Avoid flash-attention issues
        }

        self._model = AutoModelForCausalLM.from_pretrained(
            self.model_id,
            **model_kwargs,
        )
        self._model.eval()

    # ── Generation ─────────────────────────────────────────────────────────────
    def _build_messages(self) -> list[dict]:
        """Build message list for the model."""
        msgs = []
        if self._system:
            msgs.append({"role": "system", "content": self._system})
        # Note: history management is done by the pipeline engine
        return msgs

    def _apply_chat_template(self, messages: list[dict]) -> str:
        """Apply the model's chat template."""
        if self._tokenizer.chat_template:
            return self._tokenizer.apply_chat_template(
                messages, tokenize=False, add_generation_prompt=True
            )
        # Fallback for models without chat template
        parts = []
        for m in messages:
            role = m.get("role", "user")
            content = m.get("content", "")
            if role == "system":
                parts.append(f"<|system|>\n{content}")
            elif role == "user":
                parts.append(f"<|user|>\n{content}")
            elif role == "assistant":
                parts.append(f"<|assistant|>\n{content}")
            elif role == "tool":
                parts.append(f"<|tool|>\n{content}")
        parts.append("<|assistant|>")
        return "\n".join(parts)

    async def chat(self, messages: list[dict], tools: list[dict] | None = None,
                   *, stream: bool = True, temperature: float | None = None) -> AsyncIterator[dict]:
        """Stream tokens from the local model."""
        await self._ensure_loaded()

        # Update tool declarations if they changed
        if tools and self.caps["tools"]:
            new_decls = [t.get("function", {}) for t in tools if t.get("type") == "function"]
            new_names = {d.get("name") for d in new_decls}
            if new_names != self._tool_names:
                self._declarations = new_decls
                self._tool_names = new_names
                if self._system:
                    # Rebuild system with new tools
                    tool_desc = self._build_tool_prompt(new_decls)
                    base = self._system.split("\n\nAvailable tools:")[0]
                    self._system = (base + "\n\n" + tool_desc).strip()

        # Build prompt
        prompt = self._apply_chat_template(messages)

        # Generation config
        gen_kwargs = {
            "max_new_tokens": 512,
            "temperature": temperature if temperature is not None else 0.7,
            "top_p": 0.9,
            "do_sample": True,
            "pad_token_id": self._tokenizer.eos_token_id,
            "eos_token_id": self._tokenizer.eos_token_id,
        }

        # Tokenize
        input_ids = self._tokenizer(prompt, return_tensors="pt", truncation=True, max_length=4096).input_ids
        input_ids = input_ids.to(self._model.device)

        # Stream generation
        buf = _ToolCallBuffer()
        yielded_text = ""

        # Use streamer for real-time tokens
        from transformers import TextIteratorStreamer
        from threading import Thread

        streamer = TextIteratorStreamer(self._tokenizer, skip_prompt=True, skip_special_tokens=True)

        gen_kwargs["streamer"] = streamer
        gen_kwargs["input_ids"] = input_ids

        # Run generation in thread
        thread = Thread(target=self._model.generate, kwargs=gen_kwargs)
        thread.start()

        try:
            for token in streamer:
                if not token:
                    continue
                yielded_text += token
                # Check for tool calls in the streamed text
                if self.caps["tools"] and "{" in yielded_text and "}" in yielded_text:
                    # Try to parse tool calls
                    pass  # We'll parse at the end for simplicity
                yield {"text": token}

            thread.join()

            # Check for tool calls in the final output
            if self.caps["tools"]:
                parsed = self._parse_tool_calls(yielded_text)
                if parsed:
                    yield {"tool_calls": parsed}

        except Exception as e:
            yield {"text": f"[Transformers Error] {e}"}

    def _parse_tool_calls(self, text: str) -> list[FunctionCall]:
        """Parse tool calls from model output."""
        calls = []
        # Look for JSON tool calls
        import re
        json_matches = re.findall(r'\{[^}]*"tool"[^}]*\}', text)
        for match in json_matches:
            try:
                obj = json.loads(match)
                name = obj.get("tool", "").strip()
                if name in self._tool_names:
                    args = obj.get("args", {}) if isinstance(obj.get("args"), dict) else {}
                    calls.append(FunctionCall(
                        id=f"call_{name}",
                        name=name,
                        args=args
                    ))
            except Exception:
                continue
        return calls

    # ── For settings panel ─────────────────────────────────────────────────────
    def probe(self) -> tuple[bool, str]:
        """Check if provider is working."""
        if not HAS_TRANSFORMERS:
            return False, "transformers/torch not installed"
        try:
            # Quick check - just verify imports work
            return True, f"Ready (model: {self.model_id}, device: {self._device})"
        except Exception as e:
            return False, str(e)


def _make(cfg: dict) -> TransformersLLM:
    return TransformersLLM(cfg)


PROVIDER = {
    "id": "transformers",
    "kind": "llm",
    "label": "Transformers (local)",
    "hint": "Runs entirely in-process on this machine — no server, no API key",
    "requires": ("transformers", "torch", "accelerate"),
    "install": "pip install transformers torch accelerate",
    "catalog": (
        {"id": "phi3-mini", "label": "Phi-3-mini-4k-instruct",
         "note": "Microsoft · 3.8B params · ~2.7 GB · CPU-friendly", "local": True,
         "values": {"model_id": "microsoft/Phi-3-mini-4k-instruct"}},
        {"id": "phi35-mini", "label": "Phi-3.5-mini-instruct",
         "note": "Microsoft · 3.8B params · improved · ~2.7 GB", "local": True,
         "values": {"model_id": "microsoft/Phi-3.5-mini-instruct"}},
        {"id": "tinyllama", "label": "TinyLlama-1.1B-Chat",
         "note": "TinyLlama · 1.1B params · ~0.6 GB · fastest", "local": True,
         "values": {"model_id": "TinyLlama/TinyLlama-1.1B-Chat-v1.0"}},
        {"id": "phi2", "label": "Phi-2",
         "note": "Microsoft · 2.7B params · ~1.5 GB · good for code", "local": True,
         "values": {"model_id": "microsoft/Phi-2"}},
        {"id": "custom", "label": "Custom model",
         "note": "Any Hugging Face model ID", "local": True,
         "values": {}},
    ),
    "needs": (
        Field("model_id", "Model", kind="choice", choices=tuple(m for m in RECOMMENDED_MODELS) + ("custom",),
              default=DEFAULT_MODEL,
              hint="Model from Hugging Face. First run downloads it."),
    ),
    "caps": {"tools": True, "tool_format": "prompt"},
    "factory": _make,
}


def available() -> bool:
    return HAS_TRANSFORMERS