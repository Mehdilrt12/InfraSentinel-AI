import type { Metric } from "../types/api";
import {
  metricDimension,
  metricSeriesLabel,
  normalizeUnit,
  toBaseValue,
} from "./format";

export interface ChartSeries {
  identity: string;
  dataKey: string;
  label: string;
}
export interface ChartPoint {
  timestamp: string;
  time: string;
  [key: string]: string | number | Metric | undefined;
}
export interface MetricChartGroup {
  key: string;
  title: string;
  unit: string;
  rawUnit: string;
  factor: number;
  series: ChartSeries[];
  data: ChartPoint[];
}

const GROUPS: Record<string, { key: string; title: string }> = {
  "%": { key: "percent", title: "Utilisation" },
  bytes: { key: "storage", title: "Capacité" },
  "bytes/s": { key: "throughput", title: "Débits" },
  "bits/s": { key: "bitrate", title: "Débits réseau" },
  ms: { key: "latency", title: "Latence" },
  seconds: { key: "duration", title: "Disponibilité" },
  count: { key: "count", title: "Comptages" },
  "°C": { key: "temperature", title: "Température" },
  frequency: { key: "frequency", title: "Fréquence" },
  state: { key: "state", title: "État opérationnel" },
};

function chartScale(unit: string, maximum: number) {
  if (unit === "bytes" || unit === "bytes/s") {
    const suffix = unit === "bytes/s" ? "/s" : "";
    for (const [factor, label] of [
      [1024 ** 4, `To${suffix}`],
      [1024 ** 3, `Go${suffix}`],
      [1024 ** 2, `Mo${suffix}`],
      [1024, `Ko${suffix}`],
    ] as const)
      if (maximum >= factor) return { factor, unit: label };
    return { factor: 1, unit: `o${suffix}` };
  }
  if (unit === "bits/s") {
    for (const [factor, label] of [
      [1000 ** 3, "Gb/s"],
      [1000 ** 2, "Mb/s"],
      [1000, "Kb/s"],
    ] as const)
      if (maximum >= factor) return { factor, unit: label };
    return { factor: 1, unit: "b/s" };
  }
  if (unit === "seconds")
    return maximum >= 86_400
      ? { factor: 86_400, unit: "j" }
      : maximum >= 3_600
        ? { factor: 3_600, unit: "h" }
        : maximum >= 60
          ? { factor: 60, unit: "min" }
          : { factor: 1, unit: "s" };
  return { factor: 1, unit: ["count", "state"].includes(unit) ? "" : unit };
}

export function latestMetrics(metrics: Metric[]) {
  const map = new Map<string, Metric>();
  for (const metric of metrics) {
    const key = `${metric.machine}|${metric.metric_name}|${metricDimension(metric)}`;
    const current = map.get(key);
    if (!current || new Date(metric.timestamp) > new Date(current.timestamp))
      map.set(key, metric);
  }
  return [...map.values()].sort((a, b) =>
    metricSeriesLabel(a).localeCompare(metricSeriesLabel(b), "fr"),
  );
}

export function buildMetricChartGroups(metrics: Metric[]): MetricChartGroup[] {
  const groups = new Map<
    string,
    {
      key: string;
      title: string;
      rawUnit: string;
      metrics: (Metric & { value: number; identity: string })[];
    }
  >();
  for (const metric of metrics) {
    const value = toBaseValue(metric.metric_value, metric.unit);
    if (value === null || !metric.timestamp) continue;
    const rawUnit = normalizeUnit(metric.unit);
    const definition = GROUPS[rawUnit] || {
      key: `other:${rawUnit || "value"}`,
      title: "Autres mesures",
    };
    if (!groups.has(definition.key))
      groups.set(definition.key, { ...definition, rawUnit, metrics: [] });
    groups.get(definition.key)!.metrics.push({
      ...metric,
      value,
      identity: `${metric.metric_name}|${metricDimension(metric)}`,
    });
  }
  return [...groups.values()].map((group) => {
    const identities = [
      ...new Set(group.metrics.map((metric) => metric.identity)),
    ];
    const series = identities.map((identity, index) => ({
      identity,
      dataKey: `series_${index}`,
      label: metricSeriesLabel(
        group.metrics.find((metric) => metric.identity === identity)!,
      ),
    }));
    const maximum = Math.max(
      0,
      ...group.metrics.map((metric) => Math.abs(metric.value)),
    );
    const scale = chartScale(group.rawUnit, maximum);
    const rows = new Map<string, ChartPoint>();
    for (const metric of group.metrics.sort(
      (a, b) => Date.parse(a.timestamp) - Date.parse(b.timestamp),
    )) {
      const timestamp = new Date(metric.timestamp).toISOString();
      const row = rows.get(timestamp) || {
        timestamp,
        time: new Date(metric.timestamp).toLocaleTimeString("fr-FR", {
          hour: "2-digit",
          minute: "2-digit",
        }),
      };
      const item = series.find(
        (candidate) => candidate.identity === metric.identity,
      )!;
      row[item.dataKey] = metric.value / scale.factor;
      row[`${item.dataKey}_metric`] = metric;
      rows.set(timestamp, row);
    }
    return {
      key: group.key,
      title: group.title,
      unit: scale.unit,
      rawUnit: group.rawUnit,
      factor: scale.factor,
      series,
      data: [...rows.values()].slice(-100),
    };
  });
}
