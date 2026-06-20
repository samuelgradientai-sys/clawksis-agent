/**
 * ErrorBoundary — evita que una excepción de render tire TODA la app a blanco.
 *
 * Sin un boundary, cualquier throw en el árbol del chat (p.ej. el parser de
 * Markdown con contenido parcial durante el streaming) desmonta el dashboard
 * entero. Este boundary aísla el fallo y muestra un fallback.
 *
 * `resetKey`: si cambia, el boundary se resetea (útil por mensaje — un parse que
 * falló con texto parcial se recupera cuando llega el siguiente delta).
 */

import { Component, type ErrorInfo, type ReactNode } from "react";

interface Props {
  children: ReactNode;
  fallback?: ReactNode;
  onError?: (error: Error, info: ErrorInfo) => void;
  resetKey?: unknown;
}

interface State {
  error: Error | null;
}

export class ErrorBoundary extends Component<Props, State> {
  state: State = { error: null };

  static getDerivedStateFromError(error: Error): State {
    return { error };
  }

  componentDidCatch(error: Error, info: ErrorInfo) {
    console.error("[ErrorBoundary]", error, info.componentStack);
    this.props.onError?.(error, info);
  }

  componentDidUpdate(prev: Props) {
    if (prev.resetKey !== this.props.resetKey && this.state.error) {
      this.setState({ error: null });
    }
  }

  render() {
    if (this.state.error) {
      return (
        this.props.fallback ?? (
          <div className="flex items-center justify-center p-4 text-xs text-muted-foreground">
            Algo falló al renderizar esto. El resto del panel sigue funcionando.
          </div>
        )
      );
    }
    return this.props.children;
  }
}
