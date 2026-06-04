"""
马恩全集 — 语义检索工具（仅返回地址）

对查询内容进行语义搜索，返回命中页的（卷次, 页码, 相关度）。

用法：
  python search.py "感性活动"
  python search.py "剩余价值" --top_k 5 --volume 23
  python search.py "一般智力" --min-score 0.3
  python search.py --info

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

_CHROMA_DIR = os.path.join(_PROJECT_ROOT, "chroma_db")
_COLLECTION_NAME = "marx_engels"
_MODEL_NAME = "BAAI/bge-large-zh-v1.5"
_QUERY_PREFIX = "为这个句子生成表示以用于检索相关段落: "

_model = None


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


def load_model():
    global _model
    if _model is not None:
        return _model
    from sentence_transformers import SentenceTransformer
    start = time.time()
    print("[info] 加载嵌入模型中...", file=sys.stderr)
    _model = SentenceTransformer(_MODEL_NAME, device="cpu")
    print(f"[info] 模型加载完毕（{time.time() - start:.1f}秒）", file=sys.stderr)
    return _model


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


def search(query, top_k=10, volume=None, min_score=0.0):
    """语义检索，返回 (volume, page_number, score) 列表。"""
    model = load_model()
    collection = get_collection()

    prefixed = _QUERY_PREFIX + query
    q_vec = model.encode([prefixed], normalize_embeddings=True)[0]

    n_results = min(top_k * 3, collection.count())
    where_filter = {"volume": {"$eq": volume}} if volume else None

    raw = collection.query(
        query_embeddings=[q_vec.tolist()],
        n_results=n_results,
        where=where_filter,
        include=["metadatas", "distances"],
    )

    if not raw["ids"] or not raw["ids"][0]:
        return []

    # 去重 + 过滤相关度
    seen = set()
    hits = []
    for i in range(len(raw["ids"][0])):
        meta = raw["metadatas"][0][i]
        vol = meta.get("volume", "")
        pn = meta.get("page_number", 0)
        score = 1.0 - raw["distances"][0][i]
        if score < min_score:
            continue
        key = (vol, pn)
        if key in seen:
            continue
        seen.add(key)
        hits.append({"volume": vol, "page_number": pn, "score": round(score, 4)})

    hits.sort(key=lambda r: r["score"], reverse=True)
    return hits[:top_k]


def save_history(query: str, results: list, top_k: int, volume=None, min_score=0.0):
    """将本次查询记录保存到 data/search_history.json。"""
    history_path = os.path.join(_PROJECT_ROOT, "data", "search_history.json")
    os.makedirs(os.path.dirname(history_path), exist_ok=True)

    record = {
        "query": query,
        "time": time.strftime("%Y-%m-%d %H:%M:%S"),
        "top_k": top_k,
        "volume": volume,
        "min_score": min_score,
        "results": results,
    }

    try:
        if os.path.exists(history_path):
            with open(history_path, "r", encoding="utf-8") as f:
                history = json.load(f)
        else:
            history = []
    except Exception:
        history = []

    history.append(record)

    # 只保留最近 100 条
    if len(history) > 100:
        history = history[-100:]

    with open(history_path, "w", encoding="utf-8") as f:
        json.dump(history, f, ensure_ascii=False, indent=2)


def print_db_info():
    import chromadb
    from chromadb.errors import NotFoundError
    from collections import Counter

    if not os.path.isdir(_CHROMA_DIR):
        print("⚠ 向量数据库不存在")
        return

    client = chromadb.PersistentClient(path=_CHROMA_DIR)
    try:
        collection = client.get_collection(_COLLECTION_NAME)
    except (ValueError, NotFoundError):
        print("⚠ Collection 不存在")
        return

    total = collection.count()
    print(f"Collection: {_COLLECTION_NAME}")
    print(f"总 chunk 数: {total}")
    print(f"向量维度: 1024")

    if total == 0:
        return

    chunks_path = os.path.join(_PROJECT_ROOT, "data", "chunks.jsonl")
    if not os.path.exists(chunks_path):
        print("\n⚠ 未找到 chunks.jsonl")
        return

    try:
        vols = Counter()
        page_ranges = {}
        with open(chunks_path, "r", encoding="utf-8") as f:
            for line in f:
                c = json.loads(line)
                vol = c.get("volume", "?")
                pn = c.get("page_number", 0)
                vols[vol] += 1
                if vol not in page_ranges:
                    page_ranges[vol] = [pn, pn]
                else:
                    page_ranges[vol][0] = min(page_ranges[vol][0], pn)
                    page_ranges[vol][1] = max(page_ranges[vol][1], pn)

        print(f"\n收录卷次 ({len(vols)} 卷):")
        for v in sorted(vols.keys(), key=lambda x: x or ""):
            cnt = vols[v]
            pr = page_ranges.get(v, [0, 0])
            print(f"  第{v}卷: {cnt} 页（第{pr[0]}-{pr[1]}页）")

        toc_dir = os.path.join(_PROJECT_ROOT, "data", "toc")
        if os.path.isdir(toc_dir):
            toc_files = [f for f in os.listdir(toc_dir) if f.endswith(".json")]
            print(f"\n目录文件: {len(toc_files)} 卷")
    except Exception as e:
        print(f"\n⚠ 统计失败: {e}")


def main():
    _ensure_utf8_stream()

    parser = argparse.ArgumentParser(description="马恩全集 — 语义检索（仅返回地址）")
    parser.add_argument("query", type=str, nargs="?", default=None, help="查询文本")
    parser.add_argument("--top_k", type=int, default=10, help="返回结果数（默认10）")
    parser.add_argument("--volume", type=str, default=None, help="限定卷次")
    parser.add_argument("--min-score", type=float, default=0.0, help="最低相关度阈值")
    parser.add_argument("--info", action="store_true", help="数据库统计")

    args = parser.parse_args()

    if args.info:
        print_db_info()
        sys.exit(0)

    if not args.query:
        parser.print_help()
        sys.exit(1)

    start = time.time()
    try:
        results = search(args.query, args.top_k, args.volume, args.min_score)
    except RuntimeError as e:
        print(f"检索失败: {e}", file=sys.stderr)
        sys.exit(1)

    elapsed = time.time() - start
    print(f"[用时: {elapsed:.2f}秒]", file=sys.stderr)

    if not results:
        print("未找到相关内容。", file=sys.stderr)
        sys.exit(0)

    # 保存查询记录
    save_history(args.query, results, args.top_k, args.volume, args.min_score)

    # 输出 JSON 地址列表
    print(json.dumps(results, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
