import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { act, render, screen } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import type { RealtimeEvent } from "../types/api";
import { ToastProvider } from "../components/common";
import { RealtimeProvider, useRealtime } from "./RealtimeProvider";

const mocks = vi.hoisted(() => ({
  get: vi.fn(),
  post: vi.fn(),
  hasAccessToken: vi.fn(() => true),
}));

vi.mock("../api/client", () => ({
  API_BASE_URL: "/api",
  api: { get: mocks.get, post: mocks.post },
  hasAccessToken: mocks.hasAccessToken,
}));

vi.mock("../auth/AuthProvider", () => ({
  useAuth: () => ({ user: { id: 1, customer: "tenant-a" } }),
}));

class FakeWebSocket {
  static readonly CONNECTING = 0;
  static readonly OPEN = 1;
  static readonly CLOSING = 2;
  static readonly CLOSED = 3;
  static instances: FakeWebSocket[] = [];

  readonly url: string;
  readyState = FakeWebSocket.CONNECTING;
  closed = false;
  onopen: ((event: Event) => void) | null = null;
  onmessage: ((event: MessageEvent) => void) | null = null;
  onclose: ((event: CloseEvent) => void) | null = null;
  onerror: ((event: Event) => void) | null = null;

  constructor(url: string | URL) {
    this.url = String(url);
    FakeWebSocket.instances.push(this);
  }

  open() {
    this.readyState = FakeWebSocket.OPEN;
    this.onopen?.(new Event("open"));
  }

  receive(event: RealtimeEvent) {
    this.onmessage?.(
      new MessageEvent("message", { data: JSON.stringify(event) }),
    );
  }

  serverClose() {
    this.readyState = FakeWebSocket.CLOSED;
    this.onclose?.(new CloseEvent("close"));
  }

  close() {
    this.readyState = FakeWebSocket.CLOSED;
    this.closed = true;
  }
}

const event = (
  sequence: number,
  eventType = "metric.update",
): RealtimeEvent => ({
  sequence,
  event_type: eventType,
  aggregate_id: "machine-1",
  payload: { machine_id: "machine-1" },
  created_at: `2026-08-30T12:00:0${sequence}Z`,
});

function Probe() {
  const realtime = useRealtime();
  return (
    <>
      <output data-testid="status">{realtime.status}</output>
      <output data-testid="sequence">{realtime.lastSequence}</output>
      <output data-testid="events">{realtime.events.length}</output>
    </>
  );
}

function renderRealtime() {
  const queryClient = new QueryClient({
    defaultOptions: { queries: { retry: false } },
  });
  return render(
    <QueryClientProvider client={queryClient}>
      <ToastProvider>
        <RealtimeProvider>
          <Probe />
        </RealtimeProvider>
      </ToastProvider>
    </QueryClientProvider>,
  );
}

async function flushConnection() {
  await act(async () => {
    await Promise.resolve();
    await Promise.resolve();
    await Promise.resolve();
    await Promise.resolve();
  });
}

describe("RealtimeProvider intégré", () => {
  beforeEach(() => {
    vi.useFakeTimers();
    vi.spyOn(Math, "random").mockReturnValue(0.5);
    Object.defineProperty(window.navigator, "onLine", {
      configurable: true,
      value: true,
    });
    FakeWebSocket.instances = [];
    vi.clearAllMocks();
    mocks.hasAccessToken.mockReturnValue(true);
    mocks.get.mockResolvedValue({ data: [event(2, "machine.online")] });
    mocks.post.mockResolvedValue({
      data: { ticket: "ticket-court", expires_in: 60 },
    });
  });

  afterEach(() => {
    vi.useRealTimers();
    vi.unstubAllGlobals();
  });

  it("rejoue les événements manqués puis reçoit et déduplique les trames WebSocket", async () => {
    vi.stubGlobal("WebSocket", FakeWebSocket);
    const view = renderRealtime();
    await flushConnection();

    expect(FakeWebSocket.instances).toHaveLength(1);
    const socket = FakeWebSocket.instances[0];
    expect(socket.url).toContain("/ws/events/");
    expect(socket.url).toContain("ticket=ticket-court");
    expect(socket.url).toContain("since=2");
    expect(screen.getByTestId("sequence")).toHaveTextContent("2");
    expect(screen.getByTestId("events")).toHaveTextContent("1");

    act(() => socket.open());
    expect(screen.getByTestId("status")).toHaveTextContent("live");
    act(() => socket.receive(event(3, "alert.created")));
    expect(screen.getByTestId("sequence")).toHaveTextContent("3");
    expect(screen.getByTestId("events")).toHaveTextContent("2");
    act(() => socket.receive(event(3, "alert.created")));
    expect(screen.getByTestId("events")).toHaveTextContent("2");
    expect(
      sessionStorage.getItem("infrasentinel.realtime.tenant-a.sequence"),
    ).toBe("3");
    act(() => socket.receive(event(4, "machine.offline")));
    expect(screen.getByText("Machine hors ligne")).toBeInTheDocument();

    view.unmount();
    expect(socket.closed).toBe(true);
  });

  it("repasse en polling puis recrée une connexion après le backoff", async () => {
    vi.stubGlobal("WebSocket", FakeWebSocket);
    mocks.get.mockResolvedValue({ data: [] });
    const view = renderRealtime();
    await flushConnection();
    const firstSocket = FakeWebSocket.instances[0];
    act(() => firstSocket.open());
    act(() => firstSocket.serverClose());
    expect(screen.getByTestId("status")).toHaveTextContent("polling");

    await act(async () => {
      await vi.advanceTimersByTimeAsync(1_000);
      await Promise.resolve();
      await Promise.resolve();
    });
    expect(FakeWebSocket.instances).toHaveLength(2);
    expect(mocks.post).toHaveBeenCalledTimes(2);

    view.unmount();
    expect(FakeWebSocket.instances[1].closed).toBe(true);
  });
});
