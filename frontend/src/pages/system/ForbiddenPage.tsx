import { LockKeyhole } from "lucide-react";
import { useNavigate } from "react-router-dom";
import { Button } from "../../components/common";

export default function ForbiddenPage() {
  const navigate = useNavigate();
  return (
    <section className="forbidden-page">
      <div>
        <span className="error-code">403</span>
        <LockKeyhole aria-hidden />
        <h1>Accès non autorisé</h1>
        <p>
          Votre rôle ne permet pas d’accéder à cette zone. Le serveur reste
          l’autorité finale pour toutes les permissions.
        </p>
        <Button onClick={() => navigate("/dashboard")}>
          Revenir à la vue globale
        </Button>
      </div>
    </section>
  );
}
