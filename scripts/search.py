"""
马恩全集 RAG — 检索工具（skill 独立版）

供 agent 通过 bash 调用。日志走 stderr，结果走 stdout。

用法：
  python scripts/search.py "查询内容"
  python scripts/search.py "感性活动" --top_k 5 --volume 23
  python scripts/search.py --info
"""

import argparse
import json
import os
import re
import sys
import time

# ── 路径（相对于 skill 根目录） ──
_SKILL_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
_CHROMA_DIR = os.path.join(_SKILL_ROOT, "chroma_db")
_COLLECTION_NAME = "marx_engels"
_MODEL_NAME = "BAAI/bge-large-zh-v1.5"
_QUERY_PREFIX = "为这个句子生成表示以用于检索相关段落: "

_model = None


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


def deduplicate(results: list, threshold: float = 0.5) -> list:
    """去重：文本重叠 > 50% 的只保留得分更高的。"""
    if not results:
        return []
    kept = []
    for r in results:
        is_dup = False
        for k in kept:
            shorter = r["text"] if len(r["text"]) <= len(k["text"]) else k["text"]
            longer = k["text"] if len(r["text"]) <= len(k["text"]) else r["text"]
            if shorter in longer and len(shorter) / max(len(longer), 1) > threshold:
                if r["score"] > k["score"]:
                    k["text"], k["score"], k["metadata"] = r["text"], r["score"], r["metadata"]
                is_dup = True
                break
        if not is_dup:
            kept.append(r)
    kept.sort(key=lambda x: x["score"], reverse=True)
    return kept


def search(query: str, top_k: int = 10, volume: int = None, threshold: float = 0.0) -> list:
    import chromadb
    from chromadb.errors import NotFoundError

    model = load_model()

    prefixed = _QUERY_PREFIX + query
    q_vec = model.encode([prefixed], normalize_embeddings=True)[0]

    if not os.path.isdir(_CHROMA_DIR):
        raise RuntimeError(f"向量数据库不存在: {_CHROMA_DIR}")

    client = chromadb.PersistentClient(path=_CHROMA_DIR)
    try:
        collection = client.get_collection(_COLLECTION_NAME)
    except (ValueError, NotFoundError):
        raise RuntimeError(f"Collection '{_COLLECTION_NAME}' 不存在")

    count = collection.count()
    if count == 0:
        raise RuntimeError("向量数据库为空")

    n_results = min(top_k * 3, count)
    where_filter = {"volume": volume} if volume is not None else None

    raw = collection.query(
        query_embeddings=[q_vec.tolist()],
        n_results=n_results,
        where=where_filter,
    )

    if not raw["ids"] or not raw["ids"][0]:
        return []

    results = []
    for i in range(len(raw["ids"][0])):
        distance = raw["distances"][0][i]
        score = 1.0 - distance
        if threshold > 0 and score < threshold:
            continue
        results.append({
            "text": raw["documents"][0][i],
            "score": score,
            "metadata": raw["metadatas"][0][i],
        })

    deduped = deduplicate(results)
    return deduped[:top_k]


def print_db_info():
    import chromadb
    from chromadb.errors import NotFoundError

    if not os.path.isdir(_CHROMA_DIR):
        print("⚠ 向量数据库目录不存在")
        return

    client = chromadb.PersistentClient(path=_CHROMA_DIR)
    try:
        collection = client.get_collection(_COLLECTION_NAME)
    except (ValueError, NotFoundError):
        print("⚠ Collection 不存在")
        return

    total = collection.count()
    print(f"Collection: {_COLLECTION_NAME}")
    print(f"总条目数: {total}")
    print(f"向量维度: 1024")

    if total == 0:
        return

    try:
        all_meta = collection.get(include=["metadatas"])
        volumes = {}
        for m in all_meta["metadatas"]:
            vol = m.get("volume_label") or f"第{m.get('volume', '?')}卷"
            volumes[vol] = volumes.get(vol, 0) + 1
        print(f"\n收录卷次 ({len(volumes)} 卷):")
        for vn, cnt in sorted(volumes.items(), key=lambda x: x[0] or ""):
            print(f"  {vn}: {cnt} 条")
    except Exception:
        pass


def format_results(results: list) -> str:
    lines = []
    for rank, r in enumerate(results, 1):
        meta = r.get("metadata", {})
        score = r.get("score", 0)
        text = r.get("text", "")

        parts = []
        vl = meta.get("volume_label", "")
        if vl:
            parts.append(vl)
        elif meta.get("volume"):
            parts.append(f"第{meta['volume']}卷")
        ch = meta.get("chapter", "") or ""
        if ch:
            parts.append(ch)
        pg = meta.get("page", "") or ""
        if pg:
            parts.append(pg)

        lines.append("━" * 46)
        lines.append(f"[结果 {rank}] 相关度: {score:.4f}")
        lines.append(f"出处: {' | '.join(parts)}")
        lines.append("━" * 46)
        lines.append(text)
        lines.append("")
    return "\n".join(lines)


def main():
    parser = argparse.ArgumentParser(description="马恩全集语义检索")
    parser.add_argument("query", type=str, nargs="?", default=None, help="查询文本")
    parser.add_argument("--top_k", type=int, default=10)
    parser.add_argument("--volume", type=int, default=None)
    parser.add_argument("--threshold", type=float, default=0.0)
    parser.add_argument("--info", action="store_true", help="数据库统计信息")
    args = parser.parse_args()

    if args.info:
        print_db_info()
        sys.exit(0)

    if not args.query:
        parser.print_help()
        sys.exit(1)

    start = time.time()
    try:
        results = search(args.query, args.top_k, args.volume, args.threshold)
    except RuntimeError as e:
        print(f"检索失败: {e}", file=sys.stderr)
        sys.exit(1)

    elapsed = time.time() - start

    if not results:
        print("未找到相关内容。请尝试其他关键词。", file=sys.stderr)
        sys.exit(0)

    output = format_results(results)
    print(output)
    print(f"[用时: {elapsed:.2f}秒]", file=sys.stderr)


if __name__ == "__main__":
    main()
