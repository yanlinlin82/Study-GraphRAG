# Study GraphRAG 实现文档

> 基于知识图谱的检索增强生成系统（GraphRAG），面向生物医药领域，使用 Neo4j 作为图数据库。

---

## 目录

- [1. 项目概述](#1-项目概述)
- [2. 系统架构](#2-系统架构)
- [3. 数据模型](#3-数据模型)
- [4. 配置系统](#4-配置系统)
- [5. 导入管道（Ingestion Pipeline）](#5-导入管道ingestion-pipeline)
- [6. 检索管道（Retrieval Pipeline）](#6-检索管道retrieval-pipeline)
- [7. 生成管道（Generation Pipeline）](#7-生成管道generation-pipeline)
- [8. Web 界面](#8-web-界面)
- [9. 目录结构与文件职责](#9-目录结构与文件职责)
- [10. 重要数据格式详解](#10-重要数据格式详解)
- [11. 关键技术细节与注意事项](#11-关键技术细节与注意事项)

---

## 1. 项目概述

Study GraphRAG 是一个**学习型项目**，旨在通过完整实现来理解 GraphRAG 的工作原理。它以生物医药文献为处理对象，使用 LLM 从非结构化文本中提取实体和关系，存入 Neo4j 图数据库，再通过混合检索（向量搜索 + 图遍历）召回上下文，最终由 LLM 生成带有证据引用的答案。

### 核心流程

```
文本 → LLM 提取实体/关系 → Neo4j 存储 → 用户提问 → 检索上下文 → LLM 生成答案
```

### 技术栈

| 组件 | 选型 | 说明 |
|---|---|---|
| 图数据库 | Neo4j 5 Community | Docker 部署，Bolt 协议连接 |
| LLM | DeepSeek Chat（默认）/ OpenAI 兼容 | 通过 `LLM_BASE_URL` 切换 |
| 文本嵌入 | Sentence-Transformers `all-MiniLM-L6-v2` | 384 维，余弦相似度，本地运行 |
| 语言 | Python 3.11+ | 类型注解全面 |
| Web 框架 | FastAPI + Uvicorn | 异步，自动文档 |

---

## 2. 系统架构

系统分为四个层次，自底向上：

```
┌──────────────────────────────────────────┐
│              Web 界面 (FastAPI)           │
│   HTML 聊天页面 → /api/query → JSON 响应  │
└────────────────┬─────────────────────────┘
                 │
┌────────────────▼─────────────────────────┐
│          生成层 (Generation)               │
│   接收检索上下文 + 用户问题 → LLM → 答案    │
│   src/study_graphrag/generation/          │
└────────────────┬─────────────────────────┘
                 │
┌────────────────▼─────────────────────────┐
│          检索层 (Retrieval)                │
│   ① 实体链接（LLM 从问题中识别实体）         │
│   ② 向量搜索（问题嵌入 → Neo4j 向量索引）    │
│   ③ 图扩展（从匹配实体出发 1-2 跳遍历）      │
│   ④ 上下文组装（三元组序列化）               │
│   src/study_graphrag/retrieval/            │
└────────────────┬─────────────────────────┘
                 │
┌────────────────▼─────────────────────────┐
│         图存储层 (Graph Storage)            │
│   Neo4j 客户端封装：MERGE、向量搜索、路径遍历  │
│   src/study_graphrag/graph/                │
└────────────────┬─────────────────────────┘
                 │
┌────────────────▼─────────────────────────┐
│         导入层 (Ingestion)                  │
│   文本分块 → LLM 提取实体 → LLM 提取关系     │
│   → 生成 Embedding → 写入 Neo4j            │
│   src/study_graphrag/ingestion/            │
└──────────────────────────────────────────┘
```

### 关键设计决策

| 决策 | 理由 |
|---|---|
| LLM 提取替代 NER 模型 | 无需训练数据，schema 可灵活调整，快速迭代 |
| 混合检索（向量 + 图） | 向量搜索找到语义相似的实体；图遍历捕获多跳关系路径 |
| 按 Label 分索引 | 旧版 Neo4j 不支持 `(n:Gene\|Drug\|...)` 多标签管道符语法，拆成单个索引更兼容 |
| 惰性初始化 | GraphSearcher 和 AnswerGenerator 在首次使用时才加载 embedding 模型，避免启动耗时 |

---

## 3. 数据模型

### 节点类型（7 种）

| Label | 含义 | 关键属性 | 示例 |
|---|---|---|---|
| `Gene` | 基因 | name, description, chromosome, embedding | BRCA1, TP53, EGFR |
| `Protein` | 蛋白质 | name, uniprot_id, function, embedding | p53, EGFR protein |
| `Drug` | 药物 | name, drugbank_id, mechanism, embedding | Olaparib, Gefitinib |
| `Disease` | 疾病 | name, mondo_id, description, embedding | Breast Cancer, NSCLC |
| `Pathway` | 生物通路 | name, kegg_id, description, embedding | PI3K/AKT, RAS/RAF |
| `Event` | 重化关系（n 元关系） | id, type, metadata, pmid | TREATS::BCR-ABL::CML::Imatinib |
| `Article` | 文献 | name(=pmid), title, abstract, year, embedding | pmid-12345678 |

### 关系类型

#### 二元关系（Edge）

每条 Edge 额外存储两个属性用于溯源：
- `metadata`: 原文证据片段
- `pmid`: 来源文献标识

| 类型 | 源 → 目标 | 语义 |
|---|---|---|
| `ENCODES` | Gene → Protein | 基因编码蛋白质 |
| `TARGETS` | Drug → Gene/Protein | 药物作用于靶点 |
| `ASSOCIATED_WITH` | Gene/Protein → Disease | 遗传关联 |
| `INDICATED_FOR` | Drug → Disease | 药物获批适应症 |
| `PARTICIPATES_IN` | Gene/Protein/Event → Pathway/Event | 参与通路或 n 元事件 |
| `REGULATES` | Gene/Protein → Gene/Protein | 调控关系 |
| `INTERACTS_WITH` | Protein → Protein | 蛋白互作 |
| `MENTIONED_IN` | 任意实体/Event → Article | 实体/事件出现于某篇文献 |

#### N 元关系（Event 节点）

当关系涉及超过两个实体时（如 "Drug A treats Disease B by targeting Gene C"），将其重化为一个 `:Event` 节点：

```
(Drug Imatinib)-[:PARTICIPATES_IN]->(Event {type: "TREATS", pmid: "..."})<-[...]-(Disease CML)
                                     (Event)-[:MENTIONED_IN]->(Article {pmid: "..."})
```

Event 节点属性：
- `id`: 去重键（`{relation_type}::{sorted_participant_names}`）
- `type`: 关系类型
- `metadata`: 证据文本
- `pmid`: 来源文献

### 约束与索引

导入管道在首次写入时会自动创建：

- **7 个唯一约束**：每种实体按 `name` 去重（Article 按 `pmid`，Event 按 `id`）
- **6 个向量索引**：每种 Label 各一个，用于余弦相似度搜索（384 维）

---

## 4. 配置系统

所有配置通过环境变量加载（`.env` 文件），集中管理在 `src/study_graphrag/config.py`。

```python
class Settings:
    # Neo4j 连接
    NEO4J_URI = "bolt://localhost:7687"
    NEO4J_USER = "neo4j"
    NEO4J_PASSWORD = "password"

    # LLM（OpenAI 兼容 API）
    LLM_MODEL = "deepseek-chat"           # 模型名
    LLM_API_KEY = ""                       # API Key（必填）
    LLM_BASE_URL = "https://api.deepseek.com"  # 切换为 OpenAI/Ollama 等
    LLM_MAX_TOKENS = 4096
    LLM_TEMPERATURE = 0.1                  # 提取任务用低温

    # 文本嵌入
    EMBEDDING_MODEL = "all-MiniLM-L6-v2"  # HuggingFace 模型
    VECTOR_DIMENSIONS = 384                # 必须与模型输出维度一致

    # 检索参数
    RETRIEVAL_TOP_K = 10                   # 向量搜索结果数
    RETRIEVAL_MAX_HOPS = 2                 # 图遍历最大跳数
    RETRIEVAL_MIN_SCORE = 0.5              # 向量相似度阈值

    # 导入参数
    CHUNK_SIZE = 1500                      # 文本分块大小（字符）
    CHUNK_OVERLAP = 100                    # 分块重叠
```

### 切换 LLM 提供方

只需改 `.env` 两行即可切换：

```bash
# DeepSeek（默认）
LLM_MODEL=deepseek-chat
LLM_BASE_URL=https://api.deepseek.com

# OpenAI
LLM_MODEL=gpt-4o-mini
LLM_BASE_URL=https://api.openai.com/v1

# 本地 Ollama
LLM_MODEL=llama3
LLM_BASE_URL=http://localhost:11434/v1
```

---

## 5. 导入管道（Ingestion Pipeline）

### 数据流

```
输入文件 (.jsonl / .txt)
    │
    ▼
文本分块（按 CHUNK_SIZE 分割）
    │
    ├──► LLM 实体提取 ──────────► Entity 对象列表
    │       prompt: 从文本中识别 Gene/Protein/Drug/Disease/Pathway
    │
    ├──► LLM 关系提取 ──────────► (List[Relation], List[HyperRelation])
    │       prompt: 识别二元关系 + n 元关系
    │       每条关系附带 pmid 标记来源文献
    │
    ├──► 自动关联 Article ──────► 各实体 → MENTIONED_IN → Article
    │       此关系也带 pmid 属性
    │
    ├──► HyperRelation → Event 节点创建
    │       n 元关系重化为 :Event 节点，通过 PARTICIPATES_IN 连接各参与实体
    │       通过 MENTIONED_IN 关联到 Article
    │
    ├──► Embedding 生成 ────────► 384 维向量（Sentence-Transformers）
    │       embedding_text = "{label}: {name} - {description}"
    │
    └──► Neo4j 写入 ────────────► MERGE 去重写入节点、二元关系、Event 节点
```

### 实现细节

**EntityExtractor**（`ingestion/entity_extractor.py`）：
- 使用 `response_format={"type": "json_object"}` 强制 LLM 输出合法 JSON
- 支持两种输出格式：顶层数组和 `{"entities": [...]}` 包裹格式
- 自动过滤掉 label 不在 `ENTITY_LABELS` 中的条目

**RelationExtractor**（`ingestion/relation_extractor.py`）：
- 将提取到的实体列表传给 LLM，让 LLM 在这些实体之间建立关系
- 关系类型必须属于 `RELATION_TYPES`，不匹配的自动丢弃
- Prompt 同时要求输出两种格式：`{"binary": [...], "hyper": [...]}`
  - `binary`: 标准二元关系（source_name, relation, target_name, evidence）
  - `hyper`: n 元关系（relation_type, participants 数组, evidence）
- 每条关系附带 `evidence` 字段记录原文证据
- 解析器兼容旧格式（纯数组），支持渐进迁移

**Pipeline**（`ingestion/pipeline.py`）：
- 每个文档自动创建一个 Article 节点
- 所有提取的实体通过 `MENTIONED_IN` 关系关联到 Article，该关系带 `pmid` 属性
- 二元 `Relation` 和 n 元 `HyperRelation` 对象自动注入 `pmid=doc_id`
- HyperRelation 通过 `merge_hyper_relation` 写入：创建 Event 节点 → 关联参与者 → 关联来源 Article
- 支持 `dry_run=True` 模式：打印提取结果但不写入 Neo4j
- 文本超过 `CHUNK_SIZE` 时自动分块，每块独立提取后合并

---

## 6. 检索管道（Retrieval Pipeline）

### 数据流

```
用户问题（如 "What drugs target BRCA1?"）
    │
    ├── (PMID 检测) ──► 若问题含 PMID 则查 get_relations_by_source(pmid)
    │
    ▼
① 实体链接（LLM）
    │   问题 → 识别生物医学实体 → [{"name":"BRCA1","type":"Gene"}]
    │
    ▼
② 向量搜索（Sentence-Transformers + Neo4j vector index）
    │   问题 → 384-dim 嵌入 → 各 Label 索引 → 合并按 score 排序
    │
    ▼
③ 合并去重
    │   实体链接结果 + 向量搜索结果 → 待扩展实体名集合
    │
    ▼
④ 图扩展（两路并行）
    │   4a. expand_with_relations ─── 二元边遍历（带 pmid 和 evidence）
    │   4b. expand_entity_events ───── Event 节点展开（参与者 + 来源 Article）
    │
    ▼
⑤ 上下文序列化
    │   三部分拼接：文献特定结果 + 邻域三元组 + Event 块
    │   每部分带标注标题，供 LLM 区分信息来源
    │
    ▼
⑥ 传递给 AnswerGenerator
```

### 实现细节

**实体链接**（`graph_searcher._link_entities`）：
- 温度设为 0.0 以保证确定性输出
- `max_tokens=500` 足够返回少量实体
- 只返回 label 属于 `ENTITY_LABELS` 的实体

**向量搜索**（`graph_client.search_vector`）：
- 对每种 Label 逐一查询对应的向量索引
- 结果合并后按 score 降序排列，取 top_k
- 低于 `min_score` 的结果被过滤

**图扩展**（`graph_client.expand_with_relations`）：
- 使用 `MATCH path = (s)-[r*1..N]-(t)` 变长路径遍历
- 使用 Neo4j Python Driver 的 `path.nodes` 和 `path.relationships` 解析路径
- **注意**：`len(path)` 返回的是关系数而非元素数，不能直接用下标顺序迭代
- 三元组格式现在包含 `{{pmid: "..."}}` 标注来源文献

**Event 展开**（`graph_client.expand_entity_events`）：
- 查询与实体相邻的所有 `:Event` 节点
- 对每个 Event，返回其 `type`、`pmid`、`metadata`、参与者列表、来源 Article
- 输出格式：
  ```
  [Event] TREATS {pmid: "pmid-45678901", evidence: "..."}
    participant: [Drug] Imatinib
    participant: [Disease] CML
    participant: [Gene] BCR-ABL
    source: [Article] pmid-45678901 (pmid: pmid-45678901)
  ```

**按文献查询**（`graph_client.get_relations_by_source`）：
- 当问题中检测到 PMID 时（如 "pmid-45678901"），直接查询 `r.pmid = $pmid`
- 同时返回该文献产生的二元关系和 Event 节点信息
- 结果与常规图展开合并后一起传给 LLM

---

## 7. 生成管道（Generation Pipeline)

```
检索上下文（三元组文本）
    +
用户问题
    │
    ▼
构造 Prompt ──► LLM ──► Answer(answer, context, model)
```

### Prompt 模板

```
System: You are a biomedical knowledge assistant.
        Base your answer **only** on the provided context.
        Cite supporting triples at the end.

User:
Context:
[Gene] BRCA1 -[:TARGETS]-> [Drug] Olaparib
[Drug] Olaparib -[:INDICATED_FOR]-> [Disease] Breast Cancer
...

Question: What drugs target BRCA1?
```

### Answer 数据结构

```python
@dataclass
class Answer:
    question: str      # 原始问题
    answer: str        # LLM 生成的答案文本
    context: str       # 传入的检索上下文（供追溯）
    model: str         # 使用的模型名
```

---

## 8. Web 界面

### 技术选型

- **后端**：FastAPI（异步、自动生成 OpenAPI 文档）
- **前端**：纯 HTML/CSS/JS，无框架依赖
- **部署**：Uvicorn 单进程

### API 端点

| 方法 | 路径 | 说明 |
|---|---|---|
| GET | `/` | 返回聊天页面 |
| POST | `/api/query` | 提交问题，返回答案 |
| GET | `/api/health` | 健康检查（含 Neo4j 连通性） |

### 前端特性

- 暗色主题设计
- 聊天式交互，保留历史
- 加载状态动画（三点跳动指示器）
- 自动显示从问题中检测到的实体
- 可折叠展开的上下文三元组（Show supporting triples）
- 标题栏绿点/红点实时显示 Neo4j 连接状态
- 错误友好提示

### 启动方式

```bash
python scripts/serve.py
# 默认 http://0.0.0.0:8080
# 首次加载需等待 ~10s（Sentence-Transformers 模型下载/加载）
```

---

## 9. 目录结构与文件职责

```
Study-GraphRAG/
│
├── pyproject.toml              # 包配置与依赖声明
├── .env.example                # 环境变量模板（复制为 .env 使用）
├── docker-compose.yml          # Neo4j + APOC 插件容器
├── README.md                   # 快速入门
│
├── docs/                       # 设计文档（英文）
│
├── data/
│   ├── sample_articles.jsonl   # 3 篇生物医学摘要样本
│   └── demo_articles.jsonl     # 含 n 元关系场景的测试数据（Imatinib/CML/BCR-ABL）
│
├── src/study_graphrag/
│   ├── __init__.py             # 版本号
│   ├── config.py               # 环境配置（Settings 类）
│   │
│   ├── graph/                  # 图存储层
│   │   ├── __init__.py
│   │   ├── models.py           # Entity/Relation/HyperRelation 数据类 + Cypher 模板
│   │   └── client.py           # Neo4j 客户端（CRUD、向量搜索、路径遍历）
│   │
│   ├── ingestion/              # 导入层
│   │   ├── __init__.py
│   │   ├── entity_extractor.py # LLM 实体提取
│   │   ├── relation_extractor.py # LLM 关系提取
│   │   └── pipeline.py         # 编排管道（分块→提取→Embedding→写入）
│   │
│   ├── retrieval/              # 检索层
│   │   ├── __init__.py
│   │   ├── embedder.py         # Sentence-Transformers 嵌入
│   │   └── graph_searcher.py   # 混合检索（实体链接+向量+图展开+Event展开）
│   │
│   ├── generation/             # 生成层
│   │   ├── __init__.py
│   │   └── answer_generator.py # LLM 答案组装
│   │
│   └── web/                    # Web 界面
│       ├── __init__.py
│       ├── app.py              # FastAPI 应用
│       └── static/
│           └── index.html      # 聊天页面
│
├── scripts/                    # CLI 入口
│   ├── ingest.py               # python scripts/ingest.py --input <file>
│   ├── query.py                # python scripts/query.py --question "..."
│   └── serve.py                # python scripts/serve.py
│
└── tests/                      # 单元测试占位
```

---

## 10. 重要数据格式详解

本文档贯穿整个管道的核心数据格式，详细说明每个阶段的输入输出结构。理解这些格式有助于调试、扩展和定制功能。

### 10.1 输入文件格式（JSONL）

导入管道接受 **JSONL**（JSON Lines）格式，每行一个独立的 JSON 对象，行末换行符分隔。

```jsonl
{"id": "pmid-12345678", "title": "BRCA1 and PARP inhibitors in breast cancer therapy", "abstract": "BRCA1 is a tumor suppressor gene..."}
{"id": "pmid-23456789", "title": "TP53 mutations and their role in cancer", "abstract": "TP53 is a crucial tumor suppressor gene..."}
```

**字段说明**：

| 字段 | 类型 | 必填 | 说明 |
|---|---|---|---|
| `id` | string | 是 | 文档唯一标识，用作 Article 节点的 `name` 和 `pmid` |
| `title` | string | 是 | 文章标题，拼接在全文开头供 LLM 提取 |
| `abstract` | string | 是 | 正文内容 |
| `text` | string | 否 | 备选正文字段，当 `abstract` 不存在时使用 |

也支持纯文本文件（`.txt`），整个文件作为一篇文章，文件名用作 `id`。

---

### 10.2 实体提取的 LLM 交互格式

#### 发给 LLM 的 Prompt

```
System: You are a biomedical entity extraction assistant...

User: Extract biomedical entities from the following text:

BRCA1 is a tumor suppressor gene involved in DNA damage repair...
```

System prompt 中通过 `{labels}` 注入允许的实体类型：`Article, Disease, Drug, Gene, Pathway, Protein`。

#### LLM 返回的 JSON 格式

两种格式均被支持：

**格式一：顶层数组**

```json
[
  {"name": "BRCA1", "type": "Gene", "description": "tumor suppressor gene involved in DNA damage repair"},
  {"name": "Olaparib", "type": "Drug", "description": "PARP inhibitor targeting BRCA1-mutated tumors"},
  {"name": "breast cancer", "type": "Disease", "description": "cancer type associated with BRCA1 mutations"}
]
```

**格式二：包裹对象**

```json
{
  "entities": [
    {"name": "BRCA1", "type": "Gene", "description": "..."},
    {"name": "Olaparib", "type": "Drug", "description": "..."}
  ]
}
```

#### Python 数据类（Entity）

```python
@dataclass
class Entity:
    name: str                    # 规范化名称（如 "BRCA1"）
    label: str                   # 标签（"Gene" | "Protein" | "Drug" | "Disease" | "Pathway" | "Article"）
    description: str = ""        # 上下文描述
    embedding: List[float] = None  # 384 维向量，导入阶段生成
    # 可选标识符
    uniprot_id: str | None = None
    drugbank_id: str | None = None
    mondo_id: str | None = None
    kegg_id: str | None = None
    pmid: str | None = None
    chromosome: str | None = None
    function: str | None = None
    mechanism: str | None = None

    @property
    def unique_key(self) -> tuple:
        """去重键：(label, name)"""
        return (self.label, self.name)

    @property
    def embedding_text(self) -> str:
        """用于生成 Embedding 的文本"""
        return f"{self.label}: {self.name} - {self.description}"
```

---

### 10.3 关系提取的 LLM 交互格式

#### 发给 LLM 的 Prompt

现在 Prompt 同时要求 LLM 提取两种关系：

```
System: You are a biomedical relationship extraction assistant...

### 1. Binary (pairwise) relationships
For each ordered pair...
- "source_name"
- "source_type"
- "relation"
- "target_name"
- "target_type"
- "evidence"

### 2. N-ary (multi-participant) relationships
Sometimes a relationship involves MORE THAN TWO entities...
- "relation_type"
- "participants": [{"name": ..., "type": ...}, ...]
- "evidence"

---
Return a JSON object with two keys:
- "binary": [...]
- "hyper": [...]
```

设计原则不变：**先提取实体，再提取关系**，分两次 LLM 调用。

#### LLM 返回的 JSON 格式

```json
{
  "binary": [
    {
      "source_name": "BRCA1",
      "source_type": "Gene",
      "relation": "ASSOCIATED_WITH",
      "target_name": "breast cancer",
      "target_type": "Disease",
      "evidence": "strongly associated with hereditary breast"
    },
    {
      "source_name": "Olaparib",
      "source_type": "Drug",
      "relation": "TARGETS",
      "target_name": "BRCA1",
      "target_type": "Gene",
      "evidence": "Olaparib targets BRCA1-mutated cells"
    }
  ],
  "hyper": [
    {
      "relation_type": "TREATS",
      "participants": [
        {"name": "Imatinib", "type": "Drug"},
        {"name": "CML", "type": "Disease"},
        {"name": "BCR-ABL", "type": "Gene"}
      ],
      "evidence": "effectively treats chronic myeloid leukemia by inhibiting BCR-ABL"
    }
  ]
}
```

也接受旧格式（顶层数组或 `{"relations": [...]}`）作为兼容。`source_name` 和 `target_name` **必须精确匹配**实体列表中已有的 `name`，否则被丢弃。

#### Python 数据类

**Relation（二元关系）：**

```python
@dataclass
class Relation:
    source: Entity       # 源实体（必须是已提取的 Entity 对象）
    target: Entity       # 目标实体
    type: str            # 关系类型
    metadata: str = ""   # 原文证据片段
    pmid: str = ""      # 来源文献 ID（由 Pipeline 注入）

    def to_triple(self) -> str:
        return f"[{self.source.label}] {self.source.name} -[:{self.type}]-> [{self.target.label}] {self.target.name}"
```

**HyperRelation（n 元关系）：**

```python
@dataclass
class HyperRelation:
    relation_type: str          # 关系类型，同 RELATION_TYPES
    participants: List[Entity]  # 所有参与实体（>= 2）
    metadata: str = ""          # 原文证据片段
    pmid: str = ""             # 来源文献 ID（由 Pipeline 注入）

    @property
    def event_id(self) -> str:
        """去重键：{relation_type}::{sorted_participant_names}"""
        names = sorted(p.name for p in self.participants)
        return f"{self.relation_type}::{'::'.join(names)}"
```

---

### 10.4 三元组上下文格式

检索管道输出的上下文是**结构化文本**，含最多三个段落，每段带标题供 LLM 区分来源。

#### 段落一：按文献查询结果（若问题含 PMID）
```
# Relations from pmid-45678901
[Drug] Imatinib -[:TARGETS {pmid: "pmid-45678901", evidence: "inhibiting..."}]-> [Protein] BCR-ABL
[Gene] BCR-ABL -[:ENCODES {pmid: "pmid-45678901"}]-> [Protein] BCR-ABL
[Event] TREATS {pmid: "pmid-45678901", evidence: "..."}
  participant: [Drug] Imatinib
  participant: [Disease] CML
  participant: [Gene] BCR-ABL
  source: [Article] pmid-45678901 (pmid: pmid-45678901)
```

#### 段落二：邻域展开（含 provenance）
```
# Graph neighborhood
[Gene] BRCA1 -[:ASSOCIATED_WITH]-> [Disease] breast cancer
[Gene] BRCA1 -[:TARGETS {pmid: "pmid-12345678"}]-> [Drug] Olaparib
[Drug] Olaparib -[:INDICATED_FOR]-> [Disease] breast cancer
[Drug] Olaparib -[:MENTIONED_IN {pmid: "pmid-12345678"}]-> [Article] pmid-12345678
```

**格式约定**：

| 部分 | 格式 | 示例 |
|---|---|---|
| 源节点 | `[Label] 名称` | `[Gene] BRCA1` |
| 关系 | `-[:TYPE]->` 或 `-[:TYPE {pmid: "...", evidence: "..."}]->` | `-[:TARGETS {pmid: "pmid-12345678"}]->` |
| 目标节点 | `[Label] 名称` | `[Drug] Olaparib` |
| Event | `[Event] TYPE {pmid: "..."}` + 参与者列表 | `[Event] TREATS {pmid: "..."}  participant: [Drug]...` |

#### 段落三：Event 节点块（n 元关系）
```
# Events (n-ary relationships)
[Event] TREATS {pmid: "pmid-45678901"}
  participant: [Drug] Imatinib
  participant: [Disease] CML
  participant: [Gene] BCR-ABL
  source: [Article] pmid-45678901 (pmid: pmid-45678901)
```

这种格式有两个用途：
1. 直接作为 LLM 生成答案的上下文（模型能自然理解）
2. 人类可读，用于调试和追溯证据

上下文中的 `pmid` 标注让 LLM 能够回答诸如 "pmid-45678901 中提到了哪些关系？" 这类溯源问题。

---

### 10.5 向量嵌入格式

每个实体节点在 Neo4j 中存储一个 `embedding` 属性：

```json
{
  "embedding": [0.0123, -0.0456, 0.0789, ..., 0.0034]  // 384 个 float
}
```

**技术细节**：

| 属性 | 值 |
|---|---|
| 维度 | 384 |
| 模型 | `all-MiniLM-L6-v2` |
| 相似度函数 | cosine（余弦） |
| 归一化 | 嵌入前已 L2 归一化 |
| 精度 | float32 |
| 生成时机 | 导入阶段，批量生成 |
| 存储位置 | Neo4j 节点属性 + 向量索引 |

**embedding_text 的构造规则**：

```
Gene: BRCA1 - tumor suppressor gene involved in DNA damage repair
Drug: Olaparib - PARP inhibitor targeting BRCA1-mutated tumors
```

即 `{label}: {name} - {description}`。Question 向量搜索时直接用**原始问题文本**嵌入，不使用此模板。

---

### 10.6 Neo4j 节点与关系的存储格式

#### 节点写入（Cypher MERGE）

```cypher
MERGE (n:Gene {name: "BRCA1"})
SET n += {
  name: "BRCA1",
  description: "tumor suppressor gene involved in DNA damage repair",
  embedding: [0.0123, -0.0456, ...]
}
RETURN n.name
```

`MERGE` 以 `(label, name)` 为唯一键：
- 节点不存在 → 创建
- 节点已存在 → `SET n += $props` 更新属性（不会覆盖已有属性中本批次未提供的字段）

#### 关系写入（Cypher MERGE）

```cypher
MATCH (s:Gene {name: "BRCA1"})
MATCH (t:Drug {name: "Olaparib"})
MERGE (s)-[r:TARGETS]->(t)
SET r.metadata = "Olaparib targets BRCA1-mutated cells",
    r.pmid = "pmid-12345678"
```

关系写入前需要先确保两个端点节点已存在，因此管道中**先批量写入所有实体，再批量写入所有关系**。升级后每条关系额外记录 `pmid` 字段用于溯源。

#### Event 节点写入

n 元关系被重化为 `:Event` 节点，通过三条 Cypher 完成：

```cypher
-- 1. 创建/更新 Event 节点
MERGE (e:Event {id: "TREATS::BCR-ABL::CML::Imatinib"})
SET e.type = "TREATS", e.metadata = "effectively treats...", e.pmid = "pmid-45678901"

-- 2. 关联参与者
MATCH (e:Event {id: "TREATS::BCR-ABL::CML::Imatinib"})
MATCH (n {name: "Imatinib"})
MERGE (n)-[:PARTICIPATES_IN]->(e)

-- 3. 关联来源文献
MATCH (e:Event {id: "TREATS::BCR-ABL::CML::Imatinib"})
MATCH (a:Article {pmid: "pmid-45678901"})
MERGE (e)-[:MENTIONED_IN]->(a)
```

#### 完整节点示例（Neo4j 中的数据结构）

```
(:Gene {
  name: "BRCA1",
  description: "tumor suppressor gene involved in DNA damage repair through homologous recombination",
  chromosome: "17",
  embedding: [0.0123, -0.0456, ..., 0.0034]  // 384 维
})

(:Drug {
  name: "Olaparib",
  description: "PARP inhibitor that exploits synthetic lethality in BRCA1-mutated tumors",
  mechanism: "PARP inhibition",
  embedding: [0.0234, -0.0567, ..., -0.0012]
})

(:Article {
  name: "pmid-12345678",
  description: "BRCA1 and PARP inhibitors in breast cancer therapy",
  pmid: "pmid-12345678",
  embedding: [0.0345, -0.0678, ..., 0.0056]
})
```

---

### 10.7 检索结果的 JSON 格式

`retrieve_structured()` 方法返回的结构化检索结果：

```json
{
  "question": "What drugs target BRCA1?",

  "linked_entities": [
    {"name": "BRCA1", "type": "Gene"}
  ],

  "vector_results": [
    {
      "label": "Gene",
      "name": "BRCA1",
      "description": "tumor suppressor gene...",
      "score": 0.89
    },
    {
      "label": "Drug",
      "name": "Olaparib",
      "description": "PARP inhibitor...",
      "score": 0.45
    }
  ],

  "triples": [
    "[Gene] BRCA1 -[:ASSOCIATED_WITH]-> [Disease] breast cancer",
    "[Gene] BRCA1 -[:TARGETS {pmid: \"pmid-12345678\"}]-> [Drug] Olaparib",
    "[Gene] BRCA1 -[:TARGETS]-> [Drug] Niraparib",
    "[Gene] BRCA1 -[:TARGETS]-> [Drug] Rucaparib"
  ],

  "context": "# Graph neighborhood\n[Gene] BRCA1 -[:ASSOCIATED_WITH]-> [Disease] breast cancer\n[Gene] BRCA1 -[:TARGETS {pmid: \"pmid-12345678\"}]-> [Drug] Olaparib\n..."
}
```

| 字段 | 类型 | 说明 |
|---|---|---|
| `question` | string | 原始问题 |
| `linked_entities` | array | LLM 从问题中识别出的实体 |
| `vector_results` | array | 向量搜索结果（含 score） |
| `triples` | array | 去重后的三元组列表 |
| `context` | string | `triples` 的换行拼接，直接供 LLM 使用 |

---

### 10.8 Web API 请求/响应格式

#### POST /api/query

**请求**：

```json
{"question": "What drugs target BRCA1?"}
```

**成功响应（200）**：

```json
{
  "question": "What drugs target BRCA1?",
  "answer": "Based on the context, the drugs that target BRCA1 are **Olaparib**, **Niraparib**, and **Rucaparib**.\n\nSupporting triples:\n- [Gene] BRCA1 -[:TARGETS]-> [Drug] Olaparib\n- [Gene] BRCA1 -[:TARGETS]-> [Drug] Niraparib\n- [Gene] BRCA1 -[:TARGETS]-> [Drug] Rucaparib",
  "context": "[Gene] BRCA1 -[:ASSOCIATED_WITH]-> [Disease] breast cancer\n[Gene] BRCA1 -[:TARGETS]-> [Drug] Olaparib\n...",
  "linked_entities": [{"name": "BRCA1", "type": "Gene"}],
  "model": "deepseek-chat"
}
```

**错误响应（4xx/5xx）**：

```json
{
  "detail": "Query processing failed: ..."
}
```

#### GET /api/health

**成功响应**：

```json
{
  "status": "ok",
  "neo4j": true,
  "llm_model": "deepseek-chat"
}
```

| 字段 | 类型 | 说明 |
|---|---|---|
| `status` | string | `"ok"` 或 `"degraded"` |
| `neo4j` | bool | Neo4j 是否可达 |
| `llm_model` | string | 当前配置的模型名 |

---

### 10.9 环境变量文件格式（.env）

`.env` 文件是 Key-Value 格式，`#` 开头为注释：

```bash
# Neo4j 连接配置
NEO4J_URI=bolt://localhost:7687
NEO4J_USER=neo4j
NEO4J_PASSWORD=password

# LLM 配置（OpenAI 兼容 API）
# 切换到 OpenAI 只需改这两行：
# LLM_MODEL=gpt-4o-mini
# LLM_BASE_URL=https://api.openai.com/v1
LLM_MODEL=deepseek-chat
LLM_API_KEY=sk-your-real-api-key-here    # 必须替换为真实 Key
LLM_BASE_URL=https://api.deepseek.com
LLM_MAX_TOKENS=4096
LLM_TEMPERATURE=0.1

# 文本嵌入模型
EMBEDDING_MODEL=all-MiniLM-L6-v2

# 检索参数
RETRIEVAL_TOP_K=10
RETRIEVAL_MAX_HOPS=2
RETRIEVAL_MIN_SCORE=0.5

# 导入参数
CHUNK_SIZE=1500
CHUNK_OVERLAP=100
```

加载方式：`config.py` 中的 `Settings` 类通过 `python-dotenv` 的 `load_dotenv()` 自动加载 `.env` 文件，然后通过 `os.getenv(key, default)` 读取，未设置的变量使用代码中的默认值。

---

### 10.10 各阶段数据格式转换全景图

以下用一条具体的数据追踪说明格式如何流转：

```
原始 JSONL 行
  │ {"id":"pmid-12345678", "title":"...", "abstract":"..."}
  ▼
LLM 实体提取输入 → 拼接 "{title}\n\n{abstract}"
  │ "BRCA1 and PARP inhibitors...\n\nBRCA1 is a tumor suppressor..."
  ▼
LLM 实体提取输出 → JSON → Entity 对象列表
  │ [Entity("BRCA1","Gene"), Entity("Olaparib","Drug"), ...]
  ▼
LLM 关系提取输入 → 原文 + 实体列表（JSON 序列化）
  │ Text + [{"name":"BRCA1","type":"Gene"}, ...]
  ▼
LLM 关系提取输出 → JSON → (List[Relation], List[HyperRelation])
  │ binary: [Relation(BRCA1, breast cancer, "ASSOCIATED_WITH"), ...]
  │ hyper:  [HyperRelation("TREATS", [Imatinib, CML, BCR-ABL])]
  ▼
Pipeline 注入 pmid=doc_id → 每个 Relation/HyperRelation 获得来源标记
  ▼
自动附加 Article + MENTIONED_IN 关系（也带 pmid）
  ▼
HyperRelation → Event 节点创建（三条 Cypher）
  │ MERGE Event → MATCH 参与者 → MERGE PARTICIPATES_IN → MERGE MENTIONED_IN
  ▼
Embedding 生成
  │ Entity.embedding_text → Sentence-Transformers → List[float] × 384
  ▼
Neo4j MERGE 写入
  │ (Gene {name:"BRCA1", embedding:[...]})
  │ (Gene)-[:TARGETS {pmid:"pmid-12345678"}]->(Drug {name:"Olaparib"})
  │ (Event {type:"TREATS", pmid:"pmid-45678901"})<-[PARTICIPATES_IN]-(Imatinib)
  ▼
用户查询 → PMID 检测 → 实体链接 + 向量搜索 + 图展开 + Event 展开
  │ → 三段落上下文（文献结果 + 邻域三元组 + Event 块）
  ▼
LLM 答案生成
  │ System + Context(with pmid) + Question → Answer(answer, context, model)
  ▼
JSON 响应 → 浏览器渲染
  │ {"question":"...", "answer":"...", "context":"...", ...}
```

---

## 11. 关键技术细节与注意事项

### 11.1 Neo4j Path 对象的正确迭代方式

**问题**：Neo4j Python Driver 的 `Path` 对象的 `len()` 返回的是**关系数**而非总元素数。直接 `for item in path` 只迭代出关系，不会产生节点。

**错误写法**（早期 bug 的来源）：

```python
# ❌ 错误：len(path) == 关系数，path[i] 只返回关系
for i in range(0, len(path) - 2, 2):
    src = path[i]       # 实际上是关系，不是节点
    rel = path[i + 1]
    tgt = path[i + 2]
```

**正确写法**：

```python
# ✅ 正确：使用 path.nodes 和 path.relationships
nodes = path.nodes      # [src_node, tgt_node, ...]
rels = path.relationships  # [rel1, rel2, ...]
for i in range(len(rels)):
    src = nodes[i]
    rel = rels[i]
    tgt = nodes[i + 1]
```

### 11.2 向量索引的兼容性

Neo4j 5.13+ 支持多标签向量索引语法 `FOR (n:Gene|Drug|...)`，但早期版本不支持。为最大兼容性，改为**每个 Label 创建独立索引**：

```
entity_embedding_Gene, entity_embedding_Drug, entity_embedding_Disease, ...
```

向量搜索时对所有索引逐一查询，结果合并排序。这种方式虽然多几次查询，但兼容性好。

### 11.3 Embedding 生成时机

- 实体和关系的提取是 **LLM 调用**，发生在导入阶段
- Embedding 向量在导入阶段生成，**存入 Neo4j 节点属性**中
- 查询时只对**问题文本**实时嵌入，不需要再处理实体

这意味着导入阶段有两次 LLM 调用（实体 + 关系）+ 一次向量生成，而查询阶段有一次 LLM 调用（实体链接）+ 一次向量生成 + 一次 LLM 调用（答案生成）。

### 11.4 导入的去重机制

- 实体：使用 Cypher `MERGE` 按 `(label, name)` 唯一键去重。同名同类型的实体不会重复创建，`SET n += $props` 会更新已有节点的属性。
- 关系：使用 Cypher `MERGE` 避免重复边。
- 不同文档导入相同实体（如两篇文章都提到 BRCA1），在 Neo4j 中只会有一个节点。

### 11.5 LLM 调用成本估算

以 DeepSeek Chat 为例，处理 3 篇示例摘要（约 500 词/篇）：

| 阶段 | LLM 调用次数 | 输入 tokens（约） | 输出 tokens（约） |
|---|---|---|---|
| 实体提取 | 每 chunk 1 次 | chunk 文本 | 50-100 |
| 关系提取 | 每 chunk 1 次 | chunk 文本 + 实体列表 | 50-150 |
| 实体链接（查询） | 1 次 | 问题文本 | 20-50 |
| 答案生成（查询） | 1 次 | 上下文 + 问题 | 200-500 |

3 篇摘要的总成本约 0.01-0.02 美元（DeepSeek 定价），非常便宜。

### 11.6 SOCKS 代理问题

如果终端设置了 SOCKS 代理（`all_proxy=socks5://...`），`pip install` 和 `httpx`（OpenAI/DeepSeek 客户端底层网络库）可能报错：

```
Missing dependencies for SOCKS support
```

解决方案：`pip install pysocks` 安装 SOCKS 支持，或临时 `unset all_proxy`。

### 11.7 运行方式总结

```bash
# 1. 启动 Neo4j
docker compose up -d

# 2. 激活虚拟环境（重要！不要直接用系统 Python）
source .venv/bin/activate

# 3. 导入数据（基础示例）
python scripts/ingest.py --input data/sample_articles.jsonl

# 4. 导入带 n 元关系场景的测试数据
python scripts/ingest.py --input data/demo_articles.jsonl

# 5. CLI 查询
python scripts/query.py --question "What drugs target BRCA1?"

# 6. Provenance 查询
python scripts/query.py --question "What relations are in pmid-45678901?" --show-context

# 7. Event 查询
python scripts/query.py --question "What events involve Imatinib?" --show-context

# 8. Web 界面
python scripts/serve.py
# 访问 http://localhost:8080
```

### 11.8 开发扩展方向

- **更多数据源**：接入 PubMed API 自动拉取文献
- **NER 模型替代**：用 BioBERT 等专业模型替代 LLM 提取，降低成本
- **全文索引**：对 Article 节点建立全文索引，支持关键词搜索
- **多轮对话**：维护 session 上下文，支持追问
- **可视化**：集成 Neo4j Bloom 或 D3.js 展示知识子图
- **批处理**：多文档并行提取，利用 asyncio 加速导入

> **已实现的功能**（本版本）：
> - ✅ 关系级 provenance 追踪（`r.pmid`）
> - ✅ N 元（Hyper）关系重化为 `:Event` 节点
> - ✅ NL 查询中的 PMID 自动检测与按文献过滤
> - ✅ Event 节点展开检索
