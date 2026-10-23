# Spine Cooling Log Viewer

Windows window that replays a recorded session: Temperature, Pressure and Flow, Power, and Status. It reads the three CSVs the runtime writes for one run:

```text
logs/<session>_sensors.csv
logs/<session>_pressure_100Hz.csv
logs/<session>_status_and_errors.csv
```

Open any one of those files, or the folder that contains them. The other two are picked up from the same folder and the same session stamp.

## Open with Python

From the repo root, with the project virtual environment active (`pip install -r requirements.txt` — the viewer needs PyQt6 and PyYAML):

```powershell
python tools/log_viewer/log_analyzer.py
```

That opens the newest `*_sensors.csv` it finds in the repo root, in `evaluation tool\` next to the repo, in the current directory, or in `evaluation tool\` under the current directory. Session files usually live in `logs\`, so point at one:

```powershell
python tools/log_viewer/log_analyzer.py logs
python tools/log_viewer/log_analyzer.py logs\20260817_170941_sensors.csv
```

A path can be a sensors, pressure, or status CSV, or the folder that holds them. You can also use **Open** in the window, or drop a file onto the window.

Use Python from python.org. Miniconda and Anaconda ship a PyQt6 build whose DLLs fail to load, and the window never opens.

## Build the exe

The build uses a separate virtual environment made with python.org Python 3.14 (PyInstaller can bundle that interpreter). From the repo root, once:

```powershell
py -3.14 -m venv build\logviewer-venv
.\build\logviewer-venv\Scripts\python.exe -m pip install PyQt6 pyinstaller pyyaml
```

Then, whenever you want a new exe:

```powershell
.\tools\log_viewer\build_log_analyzer.ps1
```

The script runs PyInstaller with `tools\log_viewer\log_analyzer.spec` and writes:

```text
dist\SpineCoolingLogViewer.exe
```

Double-click that file. It does not need Python installed on the machine you copy it to. Put session CSVs next to the exe, or in an `evaluation tool` folder beside it, and it opens the newest `*_sensors.csv`. Otherwise use **Open** or pass a path:

```powershell
.\dist\SpineCoolingLogViewer.exe logs\20260817_170941_sensors.csv
```
