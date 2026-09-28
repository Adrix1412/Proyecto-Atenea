[CmdletBinding()]
param(
    [switch]$RecreateVenv
)

$ErrorActionPreference = "Stop"
$projectRoot = Split-Path -Parent $PSScriptRoot
Set-Location $projectRoot

if ($RecreateVenv -and (Test-Path ".venv")) {
    Remove-Item -Recurse -Force ".venv"
}

& py -3.12 --version
if ($LASTEXITCODE -ne 0) {
    throw "Python 3.12 no está instalado. Ejecute: py install 3.12"
}

if (-not (Test-Path ".venv\Scripts\python.exe")) {
    & py -3.12 -m venv .venv
    if ($LASTEXITCODE -ne 0) {
        throw "No se pudo crear el entorno virtual."
    }
}

& .\.venv\Scripts\python.exe -m pip install --upgrade pip
& .\.venv\Scripts\python.exe -m pip install -c constraints-tested-py312.txt -r requirements.txt
if ($LASTEXITCODE -ne 0) {
    throw "No se pudieron instalar las dependencias."
}

& .\.venv\Scripts\python.exe -c "import alicia_desktop.gui; print('Importación de GUI correcta.')"
if ($LASTEXITCODE -ne 0) {
    throw "La GUI no se pudo importar; no se iniciará la aplicación."
}

if (-not (Test-Path "config.yaml")) {
    Copy-Item "config.example.yaml" "config.yaml"
    Write-Host "Se creó config.yaml. Configura el proveedor y modelo antes de iniciar Alicia."
}

Write-Host "Entorno preparado. Inicio: .\.venv\Scripts\python.exe gui.py"
