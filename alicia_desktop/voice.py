"""Bounded push-to-talk capture; inference never runs in keyboard callbacks."""

import logging
import tempfile
import threading
import wave
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import numpy as np
import sounddevice as sd
from numpy.typing import NDArray
from pynput import keyboard

from alicia_core.errors import AliciaError
from alicia_core.service import ConversationService

from .config import DesktopConfig
from .stt import SpeechToText
from .tts import TextToSpeech

logger = logging.getLogger(__name__)


class VoiceSession:
    def __init__(
        self,
        config: DesktopConfig,
        service: ConversationService,
        stt: SpeechToText,
        tts: TextToSpeech,
        stop: threading.Event,
    ) -> None:
        self.config, self.service, self.stt, self.tts, self.stop = config, service, stt, tts, stop
        self._lock = threading.Lock()
        self._frames: list[NDArray[np.int16]] = []
        self._samples = 0
        self._recording = False
        self._busy = False
        self._stream: sd.InputStream | None = None
        self._timer: threading.Timer | None = None
        self._executor = ThreadPoolExecutor(max_workers=1, thread_name_prefix="alicia-turn")

    def _callback(
        self, data: NDArray[np.int16], frames: int, timing: object, status: sd.CallbackFlags
    ) -> None:
        if status:
            logger.warning("audio_capture_status")
        with self._lock:
            remaining = self.config.audio.sample_rate * self.config.audio.max_recording_sec - self._samples
            if self._recording and remaining > 0:
                chunk = data[:remaining].copy()
                self._frames.append(chunk)
                self._samples += len(chunk)

    def start_recording(self) -> None:
        with self._lock:
            if self._busy or self._recording or self.stop.is_set():
                return
            self._recording = True
            self._frames = []
            self._samples = 0
        try:
            audio = self.config.audio
            stream = sd.InputStream(
                samplerate=audio.sample_rate,
                channels=1,
                dtype="int16",
                device=audio.input_device,
                callback=self._callback,
            )
            self._stream = stream
            stream.start()
            self._timer = threading.Timer(audio.max_recording_sec, self.finish_recording)
            self._timer.start()
            print("Grabando…", flush=True)
        except Exception:
            logger.warning("audio_start_failed")
            print("No se pudo abrir el micrófono.", flush=True)
            if self._stream:
                self._stream.close()
                self._stream = None
            with self._lock:
                self._recording = False

    def finish_recording(self) -> None:
        with self._lock:
            if not self._recording:
                return
            self._recording = False
            self._busy = True
            frames = self._frames
            self._frames = []
        if self._timer:
            self._timer.cancel()
        try:
            if self._stream:
                self._stream.stop()
                self._stream.close()
                self._stream = None
            if frames and not self.stop.is_set():
                self._executor.submit(self._process, frames)
            else:
                with self._lock:
                    self._busy = False
        except Exception:
            logger.warning("audio_stop_failed")
            with self._lock:
                self._busy = False

    def _process(self, frames: list[NDArray[np.int16]]) -> None:
        try:
            # Close the file before Whisper opens it: required on Windows.
            with tempfile.TemporaryDirectory(prefix="alicia-audio-") as directory:
                path = Path(directory) / "recording.wav"
                with wave.open(str(path), "wb") as wav:
                    wav.setnchannels(1)
                    wav.setsampwidth(2)
                    wav.setframerate(self.config.audio.sample_rate)
                    wav.writeframes(np.concatenate(frames).tobytes())
                text = self.stt.transcribe(str(path))
            if not text or self.stop.is_set():
                return
            print(f"Vos: {text}", flush=True)
            answer = self.service.reply(text)
            print(f"Alicia: {answer}", flush=True)
            if not self.stop.is_set():
                self.tts.speak(answer)
        except (AliciaError, ValueError) as exc:
            logger.warning("turn_failed type=%s", type(exc).__name__)
            print(str(exc), flush=True)
        except Exception:
            logger.error("turn_failed unexpected_error")
            print("Error inesperado al procesar el audio.", flush=True)
        finally:
            with self._lock:
                self._busy = False

    def run(self) -> None:
        target = getattr(keyboard.Key, self.config.hotkey)

        def press(key: keyboard.Key | keyboard.KeyCode | None) -> bool | None:
            if key == target:
                self.start_recording()
            if key == keyboard.Key.esc:
                self.stop.set()
                return False
            return None

        def release(key: keyboard.Key | keyboard.KeyCode | None) -> None:
            if key == target:
                self.finish_recording()

        print(f"Alicia lista. Mantenga {self.config.hotkey.upper()} para hablar; Esc para salir.", flush=True)
        try:
            with keyboard.Listener(on_press=press, on_release=release) as listener:
                while listener.is_alive() and not self.stop.wait(0.2):
                    listener.join(timeout=0.1)
                listener.stop()
        finally:
            self.stop.set()
            self.finish_recording()
            if self._timer:
                self._timer.cancel()
            self._executor.shutdown(wait=True, cancel_futures=True)
            sd.stop()
