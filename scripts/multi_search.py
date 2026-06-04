"""
马恩全集 — 多主题并发搜索

输入以 ; 分隔的多个主题，同时搜索，合并去重排序后输出。

用法：
  python multi_search.py "感性活动;异化;类本质"
  python multi_search.py "剩余价值;资本积累" --top_k 3
  python multi_search.py "一般智力;general intellect" --min-score 0.3
"""

import argparse
import json
import os
import sys
import time
import threading
from concurrent.futures import ThreadPoolExecutor, as_completed
from collections import defaultdict

_search_lock = threading.Lock()

_SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
_PROJECT_ROOT = os.path.dirname(_SCRIPT_DIR) if os.path.basename(_SCRIPT_DIR) == "scripts" else _SCRIPT_DIR
if _PROJECT_ROOT not in sys.path:
    sys.path.insert(0, _PROJECT_ROOT)

# 直接导入 search 函数（模型全局缓存，只加载一次）
from search import search as _search


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


def search_single(query: str, top_k: int, min_score: float, volume: str = None) -> list[dict]:
    """直接调用 search() 函数，模型全局缓存，ChromaDB 串行访问。"""
    try:
        import os as _os
        _os.environ["TRANSFORMERS_OFFLINE"] = "1"
        _os.environ["HF_HUB_OFFLINE"] = "1"
        with _search_lock:
            results = _search(query, top_k=top_k, volume=volume, min_score=min_score)
        return results
    except Exception as e:
        print(f"[warn] 搜索 '{query[:20]}' 异常: {e}", file=sys.stderr)
        return []


def merge_results(all_results: list[dict]) -> list[dict]:
    """合并去重，按卷排序，合并相邻页（间隔≤2合并）。"""
    seen = set()
    unique = []
    for r in all_results:
        key = (r["volume"], r["page_number"])
        if key not in seen:
            seen.add(key)
            unique.append(r)

    by_vol = defaultdict(list)
    for r in unique:
        by_vol[r["volume"]].append(r["page_number"])

    merged = []
    for vol in sorted(by_vol.keys(), key=lambda v: (
        int("".join(c for c in v if c.isdigit()) or 0),
        {"上": 0, "中": 1, "下": 2}.get("".join(c for c in v if not c.isdigit()), 3)
    )):
        pages = sorted(set(by_vol[vol]))
        blocks = []
        start = pages[0]
        prev = pages[0]
        for p in pages[1:]:
            if p - prev <= 2:
                prev = p
            else:
                blocks.append((start, prev))
                start = p
                prev = p
        blocks.append((start, prev))

        for s, e in blocks:
            merged.append({
                "address": f"v{vol} p{s}-{e}" if s != e else f"v{vol} p{s}",
                "volume": vol,
                "page_start": s,
                "page_end": e,
            })

    return merged


def main():
    _ensure_utf8_stream()

    parser = argparse.ArgumentParser(description="马恩全集 — 多主题并发搜索")
    parser.add_argument("queries", type=str, help="多个搜索主题，用 ; 分隔")
    parser.add_argument("--top_k", type=int, default=5, help="每个主题返回前N个（默认5）")
    parser.add_argument("--min-score", type=float, default=0.0, help="最低相关度阈值")
    parser.add_argument("--volume", type=str, default=None, help="限定卷次")

    args = parser.parse_args()

    queries = [q.strip() for q in args.queries.split(";") if q.strip()]
    if not queries:
        print("请提供至少一个搜索主题", file=sys.stderr)
        sys.exit(1)

    print(f"[info] 共 {len(queries)} 个搜索主题，并发搜索中...", file=sys.stderr)
    start = time.time()

    all_results = []
    with ThreadPoolExecutor(max_workers=min(len(queries), 8)) as executor:
        futures = {
            executor.submit(search_single, q, args.top_k, args.min_score, args.volume): q
            for q in queries
        }
        for future in as_completed(futures):
            q = futures[future]
            try:
                results = future.result()
                all_results.extend(results)
                print(f"[info]  '{q[:30]}' → {len(results)} 条", file=sys.stderr)
            except Exception as e:
                print(f"[info]  '{q[:30]}' 出错: {e}", file=sys.stderr)

    elapsed = time.time() - start

    if not all_results:
        print("未找到相关内容。", file=sys.stderr)
        sys.exit(0)

    merged = merge_results(all_results)

    print(f"[用时: {elapsed:.2f}秒]", file=sys.stderr)

    result = {
        "queries": queries,
        "total_blocks": len(merged),
        "results": merged,
    }
    print(json.dumps(result, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
