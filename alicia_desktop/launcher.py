"""Only administrator-configured absolute executables; never use a command shell."""

import os
import subprocess
from collections.abc import Mapping, Sequence
from pathlib import Path
from types import MappingProxyType

from alicia_core.errors import ToolError

DENIED = {
    "cmd",
    "powershell",
    "pwsh",
    "sh",
    "bash",
    "zsh",
    "dash",
    "fish",
    "python",
    "python3",
    "pythonw",
    "py",
    "node",
    "perl",
    "ruby",
    "wscript",
    "cscript",
    "mshta",
    "rundll32",
    "regsvr32",
}


def validate_command(command: Sequence[str]) -> None:
    if isinstance(command, str) or not command or len(command) > 32:
        raise ValueError("Cada aplicación requiere una lista de 1 a 32 argumentos fijos.")
    if any(
        not isinstance(arg, str) or not arg or len(arg) > 2048 or "\x00" in arg or "\n" in arg or "\r" in arg
        for arg in command
    ):
        raise ValueError("Argumentos de aplicación inválidos.")
    exe = Path(command[0])
    if not exe.is_absolute():
        raise ValueError("Use la ruta absoluta del ejecutable; no se busca en PATH.")
    if exe.suffix.lower() in {".bat", ".cmd", ".ps1", ".lnk", ".vbs", ".js", ".py", ".sh"}:
        raise ValueError("No se permiten scripts ni accesos directos.")
    if exe.stem.lower() in DENIED:
        raise ValueError("No se permiten intérpretes ni shells en el catálogo.")


class AppLauncher:
    def __init__(self, apps: Mapping[str, Sequence[str]]) -> None:
        self.apps: Mapping[str, tuple[str, ...]] = MappingProxyType({k: tuple(v) for k, v in apps.items()})
        for command in self.apps.values():
            validate_command(command)
        self._children: list[subprocess.Popen[bytes]] = []

    def launch(self, app_name: str) -> str:
        command = self.apps.get(app_name)
        if command is None:
            raise ToolError("Aplicación no permitida.")
        validate_command(command)
        exe = Path(command[0])
        # Resolve symlinks to also reject obvious interpreter aliases.
        resolved = exe.resolve(strict=True)
        validate_command((str(resolved), *command[1:]))
        if not resolved.is_file() or (os.name != "nt" and not os.access(resolved, os.X_OK)):
            raise ToolError("El ejecutable no está disponible.")
        try:
            self._children = [p for p in self._children if p.poll() is None]
            self._children.append(
                subprocess.Popen(
                    [str(resolved), *command[1:]],
                    shell=False,
                    cwd=str(resolved.parent),
                    stdin=subprocess.DEVNULL,
                    stdout=subprocess.DEVNULL,
                    stderr=subprocess.DEVNULL,
                    close_fds=True,
                )
            )
            return f"Se inició el proceso de {app_name}; no se comprobó su ventana."
        except OSError as exc:
            raise ToolError("No se pudo iniciar la aplicación.") from exc
