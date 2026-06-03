"""
马恩全集 — 原文阅读工具

用法：
  python read_raw_text.py 42 127 128 129 130
  python read_raw_text.py 46上 207 208 209 210
  python read_raw_text.py 23 100-105 110-115    # 支持页码范围

功能：
  1. 从 ChromaDB 拉取指定卷次+页码的原文
  2. 保存到 data/temp_raw_text.md
  3. 生成本地 HTML 并在浏览器中打开（左侧目录 + 右侧正文）
"""

import argparse
import json
import os
import re
import subprocess
import sys
import time
import webbrowser
from typing import Optional

# ── 路径自动适配 ──
_SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
_PROJECT_ROOT = os.path.dirname(_SCRIPT_DIR) if os.path.basename(_SCRIPT_DIR) == "scripts" else _SCRIPT_DIR
if _PROJECT_ROOT not in sys.path:
    sys.path.insert(0, _PROJECT_ROOT)

from scripts.utils import lookup_chapter

_CHROMA_DIR = os.path.join(_PROJECT_ROOT, "chroma_db")
_COLLECTION_NAME = "marx_engels"
_TEMP_MD = os.path.join(_PROJECT_ROOT, "data", "temp_raw_text.md")
_TEMP_HTML = os.path.join(_PROJECT_ROOT, "data", "temp_raw_text.html")


# ── stdout/stderr 编码 ──

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


# ── ChromaDB ──

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


# ── 卷次标签 ──

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


# ── 页码解析 ──

def parse_page_args(args: list) -> list[tuple[str, list[int]]]:
    """解析命令行参数为 [(vol, [p1, p2, ...]), ...] 格式。

    支持：
      read_raw_text.py 42 127 128 129
      read_raw_text.py 46上 207 208
      read_raw_text.py 23 100-105 110-115
    """
    if not args:
        return []

    # 第一个参数是卷次
    vol = args[0]
    page_args = args[1:]

    pages = []
    for p in page_args:
        if "-" in p:
            parts = p.split("-")
            try:
                start, end = int(parts[0]), int(parts[1])
                pages.extend(range(start, end + 1))
            except ValueError:
                print(f"⚠ 页码范围格式无效: {p}", file=sys.stderr)
        else:
            try:
                pages.append(int(p))
            except ValueError:
                print(f"⚠ 无效页码: {p}", file=sys.stderr)

    pages = sorted(set(pages))  # 去重排序
    return [(vol, pages)]


# ── 拉取原文 ──

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
            results.append({"page_number": pn, "exists": False})
            continue

        if raw["ids"] and len(raw["ids"]) > 0:
            meta = raw["metadatas"][0]
            results.append({
                "page_number": pn,
                "exists": True,
                "text": raw["documents"][0],
                "chunk_id": meta.get("chunk_id", ""),
                "header_title": meta.get("header_title", ""),
                "volume": volume,
            })
        else:
            results.append({"page_number": pn, "exists": False})

    return results


# ── 查找篇章名 ──

def get_chapter_name(volume: str, page: int) -> str:
    name = lookup_chapter(volume, page)
    if name:
        return name
    # 退一步：如果 lookup 没找到，返回空
    return ""


# ── 生成 Markdown ──

def generate_markdown(volume: str, pages: list[dict]) -> str:
    """生成 Markdown，格式：
    # 第X卷（上）— 篇章名
    ---
    ## 第X页
    （正文...）

    ## 第X+1页
    （正文...）
    """
    vol_label = format_volume_label(volume)

    # 找第一篇的篇章名作为卷标题
    chapter = ""
    for p in pages:
        if p.get("exists") and p.get("page_number"):
            chapter = get_chapter_name(volume, p["page_number"])
            if chapter:
                break

    lines = []
    title = vol_label
    if chapter:
        title += f" — {chapter}"
    lines.append(f"# {title}")
    lines.append("")

    previous_page = None
    for p in pages:
        pn = p["page_number"]

        # 页码不连续时加粗横线分隔
        if previous_page is not None and pn != previous_page + 1:
            lines.append("**——— 页码不连续，以下为第 {} 页 ———**".format(pn))
            lines.append("")

        lines.append(f"## 第{pn}页")
        lines.append("")

        if not p["exists"]:
            lines.append("（未收录）")
            lines.append("")
            previous_page = pn
            continue

        # 页内标题
        header = p.get("header_title", "")
        if header:
            lines.append(f"*{header}*")
            lines.append("")

        # 正文
        text = p.get("text", "").strip()
        if text:
            # 保持原始段落格式
            lines.append(text)
            lines.append("")

        previous_page = pn

    return "\n".join(lines)


# ── 生成 HTML ──

def generate_html(volume: str, pages: list[dict]) -> str:
    """生成带左侧目录的 HTML。"""
    vol_label = format_volume_label(volume)

    # 篇章名
    chapter = ""
    for p in pages:
        if p.get("exists") and p.get("page_number"):
            chapter = get_chapter_name(volume, p["page_number"])
            if chapter:
                break

    title = vol_label
    if chapter:
        title += f" — {chapter}"

    # 构建侧边栏条目和正文
    toc_items = []
    content_parts = []

    # 用于追踪连续性的变量（用于灰色分隔线提示）
    prev_pn = None
    gap_index = 0

    for i, p in enumerate(pages):
        pn = p["page_number"]
        anchor = f"page-{pn}"

        # 侧边栏条目
        toc_items.append(f'<li><a href="#{anchor}">第{pn}页</a></li>')

        # 正文卡片
        card_parts = []

        # 页码不连续提示
        if prev_pn is not None and pn != prev_pn + 1:
            gap_index += 1
            card_parts.append(
                f'<div class="gap-hint">— 页码不连续（第{prev_pn}页 → 第{pn}页）—</div>'
            )

        card_parts.append(f'<h2 id="{anchor}">第{pn}页</h2>')

        if not p["exists"]:
            card_parts.append('<p class="missing">（未收录）</p>')
        else:
            header = p.get("header_title", "")
            if header:
                card_parts.append(f'<p class="header-title">{header}</p>')

            text = p.get("text", "").strip()
            if text:
                # 正文每个段落用 <p> 包裹
                paragraphs = text.split("\n")
                for para in paragraphs:
                    para = para.strip()
                    if para:
                        card_parts.append(f"<p>{para}</p>")

        prev_pn = pn

        content_parts.append('<div class="page-card">\n' + "\n".join(card_parts) + '\n</div>')

    toc_html = "\n".join(toc_items)
    content_html = "\n".join(content_parts)

    html = f"""<!DOCTYPE html>
<html lang="zh-CN">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>{title}</title>
<style>
  *, *::before, *::after {{ box-sizing: border-box; margin: 0; padding: 0; }}
  html {{ scroll-behavior: smooth; }}
  body {{
    font-family: "Noto Serif SC", "Source Han Serif SC", "STSong", "SimSun", serif;
    background: #f5f5f0;
    color: #2c2c2c;
    line-height: 1.9;
    font-size: 16px;
    display: flex;
  }}

  /* ── 侧边栏 ── */
  .sidebar {{
    position: fixed;
    top: 0; left: 0;
    width: 220px;
    height: 100vh;
    background: #fff;
    border-right: 1px solid #ddd;
    overflow-y: auto;
    padding: 20px 0;
    z-index: 100;
  }}
  .sidebar-title {{
    font-size: 15px;
    font-weight: 700;
    padding: 0 16px 12px;
    border-bottom: 1px solid #eee;
    color: #8b0000;
  }}
  .sidebar ul {{ list-style: none; padding: 8px 0; }}
  .sidebar li {{ padding: 0; }}
  .sidebar a {{
    display: block;
    padding: 6px 16px;
    color: #555;
    text-decoration: none;
    font-size: 14px;
    transition: background 0.15s, color 0.15s;
  }}
  .sidebar a:hover {{
    background: #f0f0eb;
    color: #8b0000;
  }}

  /* ── 主内容区 ── */
  .main {{
    margin-left: 220px;
    flex: 1;
    max-width: 820px;
    padding: 40px 60px 80px;
  }}

  .main h1 {{
    font-size: 26px;
    font-weight: 700;
    color: #8b0000;
    border-bottom: 2px solid #8b0000;
    padding-bottom: 12px;
    margin-bottom: 24px;
  }}

  .page-card {{
    background: #fff;
    border-radius: 4px;
    padding: 24px 28px;
    margin-bottom: 20px;
    box-shadow: 0 1px 3px rgba(0,0,0,0.06);
  }}

  .page-card h2 {{
    font-size: 18px;
    font-weight: 600;
    color: #333;
    border-left: 3px solid #8b0000;
    padding-left: 10px;
    margin-bottom: 12px;
  }}

  .header-title {{
    font-size: 14px;
    color: #888;
    margin-bottom: 8px;
    font-style: italic;
  }}

  .page-card p {{
    text-indent: 2em;
    margin-bottom: 6px;
  }}

  .missing {{
    color: #aaa;
    text-indent: 0 !important;
    font-style: italic;
  }}

  .gap-hint {{
    text-align: center;
    color: #999;
    font-size: 13px;
    padding: 8px 0;
    border-top: 1px dashed #ddd;
    border-bottom: 1px dashed #ddd;
    margin-bottom: 12px;
  }}

  @media (max-width: 768px) {{
    .sidebar {{ display: none; }}
    .main {{ margin-left: 0; padding: 20px; }}
  }}
</style>
</head>
<body>
<nav class="sidebar">
  <div class="sidebar-title">{title}</div>
  <ul>
    {toc_html}
  </ul>
</nav>
<main class="main">
  <h1>{title}</h1>
  {content_html}
</main>
</body>
</html>"""
    return html


# ── 打开浏览器 ──

def open_in_browser(html_path: str):
    """在默认浏览器中打开 HTML 文件。"""
    abs_path = os.path.abspath(html_path)
    file_url = "file://" + abs_path.replace("\\", "/")
    print(f"[info] 已生成: {abs_path}", file=sys.stderr)

    try:
        webbrowser.open(file_url)
        print("[info] 已在浏览器中打开", file=sys.stderr)
    except Exception:
        # 备选：用系统命令打开
        try:
            if sys.platform == "win32":
                os.startfile(abs_path)
            elif sys.platform == "darwin":
                subprocess.run(["open", abs_path])
            else:
                subprocess.run(["xdg-open", abs_path])
        except Exception as e:
            print(f"[warn] 无法自动打开浏览器: {e}", file=sys.stderr)
            print(f"[warn] 请手动打开: {abs_path}", file=sys.stderr)


# ── 主流程 ──

def main():
    _ensure_utf8_stream()

    parser = argparse.ArgumentParser(description="马恩全集 — 原文阅读工具")
    parser.add_argument("args", type=str, nargs="*", help="卷次 页码1 [页码2] ... 或 卷次 起始-结束")
    parser.add_argument("--no-browser", action="store_true", help="不打开浏览器，只生成文件")

    parsed = parser.parse_args()
    args = parsed.args
    no_browser = parsed.no_browser

    if not args:
        print("用法:", file=sys.stderr)
        print("  python read_raw_text.py 42 127 128 129 130", file=sys.stderr)
        print("  python read_raw_text.py 46上 207 208 209 210", file=sys.stderr)
        print("  python read_raw_text.py 23 100-105 110-115", file=sys.stderr)
        sys.exit(1)

    # 解析参数
    volume_pages = parse_page_args(args)

    # 连接 ChromaDB
    try:
        collection = get_collection()
    except RuntimeError as e:
        print(f"数据库错误: {e}", file=sys.stderr)
        sys.exit(1)
    except Exception as e:
        print(f"无法连接数据库: {e}", file=sys.stderr)
        sys.exit(1)

    start = time.time()

    for vol, pages in volume_pages:
        print(f"[info] 正在拉取 {format_volume_label(vol)} 第 {pages[0]}-{pages[-1]} 页...", file=sys.stderr)
        page_data = fetch_pages(collection, vol, pages)

        # 生成 Markdown
        md_content = generate_markdown(vol, page_data)

        # 写入 Markdown
        os.makedirs(os.path.dirname(_TEMP_MD), exist_ok=True)
        with open(_TEMP_MD, "w", encoding="utf-8") as f:
            f.write(md_content)
        print(f"[info] Markdown 已保存: {_TEMP_MD}", file=sys.stderr)

        # 生成 HTML
        html_content = generate_html(vol, page_data)

        # 写入 HTML
        with open(_TEMP_HTML, "w", encoding="utf-8") as f:
            f.write(html_content)
        print(f"[info] HTML 已生成: {_TEMP_HTML}", file=sys.stderr)

        # 打开浏览器
        if not no_browser:
            open_in_browser(_TEMP_HTML)

    elapsed = time.time() - start
    print(f"[用时: {elapsed:.2f}秒]", file=sys.stderr)


if __name__ == "__main__":
    main()
