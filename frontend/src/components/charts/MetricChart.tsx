import {
  CartesianGrid,
  Legend,
  Line,
  LineChart,
  ReferenceLine,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from "recharts";
import { useId } from "react";
import type { MetricChartGroup } from "../../utils/metrics";
import { formatMetric, formatTimestamp, formatValue } from "../../utils/format";
import type { Severity } from "../../types/api";

const COLORS = [
  "#32dec2",
  "#59a8ff",
  "#a978ff",
  "#ffb454",
  "#ff5f7a",
  "#7cd992",
  "#61d6ff",
  "#f18cff",
];

interface ChartThreshold {
  value: number;
  label: string;
  severity: Severity;
}

export function MetricChart({
  group,
  height = 280,
  thresholds = [],
}: {
  group: MetricChartGroup;
  height?: number;
  thresholds?: ChartThreshold[];
}) {
  const descriptionId = `chart-description-${useId().replaceAll(":", "")}`;
  const latest = group.data.at(-1);
  const latestSummary = group.series
    .map((series) => {
      const value = latest?.[series.dataKey];
      return typeof value === "number"
        ? `${series.label} : ${formatValue(value, group.unit)}`
        : `${series.label} : valeur absente`;
    })
    .join("; ");
  return (
    <div className="chart">
      <div className="chart__heading">
        <div>
          <h3>{group.title}</h3>
          <span>Unité harmonisée : {group.unit || "état"}</span>
        </div>
        <span>{group.data.length} points chargés</span>
      </div>
      <p id={descriptionId} className="sr-only">
        {group.title}, {group.data.length} points, unité {group.unit || "état"}.
        Dernières valeurs : {latestSummary || "aucune série"}.
        {thresholds.length
          ? ` Seuils affichés : ${thresholds.map((item) => `${item.label} ${formatValue(item.value, group.rawUnit)}`).join("; ")}.`
          : " Aucun seuil affiché."}
      </p>
      <div role="img" aria-describedby={descriptionId}>
        <ResponsiveContainer width="100%" height={height}>
          <LineChart
            data={group.data}
            margin={{ top: 10, right: 14, bottom: 4, left: 0 }}
          >
            <CartesianGrid
              stroke="var(--border-subtle)"
              strokeDasharray="3 6"
              vertical={false}
            />
            <XAxis
              dataKey="time"
              tick={{ fill: "var(--text-muted)", fontSize: 12 }}
              axisLine={{ stroke: "var(--border)" }}
              tickLine={false}
              minTickGap={32}
            />
            <YAxis
              tick={{ fill: "var(--text-muted)", fontSize: 12 }}
              axisLine={false}
              tickLine={false}
              width={58}
              tickFormatter={(value) =>
                `${new Intl.NumberFormat("fr-FR", { maximumFractionDigits: 1 }).format(value)}${group.unit ? ` ${group.unit}` : ""}`
              }
            />
            <Tooltip
              content={({ active, payload, label }) =>
                active && payload?.length ? (
                  <div className="chart-tooltip">
                    <strong>
                      {formatTimestamp(
                        String(payload[0]?.payload?.timestamp || label),
                      )}
                    </strong>
                    {payload
                      .filter(
                        (item) =>
                          typeof item.dataKey === "string" &&
                          !String(item.dataKey).endsWith("_metric"),
                      )
                      .map((item) => {
                        const metric =
                          item.payload?.[`${String(item.dataKey)}_metric`];
                        return (
                          <div key={String(item.dataKey)}>
                            <span style={{ color: item.color }}>
                              {metric ? formatMetric(metric).label : item.name}
                            </span>
                            <b>
                              {metric
                                ? formatMetric(metric).text
                                : formatValue(item.value, group.unit)}
                            </b>
                          </div>
                        );
                      })}
                  </div>
                ) : null
              }
            />
            <Legend
              formatter={(value) => (
                <span className="chart-legend">{value}</span>
              )}
            />
            {thresholds.map((threshold) => (
              <ReferenceLine
                key={`${threshold.label}-${threshold.value}`}
                y={threshold.value / group.factor}
                stroke={
                  threshold.severity === "CRITICAL" ||
                  threshold.severity === "HIGH"
                    ? "#ff5f7a"
                    : "#ffb454"
                }
                strokeDasharray="6 5"
                label={{
                  value: `${threshold.label} · ${formatValue(threshold.value, group.rawUnit)}`,
                  fill: "var(--text-muted)",
                  fontSize: 11,
                  position: "insideTopRight",
                }}
              />
            ))}
            {group.series.map((series, index) => (
              <Line
                key={series.identity}
                type="monotone"
                dataKey={series.dataKey}
                name={series.label}
                stroke={COLORS[index % COLORS.length]}
                strokeWidth={2}
                dot={false}
                activeDot={{ r: 4 }}
                connectNulls
              />
            ))}
          </LineChart>
        </ResponsiveContainer>
      </div>
    </div>
  );
}

export function MiniTrend({
  data,
  color = "#32dec2",
}: {
  data: { value: number }[];
  color?: string;
}) {
  if (data.length < 2)
    return <span className="mini-trend--empty">Données insuffisantes</span>;
  return (
    <ResponsiveContainer width="100%" height={44}>
      <LineChart data={data}>
        <Line
          type="monotone"
          dataKey="value"
          stroke={color}
          strokeWidth={2}
          dot={false}
        />
      </LineChart>
    </ResponsiveContainer>
  );
}
