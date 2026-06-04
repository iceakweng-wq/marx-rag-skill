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
- 有 `python_path` → 跳过
- 没有 → 测试当前 python 能否导入 sentence-transformers 和 chromadb，成功则写入 config
- 全部失败 → 提示用户安装

**路径格式：** Git Bash 用正斜杠 `/d/Program/...`，Windows 用反斜杠 `D:\Program\...`

## 工作流

执行查询任务时，读取 `sub_agent/rag_agent.md` 中的要求执行。
执行阅读原文任务时，读取 `sub_agent/read_txt.md` 中的要求执行。

Python 路径从 `data/config.json` 读取。

**工具分工：**
- `search.py` — 单主题语义搜索，返回地址
- `multi_search.py` — 多主题并发搜索（`;` 分隔）
- `query.py` — 按地址取原文
- `save_session.py` — 保存记录到 `review_sessions.json`
