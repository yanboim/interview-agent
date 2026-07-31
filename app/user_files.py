"""用户敏感文件存储：使用服务端生成键、类型/容量校验和所有权隔离。"""

import hashlib
import os
import zipfile
from dataclasses import dataclass
from pathlib import Path
from typing import BinaryIO


class UserFileError(ValueError):
    """A user file failed validation."""


class UserFileTooLarge(UserFileError):
    pass


class UnsupportedUserFile(UserFileError):
    pass


@dataclass(frozen=True)
class StoredUserFile:
    storage_key: str
    content_type: str
    size_bytes: int
    sha256: str


class LocalUserFileStore:
    ALLOWED_CONTENT_TYPES = {
        ".pdf": "application/pdf",
        ".docx": (
            "application/vnd.openxmlformats-officedocument."
            "wordprocessingml.document"
        ),
    }
    AUDIO_CONTENT_TYPES = {
        ".mp3": "audio/mpeg",
        ".m4a": "audio/mp4",
        ".wav": "audio/wav",
        ".webm": "audio/webm",
    }

    def __init__(self, root: Path, *, max_upload_bytes: int) -> None:
        self.root = root.resolve()
        self.max_upload_bytes = max(1, int(max_upload_bytes))

    def save(
        self,
        *,
        user_id: str,
        asset_id: str,
        original_filename: str,
        source: BinaryIO,
    ) -> StoredUserFile:
        return self._save(
            user_id=user_id,
            asset_id=asset_id,
            original_filename=original_filename,
            source=source,
            allowed=self.ALLOWED_CONTENT_TYPES,
            max_upload_bytes=self.max_upload_bytes,
            label="简历",
        )

    def save_audio(
        self,
        *,
        user_id: str,
        asset_id: str,
        original_filename: str,
        source: BinaryIO,
        max_upload_bytes: int,
    ) -> StoredUserFile:
        return self._save(
            user_id=user_id,
            asset_id=asset_id,
            original_filename=original_filename,
            source=source,
            allowed=self.AUDIO_CONTENT_TYPES,
            max_upload_bytes=max_upload_bytes,
            label="音频",
        )

    def _save(
        self,
        *,
        user_id: str,
        asset_id: str,
        original_filename: str,
        source: BinaryIO,
        allowed: dict[str, str],
        max_upload_bytes: int,
        label: str,
    ) -> StoredUserFile:
        extension = Path(original_filename).suffix.casefold()
        content_type = allowed.get(extension)
        if content_type is None:
            if label == "简历":
                raise UnsupportedUserFile("仅支持 PDF 或 DOCX 简历")
            raise UnsupportedUserFile("仅支持 MP3、M4A、WAV 或 WebM 音频")

        owner = hashlib.sha256(user_id.encode("utf-8")).hexdigest()[:32]
        relative = Path(owner) / asset_id / f"source{extension}"
        target = self._resolve(relative)
        target.parent.mkdir(parents=True, exist_ok=True)
        temporary = target.with_suffix(f"{target.suffix}.upload")
        digest = hashlib.sha256()
        total = 0
        try:
            with temporary.open("xb") as destination:
                while True:
                    chunk = source.read(64 * 1024)
                    if not chunk:
                        break
                    total += len(chunk)
                    if total > max_upload_bytes:
                        raise UserFileTooLarge(
                            f"{label}文件不能超过 {max_upload_bytes} 字节"
                        )
                    digest.update(chunk)
                    destination.write(chunk)
                destination.flush()
                os.fsync(destination.fileno())
            if total == 0:
                raise UnsupportedUserFile(f"{label}文件为空")
            self._validate_content(temporary, extension)
            os.replace(temporary, target)
        except Exception:
            temporary.unlink(missing_ok=True)
            if target.parent.exists() and not any(target.parent.iterdir()):
                target.parent.rmdir()
            raise
        return StoredUserFile(
            storage_key=relative.as_posix(),
            content_type=content_type,
            size_bytes=total,
            sha256=digest.hexdigest(),
        )

    def open(self, storage_key: str) -> BinaryIO:
        return self._resolve(Path(storage_key)).open("rb")

    def path(self, storage_key: str) -> Path:
        path = self._resolve(Path(storage_key))
        if not path.is_file():
            raise FileNotFoundError(storage_key)
        return path

    def delete(self, storage_key: str) -> bool:
        target = self._resolve(Path(storage_key))
        if not target.exists():
            return False
        target.unlink()
        parent = target.parent
        if parent != self.root and not any(parent.iterdir()):
            parent.rmdir()
        return True

    def _resolve(self, relative: Path) -> Path:
        if relative.is_absolute() or ".." in relative.parts:
            raise UserFileError("非法文件存储键")
        target = (self.root / relative).resolve()
        if target != self.root and self.root not in target.parents:
            raise UserFileError("文件路径越界")
        return target

    @staticmethod
    def _validate_content(path: Path, extension: str) -> None:
        if extension == ".pdf":
            with path.open("rb") as source:
                if source.read(5) != b"%PDF-":
                    raise UnsupportedUserFile("文件内容不是有效的 PDF")
            return
        if extension in {".mp3", ".m4a", ".wav", ".webm"}:
            with path.open("rb") as source:
                header = source.read(16)
            valid = {
                ".mp3": (
                    header.startswith(b"ID3")
                    or header.startswith((b"\xff\xfb", b"\xff\xf3", b"\xff\xf2"))
                ),
                ".m4a": len(header) >= 12 and header[4:8] == b"ftyp",
                ".wav": (
                    header.startswith(b"RIFF")
                    and len(header) >= 12
                    and header[8:12] == b"WAVE"
                ),
                ".webm": header.startswith(b"\x1a\x45\xdf\xa3"),
            }[extension]
            if not valid:
                raise UnsupportedUserFile(f"文件内容不是有效的 {extension[1:].upper()}")
            return
        try:
            with zipfile.ZipFile(path) as archive:
                names = set(archive.namelist())
                if (
                    "[Content_Types].xml" not in names
                    or "word/document.xml" not in names
                ):
                    raise UnsupportedUserFile("文件内容不是有效的 DOCX")
        except zipfile.BadZipFile as exc:
            raise UnsupportedUserFile("文件内容不是有效的 DOCX") from exc
