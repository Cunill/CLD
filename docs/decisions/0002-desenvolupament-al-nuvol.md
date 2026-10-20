# 0002 · Desenvolupament en sessions al núvol

- **Data:** 20/10/2026 · **Estat:** acceptada (canvi del pla aprovat per l'usuari abans de B0)
- **Context:** el pla preveia Claude Code en local a Windows. L'usuari ha triat fer les sessions al núvol (Linux).
- **Decisió:**
  - Les sessions corren a Linux; el nucli i la interfície (Qt sense pantalla) es proven allà.
  - La CI de GitHub Actions sobre Windows verifica cada PR (rutes, FFmpeg 7.1.1 fixat, Qt a Windows).
  - FFmpeg: a Windows, `tools/obtenir_ffmpeg.ps1` descarrega la versió 7.1.1 (essentials de gyan.dev,
    mirall a GitHub `GyanD/codexffmpeg`) i en verifica el SHA-256. A Linux, `tools/obtenir_ffmpeg.sh`
    comprova que hi hagi FFmpeg ≥ 6 al sistema (el servidor de compilacions estàtiques no és accessible
    des de l'entorn al núvol).
  - Les verificacions manuals es fan amb els artefactes de la CI (captures, vídeo de mostra, ZIP).
- **Conseqüències:** les proves que depenen de la versió d'FFmpeg han de tenir toleràncies (6.x a Linux, 7.1.1 a Windows).
