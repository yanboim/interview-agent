from functools import lru_cache
from typing import Any

from langchain.agents import create_agent
from app.config import get_settings
from app.model_gateway import create_chat_model
from app.tools import (
    create_personal_learning_plan,
    get_learning_progress,
    search_interview_knowledge,
    search_public_web,
)


SYSTEM_PROMPT = """你是一名高级软件工程师面试教练，使用中文回答。

你主要帮助用户准备 Java/JVM、Spring、数据库与中间件、分布式系统、
Python 后端、RAG、向量数据库、LangChain/LangGraph、Agent 和系统设计。

要求：
1. 面试知识类问题优先调用 search_interview_knowledge。
2. 使用检索结果时标明资料来源，不编造知识库内容。
3. 知识库无相关资料时可用通用知识回答，但必须明确说明。
4. 答案应包含核心结论、原理说明、实际应用和常见面试追问。
5. 面向有多年 Java 后端经验的工程师，避免不必要的初级解释。
6. 复杂问题先给总体结构，再逐层展开。
7. 用户询问个人训练进度时调用 get_learning_progress；明确要求生成计划时
   调用 create_personal_learning_plan。
8. 只有问题需要最新公开信息且私人知识库不足时才调用 search_public_web。
   不得把私人知识库正文、密码、令牌或个人信息拼入联网查询。
9. 使用联网结果时提供可点击 URL 和抓取时间，并区分私人资料与公开网络来源。
"""


@lru_cache
def get_single_interview_agent() -> Any:
    """Create the agent lazily so the health endpoint needs no API key."""
    settings = get_settings()
    if not settings.zhipu_api_key:
        raise RuntimeError("未配置 ZHIPU_API_KEY，请先在 .env 中填写智谱 API Key。")

    model = create_chat_model(
        "single_agent",
        temperature=0.7,
        streaming=True,
        settings=settings,
    )
    tools = [
        search_interview_knowledge,
        get_learning_progress,
        create_personal_learning_plan,
    ]
    if settings.web_search_enabled:
        tools.append(search_public_web)
    return create_agent(
        name="interview_coach",
        model=model,
        tools=tools,
        system_prompt=SYSTEM_PROMPT,
    )


@lru_cache
def get_interview_agent() -> Any:
    settings = get_settings()
    if settings.multi_agent_enabled:
        from app.multi_agent import get_supervisor_agent

        return get_supervisor_agent()
    return get_single_interview_agent()
