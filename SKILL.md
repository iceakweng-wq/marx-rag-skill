---
name: mega-rag
description: >
  当用户提到搜索、查询马克思、恩格斯、马恩全集、资本论、政治经济学批判、
  德意志意识形态、1844年手稿、共产党宣言、剩余价值、历史唯物主义、
  辩证法、异化、类本质、感性活动、一般智力、商品拜物教、劳动力、资本积累、
  或任何马克思主义经典文献相关概念时，使用此技能进行语义检索和原文阅读。
  支持中文和德文术语。用于在马克思恩格斯全集中搜索相关原文段落，
  找到后基于原文回答用户的问题并标注出处。
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

子 agent 的具体任务说明在 `sub_agent/` 下的文件中，启动子 agent 时读取并传入指令。

---

### 一、查询任务工作流

当用户提出马恩理论、概念、原文相关的搜索与查询问题时，执行此工作流。

**步骤 1：发散搜索方向**
根据用户问题发散出 **3-5 个搜索方向**（不同关键词、不同表述），**每一个搜索方向启动一个**子agent作为 search_agent。
每个search_agent启动时读取 `sub_agent/search_agent.md` 中的指令传给子 agent，并告知他们的搜索方向。

**步骤 2：接收格式化总结**
每个将 search_agent 返回：
- 卷次、页码范围
- 100字以内的内容简述

主 agent **只保留这些格式化总结**，不接触原文。

**步骤 3：判断是否继续**
接受完**所有**search_agent返回的结果后，根据当前已经收集到的格式化总结判断：
- 是否覆盖了用户问题的各方面
- 是否有多样性（不同卷次、不同时期）
- 是否需要换关键词继续搜索

→ 如果需要，回到步骤 1 发散新的搜索方向，并开启新一轮search_agent搜索。
→ 如果够了，进入步骤 4。

**步骤 4：启动 summarize_agent**
汇总当前收集到的所有格式化总结的`(卷次, 页码)` ，有重叠的进行合并
启动**一个**子agent作为summarize_agent，启动时读取 `sub_agent/summarize_agent.md`，然后把汇总后的所有 `(卷次, 页码)` 传给summarize_agent。
summarize_agent 拉取原文、通读、输出结构化摘要。

**步骤 5：呈现给用户**
直接呈现 summarize_agent 返回的结构化摘要。

---

### 二、阅读原文工作流

当用户说"看原文""展示原文""读一下原文"等时，执行此工作流。

**步骤 1：确定卷次和页码**
- 如果用户指定了卷次+页码 → 进入步骤2
- 如果用户说想看某个主题的原文 → 查 `data/review_sessions.json` 中有没有该主题的 session，取 `covered_pages`→进入步骤2
- 如果都没有 → 展示已有 session 主题让用户选，或建议先用查询工作流搜索。等待用户给出更明确的信息

**步骤 2：启动 read_txt_agent**
启动子 agent 作为read_txt_agent，启动时读取 `sub_agent/read_txt.md`，并将用户要查询的内容的卷次页码传给read_txt_agent。
read_txt_agent 将会读取原文并用HTML渲染。

## 子 agent 文件

子 agent 的具体任务说明在以下文件中，启动子 agent 时读取并传入：
- `sub_agent/search_agent.md` — 搜索子 agent 任务
- `sub_agent/summarize_agent.md` — 总结子 agent 任务
- `sub_agent/read_txt.md` — 阅读原文子 agent 任务



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
