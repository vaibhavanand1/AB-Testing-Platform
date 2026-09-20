import React from "react";
import { PlusCircle, ArrowRight, FlaskConical, Calendar, CheckCircle2 } from "lucide-react";

export function ExperimentList({ experiments, onSelectExperiment, onNavigateCreate }) {
  if (experiments.length === 0) {
    return (
      <div className="state-box">
        <FlaskConical size={48} style={{ margin: "0 auto 1rem", opacity: 0.5 }} />
        <h3>No experiments yet</h3>
        <p style={{ marginBottom: "1.5rem" }}>
          Launch your first A/B test to start routing traffic and evaluating conversions.
        </p>
        <button className="btn btn-primary" onClick={onNavigateCreate}>
          <PlusCircle size={16} /> Create Experiment
        </button>
      </div>
    );
  }

  return (
    <div>
      <div className="page-header">
        <div>
          <h1 className="page-title">Experiments</h1>
          <p className="page-subtitle">
            Manage your running tests, traffic splits, and statistical evaluations.
          </p>
        </div>
        <button className="btn btn-primary" onClick={onNavigateCreate}>
          <PlusCircle size={16} /> New Experiment
        </button>
      </div>

      <div className="table-container">
        <table>
          <thead>
            <tr>
              <th>ID</th>
              <th>Experiment Name</th>
              <th>Status</th>
              <th>Traffic Allocation</th>
              <th>Created</th>
              <th style={{ textAlign: "right" }}>Action</th>
            </tr>
          </thead>
          <tbody>
            {experiments.map((exp) => (
              <tr key={exp.id}>
                <td style={{ fontFamily: "var(--font-mono)", color: "var(--text-muted)" }}>
                  #{exp.id}
                </td>
                <td style={{ fontWeight: 600 }}>{exp.name}</td>
                <td>
                  <span className={`badge ${exp.status === "active" ? "badge-active" : "badge-completed"}`}>
                    <CheckCircle2 size={12} /> {exp.status}
                  </span>
                </td>
                <td>
                  <div style={{ display: "flex", gap: "0.5rem", flexWrap: "wrap" }}>
                    {exp.variants.map((v, i) => (
                      <span
                        key={i}
                        style={{
                          fontSize: "0.75rem",
                          background: "var(--bg-secondary)",
                          padding: "0.2rem 0.5rem",
                          borderRadius: "4px",
                          border: "1px solid var(--border-subtle)",
                        }}
                      >
                        <strong>{v.name}</strong>: {v.weight}%
                      </span>
                    ))}
                  </div>
                </td>
                <td style={{ color: "var(--text-secondary)", fontSize: "0.8125rem" }}>
                  <div style={{ display: "flex", alignItems: "center", gap: "0.35rem" }}>
                    <Calendar size={14} />
                    {new Date(exp.created_at).toLocaleDateString(undefined, {
                      month: "short",
                      day: "numeric",
                      year: "numeric",
                    })}
                  </div>
                </td>
                <td style={{ textAlign: "right" }}>
                  <button
                    className="btn btn-secondary btn-sm"
                    onClick={() => onSelectExperiment(exp.id)}
                  >
                    View Results <ArrowRight size={14} />
                  </button>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  );
}
