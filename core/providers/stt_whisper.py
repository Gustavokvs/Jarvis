"""
Whisper STT Provider - Local speech-to-text
Fast, accurate, runs entirely on your machine.
"""
import asyncio
import tempfile
import os
from pathlib import Path
from typing import Optional, AsyncGenerator
import numpy as np

try:
    import whisper
    HAS_WHISPER = True
except ImportError:
    HAS_WHISPER = False

try:
    import faster_whisper
    HAS_FASTER_WHISPER = True
except ImportError:
    HAS_FASTER_WHISPER = False


class WhisperSTTProvider:
    """Local Whisper STT - supports faster-whisper for speed."""

    def __init__(self, model_size: str = "base", use_faster: bool = True):
        self.model_size = model_size
        self.use_faster = use_faster and HAS_FASTER_WHISPER
        self._model = None
        self._lang = "pt"

    def load_model(self) -> bool:
        """Load Whisper model."""
        try:
            if self.use_faster:
                from faster_whisper import WhisperModel
                self._model = WhisperModel(
                    self.model_size,
                    device="cpu",
                    compute_type="int8"  # fast on CPU
                )
                print(f"[WhisperSTT] ✅ Loaded faster-whisper {self.model_size}")
            else:
                import whisper
                self._model = whisper.load_model(self.model_size)
                print(f"[WhisperSTT] ✅ Loaded whisper {self.model_size}")
            return True
        except Exception as e:
            print(f"[WhisperSTT] ❌ Load failed: {e}")
            return False

    def transcribe(self, audio_data: np.ndarray, sample_rate: int = 16000) -> str:
        """Transcribe audio array to text."""
        if self._model is None:
            if not self.load_model():
                return ""

        # Save to temp file (Whisper needs file)
        with tempfile.NamedTemporaryFile(suffix=".wav", delete=False) as tmp:
            tmp_path = tmp.name
            import soundfile as sf
            sf.write(tmp_path, audio_data.astype(np.float32) / 32767.0, sample_rate)

        try:
            if self.use_faster:
                segments, _ = self._model.transcribe(
                    tmp_path,
                    language=self._lang,
                    beam_size=5,
                    vad_filter=True
                )
                text = " ".join([seg.text for seg in segments])
            else:
                result = self._model.transcribe(tmp_path, language=self._lang)
                text = result["text"]

            return text.strip()
        except Exception as e:
            print(f"[WhisperSTT] Transcribe error: {e}")
            return ""
        finally:
            try:
                os.unlink(tmp_path)
            except:
                pass

    async def transcribe_stream(self, audio_chunks: AsyncGenerator[bytes, None], sample_rate: int = 16000):
        """Stream transcription - yields partial results."""
        # Accumulate chunks and transcribe periodically
        buffer = bytearray()
        chunk_count = 0

        async for chunk in audio_chunks:
            buffer.extend(chunk)
            chunk_count += 1

            # Transcribe every ~2 seconds of audio
            if chunk_count >= (sample_rate * 2 // 1024):  # approx
                audio = np.frombuffer(buffer, dtype=np.int16)
                text = self.transcribe(audio, sample_rate)
                if text:
                    yield text
                buffer = bytearray()
                chunk_count = 0
                await asyncio.sleep(0)

        # Final transcription
        if buffer:
            audio = np.frombuffer(buffer, dtype=np.int16)
            text = self.transcribe(audio, sample_rate)
            if text:
                yield text


class VoskSTTProvider:
    """Vosk STT - Offline, streaming, lower resource usage."""

    def __init__(self, model_path: Path = None):
        self.model_path = model_path or Path(__file__).parent.parent.parent / "models" / "vosk"
        self._model = None
        self._rec = None

    def load_model(self) -> bool:
        try:
            from vosk import Model, KaldiRecognizer
            if not self.model_path.exists():
                print(f"[VoskSTT] Model not found at {self.model_path}")
                print("Download from: https://alphacephei.com/vosk/models")
                return False
            self._model = Model(str(self.model_path))
            print("[VoskSTT] ✅ Model loaded")
            return True
        except ImportError:
            print("[VoskSTT] ❌ vosk not installed. Run: pip install vosk")
            return False
        except Exception as e:
            print(f"[VoskSTT] ❌ Load failed: {e}")
            return False

    def create_recognizer(self, sample_rate: int = 16000):
        if not self._model:
            return None
        from vosk import KaldiRecognizer
        return KaldiRecognizer(self._model, sample_rate)

    def transcribe_chunk(self, recognizer, audio_data: bytes) -> Optional[str]:
        """Process one chunk, return partial or final result."""
        if recognizer.AcceptWaveform(audio_data):
            import json
            result = json.loads(recognizer.Result())
            return result.get("text", "")
        else:
            import json
            result = json.loads(recognizer.PartialResult())
            return result.get("partial", "")


# Singletons
_whisper_stt: Optional[WhisperSTTProvider] = None
_vosk_stt: Optional[VoskSTTProvider] = None


def get_whisper_stt(model_size: str = "base") -> WhisperSTTProvider:
    global _whisper_stt
    if _whisper_stt is None:
        _whisper_stt = WhisperSTTProvider(model_size=model_size)
    return _whisper_stt


def get_vosk_stt() -> VoskSTTProvider:
    global _vosk_stt
    if _vosk_stt is None:
        _vosk_stt = VoskSTTProvider()
    return _vosk_stt