/**
 * API Client for MSI Automotive Admin Panel
 * Handles all HTTP requests to FastAPI backend
 *
 * Updated for new architecture - HomologationElement removed,
 * added prompt sections and customer updates.
 */

import type {
  User,
  UserCreate,
  UserUpdate,
  ConversationHistory,
  SystemSetting,
  SystemSettingsResponse,
  DashboardKPIs,
  VehicleCategory,
  VehicleCategoryCreate,
  VehicleCategoryUpdate,
  TariffTier,
  TariffTierCreate,
  TariffTierUpdate,
  BaseDocumentation,
  BaseDocumentationCreate,
  BaseDocumentationUpdate,
  ElementDocumentation,
  ElementDocumentationCreate,
  ElementDocumentationUpdate,
  UploadedImage,
  UploadedImageListResponse,
  Warning,
  WarningCreate,
  WarningUpdate,
  AdditionalService,
  AdditionalServiceCreate,
  AdditionalServiceUpdate,
  VehicleCategoryWithDetails,
  TariffPromptSection,
  TariffPromptSectionCreate,
  TariffPromptSectionUpdate,
  PromptPreview,
  PaginatedResponse,
  SystemServiceName,
  SystemServicesResponse,
  ServiceActionResponse,
  ContainerErrorLog,
  ContainerErrorLogsResponse,
  ContainerErrorStats,
  ContainerErrorResolve,
  AdminUser,
  AdminUserCreate,
  AdminUserUpdate,
  AdminUserPasswordChange,
  AdminAccessLogListResponse,
  CurrentUser,
  RegulatoryDocument,
  RegulatoryDocumentStats,
  RegulatoryDocumentUpload,
  RegulatoryDocumentUpdate,
  RAGQueryResponse,
  RAGQueryHistory,
  RAGAnalyticsSummary,
  RAGHealthStatus,
  Escalation,
  EscalationStats,
  EscalationResolveResponse,
  Element,
  ElementCreate,
  ElementUpdate,
  ElementWithImages,
  ElementWithImagesAndChildren,
  ElementImage,
  ElementImageCreate,
  ElementImageUpdate,
  TierElementInclusion,
  TierElementInclusionCreate,
  TierElementInclusionUpdate,
  ElementWarningAssociation,
  ElementWarningAssociationCreate,
  TierElementsPreview,
  BatchTierInclusionCreate,
  ElementsListResponse,
  ElementsListWithChildrenResponse,
  ElementImagesListResponse,
  Case,
  CaseListItem,
  CaseStats,
  CaseStatusUpdate,
  CaseImageValidation,
  TokenUsageListResponse,
  CurrentMonthUsage,
  TokenPricing,
  ResponseConstraint,
  ResponseConstraintCreate,
  ResponseConstraintUpdate,
  ToolCallLog,
  ToolLogStats,
  PaginatedToolLogs,
} from "./types";

// Usa URL relativa - Next.js rewrites hace proxy al backend
const API_BASE_URL = "";

interface ApiError {
  error: string;
  details?: unknown;
}

class ApiClient {
  private baseUrl: string;
  private token: string | null = null;

  constructor(baseUrl: string) {
    this.baseUrl = baseUrl;
  }

  setToken(token: string | null) {
    this.token = token;
  }

  getToken(): string | null {
    if (typeof window !== "undefined") {
      return this.token || localStorage.getItem("admin_token");
    }
    return this.token;
  }

  private async request<T>(
    endpoint: string,
    options: RequestInit = {}
  ): Promise<T> {
    const url = `${this.baseUrl}${endpoint}`;
    const token = this.getToken();

    const headers: HeadersInit = {
      "Content-Type": "application/json",
      ...options.headers,
    };

    if (token) {
      (headers as Record<string, string>)["Authorization"] = `Bearer ${token}`;
    }

    const response = await fetch(url, {
      ...options,
      headers,
      credentials: "include",
    });

    if (!response.ok) {
      if (response.status === 401) {
        this.setToken(null);
        if (typeof window !== "undefined") {
          localStorage.removeItem("admin_token");
          const currentPath = window.location.pathname + window.location.search;
          if (currentPath !== "/login") {
            sessionStorage.setItem("returnTo", currentPath);
          }
          window.location.href = "/login";
        }
      }

      const error: ApiError = await response.json().catch(() => ({
        error: `HTTP ${response.status}: ${response.statusText}`,
      }));
      throw new Error(error.error || "Unknown error");
    }

    if (response.status === 204 || response.headers.get("content-length") === "0") {
      return undefined as T;
    }
    return response.json();
  }

  // ===========================================
  // Auth endpoints
  // ===========================================

  async login(
    username: string,
    password: string
  ): Promise<{ access_token: string; token_type: string; expires_in: number }> {
    const response = await this.request<{
      access_token: string;
      token_type: string;
      expires_in: number;
    }>("/api/admin/auth/login", {
      method: "POST",
      body: JSON.stringify({ username, password }),
    });
    this.setToken(response.access_token);
    if (typeof window !== "undefined") {
      localStorage.setItem("admin_token", response.access_token);
    }
    return response;
  }

  async logout(): Promise<void> {
    try {
      await this.request("/api/admin/auth/logout", { method: "POST" });
    } catch (error) {
      console.warn("Server logout failed:", error);
    }

    this.setToken(null);
    if (typeof window !== "undefined") {
      localStorage.removeItem("admin_token");
    }
  }

  async getMe(): Promise<CurrentUser> {
    return this.request("/api/admin/auth/me");
  }

  // ===========================================
  // Dashboard endpoints
  // ===========================================

  async getDashboardKPIs(): Promise<DashboardKPIs> {
    return this.request("/api/admin/dashboard/kpis");
  }

  // ===========================================
  // Generic CRUD methods
  // ===========================================

  async list<T>(
    resource: string,
    params?: Record<string, string | number | boolean | undefined>
  ): Promise<PaginatedResponse<T>> {
    const searchParams = new URLSearchParams();
    if (params) {
      Object.entries(params).forEach(([key, value]) => {
        if (value !== undefined) {
          searchParams.append(key, String(value));
        }
      });
    }
    const query = searchParams.toString();
    return this.request(`/api/admin/${resource}${query ? `?${query}` : ""}`);
  }

  async get<T>(resource: string, id: string): Promise<T> {
    return this.request(`/api/admin/${resource}/${id}`);
  }

  async create<T, D = Partial<T>>(resource: string, data: D): Promise<T> {
    return this.request(`/api/admin/${resource}`, {
      method: "POST",
      body: JSON.stringify(data),
    });
  }

  async update<T, D = Partial<T>>(resource: string, id: string, data: D): Promise<T> {
    return this.request(`/api/admin/${resource}/${id}`, {
      method: "PUT",
      body: JSON.stringify(data),
    });
  }

  async delete(resource: string, id: string): Promise<void> {
    await this.request(`/api/admin/${resource}/${id}`, {
      method: "DELETE",
    });
  }

  // ===========================================
  // User endpoints
  // ===========================================

  async getUsers(
    params?: Record<string, string | number | boolean | undefined>
  ): Promise<PaginatedResponse<User>> {
    return this.list<User>("users", params);
  }

  async getUser(id: string): Promise<User> {
    return this.get<User>("users", id);
  }

  async createUser(data: UserCreate): Promise<User> {
    return this.create<User, UserCreate>("users", data);
  }

  async updateUser(id: string, data: UserUpdate): Promise<User> {
    return this.update<User, UserUpdate>("users", id, data);
  }

  async deleteUser(id: string): Promise<void> {
    return this.delete("users", id);
  }

  // ===========================================
  // Conversation endpoints
  // ===========================================

  async getConversations(
    params?: Record<string, string | number | boolean | undefined>
  ): Promise<PaginatedResponse<ConversationHistory>> {
    return this.list<ConversationHistory>("conversations", params);
  }

  async getConversation(id: string): Promise<ConversationHistory> {
    return this.get<ConversationHistory>("conversations", id);
  }

  async deleteConversation(id: string): Promise<{ message: string; details: Record<string, number> }> {
    return this.request(`/api/admin/conversations/${id}`, {
      method: "DELETE",
    });
  }

  // ===========================================
  // System Settings
  // ===========================================

  async getSystemSettings(): Promise<SystemSettingsResponse> {
    return this.request("/api/admin/settings");
  }

  async getSystemSetting(key: string): Promise<SystemSetting> {
    return this.request(`/api/admin/settings/${key}`);
  }

  async updateSystemSetting(
    key: string,
    value: string | number | boolean
  ): Promise<SystemSetting> {
    return this.request(`/api/admin/settings/${key}`, {
      method: "PUT",
      body: JSON.stringify({ value }),
    });
  }

  // ===========================================
  // Health check
  // ===========================================

  async health(): Promise<{
    status: string;
    redis: string;
    postgres: string;
  }> {
    return this.request("/health");
  }

  // ===========================================
  // Vehicle Categories
  // ===========================================

  async getVehicleCategories(
    params?: Record<string, string | number | boolean | undefined>
  ): Promise<PaginatedResponse<VehicleCategory>> {
    return this.list<VehicleCategory>("vehicle-categories", params);
  }

  async getVehicleCategory(id: string): Promise<VehicleCategoryWithDetails> {
    return this.request(`/api/admin/vehicle-categories/${id}`);
  }

  async createVehicleCategory(
    data: VehicleCategoryCreate
  ): Promise<VehicleCategory> {
    return this.create<VehicleCategory, VehicleCategoryCreate>("vehicle-categories", data);
  }

  async updateVehicleCategory(
    id: string,
    data: VehicleCategoryUpdate
  ): Promise<VehicleCategory> {
    return this.update<VehicleCategory, VehicleCategoryUpdate>("vehicle-categories", id, data);
  }

  async deleteVehicleCategory(id: string): Promise<void> {
    return this.delete("vehicle-categories", id);
  }

  // ===========================================
  // Tariff Tiers
  // ===========================================

  async getTariffTiers(
    params?: Record<string, string | number | boolean | undefined>
  ): Promise<PaginatedResponse<TariffTier>> {
    return this.list<TariffTier>("tariff-tiers", params);
  }

  async getTariffTier(id: string): Promise<TariffTier> {
    return this.get<TariffTier>("tariff-tiers", id);
  }

  async createTariffTier(data: TariffTierCreate): Promise<TariffTier> {
    return this.create<TariffTier, TariffTierCreate>("tariff-tiers", data);
  }

  async updateTariffTier(id: string, data: TariffTierUpdate): Promise<TariffTier> {
    return this.update<TariffTier, TariffTierUpdate>("tariff-tiers", id, data);
  }

  async deleteTariffTier(id: string): Promise<void> {
    return this.delete("tariff-tiers", id);
  }

  // ===========================================
  // Prompt Sections
  // ===========================================

  async getPromptSections(
    params?: Record<string, string | number | boolean | undefined>
  ): Promise<PaginatedResponse<TariffPromptSection>> {
    return this.list<TariffPromptSection>("prompt-sections", params);
  }

  async getPromptSection(id: string): Promise<TariffPromptSection> {
    return this.get<TariffPromptSection>("prompt-sections", id);
  }

  async createPromptSection(data: TariffPromptSectionCreate): Promise<TariffPromptSection> {
    return this.create<TariffPromptSection, TariffPromptSectionCreate>("prompt-sections", data);
  }

  async updatePromptSection(
    id: string,
    data: TariffPromptSectionUpdate
  ): Promise<TariffPromptSection> {
    return this.update<TariffPromptSection, TariffPromptSectionUpdate>("prompt-sections", id, data);
  }

  async deletePromptSection(id: string): Promise<void> {
    return this.delete("prompt-sections", id);
  }

  async previewCategoryPrompt(
    categoryId: string
  ): Promise<PromptPreview> {
    // Note: client_type is now part of the category (in the slug)
    return this.request(
      `/api/admin/categories/${categoryId}/preview-prompt`
    );
  }

  // ===========================================
  // Base Documentation
  // ===========================================

  async getBaseDocumentation(
    params?: Record<string, string | number | boolean | undefined>
  ): Promise<PaginatedResponse<BaseDocumentation>> {
    return this.list<BaseDocumentation>("base-documentation", params);
  }

  async createBaseDocumentation(data: BaseDocumentationCreate): Promise<BaseDocumentation> {
    return this.create<BaseDocumentation, BaseDocumentationCreate>("base-documentation", data);
  }

  async updateBaseDocumentation(
    id: string,
    data: BaseDocumentationUpdate
  ): Promise<BaseDocumentation> {
    return this.update<BaseDocumentation, BaseDocumentationUpdate>("base-documentation", id, data);
  }

  async deleteBaseDocumentation(id: string): Promise<void> {
    return this.delete("base-documentation", id);
  }

  // ===========================================
  // Element Documentation (keyword-based)
  // ===========================================

  async getElementDocumentation(
    params?: Record<string, string | number | boolean | undefined>
  ): Promise<PaginatedResponse<ElementDocumentation>> {
    return this.list<ElementDocumentation>("element-documentation", params);
  }

  async createElementDocumentation(
    data: ElementDocumentationCreate
  ): Promise<ElementDocumentation> {
    return this.create<ElementDocumentation, ElementDocumentationCreate>(
      "element-documentation",
      data
    );
  }

  async updateElementDocumentation(
    id: string,
    data: ElementDocumentationUpdate
  ): Promise<ElementDocumentation> {
    return this.update<ElementDocumentation, ElementDocumentationUpdate>(
      "element-documentation",
      id,
      data
    );
  }

  async deleteElementDocumentation(id: string): Promise<void> {
    return this.delete("element-documentation", id);
  }

  // ===========================================
  // Element System (New Hierarchical Tariff System)
  // ===========================================

  // Elements
  async getElements(
    params?: Record<string, string | number | boolean | undefined>
  ): Promise<ElementsListResponse> {
    const searchParams = new URLSearchParams();
    if (params) {
      Object.entries(params).forEach(([key, value]) => {
        if (value !== undefined) {
          searchParams.append(key, String(value));
        }
      });
    }
    const query = searchParams.toString();
    return this.request(`/api/admin/elements${query ? `?${query}` : ""}`);
  }

  async getElementsWithChildren(
    params?: Record<string, string | number | boolean | undefined>
  ): Promise<ElementsListWithChildrenResponse> {
    const searchParams = new URLSearchParams();
    // Always include children and only base elements for hierarchical view
    searchParams.append("include_children", "true");
    searchParams.append("only_base", "true");
    if (params) {
      Object.entries(params).forEach(([key, value]) => {
        if (value !== undefined) {
          searchParams.append(key, String(value));
        }
      });
    }
    const query = searchParams.toString();
    return this.request(`/api/admin/elements?${query}`);
  }

  async getElement(id: string): Promise<ElementWithImagesAndChildren> {
    return this.get<ElementWithImagesAndChildren>("elements", id);
  }

  async createElement(data: ElementCreate): Promise<Element> {
    return this.create<Element, ElementCreate>("elements", data);
  }

  async updateElement(id: string, data: ElementUpdate): Promise<Element> {
    return this.update<Element, ElementUpdate>("elements", id, data);
  }

  async deleteElement(id: string): Promise<void> {
    return this.delete("elements", id);
  }

  // Element Images
  async getElementImages(elementId: string): Promise<ElementImagesListResponse> {
    return this.request(`/api/admin/elements/${elementId}/images`);
  }

  async createElementImage(elementId: string, data: ElementImageCreate): Promise<ElementImage> {
    return this.request(`/api/admin/elements/${elementId}/images`, {
      method: "POST",
      body: JSON.stringify(data),
    });
  }

  async updateElementImage(id: string, data: ElementImageUpdate): Promise<ElementImage> {
    return this.request(`/api/admin/element-images/${id}`, {
      method: "PUT",
      body: JSON.stringify(data),
    });
  }

  async deleteElementImage(id: string): Promise<void> {
    await this.request(`/api/admin/element-images/${id}`, {
      method: "DELETE",
    });
  }

  // Tier Element Inclusions
  async createTierInclusion(
    tierId: string,
    data: TierElementInclusionCreate
  ): Promise<TierElementInclusion> {
    return this.request(`/api/admin/tariff-tiers/${tierId}/inclusions`, {
      method: "POST",
      body: JSON.stringify(data),
    });
  }

  async batchCreateTierInclusions(
    tierId: string,
    data: BatchTierInclusionCreate
  ): Promise<{
    tier_id: string;
    created_count: number;
    inclusions: TierElementInclusion[];
  }> {
    return this.request(`/api/admin/tariff-tiers/${tierId}/inclusions/batch`, {
      method: "POST",
      body: JSON.stringify(data),
    });
  }

  async deleteTierInclusion(tierId: string, inclusionId: string): Promise<void> {
    await this.request(`/api/admin/tariff-tiers/${tierId}/inclusions/${inclusionId}`, {
      method: "DELETE",
    });
  }

  // Tier Resolved Elements (Preview)
  async getTierResolvedElements(tierId: string): Promise<TierElementsPreview> {
    return this.request(`/api/admin/tariff-tiers/${tierId}/resolved-elements`);
  }

  // Tier Element Inclusions
  async getTierInclusions(tierId: string): Promise<TierElementInclusion[]> {
    return this.request(`/api/admin/tariff-tiers/${tierId}/inclusions`);
  }

  async updateTierInclusion(
    tierId: string,
    inclusionId: string,
    data: Partial<TierElementInclusionCreate>
  ): Promise<TierElementInclusion> {
    return this.request(`/api/admin/tariff-tiers/${tierId}/inclusions/${inclusionId}`, {
      method: "PUT",
      body: JSON.stringify(data),
    });
  }

  // Element Warning Associations
  async getElementWarnings(elementId: string): Promise<ElementWarningAssociation[]> {
    return this.request(`/api/admin/elements/${elementId}/warnings`);
  }

  async createElementWarningAssociation(
    elementId: string,
    data: Omit<ElementWarningAssociationCreate, "element_id">
  ): Promise<ElementWarningAssociation> {
    return this.request(`/api/admin/elements/${elementId}/warnings`, {
      method: "POST",
      body: JSON.stringify({ ...data, element_id: elementId }),
    });
  }

  async deleteElementWarningAssociation(
    elementId: string,
    warningId: string
  ): Promise<void> {
    await this.request(`/api/admin/elements/${elementId}/warnings/${warningId}`, {
      method: "DELETE",
    });
  }

  async getWarningElements(warningId: string): Promise<ElementWarningAssociation[]> {
    return this.request(`/api/admin/warnings/${warningId}/elements`);
  }

  // ===========================================
  // Uploaded Images
  // ===========================================

  async getImages(
    params?: Record<string, string | number | boolean | undefined>
  ): Promise<UploadedImageListResponse> {
    const searchParams = new URLSearchParams();
    if (params) {
      Object.entries(params).forEach(([key, value]) => {
        if (value !== undefined) {
          searchParams.append(key, String(value));
        }
      });
    }
    const query = searchParams.toString();
    return this.request(`/api/admin/images${query ? `?${query}` : ""}`);
  }

  async uploadImage(
    file: File,
    category?: string,
    description?: string
  ): Promise<UploadedImage> {
    const formData = new FormData();
    formData.append("file", file);

    const params = new URLSearchParams();
    if (category) params.append("category", category);
    if (description) params.append("description", description);

    const url = `/api/admin/images/upload${params.toString() ? `?${params}` : ""}`;
    const token = this.getToken();

    const headers: HeadersInit = {};
    if (token) {
      headers["Authorization"] = `Bearer ${token}`;
    }

    const response = await fetch(`${this.baseUrl}${url}`, {
      method: "POST",
      headers,
      body: formData,
      credentials: "include",
    });

    if (!response.ok) {
      const error = await response.json().catch(() => ({
        error: `HTTP ${response.status}: ${response.statusText}`,
      }));
      throw new Error(error.detail || error.error || "Upload failed");
    }

    return response.json();
  }

  async deleteImage(id: string): Promise<void> {
    return this.delete("images", id);
  }

  // ===========================================
  // Warnings
  // ===========================================

  async getWarnings(
    params?: Record<string, string | number | boolean | undefined>
  ): Promise<PaginatedResponse<Warning>> {
    return this.list<Warning>("warnings", params);
  }

  async getWarning(id: string): Promise<Warning> {
    return this.get<Warning>("warnings", id);
  }

  async createWarning(data: WarningCreate): Promise<Warning> {
    return this.create<Warning, WarningCreate>("warnings", data);
  }

  async updateWarning(id: string, data: WarningUpdate): Promise<Warning> {
    return this.update<Warning, WarningUpdate>("warnings", id, data);
  }

  async deleteWarning(id: string): Promise<void> {
    return this.delete("warnings", id);
  }

  // ===========================================
  // Additional Services
  // ===========================================

  async getAdditionalServices(
    params?: Record<string, string | number | boolean | undefined>
  ): Promise<PaginatedResponse<AdditionalService>> {
    return this.list<AdditionalService>("additional-services", params);
  }

  async getAdditionalService(id: string): Promise<AdditionalService> {
    return this.get<AdditionalService>("additional-services", id);
  }

  async createAdditionalService(data: AdditionalServiceCreate): Promise<AdditionalService> {
    return this.create<AdditionalService, AdditionalServiceCreate>("additional-services", data);
  }

  async updateAdditionalService(
    id: string,
    data: AdditionalServiceUpdate
  ): Promise<AdditionalService> {
    return this.update<AdditionalService, AdditionalServiceUpdate>("additional-services", id, data);
  }

  async deleteAdditionalService(id: string): Promise<void> {
    return this.delete("additional-services", id);
  }

  // ===========================================
  // System Services
  // ===========================================

  async getSystemServices(): Promise<SystemServicesResponse> {
    return this.request("/api/admin/system/services");
  }

  async restartService(service: SystemServiceName): Promise<ServiceActionResponse> {
    return this.request(`/api/admin/system/${service}/restart`, {
      method: "POST",
    });
  }

  async stopService(service: SystemServiceName): Promise<ServiceActionResponse> {
    return this.request(`/api/admin/system/${service}/stop`, {
      method: "POST",
    });
  }

  async clearSystemCache(): Promise<ServiceActionResponse> {
    return this.request("/api/admin/system/cache/clear", {
      method: "POST",
    });
  }

  // ===========================================
  // Container Error Logs
  // ===========================================

  async getContainerErrors(
    params?: Record<string, string | number | boolean | undefined>
  ): Promise<ContainerErrorLogsResponse> {
    const searchParams = new URLSearchParams();
    if (params) {
      Object.entries(params).forEach(([key, value]) => {
        if (value !== undefined) {
          searchParams.append(key, String(value));
        }
      });
    }
    const query = searchParams.toString();
    return this.request(`/api/admin/system/errors${query ? `?${query}` : ""}`);
  }

  async getContainerErrorStats(): Promise<ContainerErrorStats> {
    return this.request("/api/admin/system/errors/stats");
  }

  async resolveContainerError(
    errorId: string,
    data: ContainerErrorResolve
  ): Promise<ServiceActionResponse> {
    return this.request(`/api/admin/system/errors/${errorId}/resolve`, {
      method: "POST",
      body: JSON.stringify(data),
    });
  }

  async deleteContainerError(errorId: string): Promise<ServiceActionResponse> {
    return this.request(`/api/admin/system/errors/${errorId}`, {
      method: "DELETE",
    });
  }

  async clearResolvedErrors(): Promise<ServiceActionResponse> {
    return this.request("/api/admin/system/errors", {
      method: "DELETE",
    });
  }

  // ===========================================
  // Admin Users
  // ===========================================

  async getAdminUsers(
    params?: Record<string, string | number | boolean | undefined>
  ): Promise<PaginatedResponse<AdminUser>> {
    return this.list<AdminUser>("admin-users", params);
  }

  async getAdminUser(id: string): Promise<AdminUser> {
    return this.get<AdminUser>("admin-users", id);
  }

  async createAdminUser(data: AdminUserCreate): Promise<AdminUser> {
    return this.create<AdminUser, AdminUserCreate>("admin-users", data);
  }

  async updateAdminUser(id: string, data: AdminUserUpdate): Promise<AdminUser> {
    return this.update<AdminUser, AdminUserUpdate>("admin-users", id, data);
  }

  async deleteAdminUser(id: string): Promise<void> {
    return this.delete("admin-users", id);
  }

  async changeAdminUserPassword(
    id: string,
    data: AdminUserPasswordChange
  ): Promise<void> {
    await this.request(`/api/admin/admin-users/${id}/password`, {
      method: "PUT",
      body: JSON.stringify(data),
    });
  }

  // ===========================================
  // Access Log
  // ===========================================

  async getAccessLog(
    params?: Record<string, string | number | boolean | undefined>
  ): Promise<AdminAccessLogListResponse> {
    const searchParams = new URLSearchParams();
    if (params) {
      Object.entries(params).forEach(([key, value]) => {
        if (value !== undefined) {
          searchParams.append(key, String(value));
        }
      });
    }
    const query = searchParams.toString();
    return this.request(`/api/admin/access-log${query ? `?${query}` : ""}`);
  }

  // ===========================================
  // RAG - Regulatory Documents
  // ===========================================

  async getRegulatoryDocuments(
    params?: Record<string, string | number | boolean | undefined>
  ): Promise<PaginatedResponse<RegulatoryDocument>> {
    return this.list<RegulatoryDocument>("regulatory-documents", params);
  }

  async getRegulatoryDocument(id: string): Promise<RegulatoryDocument> {
    return this.get<RegulatoryDocument>("regulatory-documents", id);
  }

  async uploadRegulatoryDocument(
    file: File,
    metadata: RegulatoryDocumentUpload
  ): Promise<{ id: string; status: string; message: string }> {
    const formData = new FormData();
    formData.append("file", file);
    formData.append("title", metadata.title);
    formData.append("document_type", metadata.document_type);
    if (metadata.document_number) {
      formData.append("document_number", metadata.document_number);
    }
    if (metadata.description) {
      formData.append("description", metadata.description);
    }

    const url = "/api/admin/regulatory-documents/upload";
    const token = this.getToken();

    const headers: HeadersInit = {};
    if (token) {
      headers["Authorization"] = `Bearer ${token}`;
    }

    const response = await fetch(`${this.baseUrl}${url}`, {
      method: "POST",
      headers,
      body: formData,
      credentials: "include",
    });

    if (!response.ok) {
      const error = await response.json().catch(() => ({
        error: `HTTP ${response.status}: ${response.statusText}`,
      }));
      throw new Error(error.detail || error.error || "Upload failed");
    }

    return response.json();
  }

  async updateRegulatoryDocument(
    id: string,
    data: RegulatoryDocumentUpdate
  ): Promise<RegulatoryDocument> {
    return this.update<RegulatoryDocument, RegulatoryDocumentUpdate>(
      "regulatory-documents",
      id,
      data
    );
  }

  async activateRegulatoryDocument(id: string): Promise<{ message: string }> {
    return this.request(`/api/admin/regulatory-documents/${id}/activate`, {
      method: "POST",
    });
  }

  async deactivateRegulatoryDocument(id: string): Promise<{ message: string }> {
    return this.request(`/api/admin/regulatory-documents/${id}/deactivate`, {
      method: "POST",
    });
  }

  async deleteRegulatoryDocument(id: string): Promise<void> {
    return this.delete("regulatory-documents", id);
  }

  async reprocessRegulatoryDocument(
    id: string
  ): Promise<{ message: string; status: string }> {
    return this.request(`/api/admin/regulatory-documents/${id}/reprocess`, {
      method: "POST",
    });
  }

  async getRegulatoryDocumentStats(): Promise<RegulatoryDocumentStats> {
    return this.request("/api/admin/regulatory-documents/stats/summary");
  }

  // ===========================================
  // RAG - Query
  // ===========================================

  async ragQuery(
    query: string,
    conversationId?: string
  ): Promise<RAGQueryResponse> {
    return this.request("/api/admin/rag/query", {
      method: "POST",
      body: JSON.stringify({
        query,
        conversation_id: conversationId,
      }),
    });
  }

  async clearRagCache(): Promise<{ message: string; entries_cleared: number }> {
    return this.request("/api/admin/rag/cache/clear", {
      method: "POST",
    });
  }

  async getRagQueries(
    params?: Record<string, string | number | boolean | undefined>
  ): Promise<PaginatedResponse<RAGQueryHistory>> {
    const searchParams = new URLSearchParams();
    if (params) {
      Object.entries(params).forEach(([key, value]) => {
        if (value !== undefined) {
          searchParams.append(key, String(value));
        }
      });
    }
    const query = searchParams.toString();
    return this.request(`/api/admin/rag/queries${query ? `?${query}` : ""}`);
  }

  async getRagAnalytics(): Promise<RAGAnalyticsSummary> {
    return this.request("/api/admin/rag/analytics/summary");
  }

  async getRagHealth(): Promise<RAGHealthStatus> {
    return this.request("/api/admin/rag/health");
  }

  // ===========================================
  // Escalations
  // ===========================================

  async getEscalations(
    params?: Record<string, string | number | undefined>
  ): Promise<PaginatedResponse<Escalation>> {
    const searchParams = new URLSearchParams();
    if (params) {
      Object.entries(params).forEach(([key, value]) => {
        if (value !== undefined) {
          searchParams.append(key, String(value));
        }
      });
    }
    const query = searchParams.toString();
    return this.request(`/api/admin/escalations${query ? `?${query}` : ""}`);
  }

  async getEscalationStats(): Promise<EscalationStats> {
    return this.request("/api/admin/escalations/stats");
  }

  async getEscalation(id: string): Promise<Escalation> {
    return this.request(`/api/admin/escalations/${id}`);
  }

  async resolveEscalation(id: string): Promise<EscalationResolveResponse> {
    return this.request(`/api/admin/escalations/${id}/resolve`, {
      method: "POST",
    });
  }

  // ===========================================
  // Cases (Expedientes)
  // ===========================================

  async getCases(
    params?: Record<string, string | number | undefined>
  ): Promise<PaginatedResponse<CaseListItem>> {
    const searchParams = new URLSearchParams();
    if (params) {
      Object.entries(params).forEach(([key, value]) => {
        if (value !== undefined) {
          searchParams.append(key, String(value));
        }
      });
    }
    const query = searchParams.toString();
    return this.request(`/api/admin/cases${query ? `?${query}` : ""}`);
  }

  async getCaseStats(): Promise<CaseStats> {
    return this.request("/api/admin/cases/stats");
  }

  async getCase(id: string): Promise<Case> {
    return this.request(`/api/admin/cases/${id}`);
  }

  async updateCaseStatus(
    id: string,
    data: CaseStatusUpdate
  ): Promise<{ id: string; status: string; message: string }> {
    return this.request(`/api/admin/cases/${id}/status`, {
      method: "POST",
      body: JSON.stringify(data),
    });
  }

  async takeCase(id: string): Promise<{ id: string; status: string; message: string }> {
    return this.request(`/api/admin/cases/${id}/take`, {
      method: "POST",
    });
  }

  async resolveCase(id: string): Promise<{
    id: string;
    status: string;
    resolved_at: string;
    resolved_by: string;
    message: string;
  }> {
    return this.request(`/api/admin/cases/${id}/resolve`, {
      method: "POST",
    });
  }

  async validateCaseImage(
    caseId: string,
    imageId: string,
    data: CaseImageValidation
  ): Promise<{ id: string; is_valid: boolean; message: string }> {
    return this.request(`/api/admin/cases/${caseId}/images/${imageId}/validate`, {
      method: "PUT",
      body: JSON.stringify(data),
    });
  }

  getCaseImageDownloadUrl(caseId: string, imageId: string): string {
    const token = this.getToken();
    return `/api/admin/cases/${caseId}/images/${imageId}${token ? `?token=${token}` : ""}`;
  }

  getCaseImagesZipUrl(caseId: string): string {
    const token = this.getToken();
    return `/api/admin/cases/${caseId}/images/download-all${token ? `?token=${token}` : ""}`;
  }

  // ===========================================
  // Token Usage
  // ===========================================

  async getTokenUsage(): Promise<TokenUsageListResponse> {
    return this.request("/api/token-usage");
  }

  async getCurrentMonthTokenUsage(): Promise<CurrentMonthUsage> {
    return this.request("/api/token-usage/current");
  }

  async getTokenPricing(): Promise<TokenPricing> {
    return this.request("/api/token-usage/pricing");
  }

  // ===========================================
  // Response Constraints (Anti-hallucination)
  // ===========================================

  async getConstraints(params?: { category_id?: string; is_active?: boolean }): Promise<ResponseConstraint[]> {
    const searchParams = new URLSearchParams();
    if (params?.category_id) searchParams.set("category_id", params.category_id);
    if (params?.is_active !== undefined) searchParams.set("is_active", String(params.is_active));
    const query = searchParams.toString();
    return this.request(`/api/admin/response-constraints${query ? `?${query}` : ""}`);
  }

  async createConstraint(data: ResponseConstraintCreate): Promise<ResponseConstraint> {
    return this.request("/api/admin/response-constraints", {
      method: "POST",
      body: JSON.stringify(data),
    });
  }

  async updateConstraint(id: string, data: ResponseConstraintUpdate): Promise<ResponseConstraint> {
    return this.request(`/api/admin/response-constraints/${id}`, {
      method: "PUT",
      body: JSON.stringify(data),
    });
  }

  async deleteConstraint(id: string): Promise<void> {
    await this.request(`/api/admin/response-constraints/${id}`, {
      method: "DELETE",
    });
  }

  // ===========================================
  // Tool Call Logs (Debugging)
  // ===========================================

  async getToolLogs(params?: {
    conversation_id?: string;
    tool_name?: string;
    result_type?: string;
    skip?: number;
    limit?: number;
  }): Promise<PaginatedToolLogs> {
    const searchParams = new URLSearchParams();
    if (params?.conversation_id) searchParams.set("conversation_id", params.conversation_id);
    if (params?.tool_name) searchParams.set("tool_name", params.tool_name);
    if (params?.result_type) searchParams.set("result_type", params.result_type);
    if (params?.skip !== undefined) searchParams.set("skip", String(params.skip));
    if (params?.limit !== undefined) searchParams.set("limit", String(params.limit));
    const query = searchParams.toString();
    return this.request(`/api/admin/tool-logs${query ? `?${query}` : ""}`);
  }

  async getConversationToolLogs(conversationId: string): Promise<ToolCallLog[]> {
    return this.request(`/api/admin/tool-logs/conversation/${conversationId}`);
  }

  async getToolLogStats(): Promise<ToolLogStats[]> {
    return this.request("/api/admin/tool-logs/stats");
  }

  async getToolNames(): Promise<string[]> {
    return this.request("/api/admin/tool-logs/tool-names");
  }
}

export const api = new ApiClient(API_BASE_URL);
export default api;
