"""独立运行入口（PyInstaller 打包版）。

双击或直接执行生成的 rustdesk-api-server 可执行文件即可启动：
- 数据（SQLite、录像、日志）保存在可执行文件旁的 data/ 目录；
- 首次运行自动生成并保存 SECRET_KEY 到 data/secret_key；
- 默认监听 0.0.0.0:21114，可用 PORT 环境变量覆盖；
- 可选的 .env 放在可执行文件旁（DATA_DIR 也可指向别处）。
"""

from __future__ import annotations

import os
import secrets
import shutil
import sys
import tarfile
from pathlib import Path


def _lan_ip() -> str | None:
    import socket

    try:
        with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as sock:
            sock.connect(("8.8.8.8", 80))
            ip = sock.getsockname()[0]
        return None if ip.startswith("127.") else ip
    except OSError:
        return None


def _has_desktop() -> bool:
    if not sys.platform.startswith("linux"):
        return True
    return bool(os.environ.get("DISPLAY") or os.environ.get("WAYLAND_DISPLAY"))


def _app_home() -> Path:
    if getattr(sys, "frozen", False):
        return Path(sys.executable).resolve().parent
    return Path(__file__).resolve().parent.parent


def _bundle_root(home: Path) -> Path:
    """PyInstaller onedir 把 datas 放在 _internal，源码运行时就在仓库目录。"""
    return Path(getattr(sys, "_MEIPASS", home))


def _ensure_webclient(home: Path, data_dir: Path) -> Path:
    """首次运行时把镜像内置的网页远控包解压到 data/webroot/web。"""
    web_root = data_dir / "webroot" / "web"
    if (web_root / "index.html").exists():
        return web_root
    packages = sorted((_bundle_root(home) / "deploy" / "web").glob("rustdesk-web-*.tar.gz"))
    if not packages:
        return web_root
    web_root.parent.mkdir(parents=True, exist_ok=True)
    staging = web_root.parent / ".web.new"
    shutil.rmtree(staging, ignore_errors=True)
    staging.mkdir(parents=True)
    try:
        with tarfile.open(packages[-1], "r:gz") as archive:
            try:
                archive.extractall(staging, filter="data")  # Python 3.12+
            except TypeError:
                base = staging.resolve()
                for member in archive.getmembers():
                    if member.issym() or member.islnk() or member.isdev():
                        raise ValueError(f"不安全的归档条目：{member.name}")
                    target = (base / member.name).resolve()
                    if base != target and base not in target.parents:
                        raise ValueError(f"不安全的归档路径：{member.name}")
                archive.extractall(staging)
        if web_root.exists():
            shutil.rmtree(web_root)
        staging.rename(web_root)
        print(f"[rustdesk-api] 已安装网页远控到 {web_root}", flush=True)
    finally:
        shutil.rmtree(staging, ignore_errors=True)
    return web_root


def _prepare_environment(home: Path) -> Path:
    # 先读可执行文件旁的 .env，允许其中覆盖 DATA_DIR / PORT / ALLOWED_HOSTS。
    try:
        from rustdesk_server_api.env import load_env_file

        load_env_file(home / ".env")
    except Exception:
        pass

    data_dir = Path(os.environ.get("DATA_DIR") or home / "data").resolve()
    try:
        data_dir.mkdir(parents=True, exist_ok=True)
        for sub in ("db", "records", "logs"):
            (data_dir / sub).mkdir(parents=True, exist_ok=True)
    except OSError as exc:
        raise SystemExit(
            f"[rustdesk-api] 无法创建数据目录 {data_dir}：{exc}\n"
            "请检查路径是否存在、是否有写权限，或通过 DATA_DIR 指定其他目录。"
        ) from exc

    # 打包版要让数据库、日志落到可执行文件旁，而不是临时解包目录。
    os.environ["DATA_DIR"] = str(data_dir)
    os.environ.setdefault("WEBCLIENT_ROOT", str(_ensure_webclient(home, data_dir)))

    # 独立运行时默认允许局域网访问；可用 .env 覆盖为具体域名。
    os.environ.setdefault("ALLOWED_HOSTS", "*")

    if not os.environ.get("SECRET_KEY"):
        key_file = data_dir / "secret_key"
        if key_file.exists():
            key = key_file.read_text(encoding="utf-8").strip()
        else:
            key = secrets.token_urlsafe(50)
            key_file.write_text(key + "\n", encoding="utf-8")
            try:
                key_file.chmod(0o600)
            except OSError:
                pass
        os.environ["SECRET_KEY"] = key

    # 首次初始化需要部署密钥，避免同一局域网内他人抢先创建管理员。
    if not os.environ.get("WEB_SETUP_TOKEN"):
        token_file = data_dir / "setup_token"
        if token_file.exists():
            token = token_file.read_text(encoding="utf-8").strip()
        else:
            token = secrets.token_urlsafe(32)
            token_file.write_text(token + "\n", encoding="utf-8")
            try:
                token_file.chmod(0o600)
            except OSError:
                pass
        os.environ["WEB_SETUP_TOKEN"] = token

    return home


def main() -> int:
    home = _app_home()
    if not getattr(sys, "frozen", False):
        sys.path.insert(0, str(home))
    home = _prepare_environment(home)
    os.environ.setdefault("DJANGO_SETTINGS_MODULE", "rustdesk_server_api.settings")

    if hasattr(sys.stdout, "reconfigure"):
        try:
            sys.stdout.reconfigure(encoding="utf-8")
            sys.stderr.reconfigure(encoding="utf-8")
        except Exception:
            pass

    import django

    django.setup()

    from django.core.management import call_command

    call_command("migrate", interactive=False, verbosity=0)
    # db 缓存后端需要 rustdesk_cache 表；Docker 镜像由 entrypoint.sh 建，裸机包在这里建。
    call_command("createcachetable", verbosity=0)

    try:
        from waitress import serve

        from rustdesk_server_api.wsgi import application

        port = int(os.environ.get("PORT", "21114"))
        threads = int(os.environ.get("WEB_THREADS", "8"))
        console_url = f"http://127.0.0.1:{port}/console/"
        lan_ip = _lan_ip()
        lan_url = f"http://{lan_ip}:{port}/console/" if lan_ip else ""
        lines = [
            "",
            "=" * 64,
            "  RustDesk API Server 已启动",
            f"  控制台（本机）：  {console_url}",
            f"  网页远控：        http://127.0.0.1:{port}/web/  （需先登录控制台）",
        ]
        if lan_url:
            lines.append(f"  控制台（局域网）：{lan_url}")
        try:
            from django.apps import apps

            needs_setup = not apps.get_model("api", "UserProfile").objects.exists()
        except Exception:
            needs_setup = False
        if needs_setup:
            lines.append(f"  初始化密钥：      {os.environ.get('WEB_SETUP_TOKEN', '')}")
        lines += [
            f"  健康检查：        http://127.0.0.1:{port}/api/health",
            f"  数据目录：        {os.environ['DATA_DIR']}",
            "  按 Ctrl+C 停止服务",
            "=" * 64,
            "",
        ]
        print("\n".join(lines), flush=True)

        if os.environ.get("OPEN_BROWSER", "1").lower() not in ("0", "false", "no", "off"):
            if _has_desktop():
                import threading
                import webbrowser

                def _open_console() -> None:
                    try:
                        webbrowser.open(console_url)
                    except Exception:
                        pass

                threading.Timer(1.5, _open_console).start()
            else:
                print("[rustdesk-api] 未检测到桌面环境，请手动用浏览器打开上面的控制台地址。", flush=True)

        serve(application, host="0.0.0.0", port=port, threads=threads)
    except KeyboardInterrupt:
        print("\n[rustdesk-api] 已停止")
    except OSError as exc:
        print(f"[rustdesk-api] 启动失败：端口 {os.environ.get('PORT', '21114')} 可能已被占用（{exc}）", file=sys.stderr)
        return 1
    except Exception as exc:  # pragma: no cover - 仅在打包版运行时触发
        print(f"[rustdesk-api] 启动失败：{exc}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
