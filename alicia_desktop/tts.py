"""Edge TTS playback; synchronous interface intended for a desktop worker thread."""

import asyncio
import io
import shutil
import time
from typing import Protocol

import edge_tts
import numpy as np
import sounddevice as sd
from numpy.typing import NDArray
from pydub import AudioSegment

from alicia_core.domain import validate_text
from alicia_core.errors import AliciaError


class Mouth(Protocol):
    def set_mouth_open(self, value: float) -> None: ...


class TextToSpeech:
    def __init__(
        self,
        voice: str,
        speed: float,
        sample_rate: int,
        volume: int = 100,
        avatar: Mouth | None = None,
        output_device: int | str | None = None,
    ) -> None:
        if not 0.5 <= speed <= 2.5 or not 0 <= volume <= 100 or not 8000 <= sample_rate <= 48000:
            raise ValueError("Configuración de voz inválida.")
        if shutil.which("ffmpeg") is None:
            raise AliciaError("Instale FFmpeg y agréguelo al PATH para reproducir voz.")
        self.voice = voice
        self.rate = f"{round((speed - 1) * 100):+d}%"
        self.sample_rate = sample_rate
        self.volume = volume / 100
        self.avatar = avatar
        self.output_device = output_device

    async def _synthesize(self, text: str) -> bytes:
        async with asyncio.timeout(60):
            communicate = edge_tts.Communicate(
                text, self.voice, rate=self.rate, connect_timeout=10, receive_timeout=30
            )
            data = bytearray()
            async for chunk in communicate.stream():
                if chunk["type"] == "audio":
                    data.extend(chunk["data"])
                    if len(data) > 10_000_000:
                        raise AliciaError("El audio sintetizado excede el límite.")
            if not data:
                raise AliciaError("El servicio de voz devolvió audio vacío.")
            return bytes(data)

    def _decode(self, data: bytes) -> NDArray[np.float32]:
        audio = AudioSegment.from_file(io.BytesIO(data), format="mp3")
        audio = audio.set_channels(1).set_sample_width(2).set_frame_rate(self.sample_rate)
        return (
            np.asarray(audio.get_array_of_samples(), dtype=np.float32)
            / np.float32(32768)
            * np.float32(self.volume)
        )

    def speak(self, text: str) -> None:
        validate_text(text)
        try:
            samples = self._decode(asyncio.run(self._synthesize(text)))
            sd.play(samples, self.sample_rate, device=self.output_device)
            start = time.monotonic()
            step = max(1, self.sample_rate // 20)
            if self.avatar:
                for i in range(0, len(samples), step):
                    chunk = samples[i : i + step]
                    rms = float(np.sqrt(np.mean(chunk.astype(np.float64) ** 2)))
                    self.avatar.set_mouth_open(min(1.0, rms * 4))
                    time.sleep(
                        max(0.0, start + min(i + step, len(samples)) / self.sample_rate - time.monotonic())
                    )
            sd.wait()
        except Exception as exc:
            raise AliciaError(
                "Falló la síntesis o reproducción de voz; la respuesta ya está en memoria."
            ) from exc
        finally:
            sd.stop()
            if self.avatar:
                self.avatar.set_mouth_open(0.0)
