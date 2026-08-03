"""配置加载与密钥文件回填、跨字段校验的测试。"""

from app.config import Settings


def test_settings_can_read_secret_from_file(tmp_path):
    secret = tmp_path / "zhipu-key"
    secret.write_text("secret-from-file\n", encoding="utf-8")

    settings = Settings(
        _env_file=None,
        zhipu_api_key_file=str(secret),
    )

    assert settings.zhipu_api_key == "secret-from-file"
