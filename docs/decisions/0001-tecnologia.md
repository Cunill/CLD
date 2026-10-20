# 0001 · Tecnologia: Python + Qt + NumPy/OpenCV + FFmpeg

- **Data:** 20/10/2026 · **Estat:** acceptada (aprovació del pla)
- **Context:** cal un motor únic per a la previsualització i l'exportació i proves automàtiques d'imatge i so.
- **Decisió:** opció A del Pas 2 del pla. Python 3.12, PySide6, NumPy, OpenCV, Pillow + pillow-heif,
  sounddevice, FFmpeg extern per canonada, PyInstaller.
- **Detall:** es fa servir `pyside6-essentials` (sense els mòduls addicionals de Qt) per reduir la mida del ZIP (risc R9).
- **Conseqüències:** FFmpeg GPL (amb x264) és acceptable perquè l'ús és intern (risc R7).
