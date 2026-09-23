# Build with: .venv\Scripts\python.exe -m PyInstaller --noconfirm Nearlock.spec
from PyInstaller.utils.hooks import collect_submodules, collect_dynamic_libs
from pathlib import Path

a = Analysis(
    ['app.py'], pathex=[],
    binaries=collect_dynamic_libs('winrt'),
    datas=[('README.md', '.')],
    hiddenimports=collect_submodules('winrt') + ['bleak.backends.winrt.scanner', 'bleak.backends.winrt.client'],
    hookspath=[], hooksconfig={}, runtime_hooks=[],
    excludes=['PySide6.QtWebEngineCore', 'PySide6.QtWebEngineWidgets', 'tkinter', 'unittest'],
    noarchive=False,
)
# Qt on Windows 11 imports the OS's unsuffixed ICU API. A different ICU from
# another tool on PATH (for example Poppler) must not shadow that system DLL.
a.binaries = [entry for entry in a.binaries
              if not Path(entry[0]).name.lower().startswith(('icuuc', 'icudt'))]
pyz = PYZ(a.pure)
exe = EXE(
    pyz, a.scripts, [], exclude_binaries=True,
    name='Nearlock', debug=False, bootloader_ignore_signals=False, strip=False, upx=False,
    console=False, disable_windowed_traceback=False,
    icon='assets/nearlock.ico', manifest='Nearlock.manifest',
)
coll = COLLECT(exe, a.binaries, a.datas, strip=False, upx=False, name='Nearlock')
