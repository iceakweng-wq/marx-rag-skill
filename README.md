# 马恩全集 RAG 检索系统

马克思恩格斯全集（中文版）语义检索工具。覆盖60卷、34,000+页原文。

查询语言：中文 / 德文 / 英文 术语均可。

---

## 安装

```bash
git clone git@github.com:iceakweng-wq/marx-rag-skill.git
cd marx-rag-skill
pip install sentence-transformers chromadb
python setup.py
```

`setup.py` 会从 GitHub Release 下载向量数据库（约 600MB）并自动解压。

首次运行还会自动下载嵌入模型（BAAI/bge-large-zh-v1.5，约 1.3GB），只需下载一次。

---

## 快速使用

```bash
# 语义检索
python scripts/search.py "感性活动"

# 限定卷次
python scripts/search.py "一般智力" --volume 46下

# 按页码取页
python scripts/search.py --page 42 125 126 127

# 数据库统计
python scripts/search.py --info
```

---

## 核心功能

### 语义检索

基于 bge-large-zh 嵌入模型，用自然语言查找相关原文，不依赖关键词匹配。检索结果自动返回命中页及其前后各一页，`>>>` 标记命中的核心页。

### 自动联想

当检索不到想要的内容时，子 agent 会根据对马克思理论的理解，自动推测相关的关键词、限定卷次，重新搜索。

搜索日志会完整展示每一步的决策过程和执行结果，让你看到它是怎么推测的。

### 自动翻页扩展

对每个命中结果，子 agent 会逐页检查相邻页面的内容是否与查询主题相关。相关的保留并继续翻页，不相关的停止。每块不超过20页，不同命中块的取页结果会自动去重合并。

### 搜索缓存

搜索过的结果保存在 `data/search_cache/` 中。下次遇到相同话题时直接读取缓存，不用重新搜索。缓存可以手动清除：

```
清除文献缓存       → 删除所有缓存
清除XX的缓存       → 删除指定文件（如"清除资本有机构成的缓存"）
```

### 按页码取页

已知具体页码时，直接取指定页的原文，不走语义检索，瞬间返回。

---

## 工作原理

```
1. 自然语言查询
       ↓
2. bge-large-zh 嵌入模型 → ChromaDB 语义检索
       ↓
3. 返回命中页 ± 1页 上下文
       ↓
4. 子 agent 逐页判断相关性，翻页扩展至不相关边界
       ↓
5. 结果保存到 data/search_cache/
       ↓
6. 返回结构化摘要
```

### 数据

- **分块策略**：每页一个 chunk，共 34,540 页
- **嵌入模型**：BAAI/bge-large-zh-v1.5，向量维度 1024
- **向量数据库**：ChromaDB，collection = marx_engels
- **目录文件**：data/toc/ 覆盖 60 卷，用于显示篇章名
- **附录过滤**：注释、人名索引、著作索引、期刊索引自动标记为 endnote，不入检索

---

## 目录结构

```
marx-rag-skill/
├── scripts/
│   ├── search.py        # 检索工具（核心文件）
│   └── utils.py         # 卷次解析、篇章名查询
├── chroma_db/           # 向量数据库（setup.py 自动下载）
├── data/
│   ├── toc/             # 60 卷目录文件
│   └── search_cache/    # 搜索缓存
├── setup.py             # 安装脚本
├── README.md            # 本文件
└── SKILL.md             # Claude Code Skill 配置
```

---

## 依赖

- Python 3.10+
- sentence-transformers
- chromadb
