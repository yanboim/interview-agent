"""用户档案与提醒偏好的测试。"""

import base64

import pytest
from pydantic import ValidationError

from app.api.schemas import ProfileAvatarRequest


def avatar_url(mime: str, raw: bytes) -> str:
    encoded = base64.b64encode(raw).decode("ascii")
    return f"data:{mime};base64,{encoded}"


@pytest.mark.parametrize(
    ("mime", "raw"),
    [
        ("image/jpeg", b"\xff\xd8\xffavatar"),
        ("image/png", b"\x89PNG\r\n\x1a\navatar"),
        ("image/webp", b"RIFF\x04\x00\x00\x00WEBPavatar"),
    ],
)
def test_profile_avatar_accepts_supported_image_content(mime, raw):
    payload = ProfileAvatarRequest(
        user_id="user-a",
        avatar_data_url=avatar_url(mime, raw),
    )
    assert payload.avatar_data_url == avatar_url(mime, raw)


def test_profile_avatar_rejects_mismatched_or_oversized_content():
    with pytest.raises(ValidationError, match="内容与格式不匹配"):
        ProfileAvatarRequest(
            user_id="user-a",
            avatar_data_url=avatar_url("image/png", b"\xff\xd8\xffavatar"),
        )

    with pytest.raises(ValidationError, match="不能超过 500 KB"):
        ProfileAvatarRequest(
            user_id="user-a",
            avatar_data_url=avatar_url(
                "image/png",
                b"\x89PNG\r\n\x1a\n" + b"x" * 512_001,
            ),
        )


def test_profile_avatar_can_be_removed():
    payload = ProfileAvatarRequest(user_id="user-a", avatar_data_url=None)
    assert payload.avatar_data_url is None
