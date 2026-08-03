"""从服务端会话解析身份和管理员角色，供所有 owner-scoped 路由复用。"""

from fastapi import HTTPException, Request

from app.api.runtime import get_runtime
from app.auth import AuthenticatedUser, TokenPair


def token_pair_response(pair: TokenPair) -> dict[str, object]:
    """把认证令牌对序列化为对外登录响应。

    返回:
        含 ``access_token`` / ``refresh_token`` / ``expires_in`` 与
        用户基本信息的字典；首次注册生成的恢复码（如有）一并返回。
    """
    response: dict[str, object] = {
        "access_token": pair.access_token,
        "refresh_token": pair.refresh_token,
        "token_type": "bearer",
        "expires_in": pair.expires_in,
        "user": {
            "user_id": pair.user.user_id,
            "username": pair.user.username,
            "role": pair.user.role,
        },
    }
    if pair.recovery_code:
        response["recovery_code"] = pair.recovery_code
    return response


def resolve_user_id(request: Request, claimed_user_id: str) -> str:
    """以服务端会话身份为权威，校验并解析当前用户 ID（所有者范围）。

    旧式 API 同时接受客户端传入的 ``user_id``，但客户端 ID 绝不能单独
    作为授权依据：当开启鉴权时，必须与会话中的 ``current_user`` 一致，
    否则视为越权访问。

    异常:
        HTTPException 403: 客户端声称的 user_id 与会话身份不一致。
    """
    if not get_runtime().settings.auth_required:
        return claimed_user_id.strip()
    current_user: AuthenticatedUser = request.state.current_user
    if claimed_user_id.strip() != current_user.user_id:
        raise HTTPException(status_code=403, detail="不能访问其他用户的数据")
    return current_user.user_id


def current_product_user_id(request: Request) -> str:
    """为新式 API（不接受客户端 user_id）解析产品用户所有者。

    新式 API 直接以会话身份为所有者，避免「客户端声称身份」这一不安全模式。

    异常:
        HTTPException 401: 未登录。
        HTTPException 403: 非产品用户（如管理员）不能使用产品功能。
    """
    if not get_runtime().settings.auth_required:
        return "anonymous"
    current_user: AuthenticatedUser | None = getattr(
        request.state,
        "current_user",
        None,
    )
    if not current_user:
        raise HTTPException(status_code=401, detail="需要登录")
    if current_user.role != "user":
        raise HTTPException(status_code=403, detail="仅产品用户可使用该功能")
    return current_user.user_id


def require_role(
    request: Request,
    allowed_roles: set[str],
) -> AuthenticatedUser:
    """校验当前会话用户是否具备指定角色之一（管理员路由复用）。

    参数:
        allowed_roles: 允许的角色集合，如 ``{"admin"}``。

    返回:
        通过校验的当前认证用户。

    异常:
        HTTPException 401: 未登录。
        HTTPException 403: 角色不在允许集合内。
    """
    current_user = getattr(request.state, "current_user", None)
    if not current_user:
        raise HTTPException(status_code=401, detail="需要登录")
    if current_user.role not in allowed_roles:
        raise HTTPException(status_code=403, detail="权限不足")
    return current_user
