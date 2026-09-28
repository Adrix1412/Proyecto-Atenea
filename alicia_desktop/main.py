"""Desktop entry point; --text works without audio, GUI or hotkey dependencies."""

import argparse
import logging
import signal
import threading
from pathlib import Path

from alicia_core.errors import AliciaError

from .config import load_config, resolve_path
from .factory import build_service
from .launcher import AppLauncher
from .logging_setup import setup_logging


def main() -> int:
    parser = argparse.ArgumentParser(description="Alicia desktop")
    parser.add_argument("--config", type=Path, default=Path.cwd() / "config.yaml")
    parser.add_argument("--text", action="store_true", help="Chat de texto sin micrófono")
    args = parser.parse_args()
    service = None
    avatar = None
    try:
        config = load_config(args.config)
        config.llm.ready()
        setup_logging(resolve_path(args.config, config.logging.file), config.logging.level)
        launcher = AppLauncher(config.apps)
        if args.text:

            def confirm(tool: str, app: str) -> bool:
                return input(f"¿Abrir {app}: {launcher.apps[app]}? Escriba SI: ").strip() == "SI"

            service = build_service(config, args.config, launcher, confirm)
            print("Modo texto. /salir termina la sesión.")
            while True:
                text = input("Vos: ")
                if text.strip() == "/salir":
                    return 0
                try:
                    print("Alicia:", service.reply(text))
                except (AliciaError, ValueError) as exc:
                    print(str(exc))
        from .control import ControlChannel
        from .stt import SpeechToText
        from .tts import TextToSpeech
        from .voice import VoiceSession

        stop = threading.Event()
        signal.signal(signal.SIGTERM, lambda *_: stop.set())
        if config.avatar.enabled:
            from .avatar import VTubeStudioAvatar

            candidate = VTubeStudioAvatar(config.avatar.host, config.avatar.port)
            print("Conectando a VTube Studio; apruebe el plugin en su ventana.", flush=True)
            if candidate.connect():
                avatar = candidate
            else:
                print("Avatar no disponible; la conversación seguirá sin avatar.", flush=True)
        control = ControlChannel(stop, lambda app: repr(launcher.apps[app]))
        control.start()
        service = build_service(config, args.config, launcher, control.confirm, avatar)
        stt = SpeechToText(
            config.stt.model_size, config.stt.device, config.stt.compute_type, config.stt.language
        )
        tts = TextToSpeech(**config.tts.model_dump(), avatar=avatar, output_device=config.audio.output_device)
        VoiceSession(config, service, stt, tts, stop).run()
        return 0
    except (KeyboardInterrupt, EOFError):
        return 0
    except (AliciaError, OSError, ValueError) as exc:
        logging.getLogger(__name__).error("startup_failed type=%s", type(exc).__name__)
        print(f"No se pudo iniciar Alicia: {exc}")
        return 1
    except ImportError:
        print("Faltan dependencias de escritorio; instale requirements.txt.")
        return 1
    finally:
        if service:
            service.client.close()
        if avatar:
            avatar.close()
