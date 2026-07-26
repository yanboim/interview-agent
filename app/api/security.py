from fastapi import HTTPException, Request

from app.api.runtime import get_runtime
from app.auth import AuthenticatedUser, TokenPair


def token_pair_response(pair: TokenPair) -> dict[str, object]:
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
    if not get_runtime().settings.auth_required:
        return claimed_user_id.strip()
    current_user: AuthenticatedUser = request.state.current_user
    if claimed_user_id.strip() != current_user.user_id:
        raise HTTPException(status_code=403, detail="不能访问其他用户的数据")
    return current_user.user_id


def require_role(
    request: Request,
    allowed_roles: set[str],
) -> AuthenticatedUser:
    current_user = getattr(request.state, "current_user", None)
    if not current_user:
        raise HTTPException(status_code=401, detail="需要登录")
    if current_user.role not in allowed_roles:
        raise HTTPException(status_code=403, detail="权限不足")
    return current_user
