"""
马恩全集 — 原文阅读工具

从 ChromaDB 拉取指定卷次+页码的原文，生成带左侧目录的 HTML
并在浏览器中打开。每次运行覆盖上一次的临时文件，不留痕迹。

用法：
  python read_raw_text.py -v 42 127 128 129 130
  python read_raw_text.py -v 46上 207 208 209
  python read_raw_text.py -v 23 100-105 110-115
  python read_raw_text.py -v 3 3-6 48-51 -v 42 125-130 167-170
"""

import argparse
import json
import os
import re
import subprocess
import sys
import time
import webbrowser

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


# ── 拉取原文 ──

def fetch_pages(collection, volume: str, page_numbers: list) -> list[dict]:
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
            results.append({"page_number": pn, "exists": False, "volume": volume})
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
            results.append({"page_number": pn, "exists": False, "volume": volume})

    return results


def get_chapter_name(volume: str, page: int) -> str:
    return lookup_chapter(volume, page) or ""


# ── 生成 Markdown ──

def escape_md(text: str) -> str:
    """转义 Markdown 特殊字符，避免被解析为格式。"""
    # 只转义会影响标题和列表的字符
    return text.replace("#", "\\#")


def generate_markdown(volumes_data: list[tuple[str, list[dict]]]) -> str:
    """生成 Markdown，多卷次合并。"""
    lines = []
    first = True

    for vol, pages in volumes_data:
        vol_label = format_volume_label(vol)

        # 篇章名
        chapter = ""
        for p in pages:
            if p.get("exists") and p.get("page_number"):
                chapter = get_chapter_name(vol, p["page_number"])
                if chapter:
                    break

        title = vol_label
        if chapter:
            title += f" — {chapter}"

        if not first:
            lines.append("")
            lines.append("---")
            lines.append("")
        first = False

        lines.append(f"# {title}")
        lines.append("")

        previous_page = None
        for p in pages:
            pn = p["page_number"]

            if previous_page is not None and pn != previous_page + 1:
                lines.append(f"**——— 页码不连续，以下为第{pn}页 ———**")
                lines.append("")

            lines.append(f"## 第{pn}页")
            lines.append("")

            if not p["exists"]:
                lines.append("（未收录）")
                lines.append("")
                previous_page = pn
                continue

            header = p.get("header_title", "")
            if header:
                lines.append(f"*{header}*")
                lines.append("")

            text = p.get("text", "").strip()
            if text:
                for para in _split_paragraphs(text):
                    lines.append(para)
                    lines.append("")

            previous_page = pn

    return "\n".join(lines)


# ── 生成 HTML ──

def escape_html(text: str) -> str:
    """转义 HTML 特殊字符。"""
    return (text.replace("&", "&amp;")
                .replace("<", "&lt;")
                .replace(">", "&gt;")
                .replace('"', "&quot;"))


def _split_paragraphs(text: str) -> list[str]:
    """将 OCR 原文按自然段分组，去除 PDF 机械换行。

    PDF 抽取的文本中，\n 只是版面换行，并非段落结束。
    真正的段落边界由以下标志识别：
      - 以全角空格开头（　　）的行 → 新段落
      - 空行 → 段落结束
      - 其余行属于当前段落，直接拼接
    """
    lines = text.split("\n")
    paragraphs = []
    buf = []

    for line in lines:
        stripped = line.strip()
        # 空行 → 段落结束
        if not stripped:
            if buf:
                paragraphs.append("".join(buf))
                buf = []
            continue
        # 全角空格开头 → 新段落
        if stripped.startswith("　") and buf:
            paragraphs.append("".join(buf))
            buf = [stripped.lstrip("　")]
        else:
            buf.append(stripped)

    if buf:
        paragraphs.append("".join(buf))

    return paragraphs if paragraphs else [text.strip()]


def generate_html(volumes_data: list[tuple[str, list[dict]]]) -> str:
    """生成带左侧目录的 HTML，多卷次合并。"""
    # ── 构建页面整体标题 ──
    page_titles = []
    for vol, pages in volumes_data:
        vol_label = format_volume_label(vol)
        chapter = ""
        for p in pages:
            if p.get("exists") and p.get("page_number"):
                chapter = get_chapter_name(vol, p["page_number"])
                if chapter:
                    break
        if chapter:
            page_titles.append(f"{vol_label} — {chapter}")
        else:
            page_titles.append(vol_label)
    full_title = " | ".join(page_titles)

    # ── 构建侧边栏和正文 ──
    toc_parts = []
    content_parts = []
    first_vol = True

    for vol_idx, (vol, pages) in enumerate(volumes_data):
        vol_label = format_volume_label(vol)
        vol_id = f"vol-{vol_idx}"
        vol_anchor = f"vol-{vol}"

        chapter = ""
        for p in pages:
            if p.get("exists") and p.get("page_number"):
                chapter = get_chapter_name(vol, p["page_number"])
                if chapter:
                    break

        vol_title = vol_label
        if chapter:
            vol_title += f" — {chapter}"

        # 侧边栏：卷标题
        toc_parts.append(f'<li class="vol-header"><a href="#{vol_id}">{escape_html(vol_label)}</a></li>')

        # 正文：卷首标题区域
        if not first_vol:
            content_parts.append('<div class="vol-divider"></div>')
        first_vol = False

        vol_header = f'<div class="vol-section" id="{vol_id}"><h1>{escape_html(vol_title)}</h1></div>'

        # 页面卡片
        page_cards = []
        prev_pn = None
        for p in pages:
            pn = p["page_number"]
            anchor = f"p-{vol}-{pn}"

            toc_parts.append(f'<li><a href="#{anchor}">第{pn}页</a></li>')

            card = []

            # 页码不连续提示
            if prev_pn is not None and pn != prev_pn + 1:
                card.append(
                    f'<div class="gap-hint">— 页码不连续（第{prev_pn}页 → 第{pn}页）—</div>'
                )

            card.append(f'<h2 id="{anchor}">第{pn}页</h2>')

            if not p["exists"]:
                card.append('<p class="missing">（未收录）</p>')
            else:
                header = p.get("header_title", "")
                if header:
                    card.append(f'<p class="header-title">{escape_html(header)}</p>')

                text = p.get("text", "").strip()
                if text:
                    # 将原文按自然段分组，去除 PDF 换行
                    for para in _split_paragraphs(text):
                        card.append(f"<p>{escape_html(para)}</p>")

            prev_pn = pn
            page_cards.append('<div class="page-card">' + "\n".join(card) + '</div>')

        vol_content = vol_header + "\n" + "\n".join(page_cards)
        content_parts.append(vol_content)

    toc_html = "\n".join(toc_parts)
    content_html = "\n".join(content_parts)

    html = f"""<!DOCTYPE html>
<html lang="zh-CN">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>{escape_html(full_title)}</title>
<style>
  *, *::before, *::after {{ box-sizing: border-box; margin: 0; padding: 0; }}
  html {{ scroll-behavior: smooth; }}
  body {{
    font-family: "Noto Serif SC", "Source Han Serif SC", "STSong", "SimSun", "FangSong", serif;
    background: #f5f5f0;
    color: #2c2c2c;
    line-height: 1.9;
    font-size: 16px;
    display: flex;
    justify-content: center;
  }}

  /* ── 侧边栏 ── */
  .sidebar {{
    position: fixed;
    top: 0; left: 0;
    width: 200px;
    height: 100vh;
    background: #fff;
    border-right: 1px solid #ddd;
    overflow-y: auto;
    padding: 16px 0;
    z-index: 100;
  }}
  .sidebar-title {{
    font-size: 14px;
    font-weight: 700;
    padding: 0 14px 10px;
    border-bottom: 1px solid #eee;
    color: #8b0000;
  }}
  .sidebar ul {{ list-style: none; padding: 6px 0; }}
  .sidebar li {{ padding: 0; }}
  .sidebar li.vol-header {{
    margin-top: 8px;
    padding-top: 8px;
    border-top: 1px solid #eee;
  }}
  .sidebar li.vol-header:first-child {{
    margin-top: 0;
    padding-top: 0;
    border-top: none;
  }}
  .sidebar li.vol-header a {{
    font-weight: 600;
    color: #8b0000;
    font-size: 13px;
  }}
  .sidebar a {{
    display: block;
    padding: 4px 14px;
    color: #555;
    text-decoration: none;
    font-size: 13px;
    transition: background 0.12s, color 0.12s;
  }}
  .sidebar a:hover {{
    background: #f0f0eb;
    color: #8b0000;
  }}

  /* ── 主内容区 ── */
  .main {{
    margin-left: 200px;
    width: 100%;
    max-width: 780px;
    padding: 40px 50px 80px;
  }}

  .main h1 {{
    font-size: 24px;
    font-weight: 700;
    color: #8b0000;
    border-bottom: 2px solid #8b0000;
    padding-bottom: 10px;
    margin-bottom: 20px;
  }}

  .vol-divider {{
    height: 2px;
    background: #ddd;
    margin: 32px 0;
  }}

  .page-card {{
    background: #fff;
    border-radius: 4px;
    padding: 20px 24px;
    margin-bottom: 16px;
    box-shadow: 0 1px 3px rgba(0,0,0,0.06);
  }}

  .page-card h2 {{
    font-size: 17px;
    font-weight: 600;
    color: #333;
    border-left: 3px solid #8b0000;
    padding-left: 10px;
    margin-bottom: 10px;
  }}

  .header-title {{
    font-size: 14px;
    color: #888;
    margin-bottom: 6px;
    font-style: italic;
  }}

  .page-card p {{
    text-indent: 2em;
    margin-bottom: 4px;
    text-align: justify;
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
    padding: 6px 0;
    border-top: 1px dashed #ddd;
    border-bottom: 1px dashed #ddd;
    margin-bottom: 10px;
  }}

  @media (max-width: 768px) {{
    .sidebar {{ display: none; }}
    .main {{ margin-left: 0; padding: 20px; }}
  }}
</style>
</head>
<body>
<nav class="sidebar">
  <div class="sidebar-title">目录</div>
  <ul>
    {toc_html}
  </ul>
</nav>
<main class="main">
  {content_html}
</main>
</body>
</html>"""
    return html


# ── 打开浏览器 ──

def open_in_browser(html_path: str):
    abs_path = os.path.abspath(html_path)
    file_url = "file://" + abs_path.replace("\\", "/")
    print(f"[info] 已生成: {abs_path}", file=sys.stderr)

    try:
        webbrowser.open(file_url)
        print("[info] 已在浏览器中打开", file=sys.stderr)
    except Exception:
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


# ── CLI 解析 ──

class VolumePageAction(argparse.Action):
    """解析 -v 卷次 页码1 页码2 ... 参数，支持页码范围。"""
    def __call__(self, parser, namespace, values, option_string=None):
        if not values:
            return
        vol = values[0]
        pages = []
        for v in values[1:]:
            if "-" in v:
                parts = v.split("-")
                try:
                    start, end = int(parts[0]), int(parts[1])
                    pages.extend(range(start, end + 1))
                except ValueError:
                    print(f"⚠ 页码范围格式无效: {v}", file=sys.stderr)
            else:
                try:
                    pages.append(int(v))
                except ValueError:
                    print(f"⚠ 无效页码: {v}", file=sys.stderr)

        pages = sorted(set(pages))
        if not pages:
            print(f"⚠ 卷次 {vol} 未指定有效页码", file=sys.stderr)
            return

        entries = getattr(namespace, self.dest, None)
        if entries is None:
            entries = []
        entries.append((vol, pages))
        setattr(namespace, self.dest, entries)


# ── 主流程 ──

def main():
    _ensure_utf8_stream()

    parser = argparse.ArgumentParser(description="马恩全集 — 原文阅读工具")
    parser.add_argument("-v", "--vol", action=VolumePageAction, dest="volumes",
                        nargs="+", metavar=("卷次", "页码..."),
                        help="卷次及页码，如 -v 42 127 128 或 -v 23 100-105 110-115。可重复")
    parser.add_argument("--no-browser", action="store_true", help="不打开浏览器，只生成文件")

    parsed = parser.parse_args()
    volumes_data = parsed.volumes
    no_browser = parsed.no_browser

    if not volumes_data:
        print("用法:", file=sys.stderr)
        print("  python read_raw_text.py -v 42 127 128 129 130", file=sys.stderr)
        print("  python read_raw_text.py -v 46上 207 208 209", file=sys.stderr)
        print("  python read_raw_text.py -v 23 100-105 110-115", file=sys.stderr)
        print("  python read_raw_text.py -v 3 3-6 48-51 -v 42 125-130 167-170", file=sys.stderr)
        sys.exit(1)

    try:
        collection = get_collection()
    except RuntimeError as e:
        print(f"数据库错误: {e}", file=sys.stderr)
        sys.exit(1)
    except Exception as e:
        print(f"无法连接数据库: {e}", file=sys.stderr)
        sys.exit(1)

    start = time.time()

    # 拉取所有卷次的数据
    fetched = []
    for vol, pages in volumes_data:
        print(f"[info] 正在拉取 {format_volume_label(vol)} 第 {pages[0]}-{pages[-1]} 页...", file=sys.stderr)
        page_data = fetch_pages(collection, vol, pages)
        fetched.append((vol, page_data))

    # 生成 Markdown
    md_content = generate_markdown(fetched)
    os.makedirs(os.path.dirname(_TEMP_MD), exist_ok=True)
    with open(_TEMP_MD, "w", encoding="utf-8") as f:
        f.write(md_content)
    print(f"[info] Markdown 已保存: {_TEMP_MD}", file=sys.stderr)

    # 生成 HTML
    html_content = generate_html(fetched)
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
