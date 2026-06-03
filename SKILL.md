---
name: mega-rag
description: >
  当用户提到马克思、恩格斯、马恩全集、资本论、政治经济学批判、
  德意志意识形态、1844年手稿、共产党宣言、剩余价值、历史唯物主义、
  辩证法、异化、类本质、感性活动、一般智力、商品拜物教、劳动力、资本积累、
  或任何马克思主义经典文献相关概念时，使用此技能检索原文段落。
  支持中文和德文术语。用于在马克思恩格斯全集中做语义搜索，找到相关原文后，
  基于原文回答用户的问题并标注出处。
---

# 马克思恩格斯全集 RAG 检索技能

## 首次使用：自动下载数据库

如果本目录下没有 `chroma_db/` 目录，请先执行以下命令下载并解压：

```bash
curl -L -o chroma_db.zip https://github.com/iceakweng-wq/mega-rag-skill/releases/download/v1.0/chroma_db.zip
python -m zipfile -e chroma_db.zip .
del chroma_db.zip
```

或者在 Python 中执行：
```python
import urllib.request, zipfile
urllib.request.urlretrieve("https://github.com/iceakweng-wq/mega-rag-skill/releases/download/v1.0/chroma_db.zip", "chroma_db.zip")
with zipfile.ZipFile("chroma_db.zip", "r") as zf:
    zf.extractall(".")
import os; os.remove("chroma_db.zip")
```

数据库下载约 600MB，解压后约 900MB。

本技能提供一个语义检索工具，可在马克思恩格斯全集（中文版）60 卷、
34,000+ 页中搜索与用户问题最相关的原文段落。

## 使用方法

### 语义检索
```bash
python scripts/search.py "查询内容"
python scripts/search.py "查询内容" --top_k 5      # 返回5组结果（默认10）
python scripts/search.py "查询内容" --volume 23     # 限定卷次
python scripts/search.py "查询内容" --with-footnotes
python scripts/search.py --info                     # 数据库统计
python scripts/search.py --page 46上 207 208 209   # 按页码取页

# 浏览器阅读原文
python scripts/read_raw_text.py -v 42 127 128 129 130
python scripts/read_raw_text.py -v 23 100-105 110-115  # 支持页码范围
python scripts/read_raw_text.py -v 3 3-6 48-51 -v 42 125-130 167-170  # 多卷次
```

### 检索流程（三 agent 架构）

**搜索 agent** → 即用即毁，只返回 `(卷次, 页码)` 列表
**主 agent** → 汇总、去重、合并页码范围 → 传给评审 agent
**评审 agent** → 按主题分别持久化评审进度 → 输出结构化摘要

#### ① 搜索 agent（即用即毁）

1. 运行 `python scripts/search.py "关键词" --mode expand --top_k 3` 进行语义检索
2. 对每个命中块执行翻页扩展算法（见下文）
3. **只返回 `(卷次, 页码)` 列表给主 agent**，不返回原文
4. 返回后即销毁，不保留任何状态

#### ② 主 agent 汇总

- 收集所有搜索 agent 返回的 `(卷次, 页码)`
- 去重（同卷同页码只保留一个）
- 按卷次和页码排序，合并连续的页码范围
- 将汇总结果传给评审 agent

#### ③ 评审 agent（按主题持久化 session）

所有评审 session 统一存储在一个 JSON 文件中：

```
data/review_sessions.json
```

**每次启动评审 agent 时：**

1. **读取 sessions**：检查 `data/review_sessions.json` 是否存在，存在则加载
2. **结合新结果**：把主 agent 传来的新页码与 session 中该主题已有的页码合并去重
3. **拉取原文阅读**：用 `python scripts/search.py --page {卷次} {页码1} {页码2} ...` 拉取原文（优先只拉取新页码，但如有必要可重读全部）
4. **判断是否足够**：
   - 内容是否足够回答用户问题
   - 覆盖范围是否多样（不同文本、不同时期的论述）
   - 是否需要补充搜索其他关键词
5. **如果不够**：更新 session，告诉主 agent 还需要搜索哪些关键词，主 agent 启动新的搜索 agent，更新汇总后再次传给评审 agent
6. **如果够了**：输出**结构化摘要**（格式见下文），更新 session，返回给主 agent

**Session 文件格式：**

```json
{
  "感性活动": {
    "last_updated": "2026-06-03",
    "covered_pages": {
      "42": [127, 128, 129, 130],
      "3": [4, 5, 6]
    },
    "search_keywords": ["人的感性活动", "感性活动 实践"],
    "saturated": false
  },
  "一般智力": {
    "last_updated": "2026-06-03",
    "covered_pages": {
      "46上": [207, 208, 209, 210, 211, 212, 213, 214]
    },
    "search_keywords": ["一般智力", "general intellect"],
    "saturated": true
  }
}
```

#### ④ 主 agent 呈现

- 收到评审 agent 的结构化摘要
- 直接展现给用户

### 结构化摘要格式

```
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
① 《第42卷》
② 1844年经济学哲学手稿
③ 第127-130页
④ 内容总结：
   马克思在这一部分论述了感性作为一切科学的基础地位……
   感性必须从感性意识和感性需要两种形式出发……
   自然科学将包含关于人的科学，二者将成为一门科学……
⑤ 重要表述引用：
   · "感性（见费尔巴哈）必须是一切科学的基础。科学只有从感性
      意识和感性需要这两种形式的感性出发，因而，只有从自然界
      出发，才是现实的科学。"（第128页）
   · "自然科学往后将包括关于人的科学，正象关于人的科学包括
      自然科学一样：这将是一门科学。"（第128页）
   · "人的第一个对象——人——就是自然界、感性……"（第129页）
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
```

### 翻页扩展算法

子 agent 对每个命中块独立执行以下步骤：

**① 初始块**：语义搜索返回命中页及其±1页。

**② 向上扩展**（往小页码）：
- 通读当前块最前面一页的**全部内容**
- 判断整页是否与查询主题相关
  - 相关 → 保留，再取前一页重复
  - 不相关 → 去除，停止向上

**③ 向下扩展**（往大页码）：
- 通读当前块最后面一页的**全部内容**
- 判断整页是否与查询主题相关
  - 相关 → 保留，再取后一页重复
  - 不相关 → 去除，停止向下

**④ 去重**：用集合记录已保留的 `(卷次, 页码)`，扩展前检查避免重复。

**⑤ 块上限**：每块不超过20页。达到上限停止。

**⑥ 合并排序**：所有块完成后按卷次和页码排序。

### 搜索结果说明

- 自动返回命中页及其前后各一页
- `>>>` 标记命中的核心页
- 子 agent 自动判断扩展边界，每块不超过20页
- 如需更精准定位，可用 `--page` 手动取页

## 阅读原文

当用户说想看原文时，启动子 agent 使用 `scripts/read_raw_text.py` 读取并展示原文。

### 判断流程

1. **用户指定了卷次+页码** → 直接用 `scripts/read_raw_text.py -v {卷次} {页码1} {页码2} ...`
2. **用户说想看某个主题的原文** → 查 `data/review_sessions.json` 中有没有该主题的 session，取其中的 `covered_pages` 调 read_raw_text.py
3. **都没有** → 告诉用户目前支持的 session 主题（列出已保存的主题），或建议先用 `python scripts/search.py "主题"` 检索，等用户确认后再行动

### 示例

```bash
# 用户指定卷次页码
python scripts/read_raw_text.py -v 42 128 129

# 用户指定页码范围
python scripts/read_raw_text.py -v 23 100-105

# 多卷次混合
python scripts/read_raw_text.py -v 3 3-6 48-51 -v 42 125-130 167-170

# 从 session 取页码（如"感性活动"主题）
python scripts/read_raw_text.py -v 42 127 128 129 130 -v 3 4 5 6
```

## 使用规则

1. **先检索再回答**：用户问到马恩理论、概念、原文表述时，先用 search.py 检索
2. **标注出处**：回答时标注【第X卷，第X页】
3. **引用原文**：直接引用关键表述，用引号标注
4. **多次检索**：结果不够可换关键词多次检索
5. **概念辨析**：涉及概念在不同文本中的用法，分别检索多个卷次
6. **空结果**：如实告知用户，建议尝试其他关键词
7. **中德术语**：用户可能用中文或德文提问，尝试多种表述
8. **附属页码**：给出引文时勿忘附上卷数和页码

## 输出格式

```
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
>>> [命中 1] 相关度: 0.8723
>>> 出处: 第46卷（上） | 第208页
>>> chunk_id: vol46上_p208
>>> 篇章: 政治经济学批判（1857-1858年草稿）· 资本章
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
（该页正文）

——— 上下文: 第46卷（上） | 第209页 ———
（上下文页正文）
```

## 技术说明

- 嵌入模型：BAAI/bge-large-zh-v1.5（首次使用自动下载，约 1.3GB）
- 向量维度：1024
- 分块策略：按页分块，34,540 页
- 数据库路径：`chroma_db/`
- Collection 名称：`marx_engels`
- 评审 session 路径：`data/review_sessions.json`（单个 JSON 文件管理所有主题）
- 运行环境：Python 3.10+，需安装 `sentence-transformers`、`chromadb`
