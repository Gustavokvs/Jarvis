"""
Piper TTS Provider - Local, fast, high-quality neural TTS
Supports custom voice models (.onnx + .json) for "JARVIS feminina" voice.
"""
import asyncio
import json
import subprocess
import tempfile
import os
from pathlib import Path
from typing import Optional, Dict, Any
import numpy as np

try:
    import onnxruntime as ort
    HAS_ORT = True
except ImportError:
    HAS_ORT = False

try:
    import piper
    from piper.voice import PiperVoice
    HAS_PIPER = True
except ImportError:
    HAS_PIPER = False


class PiperTTSProvider:
    """Local Piper TTS - runs entirely on your machine, no API calls."""

    def __init__(self, voice_dir: Path = None):
        self.voice_dir = voice_dir or Path(__file__).parent.parent.parent / "voices"
        self.voice_dir.mkdir(parents=True, exist_ok=True)
        self._voice_cache: Dict[str, Any] = {}
        self._current_voice: Optional[str] = None
        self.sample_rate = 22050  # Piper default

    def list_available_voices(self) -> list[dict]:
        """List all .onnx voice models in voices directory."""
        voices = []
        for onnx_file in self.voice_dir.glob("*.onnx"):
            name = onnx_file.stem
            json_file = onnx_file.with_suffix(".onnx.json")
            config = {}
            if json_file.exists():
                try:
                    config = json.loads(json_file.read_text(encoding="utf-8"))
                except:
                    pass
            voices.append({
                "id": name,
                "name": config.get("name", name),
                "language": config.get("language", {}).get("code", "pt"),
                "speaker": config.get("speaker", "default"),
                "quality": config.get("quality", "high"),
                "path": str(onnx_file)
            })
        return voices

    def download_voice(self, voice_id: str, progress_callback=None) -> bool:
        """Download a Piper voice model from Hugging Face."""
        # Common Piper voices for Portuguese
        voice_urls = {
            "pt_BR-faber-medium": "https://huggingface.co/rhasspy/piper-voices/resolve/main/pt/pt_BR/faber/medium/pt_BR-faber-medium.onnx",
            "pt_BR-faber-low": "https://huggingface.co/rhasspy/piper-voices/resolve/main/pt/pt_BR/faber/low/pt_BR-faber-low.onnx",
        }
        # Add more voices as needed

        if voice_id not in voice_urls:
            print(f"[PiperTTS] Voice {voice_id} not in known list")
            return False

        url = voice_urls[voice_id]
        onnx_path = self.voice_dir / f"{voice_id}.onnx"
        json_path = self.voice_dir / f"{voice_id}.onnx.json"

        try:
            import urllib.request
            print(f"[PiperTTS] Downloading {voice_id}...")
            urllib.request.urlretrieve(url, onnx_path)

            # Download config JSON
            json_url = url + ".json"
            urllib.request.urlretrieve(json_url, json_path)

            print(f"[PiperTTS] ✅ Downloaded {voice_id}")
            return True
        except Exception as e:
            print(f"[PiperTTS] ❌ Download failed: {e}")
            return False

    def load_voice(self, voice_id: str) -> bool:
        """Load a voice model into memory."""
        if not HAS_PIPER:
            print("[PiperTTS] ❌ piper-tts not installed. Run: pip install piper-tts")
            return False

        onnx_path = self.voice_dir / f"{voice_id}.onnx"
        if not onnx_path.exists():
            print(f"[PiperTTS] Voice not found: {onnx_path}")
            return False

        try:
            if voice_id in self._voice_cache:
                self._current_voice = voice_id
                return True

            voice = PiperVoice.load(str(onnx_path))
            self._voice_cache[voice_id] = voice
            self._current_voice = voice_id
            print(f"[PiperTTS] ✅ Loaded voice: {voice_id}")
            return True
        except Exception as e:
            print(f"[PiperTTS] ❌ Load failed: {e}")
            return False

    def synthesize(self, text: str, voice_id: str = None) -> Optional[np.ndarray]:
        """Synthesize text to audio (int16 numpy array)."""
        voice_id = voice_id or self._current_voice
        if not voice_id:
            print("[PiperTTS] No voice selected")
            return None

        if not self.load_voice(voice_id):
            return None

        try:
            voice = self._voice_cache[voice_id]
            audio_chunks = []
            for chunk in voice.synthesize(text):
                audio_chunks.append(chunk)

            if audio_chunks:
                audio = np.concatenate(audio_chunks)
                # Convert to int16
                audio = (audio * 32767).astype(np.int16)
                return audio
            return None
        except Exception as e:
            print(f"[PiperTTS] Synthesis error: {e}")
            return None

    async def synthesize_stream(self, text: str, voice_id: str = None, chunk_size: int = 1024):
        """Async generator yielding audio chunks for streaming."""
        audio = self.synthesize(text, voice_id)
        if audio is None:
            return

        # Yield in chunks
        for i in range(0, len(audio), chunk_size):
            yield audio[i:i+chunk_size].tobytes()
            await asyncio.sleep(0)  # yield control


class XTTSProvider:
    """Coqui XTTS v2 - Voice cloning & multilingual TTS (higher quality, slower)."""

    def __init__(self, model_dir: Path = None):
        self.model_dir = model_dir or Path(__file__).parent.parent.parent / "models" / "xtts"
        self.model_dir.mkdir(parents=True, exist_ok=True)
        self._model = None
        self._speaker_wav = None

    def load_model(self) -> bool:
        """Load XTTS model."""
        try:
            from TTS.api import TTS
            self._model = TTS("tts_models/multilingual/multi-dataset/xtts_v2", gpu=False)
            print("[XTTS] ✅ Model loaded")
            return True
        except ImportError:
            print("[XTTS] ❌ Coqui TTS not installed. Run: pip install TTS")
            return False
        except Exception as e:
            print(f"[XTTS] ❌ Load failed: {e}")
            return False

    def set_speaker_reference(self, wav_path: Path):
        """Set reference audio for voice cloning."""
        self._speaker_wav = str(wav_path)
        print(f"[XTTS] Speaker reference set: {wav_path}")

    def synthesize(self, text: str, language: str = "pt") -> Optional[np.ndarray]:
        """Synthesize with voice cloning."""
        if not self._model:
            if not self.load_model():
                return None
        if not self._speaker_wav:
            print("[XTTS] No speaker reference set")
            return None

        try:
            with tempfile.NamedTemporaryFile(suffix=".wav", delete=False) as tmp:
                tmp_path = tmp.name
            self._model.tts_to_file(
                text=text,
                speaker_wav=self._speaker_wav,
                language=language,
                file_path=tmp_path
            )
            import soundfile as sf
            audio, sr = sf.read(tmp_path)
            os.unlink(tmp_path)
            return (audio * 32767).astype(np.int16)
        except Exception as e:
            print(f"[XTTS] Synthesis error: {e}")
            return None


# Singleton instances
_piper_provider: Optional[PiperTTSProvider] = None
_xtts_provider: Optional[XTTSProvider] = None


def get_piper_tts() -> PiperTTSProvider:
    global _piper_provider
    if _piper_provider is None:
        _piper_provider = PiperTTSProvider()
    return _piper_provider


def get_xtts_provider() -> XTTSProvider:
    global _xtts_provider
    if _xtts_provider is None:
        _xtts_provider = XTTSProvider()
    return _xtts_provider