import React from "react";
import ReactDOM from "react-dom/client";
import { QueryClient, QueryClientProvider, useQuery } from "@tanstack/react-query";

import "@fontsource-variable/plus-jakarta-sans";
import "@fontsource/inter/400.css";
import "@fontsource/inter/500.css";
import "@fontsource/inter/600.css";
import "@fontsource-variable/jetbrains-mono";
import "./styles.css";

import { getHealth } from "./api/client";

const queryClient = new QueryClient();

function HealthVersion() {
  const health = useQuery({
    queryKey: ["health"],
    queryFn: getHealth,
    retry: false,
  });

  if (health.isLoading) {
    return <p className="status">Checking backend health...</p>;
  }

  if (health.isError) {
    return (
      <p className="status error" role="alert">
        Backend health unavailable.
      </p>
    );
  }

  if (!health.data) {
    return <p className="status">Waiting for backend health...</p>;
  }

  return (
    <p className="status" data-testid="health-version">
      Backend version <strong>{health.data.meta.version}</strong>
    </p>
  );
}

function App() {
  return (
    <main className="shell">
      <section className="panel" aria-labelledby="phase-title">
        <p className="eyebrow">DeployWhisper UI Migration</p>
        <h1 id="phase-title">React shell is connected</h1>
        <p className="lede">
          Phase 0 placeholder served by Vite. The full design system starts in Phase 2.
        </p>
        <HealthVersion />
      </section>
    </main>
  );
}

ReactDOM.createRoot(document.getElementById("root") as HTMLElement).render(
  <React.StrictMode>
    <QueryClientProvider client={queryClient}>
      <App />
    </QueryClientProvider>
  </React.StrictMode>,
);
