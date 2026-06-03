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

### 使用规则

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
- 运行环境：Python 3.10+，需安装 `sentence-transformers`、`chromadb`
