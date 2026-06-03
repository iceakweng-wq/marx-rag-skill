# 马恩全集 RAG 检索系统

马克思恩格斯全集（中文版）语义检索工具。覆盖60卷、34,000+页原文。

查询语言：中文 / 德文 / 英文 术语均可。

---

## 安装

### 方式一：自动配置（推荐）

在 Claude Code 中加载本 skill，agent 会自动读取 `SKILL.md` 完成配置。如果检测到 `chroma_db/` 不存在，会自动从 GitHub Release 下载并解压。

### 方式二：手动下载数据库

如果 agent 无法自动下载，可以手动操作：

1. 下载依赖：
   ```bash
   pip install sentence-transformers chromadb
   ```

2. 下载向量数据库：
   打开 https://github.com/iceakweng-wq/mega-rag-skill/releases/tag/v1.0 ，下载 `chroma_db.zip`，解压到 skill 根目录，使 `chroma_db/` 文件夹出现在 `scripts/` 同级。

完成后目录结构应为：
```
mega-rag-skill/
├── chroma_db/       ← 解压后得到的文件夹
├── scripts/
├── data/
├── README.md
└── SKILL.md
```

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

# 浏览器阅读原文
python scripts/read_raw_text.py 42 127 128 129 130
python scripts/read_raw_text.py 23 100-105 110-115    # 支持页码范围
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

### 三 agent 架构

系统使用三个 agent 分工协作，控制 token 消耗：

| Agent | 任务 | 输出 |
|-------|------|------|
| **搜索 agent** | 语义检索 + 翻页扩展 | `(卷次, 页码)` 列表（无原文） |
| **主 agent** | 汇总、去重、编排 | 页码范围传给评审 agent |
| **评审 agent** | 拉取原文阅读、判断是否足够、补充搜索（按主题持久化 session） | 结构化摘要 |

### 按页码取页

已知具体页码时，直接取指定页的原文，不走语义检索，瞬间返回。

### 浏览器阅读原文

用 `read_raw_text.py` 按卷次+页码拉取原文，生成带左侧目录的 HTML 页面并在浏览器中打开。支持连续页码和页码范围（`100-105`），每次查询覆盖上一次的临时文件，不留痕迹。

---

## 工作原理

```
1. 用户提问 → 主 agent 判断是否马恩问题
       ↓
2. 搜索 agent：语义检索 + 翻页扩展 → 返回 (卷次, 页码)
       ↓
3. 主 agent：汇总去重排序，传给评审 agent
       ↓
4. 评审 agent：拉取原文阅读，判断是否足够
       ↓
5. 若不够 → 要求主 agent 补充搜索（回到步骤2）
       ↓
6. 若足够 → 输出结构化摘要 → 主 agent 呈现给用户
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
mega-rag-skill/
├── scripts/
│   ├── search.py        # 检索工具（核心文件）
│   ├── read_raw_text.py # 浏览器阅读原文
│   └── utils.py         # 卷次解析、篇章名查询
├── chroma_db/           # 向量数据库（从 Release 下载）
├── data/
│   ├── toc/             # 60 卷目录文件
│   └── review_sessions.json # 评审 agent session（按主题持久化）
├── README.md            # 本文件
└── SKILL.md             # Claude Code Skill 配置
```

---

## 依赖

- Python 3.10+
- sentence-transformers
- chromadb
