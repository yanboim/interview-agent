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
    user_id: str
    username: str
    role: str


@dataclass(frozen=True)
class TokenPair:
    access_token: str
    refresh_token: str
    expires_in: int
    user: AuthenticatedUser
    recovery_code: str | None = None


class AuthSurfaceError(ValueError):
    """Credentials are valid, but belong to a different login surface."""


def hash_password(password: str, salt: bytes | None = None) -> tuple[str, str]:
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
    actual_hash, _ = hash_password(password, bytes.fromhex(salt_hex))
    return secrets.compare_digest(actual_hash, expected_hash)


def token_digest(token: str) -> str:
    return hashlib.sha256(token.encode("utf-8")).hexdigest()


class AuthService:
    def __init__(
        self,
        engine: Engine,
        *,
        access_token_minutes: int = 60,
        refresh_token_days: int = 30,
    ) -> None:
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
        return self._issue_token_pair(self._authenticate(username, password))

    def login_user(self, username: str, password: str) -> TokenPair:
        user = self._authenticate(username, password)
        if user.role != "user":
            raise AuthSurfaceError("管理员账号请使用独立管理入口")
        return self._issue_token_pair(user)

    def login_admin(self, username: str, password: str) -> TokenPair:
        user = self._authenticate(username, password)
        if user.role != "admin":
            raise AuthSurfaceError("该账号不是管理员")
        return self._issue_token_pair(user)

    def _authenticate(self, username: str, password: str) -> AuthenticatedUser:
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
        user = self._resolve_token(refresh_token, "refresh")
        if not user:
            raise ValueError("刷新令牌无效或已过期")
        self.revoke(refresh_token)
        return self._issue_token_pair(user)

    def resolve_access_token(self, access_token: str) -> AuthenticatedUser | None:
        return self._resolve_token(access_token, "access")

    def revoke(self, token: str) -> None:
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
