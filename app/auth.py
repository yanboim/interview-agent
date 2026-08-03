"""认证服务：管理密码校验、短期访问令牌与可轮换/撤销的刷新令牌生命周期。"""

import hashlib
import secrets
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from uuid import uuid4

from sqlalchemy import insert, select, update
from sqlalchemy.engine import Engine
from sqlalchemy.exc import IntegrityError

from app.database import auth_tokens, users


@dataclass(frozen=True)
class AuthenticatedUser:
    """认证通过后的用户身份（服务端解析，作为所有者权威来源）。"""

    user_id: str
    username: str
    role: str


@dataclass(frozen=True)
class TokenPair:
    """登录成功后返回的令牌对（访问 + 刷新）。"""

    access_token: str
    refresh_token: str
    expires_in: int
    user: AuthenticatedUser
    recovery_code: str | None = None


class AuthSurfaceError(ValueError):
    """凭据有效但属于不同的登录入口（产品用户 vs 管理员）。"""


def hash_password(password: str, salt: bytes | None = None) -> tuple[str, str]:
    """用 scrypt 对密码加盐哈希，返回 ``(哈希 hex, 盐 hex)``。

    盐省略时随机生成 16 字节；参数固定（n=2^14, r=8, p=1, dklen=32）保证
    计算开销足以抗暴力，且可复现校验。
    """
    password_salt = salt or secrets.token_bytes(16)
    digest = hashlib.scrypt(
        password.encode("utf-8"),
        salt=password_salt,
        n=2**14,
        r=8,
        p=1,
        dklen=32,
    )
    return digest.hex(), password_salt.hex()


def verify_password(password: str, expected_hash: str, salt_hex: str) -> bool:
    """用恒定时间比较校验密码，避免时序侧信道泄露信息。"""
    actual_hash, _ = hash_password(password, bytes.fromhex(salt_hex))
    return secrets.compare_digest(actual_hash, expected_hash)


def token_digest(token: str) -> str:
    """计算令牌的 SHA-256 摘要；库中只存摘要，不存明文令牌。"""
    return hashlib.sha256(token.encode("utf-8")).hexdigest()


class AuthService:
    """认证领域服务：密码、令牌、恢复码的全生命周期。

    所有写操作都在 ``engine.begin()`` 单事务内原子完成；令牌仅以摘要入库，
    明文令牌只返回给客户端一次。产品用户与管理员使用独立登录入口，互不相通。
    """

    def __init__(
        self,
        engine: Engine,
        *,
        access_token_minutes: int = 60,
        refresh_token_days: int = 30,
    ) -> None:
        """注入数据库引擎与令牌有效期配置。"""
        self.engine = engine
        self.access_token_seconds = access_token_minutes * 60
        self.refresh_token_days = refresh_token_days

    def register(
        self,
        username: str,
        password: str,
        *,
        role: str = "user",
    ) -> TokenPair:
        """创建用户并直接签发令牌对，同时生成首次恢复码。

        异常:
            ValueError: 用户名已存在或不支持的角色。
        """
        user = self.create_user(username, password, role=role)
        pair = self._issue_token_pair(user)
        recovery_code = self.generate_recovery_code(user_id=user.user_id)
        return TokenPair(
            access_token=pair.access_token,
            refresh_token=pair.refresh_token,
            expires_in=pair.expires_in,
            user=pair.user,
            recovery_code=recovery_code,
        )

    def create_user(
        self,
        username: str,
        password: str,
        *,
        role: str = "user",
    ) -> AuthenticatedUser:
        """创建用户（用户名小写化存库）。

        异常:
            ValueError: 角色非法或用户名已存在（唯一约束冲突）。
        """
        if role not in {"user", "admin"}:
            raise ValueError("不支持的用户角色")
        now = datetime.now(UTC).isoformat()
        password_hash, password_salt = hash_password(password)
        user = AuthenticatedUser(
            user_id=str(uuid4()),
            username=username.casefold(),
            role=role,
        )
        try:
            with self.engine.begin() as connection:
                connection.execute(
                    insert(users).values(
                        user_id=user.user_id,
                        username=user.username,
                        password_hash=password_hash,
                        password_salt=password_salt,
                        role=user.role,
                        created_at=now,
                        updated_at=now,
                    )
                )
        except IntegrityError as exc:
            raise ValueError("用户名已存在") from exc
        return user

    def login(self, username: str, password: str) -> TokenPair:
        """通用登录（不限角色），校验通过即签发令牌对。"""
        return self._issue_token_pair(self._authenticate(username, password))

    def login_user(self, username: str, password: str) -> TokenPair:
        """产品用户入口：仅允许 role=user 登录，管理员被拒。

        异常:
            AuthSurfaceError: 该账号是管理员，需走管理入口。
        """
        user = self._authenticate(username, password)
        if user.role != "user":
            raise AuthSurfaceError("管理员账号请使用独立管理入口")
        return self._issue_token_pair(user)

    def login_admin(self, username: str, password: str) -> TokenPair:
        """管理员入口：仅允许 role=admin 登录，普通用户被拒。

        异常:
            AuthSurfaceError: 该账号不是管理员。
        """
        user = self._authenticate(username, password)
        if user.role != "admin":
            raise AuthSurfaceError("该账号不是管理员")
        return self._issue_token_pair(user)

    def _authenticate(self, username: str, password: str) -> AuthenticatedUser:
        """校验用户名密码；失败统一报「用户名或密码错误」避免枚举。"""
        with self.engine.connect() as connection:
            row = connection.execute(
                select(users).where(users.c.username == username.casefold())
            ).mappings().first()
        if not row or not verify_password(
            password,
            str(row["password_hash"]),
            str(row["password_salt"]),
        ):
            raise ValueError("用户名或密码错误")
        return AuthenticatedUser(
            user_id=str(row["user_id"]),
            username=str(row["username"]),
            role=str(row["role"]),
        )

    def refresh(self, refresh_token: str) -> TokenPair:
        """用刷新令牌换取新令牌对，并撤销旧刷新令牌（旋转）。

        异常:
            ValueError: 刷新令牌无效或已过期。
        """
        user = self._resolve_token(refresh_token, "refresh")
        if not user:
            raise ValueError("刷新令牌无效或已过期")
        self.revoke(refresh_token)
        return self._issue_token_pair(user)

    def resolve_access_token(self, access_token: str) -> AuthenticatedUser | None:
        """校验访问令牌；有效返回用户身份，否则返回 ``None``。"""
        return self._resolve_token(access_token, "access")

    def revoke(self, token: str) -> None:
        """撤销指定令牌（置 ``revoked_at``），用于登出/改密/重置。"""
        now = datetime.now(UTC).isoformat()
        with self.engine.begin() as connection:
            connection.execute(
                update(auth_tokens)
                .where(
                    auth_tokens.c.token_hash == token_digest(token),
                    auth_tokens.c.revoked_at.is_(None),
                )
                .values(revoked_at=now)
            )

    def change_password(
        self,
        *,
        user_id: str,
        current_password: str,
        new_password: str,
    ) -> None:
        """改密并在同一事务吊销该用户所有现存令牌（强制重新登录）。

        异常:
            ValueError: 当前密码错误。
        """
        with self.engine.begin() as connection:
            row = connection.execute(
                select(
                    users.c.password_hash,
                    users.c.password_salt,
                ).where(users.c.user_id == user_id)
            ).mappings().first()
            if not row or not verify_password(
                current_password,
                str(row["password_hash"]),
                str(row["password_salt"]),
            ):
                raise ValueError("当前密码错误")
            password_hash, password_salt = hash_password(new_password)
            now = datetime.now(UTC).isoformat()
            connection.execute(
                update(users)
                .where(users.c.user_id == user_id)
                .values(
                    password_hash=password_hash,
                    password_salt=password_salt,
                    updated_at=now,
                )
            )
            connection.execute(
                update(auth_tokens)
                .where(
                    auth_tokens.c.user_id == user_id,
                    auth_tokens.c.revoked_at.is_(None),
                )
                .values(revoked_at=now)
            )

    def generate_recovery_code(self, *, user_id: str) -> str:
        """生成并持久化新的恢复码（旧恢复码失效），返回明文仅此一次。

        异常:
            ValueError: 用户不存在。
        """
        recovery_code = "-".join(
            secrets.token_hex(3).upper() for _ in range(4)
        )
        with self.engine.begin() as connection:
            result = connection.execute(
                update(users)
                .where(users.c.user_id == user_id)
                .values(
                    recovery_code_hash=token_digest(recovery_code),
                    updated_at=datetime.now(UTC).isoformat(),
                )
            )
            if not result.rowcount:
                raise ValueError("用户不存在")
        return recovery_code

    def reset_password(
        self,
        *,
        username: str,
        recovery_code: str,
        new_password: str,
    ) -> str:
        """用恢复码重置密码，并在同一事务吊销所有令牌、生成新恢复码。

        返回:
            新的明文恢复码（旧恢复码与所有令牌失效）。

        异常:
            ValueError: 用户名或恢复码无效。
        """
        with self.engine.begin() as connection:
            row = connection.execute(
                select(
                    users.c.user_id,
                    users.c.recovery_code_hash,
                ).where(users.c.username == username.casefold())
            ).mappings().first()
            supplied_digest = token_digest(recovery_code.strip().upper())
            if (
                not row
                or not row["recovery_code_hash"]
                or not secrets.compare_digest(
                    supplied_digest,
                    str(row["recovery_code_hash"]),
                )
            ):
                raise ValueError("用户名或恢复码无效")
            password_hash, password_salt = hash_password(new_password)
            replacement_code = "-".join(
                secrets.token_hex(3).upper() for _ in range(4)
            )
            now = datetime.now(UTC).isoformat()
            connection.execute(
                update(users)
                .where(users.c.user_id == row["user_id"])
                .values(
                    password_hash=password_hash,
                    password_salt=password_salt,
                    recovery_code_hash=token_digest(replacement_code),
                    updated_at=now,
                )
            )
            connection.execute(
                update(auth_tokens)
                .where(
                    auth_tokens.c.user_id == row["user_id"],
                    auth_tokens.c.revoked_at.is_(None),
                )
                .values(revoked_at=now)
            )
        return replacement_code

    def _resolve_token(
        self,
        token: str,
        token_type: str,
    ) -> AuthenticatedUser | None:
        """按摘要查令牌：未撤销且未过期则返回用户身份，否则 ``None``。"""
        now = datetime.now(UTC).isoformat()
        statement = (
            select(users.c.user_id, users.c.username, users.c.role)
            .select_from(
                auth_tokens.join(
                    users,
                    auth_tokens.c.user_id == users.c.user_id,
                )
            )
            .where(
                auth_tokens.c.token_hash == token_digest(token),
                auth_tokens.c.token_type == token_type,
                auth_tokens.c.revoked_at.is_(None),
                auth_tokens.c.expires_at > now,
            )
        )
        with self.engine.connect() as connection:
            row = connection.execute(statement).mappings().first()
        if not row:
            return None
        return AuthenticatedUser(
            user_id=str(row["user_id"]),
            username=str(row["username"]),
            role=str(row["role"]),
        )

    def _issue_token_pair(self, user: AuthenticatedUser) -> TokenPair:
        """签发访问+刷新令牌对（仅摘要入库），明文令牌只返回一次。"""
        now = datetime.now(UTC)
        access_token = secrets.token_urlsafe(32)
        refresh_token = secrets.token_urlsafe(48)
        records = [
            {
                "token_id": str(uuid4()),
                "user_id": user.user_id,
                "token_hash": token_digest(access_token),
                "token_type": "access",
                "expires_at": (
                    now + timedelta(seconds=self.access_token_seconds)
                ).isoformat(),
                "created_at": now.isoformat(),
            },
            {
                "token_id": str(uuid4()),
                "user_id": user.user_id,
                "token_hash": token_digest(refresh_token),
                "token_type": "refresh",
                "expires_at": (
                    now + timedelta(days=self.refresh_token_days)
                ).isoformat(),
                "created_at": now.isoformat(),
            },
        ]
        with self.engine.begin() as connection:
            connection.execute(insert(auth_tokens), records)
        return TokenPair(
            access_token=access_token,
            refresh_token=refresh_token,
            expires_in=self.access_token_seconds,
            user=user,
        )
