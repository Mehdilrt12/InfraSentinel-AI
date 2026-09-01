import { SearchX } from "lucide-react";
import { useNavigate } from "react-router-dom";
import { Button } from "../../components/common";

export default function NotFoundPage() {
  const navigate = useNavigate();
  return (
    <section className="not-found-page">
      <div>
        <span className="error-code">404</span>
        <SearchX aria-hidden />
        <h1>Page introuvable</h1>
        <p>La page demandée n’existe pas ou n’est plus disponible.</p>
        <Button onClick={() => navigate("/dashboard")}>
          Revenir à la vue globale
        </Button>
      </div>
    </section>
  );
}
