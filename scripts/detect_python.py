"""
马恩全集 — 检测可用的 Python 路径

遍历常见 Python 路径，找到能导入 sentence-transformers 和 chromadb 的那个，
保存到 data/config.json。

用法：
  python scripts/detect_python.py
"""

import importlib.util
import json
import os
import subprocess
import sys
import time

_SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
_PROJECT_ROOT = os.path.abspath(os.path.join(_SCRIPT_DIR, ".."))
_CONFIG_PATH = os.path.join(_PROJECT_ROOT, "data", "config.json")

# 常见 Python 路径
_CANDIDATES = [
    # Windows Anaconda 常见路径
    r"D:\Program\Anaconda\envs\claude-env\python.exe",
    r"D:\Program\Anaconda\python.exe",
    r"C:\ProgramData\Anaconda3\envs\claude-env\python.exe",
    r"C:\ProgramData\Anaconda3\python.exe",
    r"C:\Users\%USERNAME%\Anaconda3\envs\claude-env\python.exe",
    r"C:\Users\%USERNAME%\Anaconda3\python.exe",
    # Linux/macOS 常见路径
    "/usr/bin/python3",
    "/usr/local/bin/python3",
    "/opt/anaconda3/envs/claude-env/bin/python",
    "/opt/anaconda3/bin/python",
    # 当前 python
    sys.executable,
]

_REQUIRED_MODULES = ["sentence_transformers", "chromadb"]


def check_python(python_path: str) -> bool:
    """检查指定 Python 能否导入所需模块。"""
    expanded = os.path.expandvars(python_path)
    if not os.path.isfile(expanded):
        return False
    try:
        for mod in _REQUIRED_MODULES:
            result = subprocess.run(
                [expanded, "-c", f"import {mod}; print({mod}.__version__)"],
                capture_output=True, text=True, timeout=30,
                env={**os.environ, "TRANSFORMERS_OFFLINE": "1", "HF_HUB_OFFLINE": "1"}
            )
            if result.returncode != 0:
                return False
        return True
    except (subprocess.TimeoutExpired, OSError):
        return False


def find_python() -> str | None:
    """遍历候选路径，返回第一个可用的。"""
    tested = set()
    for path in _CANDIDATES:
        expanded = os.path.expandvars(path)
        if expanded in tested:
            continue
        tested.add(expanded)
        if check_python(expanded):
            return expanded
    return None


def load_config() -> dict:
    if os.path.exists(_CONFIG_PATH):
        try:
            with open(_CONFIG_PATH, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception:
            return {}
    return {}


def save_config(config: dict):
    os.makedirs(os.path.dirname(_CONFIG_PATH), exist_ok=True)
    with open(_CONFIG_PATH, "w", encoding="utf-8") as f:
        json.dump(config, f, ensure_ascii=False, indent=2)


def main():
    # 先检查现有 config
    config = load_config()
    if "python_path" in config:
        path = config["python_path"]
        if os.path.isfile(path) and check_python(path):
            print(f"[info] 已有可用 Python 路径: {path}", file=sys.stderr)
            print(f"PYTHON_PATH={path}")
            return

    # 遍历查找
    print("[info] 正在检测 Python 环境...", file=sys.stderr)
    found = find_python()

    if found:
        config["python_path"] = found
        save_config(config)
        print(f"[info] 已找到并保存 Python 路径: {found}", file=sys.stderr)
        print(f"PYTHON_PATH={found}")
    else:
        print("[error] 未找到可用的 Python 环境！请安装 sentence-transformers 和 chromadb。", file=sys.stderr)
        print("PYTHON_PATH=")
        sys.exit(1)


if __name__ == "__main__":
    main()
