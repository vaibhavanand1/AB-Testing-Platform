import React, { useState, useEffect } from "react";
import {
  ArrowLeft,
  RotateCw,
  TrendingUp,
  Users,
  CheckCircle2,
  AlertTriangle,
  Play,
  ShieldAlert,
  Info,
} from "lucide-react";
import { fetchExperimentResults, assignUser, trackEvent } from "../api";

export function ExperimentDetail({ experimentId, onBack }) {
  const [results, setResults] = useState(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);
  const [simulating, setSimulating] = useState(false);
  const [simMessage, setSimMessage] = useState(null);

  const loadData = async () => {
    setLoading(true);
    setError(null);
    try {
      const data = await fetchExperimentResults(experimentId);
      setResults(data);
    } catch (err) {
      setError(err.message || "Failed to load experiment results");
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    loadData();
  }, [experimentId]);

  const handleSimulate = async (count = 100) => {
    setSimulating(true);
    setSimMessage(`Simulating ${count} visitors with random conversions...`);
    try {
      for (let i = 0; i < count; i++) {
        const uid = `web_sim_${Date.now()}_${i}`;
        const assignment = await assignUser(experimentId, uid);
        const variant = assignment.variant;

        // Simulate 10% conversion for control, 15% for treatment
        const targetRate = variant === "treatment" ? 0.15 : 0.10;
        if (Math.random() < targetRate) {
          await trackEvent(experimentId, uid, variant, "conversion");
        }
      }
      setSimMessage(`Successfully simulated ${count} visitors.`);
      await loadData();
    } catch (err) {
      setSimMessage(`Simulation stopped: ${err.message}`);
    } finally {
      setSimulating(false);
    }
  };

  if (loading && !results) {
    return (
      <div className="state-box">
        <div className="spinner" />
        <p>Loading experiment metrics & statistical tests...</p>
      </div>
    );
  }

  if (error && !results) {
    return (
      <div className="state-box">
        <AlertTriangle size={36} style={{ color: "var(--error-text)", margin: "0 auto 1rem" }} />
        <h3>Failed to load results</h3>
        <p style={{ marginBottom: "1.5rem" }}>{error}</p>
        <button className="btn btn-secondary" onClick={loadData}>
          <RotateCw size={14} /> Retry
        </button>
      </div>
    );
  }

  // Calculate highest conversion rate for chart scaling
  const maxRate = Math.max(
    ...results.variants.map((v) => v.conversion_rate_percentage),
    1.0
  );

  return (
    <div>
      <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: "1.5rem" }}>
        <button className="btn btn-secondary btn-sm" onClick={onBack}>
          <ArrowLeft size={14} /> Back to Experiments
        </button>
        <button className="btn btn-secondary btn-sm" onClick={loadData} disabled={loading}>
          <RotateCw size={14} className={loading ? "spinner" : ""} /> Refresh
        </button>
      </div>

      <div className="page-header">
        <div>
          <div style={{ display: "flex", alignItems: "center", gap: "0.75rem", marginBottom: "0.5rem" }}>
            <h1 className="page-title">{results.experiment_name}</h1>
            <span className={`badge ${results.status === "active" ? "badge-active" : "badge-completed"}`}>
              {results.status}
            </span>
          </div>
          <p className="page-subtitle">
            ID: <span style={{ fontFamily: "var(--font-mono)" }}>#{results.experiment_id}</span> • Two-sample proportion Z-test with peeking guard defense.
          </p>
        </div>
      </div>

      {/* Variant Cards */}
      <div className="metrics-grid">
        {results.variants.map((v) => (
          <div
            key={v.name}
            className={`metric-card ${v.name.toLowerCase() === "control" ? "control" : "treatment"}`}
          >
            <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center" }}>
              <span className="metric-title">{v.name} ({v.weight}%)</span>
              <Users size={16} style={{ color: "var(--text-muted)" }} />
            </div>
            <div className="metric-value">{v.conversion_rate_percentage.toFixed(2)}%</div>
            <div className="metric-subtext">
              <strong>{v.conversions.toLocaleString()}</strong> conversions / <strong>{v.sample_size.toLocaleString()}</strong> visitors
            </div>
          </div>
        ))}
      </div>

      {/* Comparisons & Significance Banner */}
      {results.comparisons.map((comp, idx) => (
        <div key={idx}>
          <div
            className={`significance-banner ${
              comp.peeking_guard_active
                ? "banner-peeking"
                : comp.is_significant
                ? "banner-significant"
                : "banner-insignificant"
            }`}
          >
            {comp.peeking_guard_active ? (
              <ShieldAlert size={24} style={{ flexShrink: 0, marginTop: "2px" }} />
            ) : comp.is_significant ? (
              <CheckCircle2 size={24} style={{ flexShrink: 0, marginTop: "2px" }} />
            ) : (
              <Info size={24} style={{ flexShrink: 0, marginTop: "2px" }} />
            )}
            <div>
              <div style={{ fontWeight: 700, fontSize: "1rem", marginBottom: "0.25rem" }}>
                {comp.peeking_guard_active
                  ? "Peeking Guard Active (Insufficient Sample Size)"
                  : comp.is_significant
                  ? "Statistically Significant Winner Detected"
                  : "No Significant Difference"}
              </div>
              <p style={{ fontSize: "0.875rem", opacity: 0.9 }}>{comp.message}</p>
            </div>
          </div>

          <div className="card">
            <h3 style={{ fontSize: "1.05rem", fontWeight: 600, marginBottom: "1rem" }}>
              Statistical Analysis: {comp.treatment_variant} vs {comp.control_variant}
            </h3>
            <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fit, minmax(180px, 1fr))", gap: "1rem" }}>
              <div>
                <div className="metric-title">Relative Lift</div>
                <div style={{ fontSize: "1.25rem", fontWeight: 700, color: comp.relative_lift_percentage >= 0 ? "var(--success-text)" : "var(--error-text)" }}>
                  {comp.relative_lift_percentage >= 0 ? "+" : ""}{comp.relative_lift_percentage.toFixed(2)}%
                </div>
              </div>
              <div>
                <div className="metric-title">P-Value</div>
                <div style={{ fontSize: "1.25rem", fontWeight: 700 }}>
                  {comp.p_value.toFixed(5)}
                </div>
                <span style={{ fontSize: "0.75rem", color: "var(--text-muted)" }}>Threshold: &alpha; = 0.05</span>
              </div>
              <div>
                <div className="metric-title">Z-Statistic</div>
                <div style={{ fontSize: "1.25rem", fontWeight: 700 }}>
                  {comp.z_score.toFixed(4)}
                </div>
              </div>
              <div>
                <div className="metric-title">95% Confidence Interval</div>
                <div style={{ fontSize: "1.05rem", fontWeight: 600, fontFamily: "var(--font-mono)", marginTop: "0.25rem" }}>
                  [{(comp.confidence_interval[0] * 100).toFixed(2)}%, {(comp.confidence_interval[1] * 100).toFixed(2)}%]
                </div>
              </div>
            </div>
          </div>
        </div>
      ))}

      {/* Visual Bar Chart */}
      <div className="chart-card">
        <h3 style={{ fontSize: "1.05rem", fontWeight: 600 }}>Conversion Rate Comparison</h3>
        <p style={{ color: "var(--text-secondary)", fontSize: "0.8125rem", marginBottom: "1rem" }}>
          Observed conversion rate per variant scaled against max observed rate.
        </p>
        <div className="bar-chart">
          {results.variants.map((v) => {
            const isControl = v.name.toLowerCase() === "control";
            const widthPct = maxRate > 0 ? (v.conversion_rate_percentage / (maxRate * 1.2)) * 100 : 0;
            return (
              <div key={v.name} className="bar-row">
                <div className="bar-label-row">
                  <span>{v.name}</span>
                  <span style={{ fontFamily: "var(--font-mono)" }}>
                    {v.conversion_rate_percentage.toFixed(2)}% ({v.conversions} / {v.sample_size})
                  </span>
                </div>
                <div className="bar-track">
                  <div
                    className={`bar-fill ${isControl ? "bar-fill-control" : "bar-fill-treatment"}`}
                    style={{ width: `${Math.max(2, widthPct)}%` }}
                  />
                </div>
              </div>
            );
          })}
        </div>
      </div>

      {/* Traffic Simulator Panel */}
      <div className="sim-panel">
        <div>
          <div style={{ fontWeight: 600, fontSize: "0.9375rem" }}>Quick Traffic Simulation</div>
          <div style={{ fontSize: "0.8125rem", color: "var(--text-secondary)" }}>
            Inject simulated user traffic directly into this experiment to test live metrics and significance.
          </div>
          {simMessage && (
            <div style={{ fontSize: "0.8125rem", color: "var(--accent-primary)", marginTop: "0.35rem" }}>
              {simMessage}
            </div>
          )}
        </div>
        <div style={{ display: "flex", gap: "0.5rem" }}>
          <button
            className="btn btn-secondary btn-sm"
            onClick={() => handleSimulate(100)}
            disabled={simulating}
          >
            <Play size={12} /> +100 Visitors
          </button>
          <button
            className="btn btn-primary btn-sm"
            onClick={() => handleSimulate(500)}
            disabled={simulating}
          >
            <Play size={12} /> +500 Visitors
          </button>
        </div>
      </div>
    </div>
  );
}
