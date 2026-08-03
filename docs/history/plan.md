# 项目：AI 面试教练 Agent

> 历史说明：本文记录项目早期设计与演进背景，不再作为当前架构规范。
> 当前事实来源依次为自动化测试、`docs/product-specs/feature-contract.json`、
> `ARCHITECTURE.md` 和 `README.md`。

结合你正在学习的 **RAG、Qdrant、LangChain 和 Python 后端**，建议先开发一个：

> 能查询个人面试知识库、连续对话、生成面试答案并追问的 AI 面试教练。

它不是普通聊天机器人。普通聊天机器人通常是“一次输入、一次回答”；Agent 会在执行过程中判断是否需要调用工具，获得工具结果后继续推理，直到完成任务。LangChain 当前推荐使用 `create_agent` 构建这种工具调用循环，底层由 LangGraph 提供状态管理和持久化能力。citeturn974302search0turn974302search7

## 一、第一版功能

先实现一个单 Agent、单知识库工具的 MVP：

1. 用户询问 Java、Python、RAG、Spring Cloud 等面试问题。
2. Agent 判断是否查询知识库。
3. 调用 Qdrant 检索相关内容。
4. 根据检索结果组织答案。
5. 记住当前会话内容。
6. 通过 FastAPI 提供接口。

后续再增加：

- 模拟面试
- 回答评分
- 薄弱知识点分析
- 自动生成学习计划
- 联网搜索
- 多 Agent 协作

## 二、系统架构

```text
                         ┌──────────────────┐
                         │ Web / Postman    │
                         └────────┬─────────┘
                                  │ HTTP
                         ┌────────▼─────────┐
                         │ FastAPI 接口层    │
                         └────────┬─────────┘
                                  │
                         ┌────────▼─────────┐
                         │ Interview Agent  │
                         │                  │
                         │ 计划 / 判断 / 调度│
                         └──────┬─────┬─────┘
                                │     │
                        不检索  │     │ 调用工具
                                │     ▼
                         ┌──────▼───────────┐
                         │ 知识库检索工具     │
                         └──────┬───────────┘
                                │
                         ┌──────▼───────────┐
                         │ Qdrant 向量数据库 │
                         └──────────────────┘
```

Qdrant 的 LangChain 集成支持稠密检索、稀疏检索和混合检索。第一版使用稠密向量检索即可，后续可以升级为 BM25 与向量结合的混合检索。citeturn882165view2

## 三、项目目录

```text
interview-agent/
├── app/
│   ├── __init__.py
│   ├── config.py
│   ├── rag.py
│   ├── tools.py
│   ├── agent.py
│   └── main.py
├── scripts/
│   └── ingest.py
├── knowledge/
│   ├── rag.md
│   ├── java.md
│   └── spring-cloud.md
├── docker-compose.yml
├── requirements.txt
├── .env.example
└── README.md
```

## 四、安装依赖

### `requirements.txt`

```txt
fastapi
uvicorn[standard]

langchain>=1.0
langgraph>=1.0
langchain-openai
langchain-qdrant
langchain-text-splitters

qdrant-client
pydantic-settings
python-dotenv
```

当前 LangChain 的高层 Agent API 是 `create_agent`，可以直接配置模型、工具、系统提示词、记忆和结构化输出。citeturn974302search0turn974302search2

## 五、启动 Qdrant

### `docker-compose.yml`

```yaml
services:
  qdrant:
    image: qdrant/qdrant:latest
    container_name: interview-qdrant
    restart: unless-stopped
    ports:
      - "6333:6333"
      - "6334:6334"
    volumes:
      - qdrant_data:/qdrant/storage

volumes:
  qdrant_data:
```

启动：

```bash
docker compose up -d
```

检查：

```bash
curl http://localhost:6333/collections
```

Qdrant 官方支持通过 `QdrantClient(url="http://localhost:6333")` 连接本地 Docker 服务，也支持不启动服务的内存或本地文件模式。citeturn988264search9turn882165view2

## 六、环境变量

### `.env.example`

```env
OPENAI_API_KEY=替换为你的API_KEY

OPENAI_MODEL=gpt-5.5
OPENAI_EMBEDDING_MODEL=text-embedding-3-small

QDRANT_URL=http://localhost:6333
QDRANT_COLLECTION=interview_knowledge
```

复制一份：

```bash
cp .env.example .env
```

Windows PowerShell：

```powershell
Copy-Item .env.example .env
```

## 七、配置类

### `app/config.py`

```python
from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """应用配置。"""

    openai_api_key: str
    openai_model: str = "gpt-5.5"
    openai_embedding_model: str = "text-embedding-3-small"

    qdrant_url: str = "http://localhost:6333"
    qdrant_collection: str = "interview_knowledge"

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )


@lru_cache
def get_settings() -> Settings:
    """缓存配置，避免重复解析环境变量。"""
    return Settings()
```

## 八、封装 Qdrant

### `app/rag.py`

```python
from functools import lru_cache

from langchain_openai import OpenAIEmbeddings
from langchain_qdrant import QdrantVectorStore

from app.config import get_settings


@lru_cache
def get_embeddings() -> OpenAIEmbeddings:
    """创建 Embedding 模型。"""

    settings = get_settings()

    return OpenAIEmbeddings(
        model=settings.openai_embedding_model,
        api_key=settings.openai_api_key,
    )


@lru_cache
def get_vector_store() -> QdrantVectorStore:
    """连接已经创建的 Qdrant Collection。"""

    settings = get_settings()

    return QdrantVectorStore.from_existing_collection(
        embeddings=get_embeddings(),
        collection_name=settings.qdrant_collection,
        url=settings.qdrant_url,
    )
```

`QdrantVectorStore.from_existing_collection()` 用于连接已经建立的 Collection；初次导入数据时则使用 `from_documents()`。citeturn882165view2

## 九、知识库检索工具

### `app/tools.py`

```python
from langchain.tools import tool

from app.rag import get_vector_store


@tool
def search_interview_knowledge(query: str) -> str:
    """
    查询私人面试知识库。

    当用户询问 Java、Python、Spring、微服务、RAG、向量数据库、
    系统设计、项目经验或面试题时，应优先调用此工具。
    """

    if not query.strip():
        return "查询内容不能为空。"

    try:
        vector_store = get_vector_store()

        documents = vector_store.similarity_search(
            query=query,
            k=4,
        )
    except Exception as exc:
        return f"知识库查询失败：{exc}"

    if not documents:
        return "知识库中没有检索到相关内容。"

    results: list[str] = []

    for index, document in enumerate(documents, start=1):
        source = document.metadata.get("source", "未知来源")
        content = document.page_content.strip()

        results.append(
            f"[资料 {index}]\n"
            f"来源：{source}\n"
            f"内容：{content}"
        )

    return "\n\n".join(results)
```

工具函数最重要的部分是文档字符串：

```python
"""
查询私人面试知识库。
当用户询问……时，应优先调用此工具。
"""
```

因为大模型会根据工具名称、参数和描述判断什么时候调用工具。

## 十、创建 Agent

### `app/agent.py`

```python
from langchain.agents import create_agent
from langgraph.checkpoint.memory import InMemorySaver

from app.config import get_settings
from app.tools import search_interview_knowledge


SYSTEM_PROMPT = """
你是一名高级软件工程师面试教练，主要帮助用户准备：

- Java 与 JVM
- Spring、Spring Boot、Spring Cloud
- MySQL、Redis、Elasticsearch、Kafka
- 分布式系统与微服务
- Python 后端开发
- RAG、向量数据库、Qdrant
- LangChain、LangGraph 和 AI Agent
- 系统设计与项目经验表达

工作要求：

1. 对面试知识类问题，优先调用 search_interview_knowledge。
2. 使用检索结果时，标明资料来源。
3. 不得编造知识库中不存在的内容。
4. 如果知识库没有相关资料，可以使用通用知识回答，但要明确说明。
5. 回答应包含：
   - 核心结论
   - 原理说明
   - 实际应用
   - 常见面试追问
6. 用户是有多年 Java 后端经验的工程师，不要把所有内容讲得过于基础。
7. 对复杂问题先给总体结构，再逐层展开。
8. 回答使用中文。
"""


settings = get_settings()

# 第一版使用内存型 Checkpointer。
# 同一个 thread_id 下的消息可以保持连续上下文。
checkpointer = InMemorySaver()

interview_agent = create_agent(
    name="interview_coach",
    model=f"openai:{settings.openai_model}",
    tools=[
        search_interview_knowledge,
    ],
    system_prompt=SYSTEM_PROMPT,
    checkpointer=checkpointer,
)
```

LangGraph 的 Checkpointer 会按照 `thread_id` 保存每个会话的状态，从而实现短期会话记忆。`InMemorySaver` 只保存在内存里，程序重启后会丢失；生产环境可替换为 SQLite 或 PostgreSQL。citeturn882165view1

## 十一、FastAPI 接口

### `app/main.py`

```python
from typing import Any

from fastapi import FastAPI, HTTPException
from pydantic import BaseModel, Field

from app.agent import interview_agent


app = FastAPI(
    title="AI 面试教练 Agent",
    description="基于 LangChain、LangGraph 和 Qdrant 的面试智能体",
    version="0.1.0",
)


class ChatRequest(BaseModel):
    session_id: str = Field(
        min_length=1,
        max_length=128,
        description="会话 ID，相同 ID 会共享聊天上下文",
    )
    message: str = Field(
        min_length=1,
        max_length=10000,
        description="用户消息",
    )


class ChatResponse(BaseModel):
    session_id: str
    answer: str


def extract_message_text(message: Any) -> str:
    """
    兼容字符串和 Content Blocks 两种消息格式。
    """

    content = message.content

    if isinstance(content, str):
        return content

    if isinstance(content, list):
        texts: list[str] = []

        for block in content:
            if isinstance(block, str):
                texts.append(block)
            elif isinstance(block, dict):
                text = block.get("text")
                if text:
                    texts.append(text)

        return "\n".join(texts)

    return str(content)


@app.get("/health")
async def health() -> dict[str, str]:
    return {"status": "ok"}


@app.post("/api/chat", response_model=ChatResponse)
async def chat(request: ChatRequest) -> ChatResponse:
    try:
        result = await interview_agent.ainvoke(
            {
                "messages": [
                    {
                        "role": "user",
                        "content": request.message,
                    }
                ]
            },
            config={
                "configurable": {
                    "thread_id": request.session_id,
                }
            },
        )

        last_message = result["messages"][-1]
        answer = extract_message_text(last_message)

        return ChatResponse(
            session_id=request.session_id,
            answer=answer,
        )

    except Exception as exc:
        raise HTTPException(
            status_code=500,
            detail=f"Agent 执行失败：{exc}",
        ) from exc
```

## 十二、导入知识库

先在 `knowledge` 目录放入 Markdown 或 TXT 文件，例如：

### `knowledge/rag.md`

```md
# RAG

RAG 是 Retrieval-Augmented Generation，即检索增强生成。

典型流程：

1. 文档加载
2. 文档清洗
3. 文档分块
4. Embedding
5. 写入向量数据库
6. 用户问题向量化
7. 相似度检索
8. 重排
9. 拼接上下文
10. 调用大模型生成答案
```

### `scripts/ingest.py`

```python
from pathlib import Path

from langchain_core.documents import Document
from langchain_qdrant import QdrantVectorStore
from langchain_text_splitters import RecursiveCharacterTextSplitter
from qdrant_client import QdrantClient

from app.config import get_settings
from app.rag import get_embeddings


SUPPORTED_SUFFIXES = {
    ".md",
    ".txt",
}


def load_documents(directory: Path) -> list[Document]:
    """读取知识库目录中的文本文件。"""

    documents: list[Document] = []

    for file_path in directory.rglob("*"):
        if not file_path.is_file():
            continue

        if file_path.suffix.lower() not in SUPPORTED_SUFFIXES:
            continue

        try:
            content = file_path.read_text(encoding="utf-8")
        except UnicodeDecodeError:
            content = file_path.read_text(
                encoding="gb18030",
                errors="ignore",
            )

        if not content.strip():
            continue

        documents.append(
            Document(
                page_content=content,
                metadata={
                    "source": str(file_path),
                    "filename": file_path.name,
                },
            )
        )

    return documents


def main() -> None:
    settings = get_settings()
    knowledge_directory = Path("knowledge")

    documents = load_documents(knowledge_directory)

    if not documents:
        raise RuntimeError(
            "knowledge 目录中没有找到 Markdown 或 TXT 文件。"
        )

    splitter = RecursiveCharacterTextSplitter(
        chunk_size=800,
        chunk_overlap=150,
        separators=[
            "\n# ",
            "\n## ",
            "\n### ",
            "\n\n",
            "\n",
            "。",
            "；",
            "，",
            " ",
        ],
    )

    chunks = splitter.split_documents(documents)

    client = QdrantClient(url=settings.qdrant_url)

    if client.collection_exists(settings.qdrant_collection):
        client.delete_collection(settings.qdrant_collection)

    QdrantVectorStore.from_documents(
        documents=chunks,
        embedding=get_embeddings(),
        url=settings.qdrant_url,
        collection_name=settings.qdrant_collection,
    )

    print("知识库导入完成")
    print(f"原始文档数量：{len(documents)}")
    print(f"分块数量：{len(chunks)}")
    print(f"Collection：{settings.qdrant_collection}")


if __name__ == "__main__":
    main()
```

执行：

```bash
python -m scripts.ingest
```

## 十三、启动服务

创建虚拟环境：

```bash
python -m venv .venv
```

Windows：

```powershell
.venv\Scripts\Activate.ps1
```

Linux：

```bash
source .venv/bin/activate
```

安装依赖：

```bash
pip install -r requirements.txt
```

启动：

```bash
uvicorn app.main:app --reload --port 8000
```

访问接口文档：

```text
http://localhost:8000/docs
```

## 十四、测试 Agent

### 第一次提问

```bash
curl -X POST http://localhost:8000/api/chat \
  -H "Content-Type: application/json" \
  -d '{
    "session_id": "yanbo-interview-001",
    "message": "请解释一下RAG的完整工作流程"
  }'
```

### 连续追问

继续使用同一个 `session_id`：

```bash
curl -X POST http://localhost:8000/api/chat \
  -H "Content-Type: application/json" \
  -d '{
    "session_id": "yanbo-interview-001",
    "message": "刚才提到的分块大小应该怎么选择？"
  }'
```

由于 `thread_id` 相同，Agent 可以获取前面的对话状态。

## 十五、Agent 实际执行流程

用户输入：

```text
请解释 RAG 的完整流程
```

Agent 的内部工作过程可以抽象为：

```text
用户问题
   ↓
模型判断：这是知识类问题
   ↓
调用 search_interview_knowledge
   ↓
Qdrant 返回相关文档
   ↓
工具结果放回 Agent 上下文
   ↓
模型根据问题 + 工具结果生成答案
   ↓
返回用户
```

核心不是“调用了一次大模型”，而是一个循环：

```text
模型 → 工具 → 模型 → 工具 → 模型 → 最终答案
```

LangChain 将 Agent 定义为模型反复调用工具，直到达到停止条件的执行循环。citeturn974302search0turn974302search4

## 十六、第二阶段升级

### 1. 增加模拟面试模式

```text
用户选择：RAG 面试
    ↓
Agent 随机生成题目
    ↓
用户回答
    ↓
Agent 评分
    ↓
指出遗漏
    ↓
继续追问
```

可以返回结构化结果：

```json
{
  "score": 78,
  "advantages": [
    "解释了向量检索流程"
  ],
  "problems": [
    "没有提到重排",
    "没有说明召回率评估"
  ],
  "follow_up_question": "RAG 中为什么需要重排模型？"
}
```

当前 `create_agent` 支持通过 `response_format` 和 Pydantic 模型获得经过验证的结构化输出。citeturn974302search0turn988264search4

### 2. 增加长期记忆

第一版：

```python
InMemorySaver()
```

生产版改为：

```text
PostgreSQL Checkpointer
```

区分两种数据：

| 数据 | 保存位置 |
|---|---|
| 当前会话聊天记录 | Checkpointer |
| 用户薄弱知识点 | PostgreSQL |
| 面试题资料 | Qdrant |
| 用户学习进度 | PostgreSQL |
| 原始知识文件 | MinIO 或本地文件 |

LangGraph 官方把 Checkpointer 定位为线程内短期记忆，把 Store 定位为跨线程的长期记忆。citeturn882165view1

### 3. 增加多个工具

```text
search_interview_knowledge
search_web
generate_interview_question
evaluate_candidate_answer
save_weak_point
query_learning_progress
create_learning_plan
```

### 4. 升级为多 Agent

```text
Supervisor Agent
├── Knowledge Agent：查询知识库
├── Interviewer Agent：负责提问
├── Evaluator Agent：负责评分
└── Planner Agent：生成学习计划
```

不过第一版不要立即做多 Agent。先把以下内容跑通：

```text
单 Agent
+ 单工具
+ Qdrant
+ 会话记忆
+ FastAPI
```

否则很容易出现工具调用混乱、上下文膨胀、成本不可控和问题难定位。

## 十七、面试时可以这样介绍项目

> 我开发了一个面向软件工程师的 AI 面试教练。系统使用 FastAPI 提供服务，LangChain 负责 Agent 工具调用，LangGraph 负责会话状态管理，Qdrant 用于存储和检索面试知识向量。
>
> 用户提出问题后，Agent 会根据问题语义判断是否需要调用知识库检索工具，而不是所有问题都固定执行 RAG。检索工具从 Qdrant 返回相关文档及来源，模型再结合会话上下文生成答案。
>
> 在工程设计上，我将模型、工具、检索、接口和配置进行了分层，同时使用 thread_id 隔离不同用户会话。后续可以将内存型 Checkpointer 替换为 PostgreSQL，实现服务重启后的会话恢复，并增加回答评分、长期记忆、人工审批和可观测性。

这个项目能够覆盖面试中的核心知识点：

- Agent 和普通聊天机器人的区别
- Function Calling
- ReAct 工具调用循环
- RAG
- Embedding
- 向量数据库
- 文档分块
- 会话记忆
- FastAPI
- Docker
- 状态持久化
- 多 Agent 架构设计
