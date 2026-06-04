"""
马恩全集 — 按地址查询原文

根据卷次+页码从 ChromaDB 拉取原文，返回完整文本（含 header、脚注）。

用法：
  python query.py 42 128 129
  python query.py 46上 207 208 209 210
  python query.py 23 100-105 110-115    # 支持页码范围

日志走 stderr，结果（JSON）走 stdout。
"""

import argparse
import json
import os
import re
import sys
import time


_SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
_PROJECT_ROOT = os.path.dirname(_SCRIPT_DIR) if os.path.basename(_SCRIPT_DIR) == "scripts" else _SCRIPT_DIR
if _PROJECT_ROOT not in sys.path:
    sys.path.insert(0, _PROJECT_ROOT)

from scripts.utils import lookup_chapter

_CHROMA_DIR = os.path.join(_PROJECT_ROOT, "chroma_db")
_COLLECTION_NAME = "marx_engels"


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


def get_collection():
    import chromadb
    from chromadb.errors import NotFoundError
    if not os.path.isdir(_CHROMA_DIR):
        raise RuntimeError(f"向量数据库不存在: {_CHROMA_DIR}")
    client = chromadb.PersistentClient(path=_CHROMA_DIR)
    try:
        collection = client.get_collection(_COLLECTION_NAME)
    except (ValueError, NotFoundError):
        raise RuntimeError(f"Collection '{_COLLECTION_NAME}' 不存在")
    if collection.count() == 0:
        raise RuntimeError("向量数据库为空")
    return collection


def _parse_footnotes(fn_data):
    if not fn_data:
        return []
    if isinstance(fn_data, list):
        return fn_data
    try:
        return json.loads(fn_data)
    except Exception:
        return []


def format_volume_label(volume_slug: str) -> str:
    if not volume_slug:
        return ""
    m = re.match(r"(\d+)(.*)", volume_slug)
    if not m:
        return f"第{volume_slug}卷"
    vol_num = m.group(1)
    sub = m.group(2)
    sub_map = {"上": "（上）", "中": "（中）", "下": "（下）"}
    sub_label = sub_map.get(sub, "")
    return f"第{vol_num}卷{sub_label}"


def fetch_pages(collection, volume: str, page_numbers: list) -> list[dict]:
    """从 ChromaDB 拉取指定页的原文。"""
    results = []
    for pn in page_numbers:
        try:
            raw = collection.get(
                where={"$and": [
                    {"volume": {"$eq": volume}},
                    {"page_number": {"$eq": pn}},
                ]},
                include=["documents", "metadatas"],
            )
        except Exception:
            results.append({"page_number": pn, "volume": volume, "exists": False, "text": "", "header_title": "", "footnotes": []})
            continue

        if raw["ids"] and len(raw["ids"]) > 0:
            meta = raw["metadatas"][0]
            results.append({
                "page_number": pn,
                "volume": volume,
                "address": f"v{volume} p{pn}",
                "exists": True,
                "text": raw["documents"][0],
                "chunk_id": meta.get("chunk_id", ""),
                "header_title": meta.get("header_title", ""),
                "chapter": lookup_chapter(volume, pn),
                "footnotes": _parse_footnotes(meta.get("footnotes", "")),
            })
        else:
            results.append({"page_number": pn, "volume": volume, "exists": False, "text": "", "header_title": "", "footnotes": []})

    return results


def parse_page_args(args: list) -> list[tuple[str, list[int]]]:
    """解析命令行参数为 [(vol, [p1, p2, ...]), ...] 格式。

    支持格式：
      query.py 42 128 129        传统格式
      query.py v42 p128 p129     地址格式
      query.py v42 p128-p130     地址格式+范围
    """
    if not args:
        return []

    # 标准化：去掉 v/p 前缀
    normalized = []
    for a in args:
        a = a.strip()
        if a.startswith("v") or a.startswith("V"):
            normalized.append(a[1:])  # v42 → 42
        elif a.startswith("p") or a.startswith("P"):
            normalized.append(a[1:])  # p128 → 128
        else:
            normalized.append(a)

    vol = normalized[0]
    page_args = normalized[1:]
    pages = []
    for p in page_args:
        # 去除每个部分可能残留的 v/p 前缀
        cleaned = p.lstrip("vVpP")
        if "-" in cleaned:
            parts = cleaned.split("-")
            try:
                start, end = int(parts[0].lstrip("vVpP")), int(parts[1].lstrip("vVpP"))
                pages.extend(range(start, end + 1))
            except ValueError:
                print(f"⚠ 页码范围格式无效: {p}", file=sys.stderr)
        else:
            try:
                pages.append(int(cleaned))
            except ValueError:
                print(f"⚠ 无效页码: {p}", file=sys.stderr)
    # 去重 + 保险：如果起始=结束，只保留一页
    pages = sorted(set(pages))
    if not pages:
        print(f"错误：未解析到有效页码。卷次={vol!r}, 参数={page_args}", file=sys.stderr)
        print("页码应为数字或用 - 连接的范围，如：128 或 128-130", file=sys.stderr)
        print("不要加 --page、--pages 等参数名，直接写数字", file=sys.stderr)
        print("示例: python query.py v42 p128 p129 p130", file=sys.stderr)
        sys.exit(1)
    return [(vol, pages)]


def main():
    _ensure_utf8_stream()

    parser = argparse.ArgumentParser(description="马恩全集 — 按地址查询原文")
    parser.add_argument("args", type=str, nargs="*", help="卷次 页码1 [页码2] ... 或 卷次 起始-结束")
    parser.add_argument("--json", action="store_true", help="输出 JSON 格式")

    parsed = parser.parse_args()
    args = parsed.args
    json_mode = parsed.json

    if args and args[0].startswith("--"):
        print(f"错误：未知参数 {args[0]}", file=sys.stderr)
        print("query.py 不需要 --page 或 --address 参数名，直接写卷次和页码即可", file=sys.stderr)
        sys.exit(1)

    if not args or len(args) < 2:
        print("错误：需要提供卷次和页码", file=sys.stderr)
        print("", file=sys.stderr)
        print("正确格式：", file=sys.stderr)
        print("  python query.py 42 128 129 130", file=sys.stderr)
        print("  python query.py v42 p128 p129 p130", file=sys.stderr)
        print("  python query.py 46上 207 208 209", file=sys.stderr)
        print("  python query.py v46上 p207 p208 p209", file=sys.stderr)
        print("  python query.py 23 100-105 110-115", file=sys.stderr)
        print("  python query.py v23 p100-p105 p110-p115", file=sys.stderr)
        print("", file=sys.stderr)
        print("注意：参数是字符串不是数字，卷次可加 v 前缀也可以不加，", file=sys.stderr)
        print("页码可加 p 前缀也可以不加。连续页码用 - 连接。", file=sys.stderr)
        sys.exit(1)

    volume_pages = parse_page_args(args)

    try:
        collection = get_collection()
    except RuntimeError as e:
        print(f"数据库错误: {e}", file=sys.stderr)
        sys.exit(1)

    start = time.time()
    all_results = []

    for vol, pages in volume_pages:
        vol_label = format_volume_label(vol)
        print(f"[info] 正在拉取 {vol_label} 第{pages[0]}-{pages[-1]}页...", file=sys.stderr)
        page_data = fetch_pages(collection, vol, pages)
        all_results.extend(page_data)

    elapsed = time.time() - start
    print(f"[用时: {elapsed:.2f}秒]", file=sys.stderr)

    if json_mode:
        print(json.dumps(all_results, ensure_ascii=False, indent=2))
    else:
        for p in all_results:
            vol_label = format_volume_label(p["volume"])
            if not p["exists"]:
                print(f"——— {vol_label} · 第{p['page_number']}页 ———")
                print(" （未收录）")
                print()
                continue

            print(f"——— {vol_label} · 第{p['page_number']}页 ———")
            if p.get("chapter"):
                print(f"篇章: {p['chapter']}")
            if p.get("header_title"):
                print(f"标题: {p['header_title']}")
            print(p["text"])
            if p.get("footnotes"):
                for fn in p["footnotes"][:5]:
                    marker = fn.get("marker", "") if isinstance(fn, dict) else ""
                    text = fn.get("text", "")[:80] if isinstance(fn, dict) else str(fn)[:80]
                    print(f"[脚注] {marker} {text}")
            print()


if __name__ == "__main__":
    main()
