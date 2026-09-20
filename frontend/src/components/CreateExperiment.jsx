import React, { useState } from "react";
import { ArrowLeft, Plus, Trash2, AlertCircle } from "lucide-react";
import { createExperiment } from "../api";

export function CreateExperiment({ onCancel, onSuccess }) {
  const [name, setName] = useState("");
  const [variants, setVariants] = useState([
    { name: "control", weight: 50 },
    { name: "treatment", weight: 50 },
  ]);
  const [error, setError] = useState(null);
  const [submitting, setSubmitting] = useState(false);

  const totalWeight = variants.reduce((sum, v) => sum + (Number(v.weight) || 0), 0);
  const isWeightValid = Math.abs(totalWeight - 100) < 0.01;

  const handleVariantChange = (index, field, value) => {
    const next = [...variants];
    next[index][field] = field === "weight" ? Number(value) : value;
    setVariants(next);
  };

  const handleAddVariant = () => {
    const nextNum = variants.length + 1;
    setVariants([...variants, { name: `variant_${nextNum}`, weight: 0 }]);
  };

  const handleRemoveVariant = (index) => {
    if (variants.length <= 2) return;
    setVariants(variants.filter((_, i) => i !== index));
  };

  const handleSubmit = async (e) => {
    e.preventDefault();
    setError(null);

    if (!name.trim()) {
      setError("Please provide an experiment name.");
      return;
    }

    if (!isWeightValid) {
      setError(`Variant weights must sum exactly to 100% (currently ${totalWeight}%).`);
      return;
    }

    setSubmitting(true);
    try {
      const created = await createExperiment({
        name: name.trim(),
        variants: variants.map((v) => ({
          name: v.name.trim().toLowerCase(),
          weight: Number(v.weight),
        })),
      });
      onSuccess(created.id);
    } catch (err) {
      setError(err.message || "Failed to create experiment");
    } finally {
      setSubmitting(false);
    }
  };

  return (
    <div style={{ maxWidth: "680px", margin: "0 auto" }}>
      <button
        className="btn btn-secondary btn-sm"
        onClick={onCancel}
        style={{ marginBottom: "1.5rem" }}
      >
        <ArrowLeft size={14} /> Back to Experiments
      </button>

      <div className="card">
        <h2 style={{ fontSize: "1.25rem", fontWeight: 700, marginBottom: "0.5rem" }}>
          Create New Experiment
        </h2>
        <p style={{ color: "var(--text-secondary)", fontSize: "0.875rem", marginBottom: "1.5rem" }}>
          Define experiment parameters, test variants, and traffic distribution weights.
        </p>

        {error && (
          <div
            style={{
              display: "flex",
              alignItems: "center",
              gap: "0.5rem",
              background: "var(--error-bg)",
              border: "1px solid var(--error-border)",
              color: "var(--error-text)",
              padding: "0.75rem 1rem",
              borderRadius: "var(--radius-md)",
              marginBottom: "1.5rem",
              fontSize: "0.875rem",
            }}
          >
            <AlertCircle size={16} />
            <span>{error}</span>
          </div>
        )}

        <form onSubmit={handleSubmit}>
          <div className="form-group">
            <label htmlFor="exp-name">Experiment Name</label>
            <input
              id="exp-name"
              type="text"
              placeholder="e.g. New Checkout Button CTA"
              value={name}
              onChange={(e) => setName(e.target.value)}
              required
            />
          </div>

          <div style={{ marginTop: "1.5rem", marginBottom: "1.5rem" }}>
            <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: "0.75rem" }}>
              <label style={{ margin: 0 }}>Variants & Traffic Split</label>
              <button
                type="button"
                className="btn btn-secondary btn-sm"
                onClick={handleAddVariant}
              >
                <Plus size={14} /> Add Variant
              </button>
            </div>

            {variants.map((v, i) => (
              <div key={i} className="variant-row">
                <input
                  type="text"
                  placeholder="Variant name"
                  value={v.name}
                  onChange={(e) => handleVariantChange(i, "name", e.target.value)}
                  required
                />
                <div style={{ position: "relative" }}>
                  <input
                    type="number"
                    min="1"
                    max="100"
                    placeholder="Weight"
                    value={v.weight}
                    onChange={(e) => handleVariantChange(i, "weight", e.target.value)}
                    required
                  />
                  <span
                    style={{
                      position: "absolute",
                      right: "10px",
                      top: "50%",
                      transform: "translateY(-50%)",
                      color: "var(--text-muted)",
                      fontSize: "0.8125rem",
                    }}
                  >
                    %
                  </span>
                </div>
                {variants.length > 2 ? (
                  <button
                    type="button"
                    onClick={() => handleRemoveVariant(i)}
                    style={{
                      background: "transparent",
                      border: "none",
                      color: "var(--text-muted)",
                      cursor: "pointer",
                      padding: "0.5rem",
                    }}
                  >
                    <Trash2 size={16} />
                  </button>
                ) : (
                  <div />
                )}
              </div>
            ))}

            {/* Split Visualization Bar */}
            <div style={{ marginTop: "1rem" }}>
              <div style={{ display: "flex", justifyContent: "space-between", fontSize: "0.8125rem", color: isWeightValid ? "var(--text-secondary)" : "var(--warning-text)" }}>
                <span>Total Traffic Allocation</span>
                <span style={{ fontWeight: 600 }}>{totalWeight}% / 100%</span>
              </div>
              <div className="progress-bar-container">
                {variants.map((v, i) => {
                  const colors = ["#3b82f6", "#8b5cf6", "#10b981", "#f59e0b"];
                  return (
                    <div
                      key={i}
                      className="progress-segment"
                      style={{
                        width: `${Math.max(0, Math.min(100, v.weight))}%`,
                        backgroundColor: colors[i % colors.length],
                      }}
                      title={`${v.name}: ${v.weight}%`}
                    />
                  );
                })}
              </div>
            </div>
          </div>

          <div style={{ display: "flex", justifyContent: "flex-end", gap: "0.75rem", marginTop: "2rem" }}>
            <button type="button" className="btn btn-secondary" onClick={onCancel} disabled={submitting}>
              Cancel
            </button>
            <button type="submit" className="btn btn-primary" disabled={submitting || !isWeightValid}>
              {submitting ? "Creating..." : "Launch Experiment"}
            </button>
          </div>
        </form>
      </div>
    </div>
  );
}
