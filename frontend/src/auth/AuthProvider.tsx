import {
  createContext,
  useCallback,
  useContext,
  useEffect,
  useMemo,
  useState,
  type ReactNode,
} from "react";
import { queryClient } from "../app/queryClient";
import {
  api,
  loginBrowser,
  logoutBrowser,
  onSessionExpired,
  refreshBrowserSession,
  setAccessToken,
} from "../api/client";
import type { User } from "../types/api";

interface RegisterInput {
  organization: string;
  email: string;
  password: string;
}
interface AuthContextValue {
  user: User | null;
  loading: boolean;
  sessionExpired: boolean;
  login: (email: string, password: string) => Promise<void>;
  logout: () => Promise<void>;
  register: (input: RegisterInput) => Promise<void>;
}

const AuthContext = createContext<AuthContextValue | null>(null);

function clearPrivateClientState() {
  queryClient.clear();
  for (const key of Object.keys(sessionStorage)) {
    if (key.startsWith("infrasentinel.realtime."))
      sessionStorage.removeItem(key);
  }
}

export function AuthProvider({ children }: { children: ReactNode }) {
  const [user, setUser] = useState<User | null>(null);
  const [loading, setLoading] = useState(true);
  const [sessionExpired, setSessionExpired] = useState(false);

  const expire = useCallback(() => {
    setAccessToken(null);
    setUser(null);
    setSessionExpired(true);
    clearPrivateClientState();
  }, []);

  useEffect(() => {
    onSessionExpired(expire);
    refreshBrowserSession()
      .then(() => api.get<User>("/auth/me/"))
      .then(({ data }) => {
        setUser(data);
        setSessionExpired(false);
      })
      .catch(() => {
        setAccessToken(null);
        setUser(null);
      })
      .finally(() => setLoading(false));
    return () => onSessionExpired(null);
  }, [expire]);

  const login = useCallback(async (email: string, password: string) => {
    clearPrivateClientState();
    await loginBrowser(email, password);
    const { data } = await api.get<User>("/auth/me/");
    setUser(data);
    setSessionExpired(false);
  }, []);

  const logout = useCallback(async () => {
    try {
      await logoutBrowser();
    } catch {
      /* Une déconnexion locale doit rester possible si l'API est indisponible. */
    } finally {
      setUser(null);
      setSessionExpired(false);
      clearPrivateClientState();
    }
  }, []);

  const register = useCallback(
    async (input: RegisterInput) => {
      await api.post("/auth/register/", input);
      await login(input.email, input.password);
    },
    [login],
  );

  const value = useMemo(
    () => ({ user, loading, sessionExpired, login, logout, register }),
    [user, loading, sessionExpired, login, logout, register],
  );
  return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>;
}

export function useAuth() {
  const context = useContext(AuthContext);
  if (!context) throw new Error("useAuth doit être utilisé dans AuthProvider");
  return context;
}
