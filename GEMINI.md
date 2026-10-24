# Mark-LVI - Project Instructions

## Overview
Mark-LVI is an advanced modular Python-based virtual assistant (Jarvis-style) featuring voice recognition (STT), text-to-speech (TTS), LLM integration (Gemini / OpenAI), computer vision/screen capture, desktop automation actions, a web dashboard, and a plugin architecture.

## Architecture & Directory Structure
- **`main.py` & `ui.py`**: Entry points and user interface for the assistant.
- **`core/`**: Core engines and runtime pipelines:
  - `gemini.py`, `llm_client.py`: LLM client integrations.
  - `stt.py`, `tts.py`: Speech-to-Text and Text-to-Speech wrappers.
  - `wake_word.py`: Wake word detection.
  - `avatar.py`, `avatar_mesh.py`: 3D/visual avatar rendering and management.
- **`actions/`**: Modular actions executed by the assistant (e.g., computer control, browser automation, weather, flight finder, WhatsApp desktop, system monitor).
- **`providers/`**: Pluggable backends for audio, STT (Whisper), TTS (ElevenLabs, Piper, System), and LLM engines with registry management.
- **`dashboard/`**: FastAPI/Flask or web server dashboard (`server.py`) and static frontend assets (`app.html`, `login.html`).
- **`memory/`**: Persistent memory management and configuration utilities.
- **`plugins/`**: Extensible plugin system (`_template.py`).

## Development & Testing Standards
- **Language**: Python 3.x
- **Dependencies**: Listed in `requirements.txt`. Install via `pip install -r requirements.txt`.
- **Code Style**: Adhere to PEP 8 standards, clear docstrings, explicit typing where appropriate, and modular separation between `core`, `actions`, and `providers`.
- **Execution**: Run main script via `python main.py` or `python modo_dev.py`.
