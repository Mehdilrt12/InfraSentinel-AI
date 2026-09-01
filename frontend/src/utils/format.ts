import type { Metric, Role, SourceType } from "../types/api";

const formatter = new Intl.NumberFormat("fr-FR", { maximumFractionDigits: 1 });
const integerFormatter = new Intl.NumberFormat("fr-FR", {
  maximumFractionDigits: 0,
});
const dateFormatter = new Intl.DateTimeFormat("fr-FR", {
  dateStyle: "short",
  timeStyle: "medium",
});

export const hasNumber = (value: unknown): value is number | string =>
  value !== null &&
  value !== undefined &&
  value !== "" &&
  Number.isFinite(Number(value));
export const formatNumber = (value: unknown, digits = 1) =>
  hasNumber(value)
    ? new Intl.NumberFormat("fr-FR", { maximumFractionDigits: digits }).format(
        Number(value),
      )
    : "—";
export const formatCount = (value: unknown) =>
  hasNumber(value) ? integerFormatter.format(Math.round(Number(value))) : "—";

const BYTE_UNITS = ["o", "Ko", "Mo", "Go", "To", "Po"];
const BIT_UNITS = ["b", "Kb", "Mb", "Gb", "Tb", "Pb"];

function scale(value: unknown, units: string[], base: number) {
  if (!hasNumber(value)) return null;
  const numeric = Number(value);
  const index =
    numeric === 0
      ? 0
      : Math.max(
          0,
          Math.min(
            Math.floor(Math.log(Math.abs(numeric)) / Math.log(base)),
            units.length - 1,
          ),
        );
  return {
    value: numeric / base ** index,
    unit: units[index],
    factor: base ** index,
  };
}

export function formatBytes(value: unknown) {
  const result = scale(value, BYTE_UNITS, 1024);
  return result ? `${formatter.format(result.value)} ${result.unit}` : "—";
}

export function formatByteRate(value: unknown) {
  const result = scale(value, BYTE_UNITS, 1024);
  return result ? `${formatter.format(result.value)} ${result.unit}/s` : "—";
}

export function formatBitRate(value: unknown) {
  const result = scale(value, BIT_UNITS, 1000);
  return result ? `${formatter.format(result.value)} ${result.unit}/s` : "—";
}

export function formatPercent(value: unknown, fraction = false) {
  return hasNumber(value)
    ? `${formatter.format(Number(value) * (fraction ? 100 : 1))} %`
    : "—";
}

export function formatLatency(value: unknown, unit = "ms") {
  if (!hasNumber(value)) return "—";
  const milliseconds =
    normalizeUnit(unit) === "seconds" ? Number(value) * 1000 : Number(value);
  return Math.abs(milliseconds) >= 1000
    ? `${formatter.format(milliseconds / 1000)} s`
    : `${formatter.format(milliseconds)} ms`;
}

export function formatDuration(value: unknown, maxParts = 2) {
  if (!hasNumber(value) || Number(value) < 0) return "—";
  let remaining = Math.round(Number(value));
  if (!remaining) return "0 s";
  const result: string[] = [];
  for (const [label, seconds] of [
    ["j", 86_400],
    ["h", 3_600],
    ["min", 60],
    ["s", 1],
  ] as const) {
    const amount = Math.floor(remaining / seconds);
    if (amount) {
      result.push(`${amount} ${label}`);
      remaining -= amount * seconds;
    }
    if (result.length >= maxParts) break;
  }
  return result.join(" ");
}

export function formatTimestamp(value?: string | null) {
  if (!value) return "—";
  const date = new Date(value);
  return Number.isNaN(date.getTime()) ? "—" : dateFormatter.format(date);
}

export function formatRelativeTime(value?: string | null, now = Date.now()) {
  if (!value) return "Jamais";
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return "Date invalide";
  const delta = Math.round((now - date.getTime()) / 1000);
  const abs = Math.abs(delta);
  const text =
    abs < 60
      ? `${abs} s`
      : abs < 3_600
        ? `${Math.floor(abs / 60)} min`
        : abs < 86_400
          ? `${Math.floor(abs / 3_600)} h`
          : abs < 604_800
            ? `${Math.floor(abs / 86_400)} j`
            : formatTimestamp(value);
  return abs >= 604_800 ? text : delta < 0 ? `Dans ${text}` : `Il y a ${text}`;
}

export function normalizeUnit(unit = "") {
  const raw = String(unit).trim();
  const lower = raw.toLowerCase();
  if (["bytes", "byte", "o", "octet", "octets"].includes(lower)) return "bytes";
  if (
    [
      "bytes/s",
      "byte/s",
      "o/s",
      "octets/s",
      "kib/s",
      "mib/s",
      "gib/s",
    ].includes(lower) ||
    (raw.includes("B") && /b\/s$/i.test(raw))
  )
    return "bytes/s";
  if (["bits/s", "bit/s", "bps", "b/s", "kb/s", "mb/s", "gb/s"].includes(lower))
    return "bits/s";
  if (["%", "percent", "percentage"].includes(lower)) return "%";
  if (["ms", "millisecond", "milliseconds"].includes(lower)) return "ms";
  if (["s", "sec", "second", "seconds"].includes(lower)) return "seconds";
  if (["count", "counter", "items", "processes"].includes(lower))
    return "count";
  if (["state", "status", "boolean", "bool"].includes(lower)) return "state";
  if (["°c", "c", "celsius"].includes(lower)) return "°C";
  if (["hz", "khz", "mhz", "ghz"].includes(lower)) return "frequency";
  return raw;
}

export function toBaseValue(value: unknown, unit = "") {
  if (!hasNumber(value)) return null;
  const lower = unit.toLowerCase();
  let numeric = Number(value);
  if (lower === "kib/s") numeric *= 1024;
  if (lower === "mib/s") numeric *= 1024 ** 2;
  if (lower === "gib/s") numeric *= 1024 ** 3;
  if (lower === "kb/s") numeric *= 1000;
  if (lower === "mb/s") numeric *= 1000 ** 2;
  if (lower === "gb/s") numeric *= 1000 ** 3;
  return numeric;
}

export function formatValue(value: unknown, unit = "") {
  const normalized = normalizeUnit(unit);
  const base = toBaseValue(value, unit);
  if (base === null) return "—";
  if (normalized === "bytes") return formatBytes(base);
  if (normalized === "bytes/s") return formatByteRate(base);
  if (normalized === "bits/s") return formatBitRate(base);
  if (normalized === "%") return formatPercent(base);
  if (normalized === "ms") return formatLatency(base);
  if (normalized === "seconds") return formatDuration(base);
  if (normalized === "count") return formatCount(base);
  if (normalized === "state") return base === 1 ? "Actif" : "Inactif";
  if (normalized === "°C") return `${formatter.format(base)} °C`;
  if (normalized === "frequency") {
    let mhz = base;
    const lower = unit.toLowerCase();
    if (lower === "hz") mhz /= 1_000_000;
    if (lower === "khz") mhz /= 1_000;
    if (lower === "ghz") mhz *= 1_000;
    return mhz >= 1_000
      ? `${formatter.format(mhz / 1_000)} GHz`
      : `${formatter.format(mhz)} MHz`;
  }
  return `${formatter.format(base)}${normalized ? ` ${normalized}` : ""}`;
}

export const metricLabels: Record<string, string> = {
  "system.cpu.utilization": "CPU",
  "system.memory.utilization": "Mémoire",
  "system.disk.utilization": "Disque utilisé",
  "system.disk.free": "Disque libre",
  "system.disk.io.read": "Lecture disque",
  "system.disk.io.write": "Écriture disque",
  "system.network.in": "Réseau entrant",
  "system.network.out": "Réseau sortant",
  "system.network.latency": "Latence réseau",
  "system.uptime": "Disponibilité",
  "system.process.count": "Processus",
  "system.gpu.utilization": "GPU",
  "windows.service.state": "Service Windows",
  "virtual.machine.state": "État VM",
  "vmware.datastore.utilization": "Datastore utilisé",
  "machine.online": "Disponibilité machine",
};
export const metricLabel = (name?: string) =>
  metricLabels[name || ""] || String(name || "Mesure").replace(/[._]/g, " ");

export function metricDimension(metric?: Pick<Metric, "metadata">) {
  const metadata = metric?.metadata || {};
  return String(
    metadata.device ||
      metadata.mountpoint ||
      metadata.interface ||
      metadata.service_name ||
      metadata.service ||
      metadata.gpu_name ||
      metadata.datastore ||
      metadata.resource_external_id ||
      "",
  );
}

export function metricSeriesLabel(
  metric: Pick<Metric, "metric_name" | "metadata">,
) {
  const dimension = metricDimension(metric);
  return dimension
    ? `${metricLabel(metric.metric_name)} · ${dimension}`
    : metricLabel(metric.metric_name);
}

export function formatMetric(
  metric: Pick<
    Metric,
    "metric_name" | "metric_value" | "unit" | "status" | "metadata"
  >,
) {
  const state =
    normalizeUnit(metric.unit) === "state" ||
    ["windows.service.state", "virtual.machine.state"].includes(
      metric.metric_name,
    );
  return {
    label: metricSeriesLabel(metric),
    text: state
      ? metric.status || (metric.metric_value === 1 ? "Actif" : "Inactif")
      : formatValue(metric.metric_value, metric.unit),
  };
}

export const sourceLabel = (source?: SourceType | string) =>
  (
    ({
      WINDOWS: "Windows",
      VMWARE: "VMware",
      HYPERV: "Hyper-V",
      MIXED: "Mixte",
    }) as Record<string, string>
  )[String(source || "").toUpperCase()] ||
  source ||
  "—";
export const roleDisplay = (role?: Role) =>
  (
    ({
      ADMIN: "Administrateur",
      SUPERVISOR: "Superviseur",
      TECHNICIAN: "Technicien",
      CLIENT: "Client",
      VIEWER: "Lecture seule",
    }) as Record<string, string>
  )[role || ""] ||
  role ||
  "—";
export const trendLabel = (trend?: string) =>
  (
    ({
      increasing: "Croissante",
      decreasing: "Décroissante",
      stable: "Stable",
      insufficient_data: "Données insuffisantes",
    }) as Record<string, string>
  )[String(trend || "").toLowerCase()] ||
  trend ||
  "Indéterminée";

export function formatRiskLevel(value: unknown) {
  if (!hasNumber(value)) return { label: "Indéterminé", tone: "neutral" };
  const score = Number(value);
  if (score >= 75) return { label: "Critique", tone: "critical" };
  if (score >= 50) return { label: "Élevé", tone: "high" };
  if (score >= 25) return { label: "Modéré", tone: "warning" };
  return { label: "Faible", tone: "success" };
}
