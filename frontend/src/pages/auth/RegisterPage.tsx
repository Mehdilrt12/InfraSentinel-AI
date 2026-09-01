import {
  Activity,
  ArrowRight,
  Building2,
  LockKeyhole,
  Mail,
  ShieldCheck,
} from "lucide-react";
import { useMemo, useState, type ChangeEvent, type FormEvent } from "react";
import { Link, Navigate, useNavigate } from "react-router-dom";
import { apiProblem } from "../../api/client";
import { useAuth } from "../../auth/AuthProvider";
import { Badge, Button, Field, Input } from "../../components/common";

export default function RegisterPage() {
  const { user, register } = useAuth();
  const navigate = useNavigate();
  const [form, setForm] = useState({
    organization: "",
    email: "",
    password: "",
    confirm: "",
  });
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const enabled = import.meta.env.VITE_PUBLIC_REGISTRATION_ENABLED === "true";
  const passwordChecks = useMemo(
    () => ({
      length: form.password.length >= 12,
      upper: /[A-Z]/.test(form.password),
      lower: /[a-z]/.test(form.password),
      digit: /\d/.test(form.password),
      special: /[^\w\s]/.test(form.password),
    }),
    [form.password],
  );
  if (user) return <Navigate to="/dashboard" replace />;
  if (!enabled) return <Navigate to="/login" replace />;
  const validPassword =
    Object.values(passwordChecks).every(Boolean) &&
    form.password === form.confirm;
  const submit = async (event: FormEvent) => {
    event.preventDefault();
    if (!validPassword) return;
    setLoading(true);
    setError(null);
    try {
      await register({
        organization: form.organization.trim(),
        email: form.email.trim(),
        password: form.password,
      });
      navigate("/dashboard", { replace: true });
    } catch (reason) {
      setError(apiProblem(reason).detail);
    } finally {
      setLoading(false);
    }
  };
  const update =
    (key: keyof typeof form) => (event: ChangeEvent<HTMLInputElement>) =>
      setForm((current) => ({ ...current, [key]: event.target.value }));
  return (
    <main className="auth-page">
      <section className="auth-visual">
        <div className="auth-visual__content">
          <div className="auth-visual__mark">
            <Activity aria-hidden />
          </div>
          <span className="eyebrow">Isolation multi-client</span>
          <h1>
            Votre infrastructure.
            <br />
            <span>Votre tenant.</span>
          </h1>
          <p>
            Créez l’espace initial de votre organisation. Les ressources seront
            ensuite isolées côté serveur et les agents enrôlés avec des codes à
            usage unique.
          </p>
          <div className="auth-signals">
            <Badge tone="success">
              <ShieldCheck aria-hidden /> Isolation serveur
            </Badge>
          </div>
        </div>
      </section>
      <section className="auth-panel">
        <div className="auth-card">
          <span className="eyebrow">Création client</span>
          <h2>Initialiser l’espace</h2>
          <p>
            L’inscription publique est contrôlée par la configuration du
            serveur.
          </p>
          {error && (
            <div className="auth-error" role="alert">
              <ShieldCheck aria-hidden />
              {error}
            </div>
          )}
          <form className="auth-form" onSubmit={submit}>
            <Field label="Organisation" required>
              <div className="input-with-icon">
                <Building2 aria-hidden />
                <Input
                  value={form.organization}
                  onChange={update("organization")}
                  minLength={2}
                  maxLength={160}
                  required
                />
              </div>
            </Field>
            <Field label="Email administrateur" required>
              <div className="input-with-icon">
                <Mail aria-hidden />
                <Input
                  type="email"
                  value={form.email}
                  onChange={update("email")}
                  autoComplete="email"
                  required
                />
              </div>
            </Field>
            <Field
              label="Mot de passe"
              hint="12 caractères, majuscule, minuscule, chiffre et symbole."
              required
            >
              <div className="input-with-icon">
                <LockKeyhole aria-hidden />
                <Input
                  type="password"
                  value={form.password}
                  onChange={update("password")}
                  autoComplete="new-password"
                  required
                />
              </div>
            </Field>
            <div className="password-checks">
              {Object.entries({
                length: "12 caractères",
                upper: "Une majuscule",
                lower: "Une minuscule",
                digit: "Un chiffre",
                special: "Un symbole",
              }).map(([key, label]) => (
                <span
                  className={
                    passwordChecks[key as keyof typeof passwordChecks]
                      ? "is-valid"
                      : ""
                  }
                  key={key}
                >
                  {label}
                </span>
              ))}
            </div>
            <Field
              label="Confirmer le mot de passe"
              error={
                form.confirm && form.confirm !== form.password
                  ? "Les mots de passe ne correspondent pas."
                  : undefined
              }
              required
            >
              <Input
                type="password"
                value={form.confirm}
                onChange={update("confirm")}
                autoComplete="new-password"
                required
              />
            </Field>
            <Button
              type="submit"
              size="lg"
              loading={loading}
              disabled={!validPassword}
              icon={ArrowRight}
            >
              Créer et se connecter
            </Button>
          </form>
          <p className="auth-footer">
            Déjà inscrit ? <Link to="/login">Revenir à la connexion</Link>
          </p>
        </div>
      </section>
    </main>
  );
}
