import shutil
import subprocess
import sys
import time
from pathlib import Path
from urllib.request import urlopen

ROOT = Path(__file__).resolve().parent
APP_FILE = ROOT / "streamlit_app.py"
STREAMLIT_PORT = 8501
LOCAL_URL = f"http://127.0.0.1:{STREAMLIT_PORT}"

XT_DIR = ROOT / ".xtunnel"
XT_KEY_FILE = ROOT / ".xtunnel_key"


def wait_http_ok(url: str, proc: subprocess.Popen, timeout_sec: int = 45) -> bool:
    for _ in range(timeout_sec):
        if proc.poll() is not None:
            return False
        try:
            urlopen(url, timeout=2)
            return True
        except Exception:
            time.sleep(1)
    return False


def stop_proc(proc: subprocess.Popen | None) -> None:
    if not proc:
        return
    if proc.poll() is None:
        proc.terminate()
        try:
            proc.wait(timeout=5)
        except subprocess.TimeoutExpired:
            proc.kill()


def resolve_xtunnel_exe() -> str | None:
    XT_DIR.mkdir(parents=True, exist_ok=True)
    local_exe = XT_DIR / "xtunnel.exe"
    if local_exe.exists():
        return str(local_exe)
    in_path = shutil.which("xtunnel")
    if in_path:
        return in_path
    return None


def get_xtunnel_key() -> str:
    if XT_KEY_FILE.exists():
        key = XT_KEY_FILE.read_text(encoding="utf-8", errors="replace").replace("\ufeff", "").strip()
        if key:
            return key

    print("Нужен ключ активации xTunnel (один раз).")
    print("Получить ключ: https://xtunnel.ru/register-license")
    key = input("Вставьте ключ xTunnel (или Enter, чтобы пропустить): ").replace("\ufeff", "").strip()
    if key:
        XT_KEY_FILE.write_text(key, encoding="utf-8")
    return key


def register_xtunnel_if_key_exists(xtunnel_exe: str) -> None:
    key = get_xtunnel_key()
    if not key:
        return
    cmd = [xtunnel_exe, "register", key]
    subprocess.run(cmd, capture_output=True, text=True, encoding="utf-8", errors="replace")


def start_streamlit() -> subprocess.Popen:
    cmd = [
        sys.executable,
        "-m",
        "streamlit",
        "run",
        str(APP_FILE),
        "--server.address",
        "127.0.0.1",
        "--server.port",
        str(STREAMLIT_PORT),
        "--server.headless",
        "true",
    ]
    return subprocess.Popen(cmd, cwd=str(ROOT), stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)


def main() -> int:
    if not APP_FILE.exists():
        print(f"Не найден файл приложения: {APP_FILE}")
        return 1

    xtunnel_exe = resolve_xtunnel_exe()
    if not xtunnel_exe:
        print("xTunnel не найден в системе.")
        print("Установите xTunnel: https://xtunnel.ru/docs/install/windows/zip")
        print("Или положите xtunnel.exe в папку:")
        print(str(XT_DIR))
        return 1

    print("Запускаю опросник...")
    streamlit_proc = None

    try:
        streamlit_proc = start_streamlit()
        if not wait_http_ok(LOCAL_URL, streamlit_proc, timeout_sec=45):
            print("Streamlit не запустился. Выполните: pip install -r requirements.txt")
            return 1

        register_xtunnel_if_key_exists(xtunnel_exe)

        print("Опросник готов.")
        print("Сейчас запущу xTunnel в этом окне.")
        print("Скопируйте строку 'Public URL' и отправьте респондентам.")
        print("Чтобы остановить всё, нажмите Ctrl+C.\n")

        # Важно: запускаем xTunnel в foreground, чтобы его штатный экран
        # показывал Public URL (это стабильнее, чем парсинг логов).
        cmd = [xtunnel_exe, "http", str(STREAMLIT_PORT), "--force"]
        completed = subprocess.run(cmd, cwd=str(ROOT))
        return completed.returncode

    except KeyboardInterrupt:
        print("\nОстанавливаю сервер...")
        return 0
    finally:
        stop_proc(streamlit_proc)


if __name__ == "__main__":
    raise SystemExit(main())
