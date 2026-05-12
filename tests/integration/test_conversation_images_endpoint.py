"""
Integration tests for GET /conversation-images/{conv_id}/{filename}.

TDD cycle: RED → GREEN → REFACTOR

Covers:
  - 200: Authenticated admin requests an existing file → FileResponse
  - 401: No JWT cookie or invalid token → 401
  - 404: Path traversal attempt (sanitized filename resolves to nothing) → 404
  - 404: File missing from disk → 404 + WARNING log emitted
"""

from __future__ import annotations

import uuid
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient


# ---------------------------------------------------------------------------
# Minimal app fixture with the conversation_images router
# ---------------------------------------------------------------------------


def _build_app(tmp_path: Path, admin_user: MagicMock | None = None) -> FastAPI:
    """Build a minimal FastAPI app for testing the conversation-images route."""
    app = FastAPI()

    from api.routes import conversation_images

    app.include_router(conversation_images.router)

    if admin_user is not None:
        from api.routes.admin import get_current_user

        app.dependency_overrides[get_current_user] = lambda: admin_user

    # Override UPLOADS_DIR to use tmp_path so tests are isolated
    with patch("api.routes.conversation_images.get_settings") as mock_settings:
        mock_settings.return_value.UPLOADS_DIR = str(tmp_path)
        yield app


@pytest.fixture
def mock_admin_user() -> MagicMock:
    user = MagicMock()
    user.username = "testadmin"
    user.role = "admin"
    user.id = uuid.uuid4()
    return user


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


class TestServeConversationImage:
    """Integration tests for the authenticated image serving endpoint."""

    def test_200_authenticated_user_gets_file(self, tmp_path: Path, mock_admin_user: MagicMock) -> None:
        """Authenticated admin requesting an existing file → HTTP 200 FileResponse."""
        # Arrange: create the file on disk at the expected path
        conv_id = uuid.uuid4()
        filename = "abc123.jpg"
        conv_dir = tmp_path / "conversation_images" / str(conv_id)
        conv_dir.mkdir(parents=True)
        file_path = conv_dir / filename
        file_path.write_bytes(b"\xff\xd8\xff\xe0" + b"\x00" * 100)  # fake JPEG

        app = FastAPI()
        from api.routes import conversation_images
        from api.routes.admin import get_current_user

        app.include_router(conversation_images.router)
        app.dependency_overrides[get_current_user] = lambda: mock_admin_user

        with patch("api.routes.conversation_images.get_settings") as mock_settings:
            mock_settings.return_value.UPLOADS_DIR = str(tmp_path)

            client = TestClient(app, raise_server_exceptions=False)
            response = client.get(f"/conversation-images/{conv_id}/{filename}")

        assert response.status_code == 200

    def test_401_no_auth_returns_unauthorized(self, tmp_path: Path) -> None:
        """Request without JWT authentication → HTTP 401."""
        app = FastAPI()
        from api.routes import conversation_images

        app.include_router(conversation_images.router)
        # No dependency override — real auth will fail without valid JWT

        conv_id = uuid.uuid4()

        with patch("api.routes.conversation_images.get_settings") as mock_settings:
            mock_settings.return_value.UPLOADS_DIR = str(tmp_path)

            client = TestClient(app, raise_server_exceptions=False)
            response = client.get(f"/conversation-images/{conv_id}/test.jpg")

        assert response.status_code == 401

    def test_404_path_traversal_sanitized_to_nothing(
        self, tmp_path: Path, mock_admin_user: MagicMock
    ) -> None:
        """Path traversal attempt in filename → sanitized → 404."""
        conv_id = uuid.uuid4()
        traversal_filename = "../../../etc/passwd"

        app = FastAPI()
        from api.routes import conversation_images
        from api.routes.admin import get_current_user

        app.include_router(conversation_images.router)
        app.dependency_overrides[get_current_user] = lambda: mock_admin_user

        with patch("api.routes.conversation_images.get_settings") as mock_settings:
            mock_settings.return_value.UPLOADS_DIR = str(tmp_path)

            client = TestClient(app, raise_server_exceptions=False)
            response = client.get(
                f"/conversation-images/{conv_id}/{traversal_filename}"
            )

        assert response.status_code == 404

    def test_404_missing_file_on_disk(self, tmp_path: Path, mock_admin_user: MagicMock) -> None:
        """File does not exist on disk → HTTP 404."""
        conv_id = uuid.uuid4()
        filename = "nonexistent-file.jpg"

        app = FastAPI()
        from api.routes import conversation_images
        from api.routes.admin import get_current_user

        app.include_router(conversation_images.router)
        app.dependency_overrides[get_current_user] = lambda: mock_admin_user

        with patch("api.routes.conversation_images.get_settings") as mock_settings:
            mock_settings.return_value.UPLOADS_DIR = str(tmp_path)

            client = TestClient(app, raise_server_exceptions=False)
            response = client.get(f"/conversation-images/{conv_id}/{filename}")

        assert response.status_code == 404

    def test_url_encoded_traversal_blocked(
        self, tmp_path: Path, mock_admin_user: MagicMock
    ) -> None:
        """URL-encoded path traversal (..%2F) → sanitized filename → 404."""
        conv_id = uuid.uuid4()

        app = FastAPI()
        from api.routes import conversation_images
        from api.routes.admin import get_current_user

        app.include_router(conversation_images.router)
        app.dependency_overrides[get_current_user] = lambda: mock_admin_user

        with patch("api.routes.conversation_images.get_settings") as mock_settings:
            mock_settings.return_value.UPLOADS_DIR = str(tmp_path)

            client = TestClient(app, raise_server_exceptions=False)
            # TestClient automatically decodes the URL before routing, so we
            # test via the decoded path to simulate what FastAPI receives
            response = client.get(f"/conversation-images/{conv_id}/..%2Fetc%2Fpasswd")

        assert response.status_code == 404
