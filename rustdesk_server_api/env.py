# -*- coding: utf-8 -*-
"""环境变量解析小工具。

集中在 settings 与测试里复用，避免各处 `os.environ.get(...) == "1"` 的写法不一致。
布尔值接受 1/true/yes/on（不区分大小写），其余视为 False。
"""

import hashlib
import os

_LEGACY_SECRET_DIGEST = "7cdea2def2fe4cd893bb70a43bc9623706c42d06e5b3cad206eb67ce5b0c46da"

_TRUE = {"1", "true", "yes", "y", "on"}
_FALSE = {"0", "false", "no", "n", "off", ""}


def is_valid_secret_key(value):
    """Reject placeholders, low-entropy strings and the key published by older versions."""
    if not isinstance(value, str) or len(value) < 50 or len(set(value)) < 10:
        return False
    if value.startswith("django-insecure-"):
        return False
    lowered = value.lower()
    if any(word in lowered for word in ("changeme", "change-me", "secret-key", "secretkey", "password")):
        return False
    return hashlib.sha256(value.encode()).hexdigest() != _LEGACY_SECRET_DIGEST


def env_str(name, default=""):
    value = os.environ.get(name)
    if value is None:
        return default
    return value.strip()


def env_bool(name, default=False):
    raw = os.environ.get(name)
    if raw is None:
        return default
    value = raw.strip().lower()
    if value in _TRUE:
        return True
    if value in _FALSE:
        return False
    return default


def env_int(name, default=0):
    raw = os.environ.get(name)
    if raw is None or str(raw).strip() == "":
        return default
    try:
        return int(str(raw).strip())
    except (TypeError, ValueError):
        return default


def env_list(name, default=()):
    raw = os.environ.get(name)
    if raw is None:
        return list(default)
    return [item.strip() for item in raw.split(",") if item.strip()]


def load_env_file(path):
    """读取 KEY=VALUE 形式的 .env 文件（不覆盖已存在的环境变量）。

    只做最简解析：忽略空行与 # 注释，去掉值两端的成对引号，
    不支持变量插值——需要复杂语法时请用 systemd EnvironmentFile 或容器编排。
    """
    try:
        with open(path, "r", encoding="utf-8-sig") as handle:
            for line in handle:
                line = line.strip()
                if not line or line.startswith("#") or "=" not in line:
                    continue
                key, _, value = line.partition("=")
                key = key.strip()
                value = value.strip()
                if len(value) >= 2 and value[0] == value[-1] and value[0] in ('"', "'"):
                    value = value[1:-1]
                if key and key not in os.environ:
                    os.environ[key] = value
    except OSError:
        pass
