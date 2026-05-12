"""
Unified inbox — conversations admin endpoints (PR4, T11–T20).

Provides 10 endpoints for the unified inbox feature:
  POST /api/admin/conversations/{id}/send-message
  POST /api/admin/conversations/{id}/send-template
  POST /api/admin/conversations/{id}/pause
  POST /api/admin/conversations/{id}/resume
  POST /api/admin/conversations/{id}/escalate
  GET  /api/admin/conversations/{id}/window-status
  GET  /api/admin/conversations/templates
  POST /api/admin/conversations/{id}/mark-read
  GET  /api/admin/inbox
  GET  /api/admin/conversations/{id}/messages

Endpoints that mutate LangGraph state (pause, resume, send-message) require
app.state.compiled_graph to be set at startup. If unavailable → 503.
Endpoints that only read/write DB (window-status, mark-read, inbox, messages,
templates) do not require the graph.

Design refs: D9 (endpoint contracts), D6 (24h window), D7 (templates cache).
"""

from __future__ import annotations

import logging
from datetime import UTC, datetime, timedelta
from typing import Any
from uuid import UUID

import structlog
from fastapi import APIRouter, Depends, File, Form, HTTPException, Query, Request, UploadFile
from fastapi.responses import JSONResponse
from sqlalchemy import and_, case, func, literal, select, update
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from api.models.conversation_inbox import (
    ConversationHistoryResponse,
    ConversationMessageResponse,
    CreateNoteRequest,
    EscalateRequest,
    EscalationResponse,
    InboxItemResponse,
    InboxListResponse,
    InboxStatsResponse,
    MarkReadRequest,
    MarkReadResponse,
    MessageAttachmentResponse,
    MessagesPageResponse,
    NoteResponse,
    PauseRequest,
    ResumeRequest,
    SendMessageRequest,
    SendTemplateRequest,
    SidebarResponse,
    TemplateResponse,
    UploadAttachmentsResponse,
    WindowStatusResponse,
)
from api.services.conversation_action_service import (
    BotNotPausedError,
    ConversationActionService,
    OutsideWindow24hError,
)
from api.services.conversation_image_service import get_conversation_image_service
from api.services.inbox_sidebar_service import (
    create_note as _svc_create_note,
    delete_note as _svc_delete_note,
    get_sidebar_data as _svc_get_sidebar_data,
)
from database.connection import get_async_session
from database.models import (
    AdminUser,
    ConversationHistory,
    ConversationMessage,
    Escalation,
    MessageAttachment,
    User,
)
from shared.chatwoot_client import ChatwootClient
from shared.config import get_settings
from shared.redis_client import get_redis_client

# ---------------------------------------------------------------------------
# Auth dependency — defined here so tests can override it via dependency_overrides
# without depending on api.routes.admin being importable in all test envs.
# ---------------------------------------------------------------------------


async def get_current_user(
    request: Request,
    credentials: Any = None,
) -> AdminUser:
    """Auth dependency that delegates to admin.get_current_user at call-time.

    Defined here (not imported from admin) so integration tests can override
    THIS function via app.dependency_overrides[get_current_user] without
    worrying about the admin module stub installed by other test files.
    """
    from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer  # noqa: PLC0415

    try:
        from api.routes.admin import get_current_user as _admin_auth  # noqa: PLC0415
    except (ImportError, AttributeError) as exc:
        raise HTTPException(status_code=503, detail="Auth service unavailable") from exc

    _security = HTTPBearer(auto_error=False)
    _creds: HTTPAuthorizationCredentials | None = await _security(request)
    return await _admin_auth(request=request, credentials=_creds)

logger = logging.getLogger(__name__)
_log = structlog.get_logger(__name__)

router = APIRouter(prefix="/api/admin")


def _truncate_preview(content: str) -> str:
    """Truncate message content to 80 chars for inbox preview."""
    return (content[:77] + "...") if len(content) > 80 else content


# ---------------------------------------------------------------------------
# Dependency: get compiled graph (raises 503 if unavailable)
# ---------------------------------------------------------------------------


def _get_graph(request: Request) -> Any:
    """Return the compiled LangGraph graph from app state.

    Raises 503 if not initialized — informs the client that pause/resume/
    send-message functionality is temporarily disabled.
    """
    graph = getattr(request.app.state, "compiled_graph", None)
    if graph is None:
        raise HTTPException(
            status_code=503,
            detail="Conversation graph not available — bot pause/resume disabled",
        )
    return graph


# ---------------------------------------------------------------------------
# Helper: load ConversationHistory or 404
# ---------------------------------------------------------------------------


async def _load_conversation(
    session: AsyncSession,
    conversation_history_id: UUID,
) -> ConversationHistory:
    result = await session.execute(
        select(ConversationHistory)
        .where(ConversationHistory.id == conversation_history_id)
        .options(selectinload(ConversationHistory.paused_by_user))
    )
    conv = result.scalar_one_or_none()
    if conv is None:
        raise HTTPException(status_code=404, detail="Conversation not found")
    return conv


# ---------------------------------------------------------------------------
# Helper: build ConversationHistoryResponse from ORM object
# ---------------------------------------------------------------------------


def _conv_to_response(conv: ConversationHistory) -> ConversationHistoryResponse:
    return ConversationHistoryResponse(
        id=conv.id,
        conversation_id=conv.conversation_id,
        bot_paused_at=conv.bot_paused_at,
        bot_resumed_at=conv.bot_resumed_at,
        bot_paused_by_user_id=conv.bot_paused_by_user_id,
        bot_pause_reason=conv.bot_pause_reason,
        last_inbound_at=conv.last_inbound_at,
        last_message_at=conv.last_message_at,
    )


# ---------------------------------------------------------------------------
# Helper: build ConversationMessageResponse from ORM object
# ---------------------------------------------------------------------------


def _msg_to_response(
    msg: ConversationMessage,
    author_user_name: str | None = None,
) -> ConversationMessageResponse:
    # Build sorted attachment list (relies on relationship order_by position ASC)
    raw_attachments: list[MessageAttachment] = getattr(msg, "attachments", []) or []
    attachment_responses = [
        MessageAttachmentResponse(
            id=att.id,
            url=att.url,
            kind=att.kind,
            content_type=att.content_type,
            filename=att.filename,
            size_bytes=att.size_bytes,
            width=att.width,
            height=att.height,
            position=att.position,
            created_at=att.created_at,
        )
        for att in sorted(raw_attachments, key=lambda a: a.position)
    ]
    return ConversationMessageResponse(
        id=msg.id,
        conversation_history_id=msg.conversation_history_id,
        role=msg.role,
        author_type=msg.author_type,
        author_user_id=msg.author_user_id,
        author_user_name=author_user_name,
        content=msg.content,
        created_at=msg.created_at,
        is_read=msg.is_read,
        has_images=msg.has_images,
        image_count=msg.image_count,
        chatwoot_message_id=msg.chatwoot_message_id,
        delivery_failed=getattr(msg, "delivery_failed", False),
        attachments=attachment_responses,
    )


# ---------------------------------------------------------------------------
# T11 — POST /api/admin/conversations/{id}/send-message
# ---------------------------------------------------------------------------


@router.post("/conversations/{conversation_history_id}/send-message")
async def send_message(
    request: Request,
    conversation_history_id: UUID,
    body: SendMessageRequest,
    current_user: AdminUser = Depends(get_current_user),
) -> JSONResponse:
    """Send a free-text message from the human agent.

    Validates 24h WhatsApp window. Auto-pauses bot if active (auto_pause_if_bot_on=True).
    Returns 207 if Chatwoot delivery failed but DB was persisted.
    Returns 503 if compiled graph is unavailable.
    """
    graph = _get_graph(request)

    async with get_async_session() as session:
        chatwoot = ChatwootClient()
        redis = get_redis_client()
        svc = ConversationActionService(
            session=session,
            chatwoot_client=chatwoot,
            redis_client=redis,
            graph=graph,
        )

        try:
            msg = await svc.send_human_message(
                conversation_history_id=conversation_history_id,
                content=body.content,
                author_user_id=current_user.id,
                auto_pause_if_bot_on=True,
            )
        except OutsideWindow24hError as exc:
            _log.warning(
                "send_message_outside_window",
                conversation_history_id=str(conversation_history_id),
            )
            raise HTTPException(
                status_code=422,
                detail="La ventana de 24h ha expirado. Use una plantilla para reabrir la conversación.",
            ) from exc

        response_data = _msg_to_response(msg).model_dump(mode="json")
        status_code = 207 if getattr(msg, "delivery_failed", False) else 200

        _log.info(
            "send_message_ok",
            conversation_history_id=str(conversation_history_id),
            delivery_failed=getattr(msg, "delivery_failed", False),
        )
        return JSONResponse(status_code=status_code, content=response_data)


# ---------------------------------------------------------------------------
# T12 — POST /api/admin/conversations/{id}/send-template
# ---------------------------------------------------------------------------


@router.post("/conversations/{conversation_history_id}/send-template")
async def send_template(
    request: Request,
    conversation_history_id: UUID,
    body: SendTemplateRequest,
    current_user: AdminUser = Depends(get_current_user),
) -> JSONResponse:
    """Send a Meta WhatsApp template message.

    No 24h window restriction. Returns 207 if Chatwoot delivery failed.
    Requires compiled graph for ConversationActionService.
    """
    graph = _get_graph(request)

    async with get_async_session() as session:
        chatwoot = ChatwootClient()
        redis = get_redis_client()
        svc = ConversationActionService(
            session=session,
            chatwoot_client=chatwoot,
            redis_client=redis,
            graph=graph,
        )

        msg = await svc.send_template_message(
            conversation_history_id=conversation_history_id,
            template_name=body.template_name,
            language=body.language,
            params=body.params,
            author_user_id=current_user.id,
        )

    response_data = _msg_to_response(msg).model_dump(mode="json")
    status_code = 207 if getattr(msg, "delivery_failed", False) else 200

    _log.info(
        "send_template_ok",
        conversation_history_id=str(conversation_history_id),
        template_name=body.template_name,
        delivery_failed=getattr(msg, "delivery_failed", False),
    )
    return JSONResponse(status_code=status_code, content=response_data)


# ---------------------------------------------------------------------------
# T13 — POST /api/admin/conversations/{id}/pause
# ---------------------------------------------------------------------------


@router.post("/conversations/{conversation_history_id}/pause")
async def pause_bot(
    request: Request,
    conversation_history_id: UUID,
    body: PauseRequest,
    current_user: AdminUser = Depends(get_current_user),
) -> ConversationHistoryResponse:
    """Pause the bot for a specific conversation.

    Snapshots LangGraph state to Postgres. Idempotent: if already paused,
    only updates the reason. Requires compiled graph.
    """
    graph = _get_graph(request)

    async with get_async_session() as session:
        chatwoot = ChatwootClient()
        redis = get_redis_client()
        svc = ConversationActionService(
            session=session,
            chatwoot_client=chatwoot,
            redis_client=redis,
            graph=graph,
        )

        conv = await svc.pause_bot(
            conversation_history_id=conversation_history_id,
            paused_by_user_id=current_user.id,
            reason=body.reason,
        )

    _log.info(
        "pause_bot_endpoint_ok",
        conversation_history_id=str(conversation_history_id),
        paused_by=str(current_user.id),
    )
    return _conv_to_response(conv)


# ---------------------------------------------------------------------------
# T14 — POST /api/admin/conversations/{id}/resume
# ---------------------------------------------------------------------------


@router.post("/conversations/{conversation_history_id}/resume")
async def resume_bot(
    request: Request,
    conversation_history_id: UUID,
    body: ResumeRequest,
    current_user: AdminUser = Depends(get_current_user),
) -> ConversationHistoryResponse:
    """Resume the bot for a specific conversation.

    Restores LangGraph state from snapshot, injects interval human messages.
    Returns 409 if conversation is not paused. Requires compiled graph.
    """
    graph = _get_graph(request)

    async with get_async_session() as session:
        chatwoot = ChatwootClient()
        redis = get_redis_client()
        svc = ConversationActionService(
            session=session,
            chatwoot_client=chatwoot,
            redis_client=redis,
            graph=graph,
        )

        try:
            conv = await svc.resume_bot(
                conversation_history_id=conversation_history_id,
                resumed_by_user_id=current_user.id,
            )
        except BotNotPausedError as exc:
            raise HTTPException(
                status_code=409,
                detail="El bot no está pausado en esta conversación.",
            ) from exc

    _log.info(
        "resume_bot_endpoint_ok",
        conversation_history_id=str(conversation_history_id),
        resumed_by=str(current_user.id),
    )
    return _conv_to_response(conv)


# ---------------------------------------------------------------------------
# T15 — POST /api/admin/conversations/{id}/escalate
# ---------------------------------------------------------------------------


@router.post("/conversations/{conversation_history_id}/escalate")
async def escalate_conversation(
    request: Request,
    conversation_history_id: UUID,
    body: EscalateRequest,
    current_user: AdminUser = Depends(get_current_user),
) -> EscalationResponse:
    """Escalate a conversation to human agents.

    Creates an Escalation record and pauses the bot atomically.
    PR4 note: does NOT touch escalation_service.py (PR6 cleanup).
    Uses ConversationActionService.pause_bot directly.
    """
    graph = _get_graph(request)

    import uuid as _uuid_module

    escalation_id = _uuid_module.uuid4()

    async with get_async_session() as session:
        # Load conversation to get chatwoot_conversation_id
        conv = await _load_conversation(session, conversation_history_id)

        # Create Escalation record with pre-generated ID
        escalation = Escalation(
            id=escalation_id,
            conversation_id=conv.conversation_id,
            user_id=conv.user.id if conv.user else None,
            reason=body.reason,
            source="admin_panel",
            status="pending",
            metadata_={"priority": body.priority} if body.priority else {},
        )
        session.add(escalation)

        # Pause bot with escalation reason (inside same session for atomicity)
        chatwoot = ChatwootClient()
        redis = get_redis_client()
        svc = ConversationActionService(
            session=session,
            chatwoot_client=chatwoot,
            redis_client=redis,
            graph=graph,
        )
        await svc.pause_bot(
            conversation_history_id=conversation_history_id,
            paused_by_user_id=current_user.id,
            reason=f"Escalación: {body.reason}",
        )

        await session.commit()

    _log.info(
        "escalate_endpoint_ok",
        conversation_history_id=str(conversation_history_id),
        escalation_id=str(escalation_id),
        escalated_by=str(current_user.id),
    )
    return EscalationResponse(
        id=escalation_id,
        escalation_id=escalation_id,
        conversation_id=conv.conversation_id,
        reason=body.reason,
        status="pending",
        source="admin_panel",
        triggered_at=datetime.now(UTC),
        priority=body.priority,
    )


# ---------------------------------------------------------------------------
# T16 — GET /api/admin/conversations/{id}/window-status
# ---------------------------------------------------------------------------


@router.get("/conversations/{conversation_history_id}/window-status")
async def get_window_status(
    conversation_history_id: UUID,
    current_user: AdminUser = Depends(get_current_user),
) -> WindowStatusResponse:
    """Return the 24h WhatsApp window status for a conversation.

    Does NOT require the compiled graph — pure DB read.
    """
    async with get_async_session() as session:
        conv = await _load_conversation(session, conversation_history_id)

    if conv.last_inbound_at is None:
        return WindowStatusResponse(
            within_24h=False,
            last_inbound_at=None,
            expires_at=None,
            seconds_remaining=None,
        )

    expires_at = conv.last_inbound_at + timedelta(hours=24)
    now = datetime.now(UTC)
    within = now < expires_at
    seconds_remaining = max(0, int((expires_at - now).total_seconds())) if within else 0

    return WindowStatusResponse(
        within_24h=within,
        last_inbound_at=conv.last_inbound_at,
        expires_at=expires_at,
        seconds_remaining=seconds_remaining,
    )


# ---------------------------------------------------------------------------
# T17 — GET /api/admin/conversations/templates
# ---------------------------------------------------------------------------


@router.get("/conversations/templates")
async def list_templates(
    current_user: AdminUser = Depends(get_current_user),
) -> list[TemplateResponse]:
    """List approved WhatsApp templates from Chatwoot.

    Cache handled inside ChatwootClient.list_whatsapp_templates (Redis TTL 1h).
    Does NOT require the compiled graph.
    """
    settings = get_settings()
    chatwoot = ChatwootClient()
    # Inject redis so ChatwootClient can use it for template caching (checks hasattr)
    chatwoot._redis = get_redis_client()

    raw_templates = await chatwoot.list_whatsapp_templates(
        inbox_id=int(settings.CHATWOOT_INBOX_ID),
    )

    return [
        TemplateResponse(
            name=t.get("name", ""),
            language=t.get("language", ""),
            status=t.get("status", ""),
            category=t.get("category", ""),
            components=t.get("components", []),
        )
        for t in raw_templates
    ]


# ---------------------------------------------------------------------------
# T18 — POST /api/admin/conversations/{id}/mark-read
# ---------------------------------------------------------------------------


@router.post("/conversations/{conversation_history_id}/mark-read")
async def mark_read(
    conversation_history_id: UUID,
    body: MarkReadRequest,
    current_user: AdminUser = Depends(get_current_user),
) -> MarkReadResponse:
    """Mark messages as read.

    If body.message_ids is None, marks ALL unread messages in the conversation.
    If body.message_ids is provided, marks only those specific messages.
    Does NOT require the compiled graph.
    """
    async with get_async_session() as session:
        # Verify conversation exists
        await _load_conversation(session, conversation_history_id)

        if body.message_ids is None:
            # Mark all unread messages in conversation
            stmt = (
                update(ConversationMessage)
                .where(
                    ConversationMessage.conversation_history_id == conversation_history_id,
                    ConversationMessage.is_read.is_(False),
                )
                .values(is_read=True)
                .returning(ConversationMessage.id)
            )
        else:
            # Mark only the specified message IDs
            stmt = (
                update(ConversationMessage)
                .where(
                    ConversationMessage.conversation_history_id == conversation_history_id,
                    ConversationMessage.id.in_(body.message_ids),
                    ConversationMessage.is_read.is_(False),
                )
                .values(is_read=True)
                .returning(ConversationMessage.id)
            )

        result = await session.execute(stmt)
        marked_ids = result.fetchall()
        await session.commit()

    _log.info(
        "mark_read_ok",
        conversation_history_id=str(conversation_history_id),
        marked_count=len(marked_ids),
    )
    return MarkReadResponse(marked_count=len(marked_ids))


# ---------------------------------------------------------------------------
# T19 — GET /api/admin/inbox
# ---------------------------------------------------------------------------

_VALID_SORT_VALUES = frozenset(
    {"last_message_at_desc", "last_message_at_asc", "started_at_desc", "unread_first"}
)


def _apply_sort(stmt: Any, sort: str) -> Any:
    """Apply ORDER BY clause to inbox query based on sort param."""
    if sort == "last_message_at_asc":
        return stmt.order_by(ConversationHistory.last_message_at.asc().nulls_last())
    if sort == "started_at_desc":
        return stmt.order_by(ConversationHistory.started_at.desc())
    if sort == "unread_first":
        # Uses existing partial index ix_conversation_messages_unread
        has_unread = (
            select(literal(1))
            .where(
                and_(
                    ConversationMessage.conversation_history_id == ConversationHistory.id,
                    ConversationMessage.is_read.is_(False),
                )
            )
            .correlate(ConversationHistory)
            .exists()
        )
        return stmt.order_by(
            has_unread.desc(),
            ConversationHistory.last_message_at.desc().nulls_last(),
        )
    # default: last_message_at_desc
    return stmt.order_by(ConversationHistory.last_message_at.desc().nulls_last())


async def _compute_escalation_stats(session: AsyncSession) -> InboxStatsResponse:
    """Compute daily escalation counts for the inbox stats header."""
    today_start = datetime.now(UTC).replace(hour=0, minute=0, second=0, microsecond=0)

    result = await session.execute(
        select(
            func.count(case((Escalation.status == "pending", 1))).label("pending"),
            func.count(case((Escalation.status == "in_progress", 1))).label("in_progress"),
            func.count(
                case(
                    (
                        and_(
                            Escalation.status == "resolved",
                            Escalation.resolved_at >= today_start,
                        ),
                        1,
                    )
                )
            ).label("resolved_today"),
            func.count(
                case((Escalation.triggered_at >= today_start, 1))
            ).label("total_today"),
        ).select_from(Escalation)
    )
    row = result.one()
    return InboxStatsResponse(
        pending=row.pending,
        in_progress=row.in_progress,
        resolved_today=row.resolved_today,
        total_today=row.total_today,
    )


@router.get("/inbox")
async def get_inbox(
    tab: str | None = Query(None, description="Filter tab: todas|bot_on|bot_off|escaladas|no_leidas|mias"),
    search: str | None = Query(None, max_length=200),
    sort: str | None = Query(None, description="Sort: last_message_at_desc|last_message_at_asc|started_at_desc|unread_first"),
    page: int = Query(1, ge=1),
    page_size: int = Query(50, ge=1, le=100),
    current_user: AdminUser = Depends(get_current_user),
) -> InboxListResponse:
    """List conversations for the unified inbox.

    Supports tab-based filtering, full-text search, and pagination.
    Does NOT require the compiled graph.

    Tab filters:
    - todas (default): all conversations
    - bot_on: bot_paused_at IS NULL
    - bot_off: bot_paused_at IS NOT NULL
    - escaladas: has pending/in_progress Escalation
    - no_leidas: has unread ConversationMessage
    - mias: bot_paused_by_user_id = current_user.id

    Sort options (sort param):
    - last_message_at_desc (default): most recent first
    - last_message_at_asc: oldest first
    - started_at_desc: newest conversation started first
    - unread_first: unread conversations first, then by last_message_at desc
    Invalid values fall back to default silently.
    """
    effective_sort = sort if sort in _VALID_SORT_VALUES else "last_message_at_desc"

    async with get_async_session() as session:
        # Base query: join User for name/phone, compute unread_count as subquery
        # Using explicit joins to avoid N+1 (Design T19 optimization note)
        stmt = (
            select(ConversationHistory)
            .options(
                selectinload(ConversationHistory.paused_by_user),
                selectinload(ConversationHistory.user),
            )
        )

        # Apply sort before filters so count_stmt subquery is correct
        stmt = _apply_sort(stmt, effective_sort)

        # Tab filters
        if tab == "bot_on":
            stmt = stmt.where(ConversationHistory.bot_paused_at.is_(None))
        elif tab == "bot_off":
            stmt = stmt.where(ConversationHistory.bot_paused_at.isnot(None))
        elif tab == "escaladas":
            escalated_conv_ids = (
                select(Escalation.conversation_id)
                .where(Escalation.status.in_(["pending", "in_progress"]))
                .scalar_subquery()
            )
            stmt = stmt.where(ConversationHistory.conversation_id.in_(escalated_conv_ids))
        elif tab == "no_leidas":
            unread_conv_ids = (
                select(ConversationMessage.conversation_history_id)
                .where(ConversationMessage.is_read.is_(False))
                .distinct()
                .scalar_subquery()
            )
            stmt = stmt.where(ConversationHistory.id.in_(unread_conv_ids))
        elif tab == "mias":
            stmt = stmt.where(
                ConversationHistory.bot_paused_by_user_id == current_user.id
            )

        # Search: user name/phone, Chatwoot conversation_id, message content
        if search:
            search_term = f"%{search}%"
            # Subquery: conversations that have at least one matching message
            msg_match_subq = (
                select(ConversationMessage.conversation_history_id)
                .where(ConversationMessage.content.ilike(search_term))
                .distinct()
                .scalar_subquery()
            )
            stmt = stmt.join(
                User,
                ConversationHistory.user_id == User.id,
                isouter=True,
            ).where(
                User.first_name.ilike(search_term)
                | User.last_name.ilike(search_term)
                | User.phone.ilike(search_term)
                | ConversationHistory.conversation_id.ilike(search_term)
                | ConversationHistory.id.in_(msg_match_subq)
            )

        # Count total
        count_stmt = select(func.count()).select_from(stmt.subquery())
        total_result = await session.execute(count_stmt)
        total = total_result.scalar() or 0

        # Paginate
        offset = (page - 1) * page_size
        stmt = stmt.offset(offset).limit(page_size)

        result = await session.execute(stmt)
        conversations = result.scalars().all()

        # Build unread count map for fetched conversations
        conv_ids = [c.id for c in conversations]
        unread_map: dict[UUID, int] = {}
        if conv_ids:
            unread_result = await session.execute(
                select(
                    ConversationMessage.conversation_history_id,
                    func.count(ConversationMessage.id).label("unread_count"),
                )
                .where(
                    ConversationMessage.conversation_history_id.in_(conv_ids),
                    ConversationMessage.is_read.is_(False),
                )
                .group_by(ConversationMessage.conversation_history_id)
            )
            for row in unread_result.all():
                unread_map[row[0]] = row[1]

        # Build escalation map: conversation_id → {status, source, id}
        escalation_map: dict[str, dict] = {}
        if conv_ids:
            conv_conversation_ids = [c.conversation_id for c in conversations]
            esc_result = await session.execute(
                select(
                    Escalation.conversation_id,
                    Escalation.status,
                    Escalation.source,
                    Escalation.id,
                )
                .where(
                    Escalation.conversation_id.in_(conv_conversation_ids),
                    Escalation.status.in_(["pending", "in_progress"]),
                )
            )
            for row in esc_result.all():
                escalation_map[row[0]] = {
                    "status": row[1],
                    "source": row[2],
                    "id": row[3],
                }

        # Fetch last message content per conversation (for last_message_preview)
        preview_map: dict[UUID, str | None] = {}
        if conv_ids:
            # Subquery: latest message per conversation_history_id
            latest_msg_subq = (
                select(
                    ConversationMessage.conversation_history_id,
                    ConversationMessage.content,
                    ConversationMessage.has_images,
                    func.row_number()
                    .over(
                        partition_by=ConversationMessage.conversation_history_id,
                        order_by=ConversationMessage.created_at.desc(),
                    )
                    .label("rn"),
                )
                .where(ConversationMessage.conversation_history_id.in_(conv_ids))
                .subquery()
            )
            preview_result = await session.execute(
                select(
                    latest_msg_subq.c.conversation_history_id,
                    latest_msg_subq.c.content,
                    latest_msg_subq.c.has_images,
                ).where(latest_msg_subq.c.rn == 1)
            )
            for row in preview_result.all():
                conv_hist_id, content, has_images = row[0], row[1], row[2]
                if content:
                    preview_map[conv_hist_id] = _truncate_preview(content)
                elif has_images:
                    preview_map[conv_hist_id] = "[imagen]"
                else:
                    preview_map[conv_hist_id] = None

        # Compute daily escalation stats
        stats = await _compute_escalation_stats(session)

    # Build inbox items
    items: list[InboxItemResponse] = []
    for conv in conversations:
        user = conv.user
        first_name = getattr(user, "first_name", None) if user else None
        last_name = getattr(user, "last_name", None) if user else None
        user_name = " ".join(filter(None, [first_name, last_name])) or None

        # Determine bot_status
        if conv.bot_paused_at is not None:
            bot_status = "paused"
        else:
            bot_status = "active"

        esc_data = escalation_map.get(conv.conversation_id)
        esc_status = esc_data["status"] if esc_data else "none"
        esc_source = esc_data["source"] if esc_data else None
        esc_id = esc_data["id"] if esc_data else None

        paused_by_name = None
        if conv.bot_paused_at and conv.paused_by_user:
            paused_by_name = getattr(conv.paused_by_user, "display_name", None)

        items.append(
            InboxItemResponse(
                conversation_history_id=conv.id,
                user_name=user_name,
                user_phone=getattr(user, "phone", None) if user else None,
                last_message_preview=preview_map.get(conv.id),
                last_message_at=conv.last_message_at,
                bot_status=bot_status,
                unread_count=unread_map.get(conv.id, 0),
                escalation_status=esc_status,
                escalation_source=esc_source,
                escalation_id=esc_id,
                paused_by_user_name=paused_by_name,
            )
        )

    return InboxListResponse(
        items=items,
        total=total,
        page=page,
        page_size=page_size,
        stats=stats,
    )


# ---------------------------------------------------------------------------
# T20 — GET /api/admin/conversations/{id}/messages
# ---------------------------------------------------------------------------


@router.get("/conversations/{conversation_history_id}/thread")
async def get_messages(
    conversation_history_id: UUID,
    cursor: UUID | None = Query(None, description="Cursor for next-page pagination (message ID)"),
    limit: int = Query(50, ge=1, le=200),
    current_user: AdminUser = Depends(get_current_user),
) -> MessagesPageResponse:
    """Retrieve messages for a conversation using cursor-based pagination.

    Cursor pagination: WHERE created_at < cursor_msg.created_at
    ORDER BY created_at DESC LIMIT limit+1
    (limit+1 trick to detect if there is a next page)

    Does NOT require the compiled graph.
    """
    async with get_async_session() as session:
        # Verify conversation exists
        await _load_conversation(session, conversation_history_id)

        stmt = (
            select(ConversationMessage)
            .where(ConversationMessage.conversation_history_id == conversation_history_id)
            .options(selectinload(ConversationMessage.attachments))
            .order_by(ConversationMessage.created_at.desc())
        )

        if cursor is not None:
            # Get the cursor message's created_at
            cursor_result = await session.execute(
                select(ConversationMessage.created_at).where(ConversationMessage.id == cursor)
            )
            cursor_row = cursor_result.scalar_one_or_none()
            if cursor_row is not None:
                stmt = stmt.where(ConversationMessage.created_at < cursor_row)

        stmt = stmt.limit(limit + 1)
        result = await session.execute(stmt)
        rows = result.scalars().all()

    has_next = len(rows) > limit
    messages = rows[:limit]

    next_cursor: UUID | None = None
    if has_next and messages:
        next_cursor = messages[-1].id

    _log.info(
        "get_messages_ok",
        conversation_history_id=str(conversation_history_id),
        count=len(messages),
        has_next=has_next,
    )
    return MessagesPageResponse(
        messages=[_msg_to_response(m) for m in messages],
        next_cursor=next_cursor,
    )


# ---------------------------------------------------------------------------
# T12 — POST /api/admin/conversations/{id}/attachments
# ---------------------------------------------------------------------------

# ---------------------------------------------------------------------------
# Sidebar — GET /api/admin/conversations/{conv_id}/sidebar
# ---------------------------------------------------------------------------


_SIDEBAR_ALLOWED_ROLES = frozenset({"admin", "agente_humano", "solo_lectura", "solo_lectura_global"})
_NOTES_ALLOWED_ROLES = frozenset({"admin", "agente_humano"})


@router.get(
    "/conversations/{conversation_history_id}/sidebar",
    summary="Aggregated right-sidebar data for a conversation",
)
async def get_conversation_sidebar(
    conversation_history_id: UUID,
    current_user: AdminUser = Depends(get_current_user),
) -> SidebarResponse:
    """Return combined sidebar payload: client summary, active case, and notes.

    Allowed roles: admin, agente_humano, solo_lectura, solo_lectura_global.
    Total DB queries ≤ 5 (see inbox_sidebar_service.py for budget breakdown).
    """
    if current_user.role not in _SIDEBAR_ALLOWED_ROLES:
        raise HTTPException(status_code=403, detail="Insufficient permissions for sidebar")

    async with get_async_session() as session:
        result = await _svc_get_sidebar_data(
            session=session,
            conv_id=conversation_history_id,
            current_user=current_user,
        )

    _log.info(
        "sidebar_endpoint_ok",
        conversation_history_id=str(conversation_history_id),
        user_id=str(current_user.id),
    )
    return result


# ---------------------------------------------------------------------------
# Notes — POST /api/admin/conversations/{conv_id}/notes
# ---------------------------------------------------------------------------


@router.post(
    "/conversations/{conversation_history_id}/notes",
    status_code=201,
    summary="Create an internal note on a conversation",
)
async def create_conversation_note(
    conversation_history_id: UUID,
    body: CreateNoteRequest,
    current_user: AdminUser = Depends(get_current_user),
) -> NoteResponse:
    """Create an internal admin note linked to a conversation.

    Allowed roles: admin, agente_humano.
    Content must be 1–2000 characters (validated by Pydantic schema).
    Returns 201 with the created NoteResponse (can_delete=True for the author).
    """
    if current_user.role not in _NOTES_ALLOWED_ROLES:
        raise HTTPException(status_code=403, detail="Insufficient permissions to create notes")

    async with get_async_session() as session:
        note = await _svc_create_note(
            session=session,
            conv_id=conversation_history_id,
            content=body.content,
            author=current_user,
        )
        await session.commit()

    _log.info(
        "create_note_endpoint_ok",
        conversation_history_id=str(conversation_history_id),
        note_id=str(note.id),
        author_id=str(current_user.id),
    )
    return note


# ---------------------------------------------------------------------------
# Notes — DELETE /api/admin/conversations/notes/{note_id}
# ---------------------------------------------------------------------------


@router.delete(
    "/conversations/notes/{note_id}",
    status_code=204,
    summary="Delete an internal conversation note",
)
async def delete_conversation_note(
    note_id: UUID,
    current_user: AdminUser = Depends(get_current_user),
) -> None:
    """Hard-delete a conversation note.

    Allowed roles: admin, agente_humano.
    Authorship check is enforced at the service layer:
    - Author (any role) may delete their own note.
    - admin role may delete any note.
    - agente_humano who is NOT the author → 403.
    Returns 204 on success.
    """
    if current_user.role not in _NOTES_ALLOWED_ROLES:
        raise HTTPException(status_code=403, detail="Insufficient permissions to delete notes")

    async with get_async_session() as session:
        await _svc_delete_note(
            session=session,
            note_id=note_id,
            current_user=current_user,
        )
        await session.commit()

    _log.info(
        "delete_note_endpoint_ok",
        note_id=str(note_id),
        deleted_by=str(current_user.id),
    )


# ---------------------------------------------------------------------------
# Admin image upload (existing)
# ---------------------------------------------------------------------------

_MAX_ADMIN_IMAGES = 10
_WINDOW_24H_HOURS = 24


def _require_admin_or_agent(request: Request) -> Any:
    """
    Dependency: require admin or agente_humano role.

    solo_lectura users receive 403.
    Imported lazily to avoid circular imports in test environments.
    """
    from api.routes.admin import require_role as _require_role  # noqa: PLC0415

    dep = _require_role("admin", "agente_humano")
    return dep


@router.post(
    "/conversations/{conversation_history_id}/attachments",
    status_code=201,
    summary="Upload images from the admin composer and send them via Chatwoot",
)
async def upload_conversation_attachments(
    conversation_history_id: UUID,
    files: list[UploadFile] = File(..., description="1–10 image files"),
    caption: str | None = Form(None, max_length=4096),
    current_user: AdminUser = Depends(get_current_user),
) -> UploadAttachmentsResponse:
    """Upload 1–10 images on behalf of a human agent.

    Flow (per Design A3):
      1. RBAC — 403 for solo_lectura.
      2. Count validation — 400 if < 1 or > 10 files.
      3. 24h window check — 400 if conversation is outside the WhatsApp window.
      4. Delegate to ConversationImageService.store_admin_upload:
           validate → temp write → Chatwoot send → rename → return (msg, atts).
      5. Persist ConversationMessage + MessageAttachment rows, COMMIT.
      6. Return 201 with created message + attachment list.

    RBAC: ``admin`` and ``agente_humano`` only. ``solo_lectura`` → 403.
    """
    # --- 1. RBAC (inline check, mirrors sidebar/notes endpoints) ---
    if current_user.role not in {"admin", "agente_humano"}:
        raise HTTPException(status_code=403, detail="Permiso denegado")

    # --- 2. Count validation ---
    if not (1 <= len(files) <= _MAX_ADMIN_IMAGES):
        raise HTTPException(
            status_code=400,
            detail=f"Se permiten entre 1 y {_MAX_ADMIN_IMAGES} imágenes por mensaje",
        )

    async with get_async_session() as session:
        # --- 3. Load conversation and 24h window check ---
        conv = await _load_conversation(session, conversation_history_id)

        if conv.last_inbound_at is None:
            raise HTTPException(
                status_code=400,
                detail="outside_window: no hay mensajes entrantes; no es posible enviar imágenes fuera de la ventana de 24h de WhatsApp",
            )

        now = datetime.now(UTC)
        window_expires_at = conv.last_inbound_at + timedelta(hours=_WINDOW_24H_HOURS)
        if now >= window_expires_at:
            raise HTTPException(
                status_code=400,
                detail="outside_window: no es posible enviar imágenes fuera de la ventana de 24h de WhatsApp",
            )

        # --- 4. Delegate to service ---
        svc = get_conversation_image_service()
        msg, attachment_rows = await svc.store_admin_upload(
            session=session,
            conversation_id=conv.id,
            conversation_history_id=conversation_history_id,
            conversation_chatwoot_id=conv.conversation_id,
            files=files,
            caption=caption,
            admin_user_id=current_user.id,
        )

        # --- 5. Link attachments to message and persist ---
        session.add(msg)
        await session.flush()  # assign msg.id

        for row in attachment_rows:
            row.message_id = msg.id
            session.add(row)

        await session.flush()
        await session.commit()

    _log.info(
        "admin_upload_attachments_ok",
        conversation_history_id=str(conversation_history_id),
        message_id=str(msg.id),
        file_count=len(attachment_rows),
    )

    # --- 6. Build response ---
    att_responses = [
        MessageAttachmentResponse(
            id=row.id,
            url=row.url,
            kind=row.kind,
            content_type=row.content_type,
            filename=row.filename,
            size_bytes=row.size_bytes,
            width=row.width,
            height=row.height,
            position=row.position,
            created_at=row.created_at,
        )
        for row in sorted(attachment_rows, key=lambda r: r.position)
    ]

    return UploadAttachmentsResponse(
        message=_msg_to_response(msg),
        attachments=att_responses,
    )
