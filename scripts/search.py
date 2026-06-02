"""
马恩全集 RAG — 双模式检索工具

模式 A：语义检索
  python search.py "感性活动"
  python search.py "剩余价值" --top_k 5 --volume 23
  python search.py "一般智力" --with-footnotes

模式 B：按页码取页
  python search.py --page 46上 207 208 209
  python search.py --page 23 408

其他：
  python search.py --info

日志走 stderr，结果走 stdout。
"""

import argparse
import json
import os
import re
import sys
import time

# 项目根目录：自动适配 scripts/ 或根目录运行
_SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
_PROJECT_ROOT = os.path.dirname(_SCRIPT_DIR) if os.path.basename(_SCRIPT_DIR) == "scripts" else _SCRIPT_DIR
if _PROJECT_ROOT not in sys.path:
    sys.path.insert(0, _PROJECT_ROOT)

from scripts.utils import extract_volume_info, lookup_chapter

_CHROMA_DIR = os.path.join(_PROJECT_ROOT, "chroma_db")
_COLLECTION_NAME = "marx_engels"
_MODEL_NAME = "BAAI/bge-large-zh-v1.5"
_QUERY_PREFIX = "为这个句子生成表示以用于检索相关段落: "

_model = None


def load_model():
    """加载嵌入模型（全局缓存）。"""
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
    """获取 ChromaDB collection。"""
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


def _format_volume_label(volume_slug: str) -> str:
    """从 volume slug 构造显示名。
    slug 如 "46上" → "第46卷（上）"，"23" → "第23卷"
    """
    if not volume_slug:
        return ""
    # 分离数字和子卷标记
    m = re.match(r"(\d+)(.*)", volume_slug)
    if not m:
        return f"第{volume_slug}卷"
    vol_num = m.group(1)
    sub = m.group(2)
    sub_map = {"上": "（上）", "中": "（中）", "下": "（下）"}
    sub_label = sub_map.get(sub, "")
    return f"第{vol_num}卷{sub_label}"


def search(query, top_k=10, volume=None, with_footnotes=False, expand_context=True):
    """模式 A：语义检索。

    Args:
        expand_context: True 时自动取命中页±1页上下文；False 时只返回命中页。
    """
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
        include=["documents", "metadatas", "distances"],
    )

    if not raw["ids"] or not raw["ids"][0]:
        return []

    # 收集结果并去重（同卷同页码只保留一个）
    seen = set()
    hit_pages = []  # (volume, page_number, score)
    for i in range(len(raw["ids"][0])):
        meta = raw["metadatas"][0][i]
        vol = meta.get("volume", "")
        pn = meta.get("page_number", 0)
        dedup_key = (vol, pn)
        if dedup_key in seen:
            continue
        seen.add(dedup_key)
        score = 1.0 - raw["distances"][0][i]
        hit_pages.append((vol, pn, score))

    hit_pages.sort(key=lambda r: r[2], reverse=True)
    hit_pages = hit_pages[:top_k]

    if expand_context:
        # 对每个命中页，自动扩展前后各一页
        fetch_map = {}
        for vol, pn, score in hit_pages:
            fetch_map[(vol, pn)] = {"is_hit": True, "score": score}
            for adj in [pn - 1, pn + 1]:
                key = (vol, adj)
                if key not in fetch_map:
                    fetch_map[key] = {"is_hit": False, "score": 0}

        results = []
        for (vol, pn), info in fetch_map.items():
            try:
                raw_page = collection.get(
                    where={"$and": [
                        {"volume": {"$eq": vol}},
                        {"page_number": {"$eq": pn}},
                    ]},
                    include=["documents", "metadatas"],
                )
            except Exception:
                continue
            if not raw_page["ids"] or len(raw_page["ids"]) == 0:
                continue
            results.append({
                "is_hit": info["is_hit"],
                "score": info["score"],
                "text": raw_page["documents"][0],
                "volume": vol,
                "page_number": pn,
                "chunk_id": raw_page["metadatas"][0].get("chunk_id", ""),
                "header_title": raw_page["metadatas"][0].get("header_title", ""),
                "footnotes": _parse_footnotes(raw_page["metadatas"][0].get("footnotes", "")),
            })
    else:
        # 只返回命中页，不扩展
        results = []
        for vol, pn, score in hit_pages:
            try:
                raw_page = collection.get(
                    where={"$and": [
                        {"volume": {"$eq": vol}},
                        {"page_number": {"$eq": pn}},
                    ]},
                    include=["documents", "metadatas"],
                )
            except Exception:
                continue
            if not raw_page["ids"] or len(raw_page["ids"]) == 0:
                continue
            results.append({
                "is_hit": True,
                "score": score,
                "text": raw_page["documents"][0],
                "volume": vol,
                "page_number": pn,
                "chunk_id": raw_page["metadatas"][0].get("chunk_id", ""),
                "header_title": raw_page["metadatas"][0].get("header_title", ""),
                "footnotes": _parse_footnotes(raw_page["metadatas"][0].get("footnotes", "")),
            })

    if not with_footnotes:
        for r in results:
            r["footnotes"] = []
    results.sort(key=lambda r: (r["volume"] or "", r["page_number"] or 0))
    return results


def fetch_pages(volume: str, page_numbers: list):
    """模式 B：按页码取页。"""
    if not page_numbers:
        return []

    collection = get_collection()
    pages = []

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
            pages.append({"page_number": pn, "volume": volume, "exists": False})
            continue

        if raw["ids"] and len(raw["ids"]) > 0:
            pages.append({
                "page_number": pn,
                "volume": volume,
                "exists": True,
                "text": raw["documents"][0],
                "chunk_id": raw["metadatas"][0].get("chunk_id", ""),
                "header_title": raw["metadatas"][0].get("header_title", ""),
                "footnotes": _parse_footnotes(raw["metadatas"][0].get("footnotes", "")),
            })
        else:
            pages.append({"page_number": pn, "volume": volume, "exists": False})

    return pages


def _parse_footnotes(fn_data):
    """将 ChromaDB 中存储的脚注 JSON 字符串解析为列表。"""
    if not fn_data:
        return []
    if isinstance(fn_data, list):
        return fn_data
    try:
        return json.loads(fn_data)
    except Exception:
        return []


def format_search_results(results):
    """格式化语义检索结果（含自动上下文）。"""
    lines = []
    for rank, r in enumerate(results, 1):
        vol_label = _format_volume_label(r["volume"])
        is_hit = r.get("is_hit", False)

        if is_hit:
            lines.append("━" * 46)
            score = r["score"]
            lines.append(f">>> [命中 {rank}] 相关度: {score:.4f}")
            lines.append(f">>> 出处: {vol_label} | 第{r['page_number']}页")
            lines.append(f">>> chunk_id: {r['chunk_id']}")
            chapter = lookup_chapter(r["volume"], r["page_number"])
            if chapter:
                lines.append(f">>> 篇章: {chapter}")
            lines.append("━" * 46)
        else:
            lines.append(f"——— 上下文: {vol_label} | 第{r['page_number']}页 ———")

        lines.append(r["text"])

        # 脚注（语义检索时需带 --with-footnotes；--page 模式始终显示）
        if r.get("footnotes"):
            for fn in r["footnotes"][:5]:
                marker = fn.get("marker", "") if isinstance(fn, dict) else ""
                text = fn.get("text", "")[:80] if isinstance(fn, dict) else str(fn)[:80]
                lines.append(f"[脚注] {marker} {text}")

        lines.append("")

    return "\n".join(lines)


def format_page_results(pages):
    """格式化按页取结果。"""
    lines = []
    for p in pages:
        vol_label = _format_volume_label(p["volume"])

        if not p["exists"]:
            lines.append(f"——— {vol_label} · 第{p['page_number']}页 ———")
            lines.append(" （未收录）")
            lines.append("")
            continue

        lines.append(f"——— {vol_label} · 第{p['page_number']}页 ———")

        chapter = lookup_chapter(p["volume"], p["page_number"])
        if chapter:
            lines.append(f"篇章: {chapter}")
        elif p.get("header_title"):
            lines.append(f"标题: {p['header_title']}")

        lines.append(p["text"])

        # 脚注（--page 模式始终显示）
        if p.get("footnotes"):
            for fn in p["footnotes"][:5]:
                marker = fn.get("marker", "") if isinstance(fn, dict) else ""
                text = fn.get("text", "")[:80] if isinstance(fn, dict) else str(fn)[:80]
                lines.append(f"[脚注] {marker} {text}")

        lines.append("")

    return "\n".join(lines)


def print_db_info():
    """数据库统计信息。"""
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

    # 从 chunks.jsonl 读取统计（避免 ChromaDB SQL 变量限制）
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
            vl = _format_volume_label(v)
            print(f"  {vl}: {cnt} 页（第{pr[0]}-{pr[1]}页）")

        # 目录覆盖情况
        toc_dir = os.path.join(_PROJECT_ROOT, "data", "toc")
        if os.path.isdir(toc_dir):
            toc_files = [f for f in os.listdir(toc_dir) if f.endswith(".json")]
            print(f"\n目录文件: {len(toc_files)} 卷")
    except Exception as e:
        print(f"\n⚠ 统计失败: {e}")


def main():
    parser = argparse.ArgumentParser(description="马恩全集 RAG 检索")
    parser.add_argument("query", type=str, nargs="?", default=None, help="查询文本")
    parser.add_argument("--top_k", type=int, default=10, help="返回结果数（默认10）")
    parser.add_argument("--volume", type=str, default=None, help="限定卷次")
    parser.add_argument("--with-footnotes", action="store_true", help="显示脚注")
    parser.add_argument("--mode", type=str, default="expand", choices=["hit", "expand"],
                        help='检索模式：hit（只返回命中页，不翻页），expand（默认，自动扩展前后页）')
    parser.add_argument("--info", action="store_true", help="数据库统计")
    parser.add_argument("--page", type=str, nargs="+", default=None,
                        help="按页码取页：--page {卷次} {页码1} [页码2] ...")

    args = parser.parse_args()

    # ── 数据库信息 ──
    if args.info:
        print_db_info()
        sys.exit(0)

    # ── 模式 B：按页码取页 ──
    if args.page is not None:
        if len(args.page) < 2:
            print("用法: python search.py --page {卷次} {页码1} [页码2] ...", file=sys.stderr)
            sys.exit(1)
        vol = args.page[0]
        page_nums = []
        for p in args.page[1:]:
            try:
                page_nums.append(int(p))
            except ValueError:
                print(f"⚠ 无效页码: {p}", file=sys.stderr)
                sys.exit(1)

        start = time.time()
        pages = fetch_pages(vol, page_nums)
        elapsed = time.time() - start
        output = format_page_results(pages)
        print(output)
        print(f"[用时: {elapsed:.2f}秒]", file=sys.stderr)
        sys.exit(0)

    # ── 模式 A：语义检索 ──
    if not args.query:
        parser.print_help()
        sys.exit(1)

    start = time.time()
    try:
        results = search(args.query, args.top_k, args.volume, args.with_footnotes,
                          expand_context=(args.mode == "expand"))
    except RuntimeError as e:
        print(f"检索失败: {e}", file=sys.stderr)
        sys.exit(1)

    elapsed = time.time() - start

    if not results:
        print("未找到相关内容。请尝试其他关键词。", file=sys.stderr)
        sys.exit(0)

    output = format_search_results(results)
    print(output)
    print(f"[用时: {elapsed:.2f}秒]", file=sys.stderr)


if __name__ == "__main__":
    main()
