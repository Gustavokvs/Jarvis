"""
Local LLM Provider - Supports Ollama, llama.cpp, or direct transformers
For pipeline mode when not using Gemini Live.
"""
import asyncio
import json
from pathlib import Path
from typing import Optional, AsyncGenerator, Dict, Any, List
import aiohttp

try:
    from transformers import AutoModelForCausalLM, AutoTokenizer
    import torch
    HAS_TRANSFORMERS = True
except ImportError:
    HAS_TRANSFORMERS = False


class OllamaProvider:
    """Ollama local LLM - easy to run, many models available."""

    def __init__(self, base_url: str = "http://localhost:11434", model: str = "llama3.1:8b"):
        self.base_url = base_url.rstrip("/")
        self.model = model
        self._session: Optional[aiohttp.ClientSession] = None

    async def _get_session(self) -> aiohttp.ClientSession:
        if self._session is None or self._session.closed:
            self._session = aiohttp.ClientSession()
        return self._session

    async def is_available(self) -> bool:
        try:
            session = await self._get_session()
            async with session.get(f"{self.base_url}/api/tags") as resp:
                return resp.status == 200
        except:
            return False

    async def list_models(self) -> List[str]:
        try:
            session = await self._get_session()
            async with session.get(f"{self.base_url}/api/tags") as resp:
                data = await resp.json()
                return [m["name"] for m in data.get("models", [])]
        except:
            return []

    async def generate(self, prompt: str, system: str = "", stream: bool = True) -> AsyncGenerator[str, None]:
        """Generate response from Ollama."""
        session = await self._get_session()

        payload = {
            "model": self.model,
            "prompt": prompt,
            "system": system,
            "stream": stream,
            "options": {
                "temperature": 0.7,
                "top_p": 0.9,
                "num_ctx": 8192,
            }
        }

        try:
            async with session.post(f"{self.base_url}/api/generate", json=payload) as resp:
                if resp.status != 200:
                    error = await resp.text()
                    yield f"[Ollama Error] {error}"
                    return

                if stream:
                    async for line in resp.content:
                        if line:
                            try:
                                data = json.loads(line)
                                if "response" in data:
                                    yield data["response"]
                                if data.get("done"):
                                    break
                            except:
                                pass
                else:
                    data = await resp.json()
                    yield data.get("response", "")
        except Exception as e:
            yield f"[Ollama Error] {e}"

    async def chat(self, messages: List[Dict[str, str]], stream: bool = True) -> AsyncGenerator[str, None]:
        """Chat completion with message history."""
        session = await self._get_session()

        payload = {
            "model": self.model,
            "messages": messages,
            "stream": stream,
            "options": {
                "temperature": 0.7,
                "top_p": 0.9,
                "num_ctx": 8192,
            }
        }

        try:
            async with session.post(f"{self.base_url}/api/chat", json=payload) as resp:
                if resp.status != 200:
                    error = await resp.text()
                    yield f"[Ollama Error] {error}"
                    return

                if stream:
                    async for line in resp.content:
                        if line:
                            try:
                                data = json.loads(line)
                                if "message" in data and "content" in data["message"]:
                                    yield data["message"]["content"]
                                if data.get("done"):
                                    break
                            except:
                                pass
                else:
                    data = await resp.json()
                    if "message" in data:
                        yield data["message"].get("content", "")
        except Exception as e:
            yield f"[Ollama Error] {e}"


class TransformersProvider:
    """Direct transformers inference - fully local, no server needed."""

    def __init__(self, model_id: str = "microsoft/Phi-3-mini-4k-instruct"):
        self.model_id = model_id
        self._model = None
        self._tokenizer = None
        self._device = "cuda" if torch.cuda.is_available() else "cpu"

    def load_model(self) -> bool:
        if not HAS_TRANSFORMERS:
            print("[Transformers] ❌ transformers not installed")
            return False

        try:
            print(f"[Transformers] Loading {self.model_id} on {self._device}...")
            self._tokenizer = AutoTokenizer.from_pretrained(self.model_id)
            self._model = AutoModelForCausalLM.from_pretrained(
                self.model_id,
                torch_dtype=torch.float16 if self._device == "cuda" else torch.float32,
                device_map="auto",
                trust_remote_code=True
            )
            print("[Transformers] ✅ Model loaded")
            return True
        except Exception as e:
            print(f"[Transformers] ❌ Load failed: {e}")
            return False

    def generate(self, prompt: str, system: str = "", max_tokens: int = 512) -> str:
        if not self._model:
            if not self.load_model():
                return "[Transformers] Model not loaded"

        try:
            messages = []
            if system:
                messages.append({"role": "system", "content": system})
            messages.append({"role": "user", "content": prompt})

            input_ids = self._tokenizer.apply_chat_template(
                messages, tokenize=True, add_generation_prompt=True, return_tensors="pt"
            ).to(self._device)

            with torch.no_grad():
                output_ids = self._model.generate(
                    input_ids,
                    max_new_tokens=max_tokens,
                    temperature=0.7,
                    top_p=0.9,
                    do_sample=True,
                    pad_token_id=self._tokenizer.eos_token_id
                )

            response = self._tokenizer.decode(
                output_ids[0][input_ids.shape[-1]:],
                skip_special_tokens=True
            )
            return response.strip()
        except Exception as e:
            return f"[Transformers Error] {e}"


class PipelineOrchestrator:
    """Orchestrates STT → LLM → TTS for fully local voice assistant."""

    def __init__(self):
        self.stt = None
        self.llm = None
        self.tts = None
        self._running = False

    def set_providers(self, stt_provider, llm_provider, tts_provider):
        self.stt = stt_provider
        self.llm = llm_provider
        self.tts = tts_provider

    async def process_audio(self, audio_data: bytes, sample_rate: int = 16000) -> Optional[bytes]:
        """Full pipeline: audio → text → LLM → audio."""
        if not all([self.stt, self.llm, self.tts]):
            print("[Pipeline] Missing providers")
            return None

        # 1. STT
        text = self.stt.transcribe(
            np.frombuffer(audio_data, dtype=np.int16),
            sample_rate
        )
        if not text:
            return None

        # 2. LLM
        response_text = ""
        async for chunk in self.llm.generate(text):
            response_text += chunk

        if not response_text:
            return None

        # 3. TTS
        audio = self.tts.synthesize(response_text)
        if audio is not None:
            return audio.tobytes()

        return None


# Singletons
_ollama: Optional[OllamaProvider] = None
_transformers: Optional[TransformersProvider] = None
_pipeline: Optional[PipelineOrchestrator] = None


def get_ollama(model: str = "llama3.1:8b") -> OllamaProvider:
    global _ollama
    if _ollama is None:
        _ollama = OllamaProvider(model=model)
    return _ollama


def get_transformers(model_id: str = "microsoft/Phi-3-mini-4k-instruct") -> TransformersProvider:
    global _transformers
    if _transformers is None:
        _transformers = TransformersProvider(model_id=model_id)
    return _transformers


def get_pipeline() -> PipelineOrchestrator:
    global _pipeline
    if _pipeline is None:
        _pipeline = PipelineOrchestrator()
    return _pipeline