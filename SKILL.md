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

## 主 agent 工作流

主 agent 是编排者，不直接执行任何搜索或阅读命令。所有具体操作通过子 agent 完成。

### ① 发散搜索方向

根据用户问题，发散出 **3-5 个搜索方向**（不同关键词、不同表述），然后逐一启动 search_agent。

启动 search_agent 时，读取 `sub_agent/search_agent.md` 中的指令传给子 agent。

### ② 接收格式化总结

每个 search_agent 返回：
- 卷次、页码范围
- 100字以内的内容简述

主 agent **只保留这些格式化总结**，不接触原文。

### ③ 判断是否继续

根据收到的格式化总结判断：
- 是否覆盖了用户问题的各方面
- 是否有多样性（不同卷次、不同时期）
- 是否需要换关键词继续搜索

如果需要，回到步骤①发散新的搜索方向。
如果够了，进入步骤④。

### ④ 启动 summarize_agent

读取 `sub_agent/summarize_agent.md` 中的指令，把汇总后的 `(卷次, 页码)` 传给总结子 agent。

总结子 agent 会：
1. 用 `python search.py --page {卷次} {页码1} {页码2} ...` 拉取原文
2. 通读全部原文
3. 输出结构化摘要（卷名、篇章名、页码范围、内容总结、重要引用）

### ⑤ 呈现给用户

收到 summarize_agent 的结构化摘要后，直接呈现给用户。

### 阅读原文

当用户要看原文时，读取 `sub_agent/read_txt.md`，启动子 agent 调用 `read_raw_text.py`。

## 子 agent 文件

子 agent 的具体任务说明在以下文件中，启动子 agent 时读取并传入：
- `sub_agent/search_agent.md` — 搜索子 agent 任务
- `sub_agent/summarize_agent.md` — 总结子 agent 任务
- `sub_agent/read_txt.md` — 阅读原文子 agent 任务

## 翻页扩展算法

搜索子 agent 对每个命中块执行以下步骤：

**① 初始块**：语义搜索返回命中页及其±1页。

**② 向上扩展**（往小页码）：
- 通读当前块最前面一页的**全部内容**
- 判断整页是否与查询主题相关（标准见下文）
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

### 判断标准

"与查询主题直接相关"指该页在讨论同一个论点或同一组概念：
- 该页在论证同一个命题 → 相关
- 该页在展开同一个概念的不同面向 → 相关
- 该页只是碰巧提到相同术语但在讨论另一个话题 → 不相关
- 该页是前文的结论总结 → 相关
- 该页已经转入下一节/下一章 → 不相关

## 引用规则

1. 标注出处格式：【《篇名》，第X卷，第X页】
2. 尽量引用原文关键表述（用引号标注）
3. 如果论述跨多页，标注实际引用的页码范围
4. 一次检索不够就换关键词多次检索
5. 用户可能用中文或德文术语提问，尝试多种表述
6. 脚注通常是编者注或恩格斯补注，需要时加 --with-footnotes
7. 如果命中多个结果且卷次页码相近，先合并再扩展

## 技术说明

- 嵌入模型：BAAI/bge-large-zh-v1.5（首次使用自动下载，约 1.3GB）
- 向量维度：1024
- 分块策略：每页一个 chunk，34,540 页
- 数据库路径：`chroma_db/`
- Collection 名称：`marx_engels`
- 目录文件：`data/toc/` 覆盖 60 卷
- 评审 session 路径：`data/review_sessions.json`
- 运行环境：Python 3.10+，需安装 `sentence-transformers`、`chromadb`
