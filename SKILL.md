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
  4. 全部失败 → 若存在可用的Python路径，但没有安装对应包（sentence-transformers 和 chromadb），则协助用户在该路径下安装对应包（sentence-transformers 和 chromadb）。安装前向用户询问是否在此路径下安装。
  5. 如果没有可用的Python路径，提示用户安装 Python 环境

**路径格式说明：**
- Git Bash / Unix 终端 → 正斜杠，如 `/d/Program/Anaconda/envs/claude-env/python.exe`
- Windows CMD / PowerShell → 反斜杠，如 `D:\Program\Anaconda\envs\claude-env\python.exe`
在config保存路径时请确保对应终端的格式正确。

## Python 路径

从 `data/config.json` 读取 `python_path`，所有命令用此路径执行。

## 工作流

主 agent 直接执行命令，不启动子 agent。

**工具分工：**
- `search.py` — 单主题语义搜索，返回 `(卷次, 页码, 相关度)` 地址
- `multi_search.py` — 多主题并发搜索，自动合并去重排序（用 `;` 分隔主题）
- `query.py` — 根据卷次+页码拉取原文（含 header、脚注）
- `save_session.py` — 保存/更新搜索记录到 `review_sessions.json`

### 一、查询任务

**步骤 1：初始化已有内容**
查 `data/review_sessions.json` 中该主题的地址列表，用 `query.py` 读取已有原文。

**步骤 2：发散搜索方向**
参考已有内容，发散 2-4 个搜索方向，用 `multi_search.py` 并发搜索。

**步骤 3：翻页扩展**
对每个返回的地址块，用 `query.py` 逐页拉取原文，判断相关性。相关则继续扩展，不相关则停止。每块不超过 20 页。去重。

**步骤 4：通读 + 判断**
通读全部已有+新增内容，判断是否足够。不够则回到步骤 2。

**步骤 5：保存 + 输出**
用 `save_session.py` 保存结果，用 markdown 输出结构化摘要。

### 二、阅读原文

确定卷次页码后，直接运行：
```bash
{python_path} scripts/read_raw_text.py -v {卷次} {页码1} {页码2} ...
```



## 技术说明

- 嵌入模型：BAAI/bge-large-zh-v1.5（首次使用自动下载，约 1.3GB）
- 向量维度：1024
- 分块策略：每页一个 chunk，34,540 页
- 数据库路径：`chroma_db/`
- 运行环境：Python 3.10+，需安装 `sentence-transformers`、`chromadb`
