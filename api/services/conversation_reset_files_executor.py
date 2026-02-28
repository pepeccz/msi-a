"""File cleanup executor for conversation reset pipeline."""

from __future__ import annotations

import logging
import os
from pathlib import Path

from api.models.conversation_reset import ResetDomainResult
from api.services.conversation_reset_coordinator import ResetExecutionContext
from shared.config import get_settings

logger = logging.getLogger(__name__)


class ConversationResetFilesExecutor:
    """Best-effort local file deletion for case image assets."""

    domain = "files"

    def __init__(self, case_images_dir: Path | None = None) -> None:
        if case_images_dir is None:
            settings = get_settings()
            case_images_dir = Path(settings.CASE_IMAGES_DIR)
        self._base_dir = case_images_dir.resolve()

    async def execute(self, context: ResetExecutionContext) -> ResetDomainResult:
        filenames = context.case_image_filenames or []
        if not filenames:
            return ResetDomainResult(
                domain=self.domain,
                status="skipped",
                details={"reason": "no_case_image_filenames"},
            )

        deleted_files = 0
        missing_files = 0
        unsafe_paths = 0
        failed_files = 0

        for stored_filename in filenames:
            safe_name = os.path.basename(stored_filename)
            if safe_name != stored_filename:
                unsafe_paths += 1
                continue

            target_path = (self._base_dir / safe_name).resolve()
            if not target_path.is_relative_to(self._base_dir):
                unsafe_paths += 1
                continue

            if not target_path.exists():
                missing_files += 1
                continue

            try:
                target_path.unlink()
                deleted_files += 1
            except OSError:
                failed_files += 1

        details = {
            "requested_files": len(filenames),
            "deleted_files": deleted_files,
            "missing_files": missing_files,
            "unsafe_paths": unsafe_paths,
            "failed_files": failed_files,
        }

        if failed_files > 0:
            logger.warning(
                "conversation_reset_files_partial",
                extra={
                    "conversation_id": context.conversation_id,
                    **details,
                },
            )
            return ResetDomainResult(
                domain=self.domain,
                status="partial",
                details=details,
                error="Some files could not be deleted",
            )

        return ResetDomainResult(
            domain=self.domain,
            status="success",
            details=details,
        )
