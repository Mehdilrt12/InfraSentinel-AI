import { describe, expect, it } from "vitest";
import {
  formatByteRate,
  formatBytes,
  formatDuration,
  formatLatency,
  formatMetric,
  formatPercent,
  formatRelativeTime,
  formatValue,
  normalizeUnit,
} from "./format";

describe("formatage des unités de supervision", () => {
  it("convertit les octets vers la grande unité lisible", () =>
    expect(formatBytes(1_073_741_824)).toBe("1 Go"));
  it("limite les débits à une décimale", () =>
    expect(formatByteRate(1_536 * 1024)).toBe("1,5 Mo/s"));
  it("convertit une longue durée", () =>
    expect(formatDuration(187_200)).toBe("2 j 4 h"));
  it("convertit les grandes latences en secondes", () =>
    expect(formatLatency(1_400)).toBe("1,4 s"));
  it("affiche les pourcentages français", () =>
    expect(formatPercent(84.24)).toBe("84,2 %"));
  it("normalise MiB/s puis choisit une unité lisible", () =>
    expect(formatValue(4, "MiB/s")).toBe("4 Mo/s"));
  it("différencie bytes/s et bits/s", () => {
    expect(normalizeUnit("MB/s")).toBe("bytes/s");
    expect(normalizeUnit("Mb/s")).toBe("bits/s");
  });
  it("rend un état de service au lieu d’un nombre", () =>
    expect(
      formatMetric({
        metric_name: "windows.service.state",
        metric_value: 0,
        unit: "state",
        status: "STOPPED",
        metadata: { service_name: "W32Time" },
      }).text,
    ).toBe("STOPPED"));
  it("rend un temps relatif sans masquer la date exacte disponible ailleurs", () =>
    expect(
      formatRelativeTime(
        "2026-08-30T11:59:30Z",
        Date.parse("2026-08-30T12:00:00Z"),
      ),
    ).toBe("Il y a 30 s"));
});
