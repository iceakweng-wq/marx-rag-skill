---
name: mega-rag
description: >
  当用户提到搜索、查询与马克思、恩格斯、马恩全集、资本论、政治经济学等与马克思主义经典文献相关概念时，使用此技能进行语义检索和原文阅读。
  支持中文和德文术语。用于在马克思恩格斯全集中搜索相关原文段落，找到后基于原文回答用户的问题并标注出处。
---

# 马克思恩格斯全集 RAG 检索技能

## 首次使用：初始化

### 1. 下载数据库
如果 `chroma_db/` 不存在，从 GitHub Release 下载约 900MB：
```bash
curl -L -o chroma_db.zip https://github.com/iceakweng-wq/mega-rag-skill/releases/download/v1.0/chroma_db.zip
python -m zipfile -e chroma_db.zip .
del chroma_db.zip
```

### 2. 检测 Python 路径
检查 `data/config.json`：
- **有 `python_path`** → 跳过，直接用
- **没有** → 主 agent 尝试以下步骤：
  1. 运行 `python -c "import sentence_transformers; import chromadb"` 测试当前 python
  2. 如果成功，将路径写入 `data/config.json`：`{"python_path": "当前python路径"}`
  3. 如果失败，尝试常见路径（如 Anaconda 环境），测试成功则写入 config
  4. 全部失败 → 提示用户安装 Python 环境并安装 sentence-transformers 和 chromadb

## Python 路径获取规则

启动任何子 agent 时，从 `data/config.json` 读取 `python_path` 字段，替换 `{python_path}` 占位符。

## 工作流

主 agent 只负责编排，不直接执行任何命令。所有脏活由 子 agent 独立完成。

**工具分工：**
- `search.py` — 单主题语义搜索，返回 `(卷次, 页码, 相关度)` 地址
- `multi_search.py` — 多主题并发搜索，自动合并去重排序（用 `;` 分隔主题）
- `query.py` — 根据卷次+页码拉取原文（含 header、脚注）

### 一、查询任务

当用户提到搜索、查询与马克思、恩格斯、马恩全集、资本论、政治经济学等与马克思主义经典文献相关概念时，使用此技能进行语义检索和原文阅读：

**启动 RAG 子 agent**
读取 `sub_agent/rag_agent.md`，把 `{python_path}` 替换为实际 Python 路径。

启动时从 `data/review_sessions.json` 查找该主题是否有已有内容（地址列表），如果有，一并传给子 agent 作为「初始已有内容」。

RAG 子 agent 会自己完成：
1. 参考已有内容，发散 2-4 个搜索方向（聚焦未覆盖角度）
2. 用 `multi_search.py` 并发搜索
3. 翻页扩展
4. 通读全部内容（已有+新增），判断是否足够
5. 不够则继续发散搜索，够了则输出结构化摘要

主 agent 等待子 agent 返回结构化摘要，直接呈现给用户。子 agent 返回后自动保存 session。

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
- 运行环境：Python 3.10+，需安装 `sentence-transformers`、`chromadb`
