import type { Role, User } from "../types/api";

export type Capability =
  | "read:infrastructure"
  | "manage:operations"
  | "manage:users"
  | "read:audit"
  | "read:tasks"
  | "read:reports"
  | "manage:customers";

const ROLE_CAPABILITIES: Record<Role, Capability[]> = {
  ADMIN: [
    "read:infrastructure",
    "manage:operations",
    "manage:users",
    "read:audit",
    "read:tasks",
    "read:reports",
  ],
  SUPERVISOR: [
    "read:infrastructure",
    "manage:operations",
    "read:audit",
    "read:reports",
  ],
  TECHNICIAN: ["read:infrastructure", "read:reports"],
  CLIENT: ["read:infrastructure", "read:reports"],
  VIEWER: ["read:infrastructure", "read:reports"],
};

export function can(user: User | null, capability: Capability) {
  if (!user?.is_active) return false;
  if (user.is_superuser) return true;
  return ROLE_CAPABILITIES[user.role]?.includes(capability) ?? false;
}

export const canManage = (user: User | null) => can(user, "manage:operations");
export const canManageUsers = (user: User | null) => can(user, "manage:users");
export const canReadAudit = (user: User | null) => can(user, "read:audit");

export const roleLabel = (role?: Role) =>
  ({
    ADMIN: "Administrateur",
    SUPERVISOR: "Superviseur",
    TECHNICIAN: "Technicien",
    CLIENT: "Client",
    VIEWER: "Lecture seule",
  })[role || "VIEWER"];
