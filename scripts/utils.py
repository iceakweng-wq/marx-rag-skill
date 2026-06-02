"""
马恩全集 RAG 系统 — 公用函数
"""

import json
import os
import re
from functools import lru_cache


def fullwidth_to_halfwidth(s: str) -> str:
    """全角数字转半角。"""
    return s.translate(str.maketrans("０１２３４５６７８９", "0123456789"))


def extract_page_number(s: str) -> int | None:
    """从全角/半角数字字符串提取整数页码。

    Args:
        s: 可能包含数字的字符串

    Returns:
        整数页码，如果无法提取则返回 None
    """
    if not s:
        return None
    half = fullwidth_to_halfwidth(s.strip())
    nums = re.findall(r"\d+", half)
    if nums:
        n = int(nums[0])
        if n > 2 and not (1800 <= n <= 1999):
            return n
    return None


def extract_volume_info(filename: str) -> dict:
    """从文件名提取卷次信息。

    文件名示例：
        "马克思恩格斯全集_第23卷.pdf"  →  vol=23, label="第23卷"
        "马克思恩格斯全集+第46卷（上）.pdf" →  vol=46, sub="上"

    Returns:
        {"volume": int|None, "sub_volume": str, "volume_label": str, "volume_slug": str}
    """
    match = re.search(r"第(\d+)卷", filename)
    if not match:
        return {"volume": None, "sub_volume": "", "volume_label": "", "volume_slug": ""}

    vol = int(match.group(1))

    # 分册标记
    after_vol = filename[match.end(0):match.end(0) + 4]
    sub_match = re.search(r"[（(]?([上中下])[）)]?", after_vol)
    sub_vol = sub_match.group(1) if sub_match else ""

    if sub_vol:
        volume_label = f"第{vol}卷（{sub_vol}）"
        volume_slug = f"{vol}{sub_vol}"
    else:
        volume_label = f"第{vol}卷"
        volume_slug = str(vol)

    return {
        "volume": vol,
        "sub_volume": sub_vol,
        "volume_label": volume_label,
        "volume_slug": volume_slug,
    }


# ── 目录查询 ──

@lru_cache(maxsize=64)
def load_toc(volume_slug: str) -> dict | None:
    """加载指定卷次的目录文件（带缓存）。

    Args:
        volume_slug: 卷次标识，如 "23" 或 "46上"

    Returns:
        目录 dict，文件不存在时返回 None
    """
    toc_dir = os.path.join(os.path.dirname(__file__), "..", "data", "toc")
    candidates = [
        f"vol{volume_slug}.json",
        f"vol{volume_slug.replace('第', '').replace('卷', '')}.json",
    ]
    for candidate in candidates:
        path = os.path.join(toc_dir, candidate)
        if os.path.exists(path):
            with open(path, "r", encoding="utf-8") as f:
                return json.load(f)
    return None


def lookup_chapter(volume_slug: str, page: int) -> str:
    """根据卷次和页码查询篇章名。

    优先精确匹配（page 在 section 区间内），
    若无精确匹配则返回到该 page 为止的最近一个 section。

    Args:
        volume_slug: 卷次标识
        page: 正文页码

    Returns:
        篇章名，未找到时返回空字符串
    """
    toc = load_toc(volume_slug)
    if toc is None:
        return ""

    # 精确匹配
    matches = []
    for section in toc.get("sections", []):
        if section["page_start"] <= page <= section["page_end"]:
            matches.append(section)

    if matches:
        # 返回页码范围最窄的匹配
        best = min(matches, key=lambda s: s["page_end"] - s["page_start"])
        return best["name"]

    # 退而求其次：找最近的前一个 section
    preceding = [s for s in toc.get("sections", []) if s["page_start"] <= page]
    if preceding:
        nearest = max(preceding, key=lambda s: s["page_end"])
        return nearest["name"]

    return ""


# ── 相似度计算 ──


def cosine_similarity(vec_a, vec_b) -> float:
    """计算两个向量的余弦相似度。"""
    dot = sum(x * y for x, y in zip(vec_a, vec_b))
    na = sum(x * x for x in vec_a) ** 0.5
    nb = sum(x * x for x in vec_b) ** 0.5
    if na == 0 or nb == 0:
        return 0.0
    return dot / (na * nb)


# ── 结果格式化 ──

def format_result(rank: int, score: float, chunk: dict, chapter_name: str = "") -> str:
    """格式化单条检索结果为终端显示文本。"""
    meta = chunk.get("metadata", {})
    text = chunk.get("text", "")

    vol_label = meta.get("volume_label", "")
    page_display = meta.get("page_display", "")

    source = f"{vol_label} | {page_display}" if page_display else vol_label
    chapter_line = f"篇章: {chapter_name}" if chapter_name else "篇章: （未录入目录）"

    lines = []
    lines.append("━" * 46)
    lines.append(f"[结果 {rank}] 相关度: {score:.4f}")
    lines.append(f"出处: {source}")
    lines.append(chapter_line)
    lines.append("━" * 46)
    lines.append(text)
    lines.append("")
    return "\n".join(lines)
