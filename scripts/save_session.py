"""
马恩全集 — 保存搜索记录到 review_sessions.json

用法：
  python save_session.py --topic "感性活动" --keywords "感性活动;人的感性活动" --address 42 128 129 130
  python save_session.py --topic "异化" --keywords "异化;异化劳动" --address 42 94-100 --address 3 317

参数可重复，--address 的格式为 {卷次} {页码1} {页码2} ... 支持页码范围。
"""

import argparse
import json
import os
import re
import sys
import time

_SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
_PROJECT_ROOT = os.path.dirname(_SCRIPT_DIR) if os.path.basename(_SCRIPT_DIR) == "scripts" else _SCRIPT_DIR

_SESSION_PATH = os.path.join(_PROJECT_ROOT, "data", "review_sessions.json")


def _ensure_utf8_stream():
    for name in ("stdout", "stderr"):
        stream = getattr(sys, name, None)
        if stream is None:
            continue
        if hasattr(stream, "reconfigure"):
            stream.reconfigure(encoding="utf-8")
        elif hasattr(stream, "detach"):
            import io
            setattr(sys, name,
                    io.TextIOWrapper(stream.detach(), encoding="utf-8", line_buffering=True))


def parse_address(raw: str) -> list[tuple[str, int]]:
    """解析地址字符串。

    支持格式：
      --address 42 128 129          传统格式
      --address v42 p128 p129       地址格式
      --address v42 p128-p130       地址格式+范围
    """
    parts = raw.strip().split()
    if len(parts) < 2:
        print(f"⚠ 无效地址: {raw}", file=sys.stderr)
        return []

    # 标准化：去掉 v/p 前缀
    normalized = []
    for a in parts:
        a = a.strip()
        if a.startswith("v") or a.startswith("V"):
            normalized.append(a[1:])
        elif a.startswith("p") or a.startswith("P"):
            normalized.append(a[1:])
        else:
            normalized.append(a)

    vol = normalized[0]
    pages = []
    for p in normalized[1:]:
        if "-" in p:
            try:
                s, e = p.split("-")
                pages.extend(range(int(s), int(e) + 1))
            except ValueError:
                print(f"⚠ 页码范围无效: {p}", file=sys.stderr)
        else:
            try:
                pages.append(int(p))
            except ValueError:
                print(f"⚠ 无效页码: {p}", file=sys.stderr)
    return [(vol, pn) for pn in sorted(set(pages))]


def load_sessions() -> dict:
    if os.path.exists(_SESSION_PATH):
        try:
            with open(_SESSION_PATH, "r", encoding="utf-8") as f:
                return json.load(f)
        except (json.JSONDecodeError, Exception):
            return {}
    return {}


def save_sessions(sessions: dict):
    os.makedirs(os.path.dirname(_SESSION_PATH), exist_ok=True)
    with open(_SESSION_PATH, "w", encoding="utf-8") as f:
        json.dump(sessions, f, ensure_ascii=False, indent=2)


def main():
    _ensure_utf8_stream()

    parser = argparse.ArgumentParser(description="马恩全集 — 保存搜索记录")
    parser.add_argument("--topic", required=True, help="主题名称")
    parser.add_argument("--keywords", help="搜索关键词，多个用 ; 分隔")
    parser.add_argument("--address", action="append", default=[], help="卷次+页码，可重复，如 --address 42 128 129")

    args = parser.parse_args()

    if not args.address:
        print("请提供至少一个地址 (--address)", file=sys.stderr)
        sys.exit(1)

    # 解析所有地址
    all_pages = []
    for addr in args.address:
        all_pages.extend(parse_address(addr))

    if not all_pages:
        print("未解析到有效地址", file=sys.stderr)
        sys.exit(1)

    # 按卷分组
    from collections import defaultdict
    by_vol = defaultdict(set)
    for vol, pn in all_pages:
        by_vol[vol].add(pn)

    # 转换为 sorted list
    covered_pages = {}
    for vol in sorted(by_vol.keys(), key=lambda v: (
        int("".join(c for c in v if c.isdigit()) or 0),
        {"上": 0, "中": 1, "下": 2}.get("".join(c for c in v if not c.isdigit()), 3)
    )):
        covered_pages[vol] = sorted(by_vol[vol])

    # 加载已有 sessions
    sessions = load_sessions()

    # 合并或新增
    topic = args.topic.strip()
    if topic in sessions:
        existing = sessions[topic]
        for vol, pages in covered_pages.items():
            existing.setdefault("covered_pages", {}).setdefault(vol, [])
            existing["covered_pages"][vol] = sorted(set(existing["covered_pages"][vol]) | set(pages))
        if args.keywords:
            existing.setdefault("search_keywords", [])
            for kw in args.keywords.split(";"):
                kw = kw.strip()
                if kw and kw not in existing["search_keywords"]:
                    existing["search_keywords"].append(kw)
        existing["last_updated"] = time.strftime("%Y-%m-%d")
    else:
        # 生成地址列表
        addr_list = []
        for v, pages in covered_pages.items():
            for pn in sorted(pages):
                addr_list.append(f"v{v} p{pn}")
        entry = {
            "last_updated": time.strftime("%Y-%m-%d"),
            "covered_pages": {v: sorted(p) for v, p in covered_pages.items()},
            "addresses": addr_list,
            "search_keywords": [kw.strip() for kw in args.keywords.split(";") if kw.strip()] if args.keywords else [],
            "saturated": False,
        }
        sessions[topic] = entry

    save_sessions(sessions)

    count = sum(len(p) for p in covered_pages.values())
    print(f"[info] 已保存 '{topic}' 的搜索记录: {count} 页", file=sys.stderr)
    print(f"[info] 当前共 {len(sessions)} 个主题", file=sys.stderr)


if __name__ == "__main__":
    main()
