import { describe, expect, it } from "vitest";
import { auditDateBoundary } from "./AuditPage";

describe("bornes calendaires du journal d’audit", () => {
  it("inclut la journée entière sélectionnée", () => {
    const start = Date.parse(auditDateBoundary("2026-08-31"));
    const end = Date.parse(auditDateBoundary("2026-08-31", true));
    expect(end - start).toBe(86_399_999);
  });

  it("ignore une date absente ou invalide", () => {
    expect(auditDateBoundary("")).toBe("");
    expect(auditDateBoundary("date-invalide")).toBe("");
  });
});
