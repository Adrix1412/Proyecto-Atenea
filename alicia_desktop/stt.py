"""Whisper adapter loaded only by the voice interface."""

from pathlib import Path

from faster_whisper import WhisperModel

from alicia_core.errors import AliciaError


class SpeechToText:
    def __init__(self, model_size: str, device: str, compute_type: str, language: str) -> None:
        try:
            self.model = WhisperModel(model_size, device=device, compute_type=compute_type)
        except Exception as exc:
            raise AliciaError("No se pudo cargar Whisper; revise modelo, red y dispositivo.") from exc
        self.language = language

    def transcribe(self, audio_path: str) -> str:
        if not Path(audio_path).is_file():
            raise AliciaError("No existe el audio para transcribir.")
        try:
            segments, _ = self.model.transcribe(audio_path, language=self.language, beam_size=5)
            return " ".join(segment.text.strip() for segment in segments).strip()
        except Exception as exc:
            raise AliciaError("No se pudo transcribir el audio.") from exc
