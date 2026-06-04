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
import subprocess
import sys
import time
from concurrent.futures import ThreadPoolExecutor, as_completed


_SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
_PROJECT_ROOT = os.path.dirname(_SCRIPT_DIR) if os.path.basename(_SCRIPT_DIR) == "scripts" else _SCRIPT_DIR


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


def _get_python_path() -> str:
    """获取当前 Python 路径。"""
    return sys.executable


def search_single(query: str, top_k: int, min_score: float, volume: str = None) -> list[dict]:
    """调用 search.py 搜索单个主题，返回结果列表。"""
    python_path = _get_python_path()
    search_script = os.path.join(_PROJECT_ROOT, "search.py")

    cmd = [python_path, "-X", "utf8", search_script, query,
           "--top_k", str(top_k), "--min-score", str(min_score)]
    if volume:
        cmd.extend(["--volume", volume])

    try:
        result = subprocess.run(
            cmd, capture_output=True, text=True, timeout=120,
            env={**os.environ, "TRANSFORMERS_OFFLINE": "1", "HF_HUB_OFFLINE": "1"}
        )
        if result.returncode != 0:
            print(f"[warn] 搜索 '{query[:20]}' 失败: {result.stderr.strip()}", file=sys.stderr)
            return []

        # 解析 JSON 输出（search.py 的 stdout 是 JSON）
        output = result.stdout.strip()
        if not output:
            return []
        # 找到 JSON 开始位置（跳过 info 日志）
        json_start = output.find("[")
        if json_start == -1:
            return []
        return json.loads(output[json_start:])

    except subprocess.TimeoutExpired:
        print(f"[warn] 搜索 '{query[:20]}' 超时", file=sys.stderr)
        return []
    except Exception as e:
        print(f"[warn] 搜索 '{query[:20]}' 异常: {e}", file=sys.stderr)
        return []


def merge_results(all_results: list[dict]) -> list[dict]:
    """合并去重，按卷排序，合并相邻页（间隔≤2合并）。"""
    # 去重
    seen = set()
    unique = []
    for r in all_results:
        key = (r["volume"], r["page_number"])
        if key not in seen:
            seen.add(key)
            unique.append(r)

    # 按卷分组，卷内按页码排序
    from collections import defaultdict
    by_vol = defaultdict(list)
    for r in unique:
        by_vol[r["volume"]].append(r["page_number"])

    # 每卷内排序 + 合并相邻页（间隔≤2）
    merged = []
    for vol in sorted(by_vol.keys(), key=lambda v: (
        int("".join(c for c in v if c.isdigit()) or 0),
        {"上": 0, "中": 1, "下": 2}.get("".join(c for c in v if not c.isdigit()), 3)
    )):
        pages = sorted(set(by_vol[vol]))
        # 合并
        blocks = []
        start = pages[0]
        prev = pages[0]
        for p in pages[1:]:
            if p - prev <= 2:  # 间隔≤2合并
                prev = p
            else:
                blocks.append((start, prev))
                start = p
                prev = p
        blocks.append((start, prev))

        for s, e in blocks:
            merged.append({
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

    # 按 ; 分割查询
    queries = [q.strip() for q in args.queries.split(";") if q.strip()]
    if not queries:
        print("请提供至少一个搜索主题", file=sys.stderr)
        sys.exit(1)

    print(f"[info] 共 {len(queries)} 个搜索主题，并发搜索中...", file=sys.stderr)
    start = time.time()

    # 并发搜索
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

    # 合并去重排序
    merged = merge_results(all_results)

    print(f"[用时: {elapsed:.2f}秒]", file=sys.stderr)

    # 输出 JSON（子 agent 解析用）
    result = {
        "queries": queries,
        "total_blocks": len(merged),
        "results": merged,
    }
    print(json.dumps(result, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
