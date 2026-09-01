import { Component, type ErrorInfo, type ReactNode } from "react";
import { AlertTriangle } from "lucide-react";
import { Button } from "../components/common";

interface State {
  failed: boolean;
}

export class ErrorBoundary extends Component<{ children: ReactNode }, State> {
  state: State = { failed: false };
  static getDerivedStateFromError(): State {
    return { failed: true };
  }
  componentDidCatch(_error: Error, _info: ErrorInfo) {
    /* Never render stack traces or payloads to the user. */
  }
  render() {
    if (!this.state.failed) return this.props.children;
    return (
      <main className="fatal-error">
        <AlertTriangle aria-hidden />
        <h1>L’interface a rencontré une erreur</h1>
        <p>
          Vos données et votre session n’ont pas été affichées dans ce message.
          Rechargez le module pour réessayer.
        </p>
        <Button onClick={() => window.location.reload()}>
          Recharger l’application
        </Button>
      </main>
    );
  }
}
