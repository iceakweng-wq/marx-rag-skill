---
name: mega-rag
description: >
  当用户提到搜索、查询与马克思、恩格斯、马恩全集、资本论、政治经济学等与马克思主义经典文献相关概念时，使用此技能进行语义检索和原文阅读。
  支持中文和德文术语。用于在马克思恩格斯全集中搜索相关原文段落，找到后基于原文回答用户的问题并标注出处。
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

## 工作流

主 agent 只负责编排，不直接执行任何命令。所有脏活由 子 agent 独立完成。

实际Python路径：运行Python需要用到的启动路径，该路径可能在你的长期记忆里（.CLAUDE.md）也可能在你的短期记忆里。请你确保你已经明确知道实际的Python路径。

**工具分工：**
- `search.py` — 单主题语义搜索，返回 `(卷次, 页码, 相关度)` 地址
- `multi_search.py` — 多主题并发搜索，自动合并去重排序（用 `;` 分隔主题）
- `query.py` — 根据卷次+页码拉取原文（含 header、脚注）

### 一、查询任务

当用户提到搜索、查询与马克思、恩格斯、马恩全集、资本论、政治经济学等与马克思主义经典文献相关概念时，使用此技能进行语义检索和原文阅读：

**启动 RAG 子 agent**
读取 `sub_agent/rag_agent.md`，把 `{python_path}` 替换为实际 Python 路径，然后启动一个子agent，将用户问题传给子 agent。

RAG 子 agent 会自己完成：
1. 发散 2-4 个搜索方向
2. 逐一搜索 + 翻页扩展
3. 汇总判断是否足够，不够则继续发散
4. 够了则通读所有原文，输出结构化摘要

主 agent 等待子 agent 返回结构化摘要，直接呈现给用户。

主 agent context 中只保留：用户问题、子 agent 返回的结构化摘要。

### 二、阅读原文

当用户说"看原文""展示原文""读一下原文"时：

1. 确定卷次和页码：
   - 用户指定了 → 直接用
   - 用户说某个主题 → 查 `data/review_sessions.json` 取页码
   - 都没有 → 让用户补充信息

2. 读取 `sub_agent/read_txt.md`，替换 `{python_path}` 后启动子 agent

## 子 agent 文件

- `sub_agent/rag_agent.md` — RAG 子 agent（查询任务）
- `sub_agent/read_txt.md` — 阅读原文子 agent



## 技术说明

- 嵌入模型：BAAI/bge-large-zh-v1.5（首次使用自动下载，约 1.3GB）
- 向量维度：1024
- 分块策略：每页一个 chunk，34,540 页
- 数据库路径：`chroma_db/`
- Collection 名称：`marx_engels`
- 目录文件：`data/toc/` 覆盖 60 卷
- 评审 session 路径：`data/review_sessions.json`
- 运行环境：Python 3.10+，需安装 `sentence-transformers`、`chromadb`
