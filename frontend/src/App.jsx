import React, { useState, useEffect } from "react";
import { FlaskConical, Activity, CheckCircle2, AlertCircle } from "lucide-react";
import { fetchExperiments, fetchHealth } from "./api";
import { ExperimentList } from "./components/ExperimentList";
import { CreateExperiment } from "./components/CreateExperiment";
import { ExperimentDetail } from "./components/ExperimentDetail";

export function App() {
  const [view, setView] = useState("list"); // "list" | "create" | "detail"
  const [selectedExpId, setSelectedExpId] = useState(null);
  const [experiments, setExperiments] = useState([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);
  const [health, setHealth] = useState(null);

  const loadAll = async () => {
    setLoading(true);
    setError(null);
    try {
      const [exps, h] = await Promise.allSettled([
        fetchExperiments(),
        fetchHealth(),
      ]);

      if (exps.status === "fulfilled") {
        setExperiments(exps.value);
      } else {
        setError("Could not connect to FastAPI backend. Is it running on port 8000?");
      }

      if (h.status === "fulfilled") {
        setHealth(h.value);
      } else {
        setHealth({ status: "disconnected" });
      }
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    loadAll();
  }, []);

  const handleSelectExperiment = (id) => {
    setSelectedExpId(id);
    setView("detail");
  };

  const handleCreateSuccess = (id) => {
    loadAll();
    setSelectedExpId(id);
    setView("detail");
  };

  return (
    <div>
      {/* Top Navbar */}
      <nav className="navbar">
        <div
          className="nav-brand"
          onClick={() => {
            setView("list");
            loadAll();
          }}
        >
          <FlaskConical size={24} style={{ stroke: "#3b82f6" }} />
          <span>OptiScale</span>
          <span style={{ fontSize: "0.75rem", color: "var(--text-muted)", fontWeight: 400 }}>
            A/B Testing Platform
          </span>
        </div>

        <div className="nav-actions">
          {health && (
            <div
              style={{
                display: "flex",
                alignItems: "center",
                gap: "0.4rem",
                fontSize: "0.75rem",
                padding: "0.25rem 0.6rem",
                borderRadius: "9999px",
                background: health.status === "ok" ? "var(--success-bg)" : "var(--error-bg)",
                color: health.status === "ok" ? "var(--success-text)" : "var(--error-text)",
                border: `1px solid ${health.status === "ok" ? "var(--success-border)" : "var(--error-border)"}`,
              }}
            >
              {health.status === "ok" ? <CheckCircle2 size={12} /> : <AlertCircle size={12} />}
              <span>API: {health.status === "ok" ? "Online" : "Offline"}</span>
              {health.redis && (
                <span style={{ opacity: 0.75 }}>• Redis: {health.redis}</span>
              )}
            </div>
          )}
        </div>
      </nav>

      {/* Main Container */}
      <main className="container">
        {error && view === "list" && (
          <div
            style={{
              background: "var(--error-bg)",
              border: "1px solid var(--error-border)",
              color: "var(--error-text)",
              padding: "1rem",
              borderRadius: "var(--radius-md)",
              marginBottom: "1.5rem",
              display: "flex",
              alignItems: "center",
              gap: "0.5rem",
            }}
          >
            <AlertCircle size={18} />
            <span>{error}</span>
          </div>
        )}

        {view === "list" && (
          <ExperimentList
            experiments={experiments}
            onSelectExperiment={handleSelectExperiment}
            onNavigateCreate={() => setView("create")}
          />
        )}

        {view === "create" && (
          <CreateExperiment
            onCancel={() => setView("list")}
            onSuccess={handleCreateSuccess}
          />
        )}

        {view === "detail" && selectedExpId && (
          <ExperimentDetail
            experimentId={selectedExpId}
            onBack={() => {
              setView("list");
              loadAll();
            }}
          />
        )}
      </main>
    </div>
  );
}

export default App;
