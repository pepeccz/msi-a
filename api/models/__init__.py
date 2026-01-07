"""
MSI Automotive - API Models module.
"""

from api.models.admin_user import (
    AdminRole,
    AccessAction,
    AdminUserBase,
    AdminUserCreate,
    AdminUserUpdate,
    AdminUserPasswordChange,
    AdminUserResponse,
    AdminUserWithStats,
    AdminAccessLogResponse,
    AdminAccessLogListResponse,
    LoginRequest,
    LoginResponse,
    CurrentUserResponse,
    AdminUserListResponse,
)
from api.models.chatwoot_webhook import (
    ChatwootAttachment,
    ChatwootConversation,
    ChatwootMessage,
    ChatwootMessageEvent,
    ChatwootSender,
    ChatwootWebhookPayload,
)
from api.models.tariff_schemas import (
    # Vehicle Category
    VehicleCategoryBase,
    VehicleCategoryCreate,
    VehicleCategoryUpdate,
    VehicleCategoryResponse,
    VehicleCategoryWithRelations,
    # Tariff Tier
    ClassificationRules,
    TariffTierBase,
    TariffTierCreate,
    TariffTierUpdate,
    TariffTierResponse,
    # Base Documentation
    BaseDocumentationBase,
    BaseDocumentationCreate,
    BaseDocumentationUpdate,
    BaseDocumentationResponse,
    # Warning
    TriggerConditions,
    WarningBase,
    WarningCreate,
    WarningUpdate,
    WarningResponse,
    # Additional Service
    AdditionalServiceBase,
    AdditionalServiceCreate,
    AdditionalServiceUpdate,
    AdditionalServiceResponse,
    # Tariff Prompt Section
    TariffPromptSectionBase,
    TariffPromptSectionCreate,
    TariffPromptSectionUpdate,
    TariffPromptSectionResponse,
    # Customer
    CustomerBase,
    CustomerCreate,
    CustomerUpdate,
    CustomerResponse,
    # Audit Log
    AuditLogResponse,
    # Public API
    TariffSelectionRequest,
    TariffSelectionResponse,
    DocumentationResponse,
    PromptPreviewResponse,
    CategoryFullDataResponse,
    # Common
    ListResponse,
)

__all__ = [
    # Admin User
    "AdminRole",
    "AccessAction",
    "AdminUserBase",
    "AdminUserCreate",
    "AdminUserUpdate",
    "AdminUserPasswordChange",
    "AdminUserResponse",
    "AdminUserWithStats",
    "AdminAccessLogResponse",
    "AdminAccessLogListResponse",
    "LoginRequest",
    "LoginResponse",
    "CurrentUserResponse",
    "AdminUserListResponse",
    # Chatwoot
    "ChatwootAttachment",
    "ChatwootConversation",
    "ChatwootMessage",
    "ChatwootMessageEvent",
    "ChatwootSender",
    "ChatwootWebhookPayload",
    # Vehicle Category
    "VehicleCategoryBase",
    "VehicleCategoryCreate",
    "VehicleCategoryUpdate",
    "VehicleCategoryResponse",
    "VehicleCategoryWithRelations",
    # Tariff Tier
    "ClassificationRules",
    "TariffTierBase",
    "TariffTierCreate",
    "TariffTierUpdate",
    "TariffTierResponse",
    # Base Documentation
    "BaseDocumentationBase",
    "BaseDocumentationCreate",
    "BaseDocumentationUpdate",
    "BaseDocumentationResponse",
    # Warning
    "TriggerConditions",
    "WarningBase",
    "WarningCreate",
    "WarningUpdate",
    "WarningResponse",
    # Additional Service
    "AdditionalServiceBase",
    "AdditionalServiceCreate",
    "AdditionalServiceUpdate",
    "AdditionalServiceResponse",
    # Tariff Prompt Section
    "TariffPromptSectionBase",
    "TariffPromptSectionCreate",
    "TariffPromptSectionUpdate",
    "TariffPromptSectionResponse",
    # Customer
    "CustomerBase",
    "CustomerCreate",
    "CustomerUpdate",
    "CustomerResponse",
    # Audit Log
    "AuditLogResponse",
    # Public API
    "TariffSelectionRequest",
    "TariffSelectionResponse",
    "DocumentationResponse",
    "PromptPreviewResponse",
    "CategoryFullDataResponse",
    # Common
    "ListResponse",
]
