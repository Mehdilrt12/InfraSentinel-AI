import { describe, expect, it } from "vitest";
import {
  can,
  canManage,
  canManageUsers,
  canReadAudit,
  roleLabel,
} from "./permissions";
import type { Role, User } from "../types/api";

const user = (role: Role, extra: Partial<User> = {}): User => ({
  id: 1,
  email: "user@example.test",
  username: "user",
  first_name: "",
  last_name: "",
  role,
  customer: "tenant-a",
  is_active: true,
  is_superuser: false,
  ...extra,
});

describe("matrice RBAC frontend alignée au backend", () => {
  it("autorise ADMIN à gérer les utilisateurs et lire audit", () => {
    expect(canManageUsers(user("ADMIN"))).toBe(true);
    expect(canReadAudit(user("ADMIN"))).toBe(true);
  });
  it("autorise SUPERVISOR aux opérations mais pas aux utilisateurs", () => {
    expect(canManage(user("SUPERVISOR"))).toBe(true);
    expect(canManageUsers(user("SUPERVISOR"))).toBe(false);
  });
  it.each(["TECHNICIAN", "CLIENT", "VIEWER"] as Role[])(
    "%s reste en lecture seule",
    (role) => {
      expect(can(user(role), "read:infrastructure")).toBe(true);
      expect(can(user(role), "read:reports")).toBe(true);
      expect(canManage(user(role))).toBe(false);
    },
  );
  it("refuse tout à un compte inactif", () =>
    expect(can(user("ADMIN", { is_active: false }), "manage:users")).toBe(
      false,
    ));
  it("accorde les capacités plateforme au superuser actif", () =>
    expect(
      can(user("VIEWER", { is_superuser: true }), "manage:customers"),
    ).toBe(true));
  it("affiche tous les rôles réels", () =>
    expect(roleLabel("TECHNICIAN")).toBe("Technicien"));
});
