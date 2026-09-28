"""Shared Qt controller: two visual themes, one configuration/process/history flow."""

# ruff: noqa: I001  # Pydantic must load before PySide6 on affected Windows builds.

import argparse
import codecs
import json
import sys
from importlib.resources import files
from pathlib import Path

import yaml
from pydantic import ValidationError

from alicia_core.adapters.sqlite_memory import SQLiteMemory
from alicia_core.errors import AliciaError

from .config import DesktopConfig, load_config, resolve_path, save_config
from PySide6.QtCore import QProcess, QTimer
from PySide6.QtGui import QCloseEvent
from PySide6.QtWidgets import (
    QApplication,
    QFileDialog,
    QHBoxLayout,
    QInputDialog,
    QLabel,
    QMainWindow,
    QMessageBox,
    QPlainTextEdit,
    QPushButton,
    QTabWidget,
    QVBoxLayout,
    QWidget,
)

CLASSIC = "QWidget {font-size: 14px;} QPlainTextEdit {font-family: monospace;} QPushButton {padding: 8px;}"
ULTIMATE = (
    CLASSIC
    + "QWidget {background: #161b24; color: #eef2f9;} QPlainTextEdit {background: #0c1119; color: #c9e7f0;} QPushButton {background: #253b50; border: 1px solid #658ca7;}"
)


class MainWindow(QMainWindow):
    def __init__(self, config_path: Path, theme: str = "classic") -> None:
        super().__init__()
        self.config_path = config_path.resolve()
        self._closing = False
        self._line_buffer = ""
        self._decoder = codecs.getincrementaldecoder("utf-8")(errors="replace")
        self.setWindowTitle("Alicia · Asistente de escritorio")
        self.resize(980, 720)
        self.setStyleSheet(ULTIMATE if theme == "ultimate" else CLASSIC)
        self.process = QProcess(self)
        self.process.setProcessChannelMode(QProcess.ProcessChannelMode.MergedChannels)
        self.process.readyReadStandardOutput.connect(self.read_output)
        self.process.finished.connect(self.finished)
        self.process.errorOccurred.connect(self.process_error)
        self.kill_timer = QTimer(self)
        self.kill_timer.setSingleShot(True)
        self.kill_timer.timeout.connect(self.force_stop)
        tabs = QTabWidget()
        self.setCentralWidget(tabs)
        panel = QWidget()
        layout = QVBoxLayout(panel)
        self.status = QLabel("Detenida")
        layout.addWidget(self.status)
        buttons = QHBoxLayout()
        self.start_button = QPushButton("Iniciar voz")
        self.stop_button = QPushButton("Detener")
        self.stop_button.setEnabled(False)
        buttons.addWidget(self.start_button)
        buttons.addWidget(self.stop_button)
        layout.addLayout(buttons)
        self.console = QPlainTextEdit()
        self.console.setReadOnly(True)
        self.console.setMaximumBlockCount(2000)
        layout.addWidget(self.console)
        self.start_button.clicked.connect(self.start)
        self.stop_button.clicked.connect(self.stop)
        tabs.addTab(panel, "Asistente")
        settings = QWidget()
        settings_layout = QVBoxLayout(settings)
        settings_layout.addWidget(
            QLabel("YAML validado. Las API keys se leen del entorno. Guarde y reinicie para aplicar.")
        )
        self.editor = QPlainTextEdit()
        text = (
            self.config_path.read_text(encoding="utf-8")
            if self.config_path.exists()
            else files("alicia_desktop").joinpath("config.example.yaml").read_text(encoding="utf-8")
        )
        self.editor.setPlainText(text)
        settings_layout.addWidget(self.editor)
        save = QPushButton("Validar y guardar")
        save.clicked.connect(self.save)
        settings_layout.addWidget(save)
        add_app = QPushButton("Añadir ejecutable al catálogo")
        add_app.clicked.connect(self.add_app)
        settings_layout.addWidget(add_app)
        tabs.addTab(settings, "Configuración")
        history_panel = QWidget()
        history_layout = QVBoxLayout(history_panel)
        self.history = QPlainTextEdit()
        self.history.setReadOnly(True)
        history_layout.addWidget(self.history)
        refresh = QPushButton("Cargar últimos 50 turnos")
        refresh.clicked.connect(self.refresh_history)
        clear = QPushButton("Borrar historial local")
        clear.clicked.connect(self.clear_history)
        history_layout.addWidget(refresh)
        history_layout.addWidget(clear)
        tabs.addTab(history_panel, "Memoria")

    def edited_config(self) -> DesktopConfig:
        text = self.editor.toPlainText()
        if len(text.encode()) > 65536:
            raise ValueError("El YAML supera 64 KiB.")
        return DesktopConfig.model_validate(yaml.safe_load(text))

    def save(self) -> None:
        try:
            save_config(self.config_path, self.edited_config())
            QMessageBox.information(
                self, "Configuración", "Configuración guardada. Reinicie Alicia para aplicar los cambios."
            )
        except (AliciaError, OSError, ValueError, ValidationError, yaml.YAMLError):
            QMessageBox.warning(
                self,
                "Configuración inválida",
                "Revise tipos, campos y rutas. No se admiten claves ni tokens en YAML.",
            )

    def add_app(self) -> None:
        executable, _ = QFileDialog.getOpenFileName(self, "Elegir ejecutable")
        if not executable:
            return
        name, accepted = QInputDialog.getText(
            self, "Aplicación", "Nombre del catálogo (letras, números, _ o -):"
        )
        if not accepted:
            return
        try:
            value = self.edited_config().model_dump()
            apps = dict(self.edited_config().apps)
            apps[name.strip()] = [str(Path(executable).resolve())]
            value["apps"] = apps
            cfg = DesktopConfig.model_validate(value)
            self.editor.setPlainText(yaml.safe_dump(cfg.model_dump(), allow_unicode=True, sort_keys=False))
        except (ValueError, yaml.YAMLError):
            QMessageBox.warning(
                self,
                "Aplicación inválida",
                "Seleccione un ejecutable real, no scripts, shells ni accesos directos.",
            )

    def start(self) -> None:
        if self.process.state() != QProcess.ProcessState.NotRunning:
            return
        try:
            load_config(self.config_path).llm.ready()
        except AliciaError as exc:
            QMessageBox.warning(self, "No se puede iniciar", str(exc))
            return
        self.console.clear()
        self._line_buffer = ""
        self._decoder.reset()
        self.process.setWorkingDirectory(str(self.config_path.parent))
        self.process.start(
            sys.executable, ["-u", "-m", "alicia_desktop.main_runner", "--config", str(self.config_path)]
        )
        self.start_button.setEnabled(False)
        self.stop_button.setEnabled(True)
        self.status.setText("Proceso iniciándose; consulte la salida para confirmar que está listo.")

    def read_output(self) -> None:
        text = self._decoder.decode(self.process.readAllStandardOutput().data())
        self.console.insertPlainText(text)
        self._line_buffer += text
        while "\n" in self._line_buffer:
            line, self._line_buffer = self._line_buffer.split("\n", 1)
            if line.startswith("ALICIA_CONFIRM:"):
                self.confirm_action(line.removeprefix("ALICIA_CONFIRM:"))
        self._line_buffer = self._line_buffer[-65536:]

    def confirm_action(self, raw: str) -> None:
        try:
            data = json.loads(raw)
            if not isinstance(data, dict) or not isinstance(data.get("approval_id"), str):
                return
            box = QMessageBox(self)
            box.setWindowTitle("Confirmar apertura")
            from PySide6.QtCore import Qt

            box.setTextFormat(Qt.TextFormat.PlainText)
            box.setText(f"¿Autoriza abrir {data.get('value')}?\nComando fijo: {data.get('command')}")
            box.setStandardButtons(QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No)
            box.setDefaultButton(QMessageBox.StandardButton.No)
            approved = box.exec() == QMessageBox.StandardButton.Yes
            self.process.write(
                (json.dumps({"approval_id": data["approval_id"], "approved": approved}) + "\n").encode()
            )
        except (ValueError, TypeError):
            return

    def stop(self) -> None:
        if self.process.state() != QProcess.ProcessState.NotRunning:
            self.process.write(b"quit\n")
            self.status.setText("Cerrando; si no responde en 5 s se cancelará el proceso.")
            self.kill_timer.start(5000)

    def force_stop(self) -> None:
        if self.process.state() != QProcess.ProcessState.NotRunning:
            self.console.appendPlainText("Cierre forzado: el turno pendiente puede no haberse guardado.")
            self.process.kill()

    def finished(self, exit_code: int, exit_status: QProcess.ExitStatus) -> None:
        self.kill_timer.stop()
        self.status.setText(f"Detenida · código de salida {exit_code}")
        self.start_button.setEnabled(True)
        self.stop_button.setEnabled(False)
        if self._closing:
            self.close()

    def process_error(self, error: QProcess.ProcessError) -> None:
        self.status.setText("El proceso falló; revise las dependencias y la configuración.")
        self.start_button.setEnabled(True)
        self.stop_button.setEnabled(False)

    def refresh_history(self) -> None:
        try:
            cfg = load_config(self.config_path)
            memory = SQLiteMemory(resolve_path(self.config_path, cfg.memory_path))
            self.history.setPlainText(
                "\n\n".join(f"{m.role}: {m.content}" for m in memory.snapshot(50).messages)
            )
        except (AliciaError, OSError):
            QMessageBox.warning(self, "Memoria", "No se pudo leer el historial.")

    def clear_history(self) -> None:
        if self.process.state() != QProcess.ProcessState.NotRunning:
            QMessageBox.information(self, "Memoria", "Detenga Alicia antes de borrar la memoria.")
            return
        if (
            QMessageBox.question(
                self,
                "Borrar historial",
                "¿Eliminar todo el historial local de esta conversación?",
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
                QMessageBox.StandardButton.No,
            )
            != QMessageBox.StandardButton.Yes
        ):
            return
        try:
            cfg = load_config(self.config_path)
            SQLiteMemory(resolve_path(self.config_path, cfg.memory_path)).clear()
            self.refresh_history()
        except (AliciaError, OSError):
            QMessageBox.warning(self, "Memoria", "No se pudo borrar el historial.")

    def closeEvent(self, event: QCloseEvent) -> None:
        if self.process.state() != QProcess.ProcessState.NotRunning:
            self._closing = True
            self.stop()
            event.ignore()
        else:
            event.accept()


def main(theme: str = "classic") -> int:
    parser = argparse.ArgumentParser(description="Alicia GUI")
    parser.add_argument("--config", type=Path, default=Path.cwd() / "config.yaml")
    args = parser.parse_args()
    app = QApplication(sys.argv)
    window = MainWindow(args.config, theme)
    window.show()
    return app.exec()
