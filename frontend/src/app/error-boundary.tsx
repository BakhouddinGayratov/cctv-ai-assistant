import { TriangleAlert } from "lucide-react";
import { Component, type ErrorInfo, type ReactNode } from "react";

interface State {
  error: Error | null;
}

export class ErrorBoundary extends Component<{ children: ReactNode }, State> {
  state: State = { error: null };

  static getDerivedStateFromError(error: Error): State {
    return { error };
  }

  componentDidCatch(error: Error, info: ErrorInfo) {
    console.error("UI xatosi:", error, info.componentStack);
  }

  render() {
    if (!this.state.error) return this.props.children;
    return (
      <div role="alert" className="card mx-auto my-10 max-w-lg p-8 text-center">
        <TriangleAlert className="mx-auto size-10 text-critical" />
        <h2 className="mt-4 text-lg font-semibold">Sahifada xatolik yuz berdi</h2>
        <p className="mt-2 font-mono text-xs text-fg-muted">{this.state.error.message}</p>
        <button
          className="mt-6 rounded-lg bg-brand px-4 py-2 text-sm font-medium text-white"
          onClick={() => this.setState({ error: null })}
        >
          Qayta urinish
        </button>
      </div>
    );
  }
}
