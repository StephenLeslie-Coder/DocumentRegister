# -*- mode: python ; coding: utf-8 -*-
"""One-folder, windowed Windows distribution with a private Tesseract runtime."""

import os
import sys
from pathlib import Path

project = Path(SPECPATH).resolve()
sys.path.insert(0, str(project))
from src.config import APP_NAME, APP_VERSION  # noqa: E402
from PyInstaller.utils.win32.versioninfo import (  # noqa: E402
    FixedFileInfo, StringFileInfo, StringStruct, StringTable,
    VSVersionInfo, VarFileInfo, VarStruct,
)

version_parts = tuple(int(part) for part in APP_VERSION.split("."))
version_tuple = (version_parts + (0, 0, 0, 0))[:4]
version_info = VSVersionInfo(
    ffi=FixedFileInfo(filevers=version_tuple, prodvers=version_tuple),
    kids=[
        StringFileInfo([StringTable("040904B0", [
            StringStruct("FileDescription", APP_NAME),
            StringStruct("FileVersion", APP_VERSION),
            StringStruct("InternalName", APP_NAME),
            StringStruct("OriginalFilename", f"{APP_NAME}.exe"),
            StringStruct("ProductName", APP_NAME),
            StringStruct("ProductVersion", APP_VERSION),
        ])]),
        VarFileInfo([VarStruct("Translation", [1033, 1200])]),
    ],
)

default_tesseract = Path(os.environ.get("ProgramFiles", r"C:\Program Files")) / "Tesseract-OCR"
tesseract_home = Path(os.environ.get("TESSERACT_HOME", default_tesseract))
exe_path = tesseract_home / "tesseract.exe"
eng_path = tesseract_home / "tessdata" / "eng.traineddata"
if not exe_path.is_file() or not eng_path.is_file():
    raise RuntimeError("Tesseract executable and eng.traineddata are required. Set TESSERACT_HOME.")

ocr_binaries = [(str(exe_path), "tesseract")]
ocr_binaries += [(str(path), "tesseract") for path in tesseract_home.glob("*.dll")]
ocr_data = [(str(eng_path), "tesseract/tessdata")]
osd_path = tesseract_home / "tessdata" / "osd.traineddata"
if osd_path.is_file():
    ocr_data.append((str(osd_path), "tesseract/tessdata"))

a = Analysis(
    [str(project / "desktop.py")],
    pathex=[str(project)],
    binaries=ocr_binaries,
    datas=ocr_data,
    hiddenimports=[],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[],
    noarchive=False,
)
pyz = PYZ(a.pure)
exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name=APP_NAME,
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=False,
    console=False,
    version=version_info,
)
coll = COLLECT(
    exe,
    a.binaries,
    a.datas,
    strip=False,
    upx=False,
    name=APP_NAME,
)
