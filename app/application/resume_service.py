"""简历应用服务：协调私有文件、持久状态与异步分析任务的生命周期。"""

import hashlib
import json
from collections.abc import Callable
from typing import Any, BinaryIO, Protocol
from uuid import uuid4

from app.config import Settings
from app.resume_engine import (
    ResumeAnalysisResult,
    ResumeDraft,
    analyze_resume,
    deserialize_json,
    find_fact_warnings,
    parse_resume,
    render_docx,
    serialize_analysis,
)
from app.user_files import LocalUserFileStore


class ResumeRepository(Protocol):
    def get_user_profile(self, **kwargs: Any) -> Any: ...
    def create_resume_with_analysis(self, **kwargs: Any) -> Any: ...
    def create_resume_analysis(self, **kwargs: Any) -> Any: ...
    def list_resumes(self, **kwargs: Any) -> Any: ...
    def get_resume(self, **kwargs: Any) -> Any: ...
    def get_resume_analysis(self, **kwargs: Any) -> Any: ...
    def claim_resume_analysis(self, **kwargs: Any) -> Any: ...
    def complete_resume_analysis(self, **kwargs: Any) -> Any: ...
    def fail_resume_analysis(self, **kwargs: Any) -> Any: ...
    def update_resume_draft(self, **kwargs: Any) -> Any: ...
    def delete_resume(self, **kwargs: Any) -> Any: ...


class ResumeServiceError(RuntimeError):
    """简历服务应用层基类错误。"""


class ResumeNotFound(ResumeServiceError):
    pass


class ResumeConflict(ResumeServiceError):
    pass


class ResumeUnavailable(ResumeServiceError):
    pass


class ResumeService:
    """简历评估应用服务：协调私有文件、持久状态与后台分析任务的生命周期。

    上传的简历是用户敏感文件，使用服务端生成的存储键持久化，绝不进入
    管理员知识库或 Qdrant。分析在后台任务中用 claim_token 所有者封闭执行，
    重试通过幂等键安全重放；可编辑草稿用乐观版本（revision）保护并发。
    """

    def __init__(
        self,
        repository: ResumeRepository,
        files: LocalUserFileStore,
        settings: Settings,
        *,
        enqueue: Callable[..., str],
        analyzer: Callable[..., ResumeAnalysisResult] = analyze_resume,
    ) -> None:
        """注入持久化仓库、文件存储、配置与异步分析回调。

        参数:
            repository: 持久化适配器（``ConversationStore`` 或替身）。
            files: 本地用户文件存储，负责简历文件的持久化与清理。
            settings: 应用配置（文件大小上限、提示词版本等）。
            enqueue: 后台任务入队回调（返回 job id）。
            analyzer: 实际执行模型分析的回调，默认为纯函数实现。
        """
        self.repository = repository
        self.files = files
        self.settings = settings
        self.enqueue = enqueue
        self.analyzer = analyzer

    def create(
        self,
        *,
        user_id: str,
        original_filename: str,
        source: BinaryIO,
        job_description: str,
        idempotency_key: str,
    ) -> dict[str, object]:
        """上传一份简历并创建对应评估任务（幂等）。

        先持久化用户文件得到存储键与摘要，再以 ``(sha256, JD, 岗位, 经验)``
        摘要幂等创建评估记录：重放相同输入直接返回已有记录；同一幂等键换
        不同输入则报冲突并删除已存文件。随后入队后台分析。

        参数:
            user_id: 服务端解析的当前用户 ID。
            original_filename: 原始文件名（仅展示用）。
            source: 简历二进制流。
            job_description: 目标 JD；为空时回退到用户档案中的 JD。
            idempotency_key: 客户端幂等键。

        返回:
            该简历的最新文档视图（含评估状态）。

        异常:
            ResumeConflict: 幂等键复用于不同简历，或既有记录缺少分析任务。
            ResumeUnavailable: 分析队列暂不可用（可重试）。
        """
        resume_id = str(uuid4())
        analysis_id = str(uuid4())
        stored = self.files.save(
            user_id=user_id,
            asset_id=resume_id,
            original_filename=original_filename,
            source=source,
        )
        profile = self.repository.get_user_profile(user_id=user_id) or {}
        selected_job = (
            job_description.strip()
            or str(profile.get("job_description") or "").strip()
        )
        target_role = str(profile.get("target_role") or "").strip()
        experience_level = str(
            profile.get("experience_level") or ""
        ).strip()
        request_digest = self._request_digest(
            stored.sha256,
            selected_job,
            target_role,
            experience_level,
        )
        result = self.repository.create_resume_with_analysis(
            user_id=user_id,
            resume_id=resume_id,
            analysis_id=analysis_id,
            original_filename=self._display_filename(original_filename),
            content_type=stored.content_type,
            size_bytes=stored.size_bytes,
            sha256=stored.sha256,
            storage_key=stored.storage_key,
            idempotency_key=idempotency_key,
            request_digest=request_digest,
            job_description=selected_job,
            target_role=target_role,
            experience_level=experience_level,
            prompt_version=self.settings.resume_prompt_version,
        )
        outcome = str(result["outcome"])
        if outcome == "key_reused":
            self.files.delete(stored.storage_key)
            raise ResumeConflict("同一 Idempotency-Key 不能用于不同简历")
        if outcome == "existing":
            self.files.delete(stored.storage_key)
            existing_analysis = result.get("analysis")
            if not isinstance(existing_analysis, dict):
                raise ResumeConflict("简历上传记录缺少分析任务")
            analysis_id = str(existing_analysis["analysis_id"])
            resume_id = str(existing_analysis["resume_id"])
            if existing_analysis.get("status") in {"pending", "failed"}:
                self._enqueue_analysis(analysis_id, idempotency_key)
        else:
            self._enqueue_analysis(analysis_id, idempotency_key)
        return self.get(user_id=user_id, resume_id=resume_id)

    def create_analysis(
        self,
        *,
        user_id: str,
        resume_id: str,
        job_description: str,
        idempotency_key: str,
    ) -> dict[str, object]:
        """为已存在的简历创建新的评估任务（幂等）。

        与 ``create`` 类似，但基于既有简历文件，复用其 sha256 计算请求摘要，
        用于「换 JD 重新评估」的场景。

        返回:
            该简历的最新文档视图（含评估状态）。

        异常:
            ResumeNotFound: 简历不存在。
            ResumeConflict: 幂等键复用于不同评估，或评估记录损坏。
            ResumeUnavailable: 分析队列暂不可用（可重试）。
        """
        document = self.repository.get_resume(
            user_id=user_id,
            resume_id=resume_id,
        )
        if not document:
            raise ResumeNotFound("简历不存在")
        profile = self.repository.get_user_profile(user_id=user_id) or {}
        selected_job = (
            job_description.strip()
            or str(profile.get("job_description") or "").strip()
        )
        target_role = str(profile.get("target_role") or "").strip()
        experience_level = str(
            profile.get("experience_level") or ""
        ).strip()
        request_digest = self._request_digest(
            str(document["sha256"]),
            selected_job,
            target_role,
            experience_level,
        )
        analysis_id = str(uuid4())
        result = self.repository.create_resume_analysis(
            user_id=user_id,
            resume_id=resume_id,
            analysis_id=analysis_id,
            idempotency_key=idempotency_key,
            request_digest=request_digest,
            job_description=selected_job,
            target_role=target_role,
            experience_level=experience_level,
            prompt_version=self.settings.resume_prompt_version,
        )
        outcome = str(result["outcome"])
        if outcome == "not_found":
            raise ResumeNotFound("简历不存在")
        if outcome == "key_reused":
            raise ResumeConflict("同一 Idempotency-Key 不能用于不同评估")
        if outcome == "existing":
            analysis = result.get("analysis")
            if not isinstance(analysis, dict):
                raise ResumeConflict("简历评估记录损坏")
            analysis_id = str(analysis["analysis_id"])
            if analysis.get("status") in {"pending", "failed"}:
                self._enqueue_analysis(analysis_id, idempotency_key)
        else:
            self._enqueue_analysis(analysis_id, idempotency_key)
        return self.get(user_id=user_id, resume_id=resume_id)

    def list(self, *, user_id: str) -> list[dict[str, object]]:
        """列出当前用户的所有简历文档（含评估状态，所有者范围）。"""
        return [
            self._public_document(item)
            for item in self.repository.list_resumes(user_id=user_id)
        ]

    def get(
        self,
        *,
        user_id: str,
        resume_id: str,
    ) -> dict[str, object]:
        """获取单个简历文档视图。

        异常:
            ResumeNotFound: 简历不存在或不属于该用户。
        """
        document = self.repository.get_resume(
            user_id=user_id,
            resume_id=resume_id,
        )
        if not document:
            raise ResumeNotFound("简历不存在")
        return self._public_document(document)

    def update_draft(
        self,
        *,
        user_id: str,
        analysis_id: str,
        expected_revision: int,
        draft_payload: dict[str, object],
    ) -> dict[str, object]:
        """更新事实受控的优化稿草稿（乐观并发保护）。

        先校验评估存在且已完成，再对草稿做事实一致性校验（``find_fact_warnings``），
        最后用 ``expected_revision`` 做条件更新，避免覆盖他方并发修改。

        参数:
            expected_revision: 客户端持有的草稿版本号，用于乐观并发。
            draft_payload: 草稿内容，需符合 ``ResumeDraft`` 结构。

        返回:
            更新后的评估公开视图。

        异常:
            ResumeNotFound: 评估不存在或不属于该用户。
            ResumeConflict: 评估未完成，或草稿已被并发更新（需刷新重试）。
        """
        analysis = self.repository.get_resume_analysis(
            user_id=user_id,
            analysis_id=analysis_id,
        )
        if not analysis:
            raise ResumeNotFound("简历评估不存在")
        if analysis.get("status") != "ready":
            raise ResumeConflict("简历评估尚未完成")
        draft = ResumeDraft.model_validate(draft_payload)
        warnings = find_fact_warnings(
            str(analysis.get("parsed_text") or ""),
            draft,
        )
        updated = self.repository.update_resume_draft(
            user_id=user_id,
            analysis_id=analysis_id,
            expected_revision=expected_revision,
            draft_json=draft.model_dump_json(),
            warnings_json=json.dumps(warnings, ensure_ascii=False),
        )
        if not updated:
            raise ResumeConflict("优化稿已有新版本，请刷新后重试")
        return self._public_analysis(updated)

    def export_docx(
        self,
        *,
        user_id: str,
        analysis_id: str,
    ) -> tuple[bytes, str]:
        """把已完成的优化稿导出为 DOCX 字节流。

        只在草稿无事实警告、无待补充项时允许导出，确保导出内容事实受控。

        返回:
            ``(docx 字节, 文件名)``。

        异常:
            ResumeNotFound: 评估不存在或不属于该用户。
            ResumeConflict: 评估未完成，或仍有事实警告/待补充项未解决。
        """
        analysis = self.repository.get_resume_analysis(
            user_id=user_id,
            analysis_id=analysis_id,
        )
        if not analysis:
            raise ResumeNotFound("简历评估不存在")
        if analysis.get("status") != "ready":
            raise ResumeConflict("简历评估尚未完成")
        warnings = deserialize_json(analysis.get("warnings_json"), [])
        if warnings:
            raise ResumeConflict("请先解决事实警告和待补充项")
        draft = ResumeDraft.model_validate_json(str(analysis["draft_json"]))
        if draft.pending_questions:
            raise ResumeConflict("请先解决待补充项")
        filename = (
            f"{str(analysis.get('original_filename') or 'resume').rsplit('.', 1)[0]}"
            "-optimized.docx"
        )
        return render_docx(draft), filename

    def delete(self, *, user_id: str, resume_id: str) -> bool:
        """删除简历文档及其文件（幂等清理）。

        返回:
            是否删除了记录；删除后亦尝试清理底层文件，失败不报错（幂等）。
        """
        storage_key = self.repository.delete_resume(
            user_id=user_id,
            resume_id=resume_id,
        )
        if storage_key is None:
            return False
        self.files.delete(storage_key)
        return True

    def process_analysis(self, *, analysis_id: str) -> dict[str, object]:
        """后台执行简历评估（claim_token 所有者封闭）。

        先领取任务（仅所有者能完成），再在事务之外执行解析与模型分析，
        最后用 claim_token 条件提交结果；任何异常都把任务标记失败再上抛。

        返回:
            ``{"analysis_id", "outcome"}``，``outcome`` 为
            ``"completed"`` 或 ``"not_claimed"``（已被他方领取）。
        """
        claim_token = str(uuid4())
        claimed = self.repository.claim_resume_analysis(
            analysis_id=analysis_id,
            claim_token=claim_token,
        )
        if not claimed:
            return {"analysis_id": analysis_id, "outcome": "not_claimed"}
        try:
            parsed_text = parse_resume(
                self.files.path(str(claimed["storage_key"])),
                str(claimed["content_type"]),
            )
            result = self.analyzer(
                resume_text=parsed_text,
                job_description=str(claimed.get("job_description") or ""),
                target_role=str(claimed.get("target_role") or ""),
                experience_level=str(
                    claimed.get("experience_level") or ""
                ),
                settings=self.settings,
            )
            serialized = serialize_analysis(
                result,
                source_text=parsed_text,
            )
            completed = self.repository.complete_resume_analysis(
                analysis_id=analysis_id,
                claim_token=claim_token,
                parsed_text=parsed_text,
                model_version=self.settings.zhipu_model,
                schema_version="resume-analysis-v1",
                **serialized,
            )
            if not completed:
                raise ResumeConflict("简历评估完成提交被拒绝")
            return {"analysis_id": analysis_id, "outcome": "completed"}
        except Exception as exc:
            self.repository.fail_resume_analysis(
                analysis_id=analysis_id,
                claim_token=claim_token,
                error=f"{type(exc).__name__}: {exc}",
            )
            raise

    def _enqueue_analysis(
        self,
        analysis_id: str,
        idempotency_key: str,
    ) -> None:
        """把简历评估任务入队，用幂等键保证可安全重放。"""
        try:
            self.enqueue(
                "resume_analysis",
                {"analysis_id": analysis_id},
                idempotency_key=f"resume:{analysis_id}:{idempotency_key}",
                max_attempts=self.settings.job_max_attempts,
            )
        except Exception as exc:
            raise ResumeUnavailable(
                "简历评估队列暂不可用，请使用相同幂等键重试"
            ) from exc

    @staticmethod
    def _request_digest(*parts: str) -> str:
        return hashlib.sha256(
            "\x1f".join(parts).encode("utf-8")
        ).hexdigest()

    @staticmethod
    def _display_filename(value: str) -> str:
        name = value.replace("\\", "/").rsplit("/", 1)[-1].strip()
        return (name or "resume")[:255]

    @staticmethod
    def _public_analysis(item: dict[str, object]) -> dict[str, object]:
        return {
            "analysis_id": item["analysis_id"],
            "resume_id": item["resume_id"],
            "status": item["status"],
            "job_description": item.get("job_description") or "",
            "target_role": item.get("target_role") or "",
            "experience_level": item.get("experience_level") or "",
            "report": deserialize_json(item.get("report_json"), None),
            "draft": deserialize_json(item.get("draft_json"), None),
            "warnings": deserialize_json(item.get("warnings_json"), []),
            "revision": int(item.get("revision") or 1),
            "error": item.get("error"),
            "created_at": item["created_at"],
            "updated_at": item["updated_at"],
        }

    def _public_document(
        self,
        item: dict[str, object],
    ) -> dict[str, object]:
        result = {
            "resume_id": item["resume_id"],
            "original_filename": item["original_filename"],
            "content_type": item["content_type"],
            "size_bytes": int(item["size_bytes"]),
            "status": item["status"],
            "error": item.get("error"),
            "created_at": item["created_at"],
            "updated_at": item["updated_at"],
        }
        if "analyses" in item:
            result["analyses"] = [
                self._public_analysis(dict(analysis))
                for analysis in item["analyses"]  # type: ignore[union-attr]
            ]
        elif item.get("latest_analysis"):
            result["latest_analysis"] = self._public_analysis(
                dict(item["latest_analysis"])  # type: ignore[arg-type]
            )
        else:
            result["latest_analysis"] = None
        return result
