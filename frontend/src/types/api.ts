export type UUID = string;
export type Role = "ADMIN" | "SUPERVISOR" | "TECHNICIAN" | "CLIENT" | "VIEWER";
export type SourceType = "WINDOWS" | "VMWARE" | "HYPERV" | "MIXED";
export type MachineStatus = "ONLINE" | "OFFLINE" | "UNKNOWN";
export type Severity = "INFO" | "WARNING" | "HIGH" | "CRITICAL";
export type AlertStatus = "NEW" | "ACKNOWLEDGED" | "IN_PROGRESS" | "RESOLVED";
export type TaskStatus = "RUNNING" | "SUCCESS" | "FAILED";
export type JsonObject = Record<string, unknown>;

export interface Page<T> {
  count: number;
  next: string | null;
  previous: string | null;
  results: T[];
}

export interface User {
  id: number;
  email: string;
  username: string;
  first_name: string;
  last_name: string;
  role: Role;
  customer: UUID | null;
  is_active: boolean;
  is_superuser: boolean;
}

export interface Customer {
  id: UUID;
  name: string;
  slug: string;
  active: boolean;
  created_at: string;
  updated_at: string;
}

export interface Environment {
  id: UUID;
  name: string;
  kind: SourceType;
  metadata: JsonObject;
  created_at: string;
}

export interface Machine {
  id: UUID;
  environment: UUID;
  source_type: SourceType;
  external_id: string;
  hostname: string;
  ip_address: string | null;
  os_information: JsonObject;
  status: MachineStatus;
  last_seen: string | null;
  agent_version: string;
  metadata: JsonObject;
  created_at: string;
  updated_at: string;
}

export interface Agent {
  id: UUID;
  machine: UUID;
  hostname: string;
  enabled: boolean;
  version: string;
  last_heartbeat: string | null;
  created_at: string;
}

export interface Connector {
  id: UUID;
  environment: UUID;
  kind: "VMWARE" | "HYPERV";
  name: string;
  endpoint: string;
  username: string;
  verify_tls: boolean;
  timeout_seconds: number;
  enabled: boolean;
  config: JsonObject;
  last_sync_at: string | null;
  last_error: string;
  created_at: string;
}

export interface VirtualAsset {
  id: UUID;
  connector: UUID;
  machine: UUID | null;
  external_id: string;
  parent_external_id: string;
  kind: "HOST" | "VM" | "DATASTORE";
  name: string;
  state: string;
  metadata: JsonObject;
  last_seen: string | null;
}

export interface Metric {
  id: number;
  timestamp: string;
  environment: UUID;
  machine: UUID;
  source_type: SourceType;
  metric_name: string;
  metric_value: number | null;
  unit: string;
  status: string;
  metadata: JsonObject;
  idempotency_key: string | null;
  received_at: string;
}

export interface MetricAggregate {
  id: number;
  machine: UUID;
  metric_name: string;
  bucket_start: string;
  bucket_seconds: number;
  minimum: number;
  maximum: number;
  average: number;
  sample_count: number;
}

export interface MonitoringRule {
  id: UUID;
  name: string;
  metric: string;
  operator: ">" | "<" | ">=" | "<=" | "==" | "!=";
  threshold: number;
  duration_seconds: number;
  severity: Severity;
  enabled: boolean;
  environment: UUID | null;
  machine: UUID | null;
  cooldown_seconds: number;
  created_at: string;
  updated_at: string;
}

export interface Recommendation {
  id?: UUID;
  diagnosis_hints?: string[];
  actions?: string[];
  rationale?: string;
  destructive?: boolean;
  generated_at?: string;
  [key: string]: unknown;
}

export interface Alert {
  id: UUID;
  machine: UUID;
  hostname: string;
  timestamp: string;
  updated_at: string;
  type: string;
  severity: Severity;
  source: string;
  message: string;
  context: JsonObject;
  anomaly_score: number | null;
  recommendation: string;
  structured_recommendation: Recommendation | null;
  status: AlertStatus;
  dedup_key: string;
  first_seen_at: string;
  last_seen_at: string;
  occurrences: number;
  escalation_level: number;
}

export interface Anomaly {
  id: UUID;
  machine: UUID;
  hostname: string;
  metric: number | null;
  detected_at: string;
  window_start: string | null;
  score: number;
  threshold: number;
  model_version: string;
  explanation: JsonObject;
  acknowledged: boolean;
}

export interface MLModel {
  id: UUID;
  display_number: number;
  version: string;
  algorithm: string;
  features: string[];
  preprocessing: JsonObject;
  parameters: JsonObject;
  dataset: JsonObject;
  evaluation_metrics: JsonObject;
  decision_threshold: number | null;
  trained_at: string | null;
  status: "TRAINING" | "READY" | "FAILED" | "ARCHIVED";
  active: boolean;
  created_at: string;
}

export interface Prediction {
  metric_name: string;
  unit: string;
  sample_count: number;
  window_hours: number;
  last_value: number;
  rolling_average: number;
  rate_of_change_per_hour: number;
  trend: "increasing" | "decreasing" | "stable" | "insufficient_data";
  risk_score: number;
  rule_id: UUID | null;
  threshold: number | null;
  estimated_threshold_breach_at: string | null;
  already_breached: boolean;
  confidence: "LOW" | "MEDIUM" | "HIGH" | string;
  is_estimate: boolean;
  disclaimer: string;
}

export interface DashboardSummary {
  total_assets: number;
  online: number;
  offline: number;
  critical: number;
  warning: number;
  anomalies: number;
  vmware_hosts: number;
  hyperv_hosts: number;
  active_alerts: number;
}

export interface IntegrationOverview {
  source: "VMWARE" | "HYPERV";
  connectors: Connector[];
  hosts: VirtualAsset[];
  vms: VirtualAsset[];
  datastores: VirtualAsset[];
  partial: boolean;
}

export interface NotificationPreference {
  id: number;
  user: number | null;
  channel: "EMAIL" | "TEAMS" | "SLACK" | "TELEGRAM";
  destination: string;
  minimum_severity: Severity;
  enabled: boolean;
  cooldown_seconds: number;
  created_at: string;
  updated_at: string;
}

export interface NotificationDelivery {
  id: UUID;
  event: UUID;
  preference: number;
  status: string;
  attempts: number;
  next_attempt_at: string | null;
  sent_at: string | null;
  provider_id: string;
  last_error: string;
  created_at: string;
  updated_at: string;
}

export interface CollectionRun {
  id: number;
  connector: UUID;
  task_id: string;
  status: string;
  started_at: string;
  finished_at: string | null;
  discovered_hosts: number;
  discovered_vms: number;
  discovered_datastores: number;
  metric_count: number;
  error: string;
}

export interface AuditLog {
  id: number;
  customer: UUID | null;
  customer_name: string;
  actor: number | null;
  actor_email: string;
  action: string;
  target: { type?: string; id?: string; repr?: string };
  target_type: string;
  target_id: string;
  target_repr: string;
  timestamp: string;
  created_at: string;
  ip_address: string | null;
  metadata: JsonObject;
  context: JsonObject;
}

export interface TaskRun {
  id: number;
  customer: UUID | null;
  task_name: string;
  idempotency_key: string;
  celery_task_id: string;
  status: TaskStatus;
  result: JsonObject;
  error: string;
  started_at: string | null;
  finished_at: string | null;
}

export interface Report {
  id: number;
  kind: string;
  status: TaskStatus;
  parameters: JsonObject;
  result: JsonObject;
  artifact_path: string;
  requested_at: string;
  completed_at: string | null;
}

export interface ReportRequest {
  kind: string;
  idempotency_key?: string;
}

export interface TaskQueuedResponse {
  task_id: string;
  status: "queued";
}

export interface RealtimeEvent {
  sequence: number;
  event_type:
    | "machine.online"
    | "machine.offline"
    | "metric.update"
    | "alert.created"
    | "alert.updated"
    | "anomaly.detected"
    | string;
  aggregate_id: string;
  payload: JsonObject;
  created_at: string;
}
