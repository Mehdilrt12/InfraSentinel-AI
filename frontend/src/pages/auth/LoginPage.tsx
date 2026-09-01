import {
  Activity,
  ArrowRight,
  BrainCircuit,
  CloudCog,
  Eye,
  EyeOff,
  LockKeyhole,
  Mail,
  ServerCog,
  ShieldCheck,
} from "lucide-react";
import { useState, type FormEvent } from "react";
import { Link, Navigate, useLocation, useNavigate } from "react-router-dom";
import { apiProblem } from "../../api/client";
import { useAuth } from "../../auth/AuthProvider";
import {
  Badge,
  Button,
  Field,
  IconButton,
  Input,
} from "../../components/common";

export default function LoginPage() {
  const { user, login, sessionExpired } = useAuth();
  const location = useLocation();
  const navigate = useNavigate();
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [showPassword, setShowPassword] = useState(false);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  if (user) return <Navigate to="/dashboard" replace />;

  const submit = async (event: FormEvent) => {
    event.preventDefault();
    setError(null);
    setLoading(true);
    try {
      await login(email.trim(), password);
      const destination =
        (location.state as { from?: { pathname?: string } } | null)?.from
          ?.pathname || "/dashboard";
      navigate(destination, { replace: true });
    } catch (reason) {
      const problem = apiProblem(reason);
      setError(
        problem.status === 401
          ? "Email ou mot de passe incorrect."
          : problem.detail,
      );
    } finally {
      setLoading(false);
    }
  };

  return (
    <main className="auth-page">
      <section
        className="auth-visual"
        aria-label="Présentation InfraSentinel AI"
      >
        <div className="auth-visual__content">
          <div className="auth-visual__mark">
            <Activity aria-hidden />
          </div>
          <span className="eyebrow">Infrastructure intelligence</span>
          <h1>
            InfraSentinel <span>AI</span>
          </h1>
          <p>
            Une vision centralisée et proactive de vos environnements Windows,
            VMware et Hyper-V, enrichie par la détection d’anomalies et
            l’analyse prédictive.
          </p>
          <div className="auth-signals">
            <Badge tone="windows">
              <ServerCog aria-hidden /> Windows
            </Badge>
            <Badge tone="vmware">
              <CloudCog aria-hidden /> VMware
            </Badge>
            <Badge tone="hyperv">
              <ShieldCheck aria-hidden /> Hyper-V
            </Badge>
            <Badge tone="ml">
              <BrainCircuit aria-hidden /> Isolation Forest
            </Badge>
          </div>
        </div>
      </section>
      <section className="auth-panel">
        <div className="auth-card">
          <span className="eyebrow">Accès sécurisé</span>
          <h2>Bienvenue sur le NOC</h2>
          <p>
            Connectez-vous avec votre compte InfraSentinel. Le refresh token
            reste protégé dans un cookie HttpOnly.
          </p>
          {(sessionExpired ||
            (location.state as { expired?: boolean } | null)?.expired) &&
            !error && (
              <div className="inline-notice inline-notice--warning">
                <LockKeyhole aria-hidden />
                <span>Votre session a expiré. Veuillez vous reconnecter.</span>
              </div>
            )}
          {error && (
            <div className="auth-error" role="alert">
              <ShieldCheck aria-hidden />
              <div>
                <strong>Connexion refusée</strong>
                <div>{error}</div>
              </div>
            </div>
          )}
          <form className="auth-form" onSubmit={submit}>
            <Field label="Adresse email" required>
              <div className="input-with-icon">
                <Mail aria-hidden />
                <Input
                  type="email"
                  autoComplete="email"
                  value={email}
                  onChange={(event) => setEmail(event.target.value)}
                  placeholder="administrateur@entreprise.ma"
                  required
                  autoFocus
                />
              </div>
            </Field>
            <Field label="Mot de passe" required>
              <div className="input-with-icon input-with-icon--action">
                <LockKeyhole aria-hidden />
                <Input
                  type={showPassword ? "text" : "password"}
                  autoComplete="current-password"
                  value={password}
                  onChange={(event) => setPassword(event.target.value)}
                  minLength={8}
                  required
                />
                <IconButton
                  type="button"
                  variant="ghost"
                  icon={showPassword ? EyeOff : Eye}
                  label={
                    showPassword
                      ? "Masquer le mot de passe"
                      : "Afficher le mot de passe"
                  }
                  onClick={() => setShowPassword((value) => !value)}
                />
              </div>
            </Field>
            <Button type="submit" size="lg" loading={loading} icon={ArrowRight}>
              Se connecter
            </Button>
          </form>
          {import.meta.env.VITE_PUBLIC_REGISTRATION_ENABLED === "true" && (
            <p className="auth-footer">
              Pas encore de compte ?{" "}
              <Link to="/register">Créer un espace client</Link>
            </p>
          )}
        </div>
      </section>
    </main>
  );
}
