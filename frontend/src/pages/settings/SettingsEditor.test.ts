import { describe, expect, it } from "vitest";
import { buildConnectorBody, buildEnvironmentBody } from "./SettingsEditor";

function form(values: Record<string, string>) {
  const data = new FormData();
  Object.entries(values).forEach(([key, value]) => data.set(key, value));
  return data;
}

describe("payloads de configuration non destructifs", () => {
  it("n’écrase pas les métadonnées d’un environnement pendant un PATCH", () => {
    const body = buildEnvironmentBody(
      form({ name: "Production Windows", kind: "WINDOWS" }),
    );
    expect(body).toEqual({ name: "Production Windows", kind: "WINDOWS" });
    expect(body).not.toHaveProperty("metadata");
  });

  it("n’écrase ni config ni secret existant quand le secret est vide", () => {
    const body = buildConnectorBody(
      form({
        environment: "env-1",
        kind: "VMWARE",
        name: "vCenter principal",
        endpoint: "https://vcenter.example.test/sdk",
        username: "svc-infrasentinel",
        verify_tls: "on",
        timeout_seconds: "30",
        enabled: "on",
        secret_ref: "",
      }),
    );
    expect(body).not.toHaveProperty("config");
    expect(body).not.toHaveProperty("secret_ref");
  });

  it("transmet uniquement une nouvelle référence de secret explicitement saisie", () => {
    const body = buildConnectorBody(
      form({
        environment: "env-1",
        kind: "HYPERV",
        name: "Hyper-V principal",
        endpoint: "hyperv.example.test",
        username: "svc-infrasentinel",
        timeout_seconds: "30",
        secret_ref: "INFRASENTINEL_CONNECTOR_HYPERV_SECRET",
      }),
    );
    expect(body.secret_ref).toBe("INFRASENTINEL_CONNECTOR_HYPERV_SECRET");
  });
});
