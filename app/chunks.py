"""知识分块的稳定标识与离线检索评估计算，保持为无基础设施依赖的纯模块。

该模块只做确定性计算，不依赖任何基础设施（数据库、向量库、HTTP、模型
SDK），其纯函数特性由 ``tests/test_architecture.py`` 强制保证。重算
分块 ID 时，相同 ``(来源, 内容)`` 必须得到相同结果，否则会导致知识
集合重复入库或回填脚本错配。
"""

from uuid import UUID, uuid5

#: 知识分块 UUID 命名空间。固定常量保证同一 ``(source, content)`` 在
#: 不同进程、不同时间计算出相同的稳定 ID，便于幂等重算与回填。
CHUNK_NAMESPACE = UUID("73873de7-6bd4-4ec4-bb25-e6871a6a40f3")


def stable_chunk_id(source: str, content: str) -> str:
    """为知识分块生成确定性、Qdrant 兼容的 UUID。

    用 ``uuid5`` 基于 ``source`` 与去标题上下文的稳定内容计算，使同一
    知识库重复导入时分块 ID 稳定可复用，避免向量库中出现重复点。

    参数:
        source: 分块来源文件路径或标识。
        content: 用于稳定化的分块正文（不含检索上下文前缀）。

    返回:
        形如 UUID 的字符串，可直接作为 Qdrant 点 ID。
    """
    return str(uuid5(CHUNK_NAMESPACE, f"{source}\0{content}"))
