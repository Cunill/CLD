"""B7: how processes are started, paths passed and errors classified (no ffmpeg needed)."""

from __future__ import annotations

import sys
import time
from pathlib import Path

import pytest

from passimaker import ffmpeg
from passimaker.ffmpeg import _process
from passimaker.ffmpeg._process import (
    CREATE_NO_WINDOW,
    STDERR_TAIL_BYTES,
    StreamingProcess,
    classify,
    creation_flags,
    media_url,
    os_path,
    remove_file,
    run,
)


def test_windows_processes_start_without_console() -> None:
    assert creation_flags("win32") & CREATE_NO_WINDOW


def test_other_platforms_do_not_get_windows_flags() -> None:
    assert creation_flags("linux") == 0


def test_long_windows_paths_get_the_extended_prefix() -> None:
    long_path = Path("C:/" + "carpeta amb accents àèí/" * 12 + "foto.jpg")
    if sys.platform == "win32":
        assert os_path(long_path, "win32").startswith("\\\\?\\C:\\")
    short = Path("curt.wav").absolute()
    assert os_path(short, "win32") == str(short)
    assert os_path(long_path, "linux") == str(long_path.absolute())


@pytest.mark.skipif(sys.platform != "win32", reason="camins UNC de Windows")
def test_long_unc_paths_get_the_unc_prefix() -> None:
    path = Path("\\\\servidor\\comparticio\\" + "x" * 250 + "\\a.wav")
    assert os_path(path, "win32").startswith("\\\\?\\UNC\\servidor\\")


def test_media_urls_are_absolute_file_urls(tmp_path: Path) -> None:
    tricky = tmp_path / "-comença amb guió: i dos punts.wav"
    url = media_url(tricky)
    assert url.startswith("file:")
    assert Path(url.removeprefix("file:")).is_absolute()
    assert url.endswith(tricky.name)


@pytest.mark.parametrize(
    ("stderr", "writing", "key"),
    [
        ("av_interleaved_write_frame(): No space left on device", True, ffmpeg.ERROR_DISK_FULL),
        ("Error writing trailer: There is not enough space on the disk", False, ffmpeg.ERROR_DISK_FULL),
        ("file:C:/x/out.mp4: Permission denied", True, ffmpeg.ERROR_WRITE),
        ("file:/no/such/dir/out.mp4: No such file or directory", True, ffmpeg.ERROR_WRITE),
        ("file:/no/such/dir/out.mp4: No such file or directory", False, ffmpeg.ERROR_UNREADABLE),
        ("Invalid data found when processing input", False, ffmpeg.ERROR_UNREADABLE),
    ],
)
def test_ffmpeg_messages_become_message_keys(stderr: str, writing: bool, key: str) -> None:
    assert classify(stderr, ffmpeg.ERROR_UNREADABLE, writing=writing) == key


def _python(code: str) -> list[str]:
    return [sys.executable, "-c", code]


def test_stderr_is_drained_while_the_process_runs() -> None:
    # 4 MB on stderr would fill any pipe buffer; the process must still finish.
    code = "import sys\nfor i in range(4096): sys.stderr.write('x' * 1023 + '\\n')\nsys.stderr.write('FINAL')"
    process = StreamingProcess(_python(code), stdin=False, stdout=False)
    assert process.wait(30) == 0
    tail = process.stderr_text()
    assert tail.endswith("FINAL")
    assert len(tail) <= STDERR_TAIL_BYTES


def test_stdout_and_stderr_are_read_together() -> None:
    code = "import sys\nsys.stderr.write('e' * 2_000_000)\nsys.stdout.write('o' * 2_000_000)"
    result = run(_python(code), timeout_s=30)
    assert result.returncode == 0
    assert len(result.stdout) == 2_000_000
    assert len(result.stderr) == 2_000_000


def test_a_process_that_does_not_answer_times_out() -> None:
    start = time.monotonic()
    with pytest.raises(ffmpeg.FfmpegError) as caught:
        run(_python("import time; time.sleep(30)"), timeout_s=0.5)
    assert caught.value.message_key == ffmpeg.ERROR_TIMEOUT
    assert time.monotonic() - start < 10


def test_a_missing_program_is_reported_as_not_found(tmp_path: Path) -> None:
    with pytest.raises(ffmpeg.FfmpegError) as caught:
        run([str(tmp_path / "no_existeix")], timeout_s=5)
    assert caught.value.message_key == ffmpeg.ERROR_NOT_FOUND


def test_kill_stops_a_process_quickly() -> None:
    process = StreamingProcess(_python("import time; time.sleep(30)"), stdin=True, stdout=False)
    start = time.monotonic()
    process.kill()
    assert time.monotonic() - start < 2
    assert process.process.poll() is not None


def test_remove_file_only_deletes_regular_files(tmp_path: Path) -> None:
    target = tmp_path / "parcial.mp4"
    target.write_bytes(b"x")
    remove_file(target)
    assert not target.exists()
    remove_file(target)  # Already gone: no error.
    folder = tmp_path / "carpeta"
    folder.mkdir()
    remove_file(folder)
    assert folder.is_dir()


def test_process_module_is_the_only_one_that_imports_subprocess() -> None:
    package = Path(ffmpeg.__file__).parent
    users = sorted(p.name for p in package.glob("*.py") if "import subprocess" in p.read_text("utf-8"))
    assert users == [Path(_process.__file__).name]
