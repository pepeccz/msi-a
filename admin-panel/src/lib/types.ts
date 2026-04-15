/**
 * MSI Automotive Admin Panel - Type definitions
 *
 * Updated for new architecture with classification_rules and trigger_conditions.
 * HomologationElement has been removed - AI uses rules instead.
 */

// ===========================================
// Admin User Types (Panel administrators)
// ===========================================

export type AdminRole = "admin" | "agent";

export interface AdminUser {
  id: string;
  username: string;
  display_name: string | null;
  role: AdminRole;
  is_active: boolean;
  email: string | null;
  chatwoot_agent_id: number | null;
  chatwoot_user_id: number | null;
  created_at: string;
  updated_at: string;
  created_by: string | null;
}

export interface ChatwootAgentEntry {
  id: number;
  name: string;
  email: string;
  role: string;
}

export interface AdminUserCreate {
  username: string;
  password: string;
  display_name?: string;
  role?: AdminRole;
  email?: string;
}

export interface AdminUserUpdate {
  display_name?: string | null;
  role?: AdminRole;
  is_active?: boolean;
  email?: string | null;
}

export interface AdminUserPasswordChange {
  current_password?: string;
  new_password: string;
}

export interface AdminAccessLogEntry {
  id: string;
  user_id: string;
  username: string | null;
  action: "login" | "logout" | "login_failed";
  ip_address: string | null;
  user_agent: string | null;
  details: Record<string, unknown> | null;
  created_at: string;
}

export interface AdminAccessLogListResponse {
  items: AdminAccessLogEntry[];
  total: number;
  limit: number;
  offset: number;
  has_more: boolean;
}

export interface CurrentUser {
  id: string;
  username: string;
  display_name: string | null;
  role: AdminRole;
  chatwoot_agent_id: number | null;
  chatwoot_user_id: number | null;
}

// ===========================================
// User Types (WhatsApp customers)
// ===========================================

export type ClientType = "particular" | "professional";

export interface User {
  id: string;
  phone: string;
  first_name: string | null;
  last_name: string | null;
  email: string | null;
  nif_cif: string | null;
  company_name: string | null;
  client_type: ClientType;
  domicilio_calle: string | null;
  domicilio_localidad: string | null;
  domicilio_provincia: string | null;
  domicilio_cp: string | null;
  chatwoot_contact_id: number | null;
  metadata: Record<string, unknown>;
  created_at: string;
  updated_at: string;
  last_activity_at: string | null;
}

export interface UserCreate {
  phone: string;
  first_name?: string | null;
  last_name?: string | null;
  email?: string | null;
  nif_cif?: string | null;
  company_name?: string | null;
  client_type?: ClientType;
  metadata?: Record<string, unknown>;
}

export interface UserUpdate {
  first_name?: string | null;
  last_name?: string | null;
  email?: string | null;
  nif_cif?: string | null;
  company_name?: string | null;
  client_type?: ClientType;
  domicilio_calle?: string | null;
  domicilio_localidad?: string | null;
  domicilio_provincia?: string | null;
  domicilio_cp?: string | null;
  metadata?: Record<string, unknown>;
}

// ===========================================
// Agent Memory Profile (Store API)
// ===========================================

export interface PastQuote {
  price: number | null;
  elements: string[];
  date: string;
}

export interface PastExpediente {
  case_id: string;
  elements: string[];
  date: string;
}

export interface AgentProfile {
  user_name?: string | null;
  client_type?: string | null;
  user_id?: string | null;
  first_seen?: string | null;
  last_seen?: string | null;
  past_quotes?: PastQuote[];
  past_expedientes?: PastExpediente[];
}

export interface AgentProfileResponse {
  found: boolean;
  profile: AgentProfile | null;
}

// ===========================================
// Conversation Types
// ===========================================

export interface ConversationHistory {
  id: string;
  user_id: string | null;
  user_name: string | null;
  user_phone: string | null;
  conversation_id: string;
  started_at: string;
  ended_at: string | null;
  message_count: number;
  summary: string | null;
  chatwoot_url: string;
  metadata?: Record<string, unknown>;
}

export interface ConversationMessage {
  id: string;
  conversation_history_id: string;
  role: "user" | "assistant";
  content: string;
  chatwoot_message_id?: number;
  has_images: boolean;
  image_count: number;
  created_at: string;
}

export interface ConversationMessagesResponse {
  messages: ConversationMessage[];
  total: number;
  has_more: boolean;
  conversation_id: string; // Chatwoot ID
}

export interface ConversationMessageStats {
  total_messages: number;
  user_messages: number;
  assistant_messages: number;
  messages_with_images: number;
  first_message_at: string | null;
  last_message_at: string | null;
}

// ===========================================
// System Settings
// ===========================================

export interface SystemSetting {
  id: string;
  key: string;
  value: string;
  value_type: "string" | "int" | "float" | "bool" | "json";
  description: string | null;
  created_at: string;
  updated_at: string;
}

// ===========================================
// API Response Types
// ===========================================

export interface PaginatedResponse<T> {
  items: T[];
  total: number;
  has_more: boolean;
}

export interface SystemSettingsResponse {
  items: SystemSetting[];
  total: number;
  has_more: boolean;
}

// Dashboard KPIs
export interface DashboardKPIs {
  // Cases metrics
  cases_pending_review: number;
  cases_in_progress: number;
  cases_collecting: number;
  cases_resolved_today: number;
  // Escalations metrics
  escalations_pending: number;
  escalations_resolved_today: number;
  // General metrics
  total_users: number;
  total_conversations: number;
}

// ===========================================
// Vehicle Category Types
// ===========================================

/**
 * VehicleCategory now includes client_type.
 * Categories are separated by type: motos-part, motos-prof, etc.
 */
export interface VehicleCategory {
  id: string;
  slug: string;
  name: string;
  description: string | null;
  icon: string | null;
  client_type: ClientType;
  is_active: boolean;
  sort_order: number;
  created_at: string;
  updated_at: string | null;
}

export interface VehicleCategoryCreate {
  slug: string;
  name: string;
  description?: string | null;
  icon?: string | null;
  client_type: ClientType;
  is_active?: boolean;
  sort_order?: number;
}

export interface VehicleCategoryUpdate {
  slug?: string;
  name?: string;
  description?: string | null;
  icon?: string | null;
  client_type?: ClientType;
  is_active?: boolean;
  sort_order?: number;
}

// ===========================================
// Tariff Tier Types
// ===========================================

/**
 * Note: client_type differentiation is now at the VehicleCategory level.
 * TariffTier no longer has client_type - tiers are unique by (category_id, code).
 */

export interface ClassificationRules {
  applies_if_any: string[];
  priority: number;
  requires_project: boolean;
  notes?: string;
}

export interface TariffTier {
  id: string;
  category_id: string;
  code: string;
  name: string;
  description: string | null;
  price: number;
  conditions: string | null;
  classification_rules: ClassificationRules | null;
  min_elements: number | null;
  max_elements: number | null;
  sort_order: number;
  is_active: boolean;
  created_at: string;
  updated_at: string | null;
}

export interface TariffTierCreate {
  category_id: string;
  code: string;
  name: string;
  description?: string | null;
  price: number;
  conditions?: string | null;
  classification_rules?: ClassificationRules | null;
  min_elements?: number | null;
  max_elements?: number | null;
  sort_order?: number;
  is_active?: boolean;
}

export interface TariffTierUpdate {
  code?: string;
  name?: string;
  description?: string | null;
  price?: number;
  conditions?: string | null;
  classification_rules?: ClassificationRules | null;
  min_elements?: number | null;
  max_elements?: number | null;
  sort_order?: number;
  is_active?: boolean;
}

// ===========================================
// Warning Types
// ===========================================

export type WarningSeverity = "info" | "warning" | "error";

export interface TriggerConditions {
  element_keywords: string[];
  show_with_elements: string[];
  always_show: boolean;
}

export interface Warning {
  id: string;
  code: string;
  message: string;
  severity: WarningSeverity;
  trigger_conditions: TriggerConditions | null;
  is_active: boolean;
  created_at: string;
  updated_at: string | null;
}

export interface WarningCreate {
  code: string;
  message: string;
  severity?: WarningSeverity;
  trigger_conditions?: TriggerConditions | null;
  is_active?: boolean;
}

export interface WarningUpdate {
  code?: string;
  message?: string;
  severity?: WarningSeverity;
  trigger_conditions?: TriggerConditions | null;
  is_active?: boolean;
}

// ===========================================
// Tariff Prompt Section Types
// ===========================================

export type PromptSectionType =
  | "algorithm"
  | "recognition_table"
  | "special_cases"
  | "footer";

export interface TariffPromptSection {
  id: string;
  category_id: string;
  section_type: PromptSectionType;
  content: string;
  is_active: boolean;
  version: number;
  created_at: string;
  updated_at: string;
}

export interface TariffPromptSectionCreate {
  category_id: string;
  section_type: PromptSectionType;
  content: string;
  is_active?: boolean;
}

export interface TariffPromptSectionUpdate {
  section_type?: PromptSectionType;
  content?: string;
  is_active?: boolean;
}

export interface PromptPreview {
  category: {
    id: string;
    slug: string;
    name: string;
    description: string | null;
    client_type: ClientType;
  } | null;
  sections: Record<string, string>;
  warnings_count: number;
  tiers_count: number;
  prompt_length: number;
  full_prompt: string;
}

// ===========================================
// Base Documentation Types
// ===========================================

export interface BaseDocumentation {
  id: string;
  category_id: string;
  description: string;
  image_url: string | null;
  sort_order: number;
  created_at: string;
}

export interface BaseDocumentationCreate {
  category_id: string;
  description: string;
  image_url?: string | null;
  sort_order?: number;
}

export interface BaseDocumentationUpdate {
  description?: string;
  image_url?: string | null;
  sort_order?: number;
}

// ===========================================
// Element Documentation Types (keyword-based)
// ===========================================

export interface ElementDocumentation {
  id: string;
  category_id: string | null;
  element_keywords: string[];
  description: string;
  image_url: string | null;
  sort_order: number;
  is_active: boolean;
  created_at: string;
  updated_at: string;
}

export interface ElementDocumentationCreate {
  category_id?: string | null;
  element_keywords: string[];
  description: string;
  image_url?: string | null;
  sort_order?: number;
  is_active?: boolean;
}

export interface ElementDocumentationUpdate {
  element_keywords?: string[];
  description?: string;
  image_url?: string | null;
  sort_order?: number;
  is_active?: boolean;
}

// ===========================================
// Uploaded Image Types
// ===========================================

export interface UploadedImage {
  id: string;
  filename: string;
  stored_filename: string;
  mime_type: string;
  file_size: number;
  width: number | null;
  height: number | null;
  category: string | null;
  description: string | null;
  uploaded_by: string | null;
  url: string;
  created_at: string;
}

export interface UploadedImageListResponse {
  items: UploadedImage[];
  total: number;
  has_more: boolean;
}

// ===========================================
// Additional Service Types
// ===========================================

export interface AdditionalService {
  id: string;
  category_id: string | null;
  code: string;
  name: string;
  description: string | null;
  price: number;
  is_active: boolean;
  sort_order: number;
  created_at: string;
  updated_at: string | null;
}

export interface AdditionalServiceCreate {
  category_id?: string | null;
  code: string;
  name: string;
  description?: string | null;
  price: number;
  is_active?: boolean;
  sort_order?: number;
}

export interface AdditionalServiceUpdate {
  code?: string;
  name?: string;
  description?: string | null;
  price?: number;
  category_id?: string | null;
  is_active?: boolean;
  sort_order?: number;
}

// ===========================================
// Element System Types (New Hierarchical Tariff System)
// ===========================================

export type ElementImageType = "example" | "required_document" | "warning" | "step" | "calculation";
export type ElementImageStatus = "active" | "placeholder" | "unavailable";
export type ShowCondition = "always" | "if_selected";

export interface ElementImage {
  id: string;
  element_id: string;
  image_url: string;
  title: string | null;
  description: string | null;
  image_type: ElementImageType;
  sort_order: number;
  is_required: boolean;
  status: ElementImageStatus;
  validated_at: string | null;
  user_instruction: string | null;
  created_at: string;
}

export interface ElementImageCreate {
  image_url: string;
  title?: string | null;
  description?: string | null;
  image_type: ElementImageType;
  sort_order?: number;
  is_required?: boolean;
  status?: ElementImageStatus;
  user_instruction?: string | null;
}

export interface ElementImageUpdate {
  image_url?: string;
  title?: string | null;
  description?: string | null;
  image_type?: ElementImageType;
  sort_order?: number;
  is_required?: boolean;
  status?: ElementImageStatus;
  user_instruction?: string | null;
}

export interface Element {
  id: string;
  category_id: string;
  code: string;
  name: string;
  description: string | null;
  keywords: string[];
  aliases: string[] | null;
  is_active: boolean;
  sort_order: number;
  // Hierarchy fields
  parent_element_id: string | null;
  variant_type: string | null;
  variant_code: string | null;
  question_hint: string | null;
  multi_select_keywords: string[] | null;
  inherit_parent_data: boolean;
  variant_position: number | null;
  created_at: string;
  updated_at: string;
  // Contadores agregados (devueltos por el backend)
  image_count?: number;
  warning_count?: number;
  child_count?: number;
}

export interface ElementCreate {
  category_id: string;
  code: string;
  name: string;
  description?: string | null;
  keywords: string[];
  aliases?: string[] | null;
  is_active?: boolean;
  sort_order?: number;
  // Hierarchy fields
  parent_element_id?: string | null;
  variant_type?: string | null;
  variant_code?: string | null;
  question_hint?: string | null;
  inherit_parent_data?: boolean;
}

export interface ElementUpdate {
  code?: string;
  name?: string;
  description?: string | null;
  keywords?: string[];
  aliases?: string[] | null;
  is_active?: boolean;
  sort_order?: number;
  // Hierarchy fields
  parent_element_id?: string | null;
  variant_type?: string | null;
  variant_code?: string | null;
  question_hint?: string | null;
  multi_select_keywords?: string[] | null;
  inherit_parent_data?: boolean;
}

export interface ElementWithImages extends Element {
  images: ElementImage[];
}

export interface ElementWithChildren extends Element {
  children: Element[];
}

export interface ElementWithImagesAndChildren extends ElementWithImages {
  children: ElementWithImages[];
  parent?: {
    id: string;
    code: string;
    name: string;
  };
}

export interface TierElementInclusion {
  id: string;
  tier_id: string;
  element_id: string | null;
  included_tier_id: string | null;
  min_quantity: number | null;
  max_quantity: number | null;
  notes: string | null;
  created_at: string;
}

export interface TierElementInclusionCreate {
  tier_id?: string;
  element_id?: string | null;
  included_tier_id?: string | null;
  min_quantity?: number | null;
  max_quantity?: number | null;
  notes?: string | null;
}

export interface TierElementInclusionUpdate {
  element_id?: string | null;
  included_tier_id?: string | null;
  min_quantity?: number | null;
  max_quantity?: number | null;
  notes?: string | null;
}

export interface ElementWarningAssociation {
  id: string;
  element_id: string;
  warning_id: string;
  show_condition: ShowCondition;
  threshold_quantity: number | null;
  created_at: string;
}

export interface ElementWarningAssociationCreate {
  element_id: string;
  warning_id: string;
  show_condition: ShowCondition;
  threshold_quantity?: number | null;
}

export interface TierElementsPreview {
  tier_id: string;
  tier_code: string;
  tier_name: string;
  total_elements: number;
  elements: Record<string, number | null>;
}

export interface BatchTierInclusionCreate {
  tier_id: string;
  inclusions: TierElementInclusionCreate[];
}

export interface ElementsListResponse {
  items: Element[];
  total: number;
  skip: number;
  limit: number;
}

export interface ElementsListWithChildrenResponse {
  items: ElementWithChildren[];
  total: number;
  skip: number;
  limit: number;
}

export interface ElementImagesListResponse {
  element_id: string;
  images: ElementImage[];
}

// ===========================================
// Element Required Field Types (Data Collection)
// ===========================================

export type RequiredFieldType = "text" | "number" | "boolean" | "select" | "date" | "photo";
export type ConditionOperator = "equals" | "not_equals" | "exists" | "not_exists" | "contains" | "greater_than" | "less_than";

export interface ValidationRules {
  min?: number;
  max?: number;
  min_length?: number;
  max_length?: number;
  pattern?: string;
}

export interface ElementRequiredField {
  id: string;
  element_id: string;
  field_key: string;
  field_label: string;
  field_type: RequiredFieldType;
  options: string[] | null;
  is_required: boolean;
  validation_rules: ValidationRules | null;
  example_value: string | null;
  llm_instruction: string | null;
  condition_field_id: string | null;
  condition_operator: ConditionOperator | null;
  condition_value: string | null;
  sort_order: number;
  is_active: boolean;
  created_at: string;
  updated_at: string;
}

export interface ElementRequiredFieldCreate {
  field_key: string;
  field_label: string;
  field_type: RequiredFieldType;
  options?: string[] | null;
  is_required?: boolean;
  validation_rules?: ValidationRules | null;
  example_value?: string | null;
  llm_instruction?: string | null;
  condition_field_id?: string | null;
  condition_operator?: ConditionOperator | null;
  condition_value?: string | null;
  sort_order?: number;
  is_active?: boolean;
}

export interface ElementRequiredFieldUpdate {
  field_key?: string;
  field_label?: string;
  field_type?: RequiredFieldType;
  options?: string[] | null;
  is_required?: boolean;
  validation_rules?: ValidationRules | null;
  example_value?: string | null;
  llm_instruction?: string | null;
  condition_field_id?: string | null;
  condition_operator?: ConditionOperator | null;
  condition_value?: string | null;
  sort_order?: number;
  is_active?: boolean;
}

// ===========================================
// Case Element Data Types
// ===========================================

export type CaseElementDataStatus = "pending_photos" | "pending_data" | "completed";

export interface CaseElementData {
  id: string;
  case_id: string;
  element_code: string;
  status: CaseElementDataStatus;
  field_values: Record<string, unknown>;
  photos_completed_at: string | null;
  data_completed_at: string | null;
  created_at: string;
  updated_at: string;
}

export interface CaseElementDataUpdate {
  status?: CaseElementDataStatus;
  field_values?: Record<string, unknown>;
}

// ===========================================
// Category with Relations (for detail view)
// ===========================================

export interface VehicleCategoryWithDetails extends VehicleCategory {
  tariff_tiers: TariffTier[];
  base_documentation: BaseDocumentation[];
  additional_services: AdditionalService[];
  prompt_sections: TariffPromptSection[];
}

// ===========================================
// System Service Types
// ===========================================

export type SystemServiceName =
  | "api"
  | "agent"
  | "postgres"
  | "redis"
  | "admin-panel"
  | "ollama"
  | "qdrant"
  | "document-processor";

export interface SystemService {
  name: SystemServiceName;
  container: string;
  status: string;
  health: string | null;
}

export interface SystemServicesResponse {
  services: SystemService[];
}

export interface ServiceActionResponse {
  success: boolean;
  message: string;
}

// ===========================================
// Escalation Types
// ===========================================

export type EscalationStatus = "pending" | "in_progress" | "resolved";
export type EscalationSource =
  | "tool_call"
  | "auto_escalation"
  | "error"
  | "case_completion"
  | "agent_disabled";

export interface Escalation {
  id: string;
  conversation_id: string;
  user_id: string | null;
  user_phone?: string | null;
  reason: string;
  source: EscalationSource;
  status: EscalationStatus;
  triggered_at: string;
  resolved_at: string | null;
  resolved_by: string | null;
  metadata: Record<string, unknown> | null;
}

export interface EscalationStats {
  pending: number;
  in_progress: number;
  resolved_today: number;
  total_today: number;
}

export interface EscalationResolveResponse {
  id: string;
  status: string;
  resolved_at: string;
  resolved_by: string;
  message: string;
}

// ===========================================
// Case (Expediente) Types
// ===========================================

export type CaseStatus =
  | "collecting"
  | "pending_images"
  | "pending_review"
  | "in_progress"
  | "resolved"
  | "cancelled"
  | "abandoned";

export type CollectionStep =
  | "idle"
  | "collect_element_data"
  | "collect_base_docs"
  | "collect_personal"
  | "collect_vehicle"
  | "collect_workshop"
  | "review_summary"
  | "completed";

export interface CaseImage {
  id: string;
  display_name: string;
  description: string | null;
  element_code: string | null;
  image_type: string;
  mime_type: string;
  file_size: number | null;
  is_valid: boolean | null;
  validation_notes: string | null;
  url: string;
  created_at: string;
}

export interface Case {
  id: string;
  conversation_id: string;
  user_id: string | null;
  user_phone: string | null;
  status: CaseStatus;
  current_step: CollectionStep | null;
  // User personal data (from related User)
  user_first_name: string | null;
  user_last_name: string | null;
  user_email: string | null;
  user_nif_cif: string | null;
  user_domicilio_calle: string | null;
  user_domicilio_localidad: string | null;
  user_domicilio_provincia: string | null;
  user_domicilio_cp: string | null;
  // ITV
  itv_nombre: string | null;
  // Workshop data
  taller_propio: boolean | null;
  taller_nombre: string | null;
  taller_responsable: string | null;
  taller_domicilio: string | null;
  taller_provincia: string | null;
  taller_ciudad: string | null;
  taller_telefono: string | null;
  taller_registro_industrial: string | null;
  taller_actividad: string | null;
  // Vehicle data
  vehiculo_marca: string | null;
  vehiculo_modelo: string | null;
  vehiculo_anio: number | null;
  vehiculo_matricula: string | null;
  vehiculo_bastidor: string | null;
  // Dimensional changes
  cambio_plazas: boolean | null;
  plazas_iniciales: number | null;
  plazas_finales: number | null;
  cambio_altura: boolean | null;
  altura_final: number | null;
  cambio_ancho: boolean | null;
  ancho_final: number | null;
  cambio_longitud: boolean | null;
  longitud_final: number | null;
  // Category and elements
  category_id: string | null;
  category_slug: string | null;
  category_name: string | null;
  element_codes: string[];
  // Tariff
  tariff_tier_id: string | null;
  tariff_amount: number | null;
  // Escalation
  escalation_id: string | null;
  escalation_status: string | null;
  // Metadata
  notes: string | null;
  metadata: Record<string, unknown> | null;
  // Timestamps
  created_at: string;
  updated_at: string;
  completed_at: string | null;
  resolved_at: string | null;
  resolved_by: string | null;
  // Images (only in detail view)
  images?: CaseImage[];
  image_count?: number;
}

export interface CaseListItem {
  id: string;
  conversation_id: string;
  user_id: string | null;
  user_phone: string | null;
  status: CaseStatus;
  current_step: CollectionStep | null;
  // User info (from related User)
  user_first_name: string | null;
  user_last_name: string | null;
  user_email: string | null;
  // Vehicle data
  vehiculo_marca: string | null;
  vehiculo_modelo: string | null;
  vehiculo_matricula: string | null;
  category_slug: string | null;
  category_name: string | null;
  element_codes: string[];
  tariff_amount: number | null;
  image_count: number;
  created_at: string;
  updated_at: string;
  resolved_by: string | null;
}

export interface CaseStats {
  pending_review: number;
  in_progress: number;
  collecting: number;
  resolved_today: number;
  created_today: number;
  total_active: number;
  by_status: Record<string, number>;
}

export interface CaseStatusUpdate {
  status: CaseStatus;
  notes?: string;
}

export interface CaseImageValidation {
  is_valid: boolean;
  validation_notes?: string;
}

// ===========================================
// Token Usage Types
// ===========================================

export interface TokenUsage {
  id: string;
  year: number;
  month: number;
  input_tokens: number;
  output_tokens: number;
  total_tokens: number;
  total_requests: number;
  cost_input_eur: number;
  cost_output_eur: number;
  cost_total_eur: number;
  created_at: string;
  updated_at: string;
}

export interface TokenUsageListResponse {
  items: TokenUsage[];
  total: number;
}

export interface CurrentMonthUsage {
  year: number;
  month: number;
  input_tokens: number;
  output_tokens: number;
  total_tokens: number;
  total_requests: number;
  cost_input_eur: number;
  cost_output_eur: number;
  cost_total_eur: number;
}

export interface TokenPricing {
  input_price_per_million: number;
  output_price_per_million: number;
}

// ===========================================
// Billing Types
// ===========================================

export interface PaymentRecord {
  id: string;
  stripe_payment_intent_id: string | null;
  stripe_charge_id: string | null;
  amount_eur: number;
  fee_eur: number | null;
  status: "pending" | "succeeded" | "failed" | "refunded";
  failure_reason: string | null;
  created_at: string;
}

export interface Invoice {
  id: string;
  invoice_number: string;
  year: number;
  month: number;
  maintenance_amount_eur: number;
  token_amount_eur: number;
  subtotal_eur: number;
  iva_rate: number;
  iva_amount_eur: number;
  total_eur: number;
  status: "draft" | "issued" | "paid" | "overdue" | "void";
  stripe_invoice_id: string | null;
  pdf_path: string | null;
  due_date: string | null;
  issued_at: string | null;
  paid_at: string | null;
  notes: string | null;
  payments: PaymentRecord[];
  created_at: string;
  updated_at: string;
}

export interface InvoiceListResponse {
  invoices: Invoice[];
  total: number;
  page: number;
  page_size: number;
}

export interface CurrentEstimate {
  year: number;
  month: number;
  maintenance_eur: string;
  token_eur: string;
  subtotal_eur: string;
  iva_rate: string;
  iva_amount_eur: string;
  total_eur: string;
  input_tokens: number;
  output_tokens: number;
}

export interface StripeStatus {
  has_payment_method: boolean;
  payment_method_type: string | null;
  last4: string | null;
  bank_name: string | null;
}

export interface StripeSetupSession {
  session_url: string;
}

export interface FiscalParty {
  name: string;
  nif: string;
  address: string;
}

export interface FiscalDetails {
  company: FiscalParty;
  client: FiscalParty;
}

