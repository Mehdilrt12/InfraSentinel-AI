import {
  Activity,
  Bell,
  Bot,
  Boxes,
  BrainCircuit,
  ChevronDown,
  CircleGauge,
  ClipboardList,
  CloudCog,
  FileBarChart2,
  LogOut,
  Menu,
  MonitorCog,
  PanelLeftClose,
  PanelLeftOpen,
  Search,
  Settings,
  ShieldCheck,
  TriangleAlert,
  Users,
  X,
} from "lucide-react";
import { useEffect, useMemo, useState } from "react";
import { NavLink, Outlet, useLocation, useNavigate } from "react-router-dom";
import { useAuth } from "../../auth/AuthProvider";
import { can, roleLabel, type Capability } from "../../auth/permissions";
import { useRealtime } from "../../realtime/RealtimeProvider";
import { formatRelativeTime, formatTimestamp } from "../../utils/format";
import { Badge, IconButton, Tooltip } from "../common";

interface NavigationItem {
  to: string;
  label: string;
  icon: typeof CircleGauge;
  capability?: Capability;
}
const navigation: NavigationItem[] = [
  { to: "/dashboard", label: "Vue globale", icon: CircleGauge },
  { to: "/machines", label: "Machines", icon: MonitorCog },
  { to: "/agents", label: "Agents", icon: Bot },
  { to: "/alerts", label: "Alertes", icon: TriangleAlert },
  { to: "/anomalies", label: "Anomalies", icon: Activity },
  { to: "/predictions", label: "Risques prédictifs", icon: ShieldCheck },
  { to: "/ml", label: "Machine Learning", icon: BrainCircuit },
  { to: "/vmware", label: "VMware", icon: CloudCog },
  { to: "/hyperv", label: "Hyper-V", icon: Boxes },
  {
    to: "/users",
    label: "Utilisateurs / Clients",
    icon: Users,
    capability: "manage:users",
  },
  {
    to: "/audit",
    label: "Audit",
    icon: ClipboardList,
    capability: "read:audit",
  },
  {
    to: "/reports",
    label: "Rapports",
    icon: FileBarChart2,
    capability: "read:reports",
  },
  {
    to: "/settings",
    label: "Configuration",
    icon: Settings,
    capability: "manage:operations",
  },
];

const statusCopy = {
  live: "Temps réel actif",
  connecting: "Connexion…",
  polling: "Mode résilient",
  offline: "Hors connexion",
};
const eventLabels: Record<string, string> = {
  "machine.online": "Machine reconnectée",
  "machine.offline": "Machine hors ligne",
  "alert.created": "Nouvelle alerte",
  "alert.updated": "Alerte mise à jour",
  "anomaly.detected": "Anomalie ML détectée",
};

export function AppShell() {
  const { user, logout } = useAuth();
  const realtime = useRealtime();
  const navigate = useNavigate();
  const location = useLocation();
  const [sidebarOpen, setSidebarOpen] = useState(false);
  const [sidebarCollapsed, setSidebarCollapsed] = useState(false);
  const [notificationsOpen, setNotificationsOpen] = useState(false);
  const [profileOpen, setProfileOpen] = useState(false);
  const [query, setQuery] = useState("");

  useEffect(() => {
    if (!sidebarOpen) return;

    const sidebar = document.querySelector<HTMLElement>(".sidebar");
    const previousFocus =
      document.activeElement instanceof HTMLElement
        ? document.activeElement
        : null;
    const previousOverflow = document.body.style.overflow;
    document.body.style.overflow = "hidden";

    const frame = window.requestAnimationFrame(() => {
      sidebar?.querySelector<HTMLButtonElement>(".sidebar__close")?.focus();
    });
    const onKeyDown = (event: KeyboardEvent) => {
      if (event.key === "Escape") {
        event.preventDefault();
        setSidebarOpen(false);
        return;
      }
      if (event.key !== "Tab" || !sidebar) return;

      const focusable = Array.from(
        sidebar.querySelectorAll<HTMLElement>(
          'a[href], button:not([disabled]), [tabindex]:not([tabindex="-1"])',
        ),
      ).filter((element) => element.offsetParent !== null);
      const first = focusable[0];
      const last = focusable.at(-1);
      if (!first || !last) return;
      if (event.shiftKey && document.activeElement === first) {
        event.preventDefault();
        last.focus();
      } else if (!event.shiftKey && document.activeElement === last) {
        event.preventDefault();
        first.focus();
      }
    };
    window.addEventListener("keydown", onKeyDown);

    return () => {
      window.cancelAnimationFrame(frame);
      window.removeEventListener("keydown", onKeyDown);
      document.body.style.overflow = previousOverflow;
      previousFocus?.focus();
    };
  }, [sidebarOpen]);

  useEffect(() => {
    if (!notificationsOpen && !profileOpen) return;
    const onKeyDown = (event: KeyboardEvent) => {
      if (event.key !== "Escape") return;
      setNotificationsOpen(false);
      setProfileOpen(false);
    };
    window.addEventListener("keydown", onKeyDown);
    return () => window.removeEventListener("keydown", onKeyDown);
  }, [notificationsOpen, profileOpen]);
  const available = useMemo(
    () =>
      navigation.filter(
        (item) => !item.capability || can(user, item.capability),
      ),
    [user],
  );
  const importantEvents = useMemo(
    () =>
      realtime.events.filter((event) => event.event_type !== "metric.update"),
    [realtime.events],
  );
  const suggestions = query.trim()
    ? available
        .filter((item) =>
          item.label.toLowerCase().includes(query.toLowerCase()),
        )
        .slice(0, 6)
    : [];
  const initials =
    `${user?.first_name?.[0] || ""}${user?.last_name?.[0] || ""}` ||
    user?.email?.[0]?.toUpperCase() ||
    "U";

  const go = (to: string) => {
    setSidebarOpen(false);
    setQuery("");
    navigate(to);
  };
  const handleLogout = async () => {
    await logout();
    navigate("/login", { replace: true });
  };

  return (
    <div className={`app-shell ${sidebarCollapsed ? "sidebar-collapsed" : ""}`}>
      <a className="skip-link" href="#main-content">
        Aller au contenu
      </a>
      <aside
        className={`sidebar ${sidebarOpen ? "is-open" : ""} ${sidebarCollapsed ? "is-collapsed" : ""}`}
        aria-label="Navigation principale"
      >
        <div className="brand">
          <div className="brand__mark">
            <Activity aria-hidden />
          </div>
          <div>
            <strong>InfraSentinel</strong>
            <span>AI</span>
            <small>Operations Intelligence</small>
          </div>
          <IconButton
            className="sidebar__close"
            variant="ghost"
            icon={X}
            label="Fermer le menu"
            onClick={() => setSidebarOpen(false)}
          />
        </div>
        <nav>
          {available.map(({ to, label, icon: Icon }) => (
            <NavLink
              key={to}
              to={to}
              onClick={() => setSidebarOpen(false)}
              className={({ isActive }) =>
                isActive ||
                (to !== "/dashboard" && location.pathname.startsWith(`${to}/`))
                  ? "is-active"
                  : ""
              }
              title={sidebarCollapsed ? label : undefined}
            >
              <Icon aria-hidden />
              <span>{label}</span>
            </NavLink>
          ))}
        </nav>
        <div className="sidebar__footer">
          <div className="avatar" aria-hidden>
            {initials}
          </div>
          <div>
            <strong>{user?.email}</strong>
            <span>
              {user?.is_superuser
                ? "Administrateur plateforme"
                : roleLabel(user?.role)}
            </span>
          </div>
          <IconButton
            className="sidebar__logout"
            variant="ghost"
            icon={LogOut}
            label="Se déconnecter"
            onClick={handleLogout}
          />
          <IconButton
            className="sidebar__collapse"
            variant="ghost"
            icon={sidebarCollapsed ? PanelLeftOpen : PanelLeftClose}
            label={
              sidebarCollapsed
                ? "Déployer la navigation"
                : "Réduire la navigation"
            }
            onClick={() => setSidebarCollapsed((value) => !value)}
          />
        </div>
      </aside>
      {sidebarOpen && (
        <button
          className="sidebar-scrim"
          aria-label="Fermer le menu"
          onClick={() => setSidebarOpen(false)}
        />
      )}

      <div className="app-frame">
        <header className="topbar">
          <IconButton
            className="mobile-menu"
            variant="ghost"
            icon={Menu}
            label="Ouvrir le menu"
            onClick={() => setSidebarOpen(true)}
          />
          <div className="global-search">
            <Search aria-hidden />
            <input
              aria-label="Rechercher une page"
              placeholder="Accéder rapidement à une page…"
              value={query}
              onChange={(event) => setQuery(event.target.value)}
            />
            {suggestions.length > 0 && (
              <div className="search-results">
                {suggestions.map((item) => (
                  <button key={item.to} onClick={() => go(item.to)}>
                    <item.icon aria-hidden />
                    {item.label}
                  </button>
                ))}
              </div>
            )}
          </div>
          <div className="topbar__actions">
            <Tooltip
              label={
                realtime.lastEventAt
                  ? `Dernier événement : ${formatTimestamp(realtime.lastEventAt)}`
                  : "Aucun événement reçu pendant cette session"
              }
            >
              <button
                className={`live-status live-status--${realtime.status}`}
                onClick={realtime.reconnect}
              >
                <span aria-hidden />
                {statusCopy[realtime.status]}
                <small>
                  {realtime.lastEventAt
                    ? formatRelativeTime(realtime.lastEventAt)
                    : "En attente"}
                </small>
              </button>
            </Tooltip>
            <div className="popover-anchor">
              <IconButton
                variant="ghost"
                icon={Bell}
                label="Centre de notifications"
                aria-expanded={notificationsOpen}
                aria-controls="notification-popover"
                aria-haspopup="true"
                onClick={() => {
                  setProfileOpen(false);
                  setNotificationsOpen((value) => !value);
                }}
              />
              {importantEvents.length > 0 && (
                <span className="notification-count">
                  {Math.min(99, importantEvents.length)}
                </span>
              )}
              {notificationsOpen && (
                <div
                  id="notification-popover"
                  className="popover notification-popover"
                >
                  <header>
                    <strong>Événements récents</strong>
                    <Badge
                      tone={realtime.status === "live" ? "success" : "warning"}
                    >
                      {statusCopy[realtime.status]}
                    </Badge>
                  </header>
                  {importantEvents.length ? (
                    <ul>
                      {importantEvents.slice(0, 8).map((event) => (
                        <li key={event.sequence}>
                          <span className="event-dot" />
                          <div>
                            <strong>
                              {eventLabels[event.event_type] ||
                                event.event_type.replace(".", " · ")}
                            </strong>
                            <small title={formatTimestamp(event.created_at)}>
                              {formatRelativeTime(event.created_at)}
                            </small>
                          </div>
                        </li>
                      ))}
                    </ul>
                  ) : (
                    <p className="popover-empty">
                      Aucun événement reçu pendant cette session.
                    </p>
                  )}
                </div>
              )}
            </div>
            <div className="popover-anchor profile-anchor">
              <button
                className="profile-button"
                aria-expanded={profileOpen}
                aria-controls="profile-popover"
                aria-haspopup="menu"
                onClick={() => {
                  setNotificationsOpen(false);
                  setProfileOpen((value) => !value);
                }}
              >
                <span className="avatar">{initials}</span>
                <span>
                  <strong>{user?.first_name || user?.email}</strong>
                  <small>
                    {user?.is_superuser ? "Plateforme" : roleLabel(user?.role)}
                  </small>
                </span>
                <ChevronDown aria-hidden />
              </button>
              {profileOpen && (
                <div id="profile-popover" className="popover profile-popover">
                  <div>
                    <strong>{user?.email}</strong>
                    <small>
                      Client :{" "}
                      {user?.customer
                        ? String(user.customer).slice(0, 8)
                        : "plateforme"}
                    </small>
                  </div>
                  <button onClick={handleLogout}>
                    <LogOut aria-hidden />
                    Se déconnecter
                  </button>
                </div>
              )}
            </div>
          </div>
        </header>
        <main id="main-content" className="main-content" tabIndex={-1}>
          <Outlet />
        </main>
      </div>
    </div>
  );
}
