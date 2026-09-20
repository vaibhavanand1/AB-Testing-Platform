const API_BASE_URL = import.meta.env.VITE_API_URL || "http://localhost:8000";

export async function fetchHealth() {
  const res = await fetch(`${API_BASE_URL}/health`);
  if (!res.ok) throw new Error("Health check failed");
  return res.json();
}

export async function fetchExperiments() {
  const res = await fetch(`${API_BASE_URL}/experiments`);
  if (!res.ok) throw new Error("Failed to load experiments");
  return res.json();
}

export async function fetchExperiment(id) {
  const res = await fetch(`${API_BASE_URL}/experiments/${id}`);
  if (!res.ok) throw new Error(`Experiment ${id} not found`);
  return res.json();
}

export async function createExperiment(payload) {
  const res = await fetch(`${API_BASE_URL}/experiments`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(payload),
  });
  if (!res.ok) {
    const err = await res.json().catch(() => ({ detail: "Failed to create experiment" }));
    throw new Error(err.detail || "Failed to create experiment");
  }
  return res.json();
}

export async function assignUser(experimentId, userId) {
  const res = await fetch(
    `${API_BASE_URL}/assign?experiment_id=${encodeURIComponent(experimentId)}&user_id=${encodeURIComponent(userId)}`
  );
  if (!res.ok) throw new Error("Failed to assign user");
  return res.json();
}

export async function trackEvent(experimentId, userId, variant = null, eventType = "conversion") {
  const res = await fetch(`${API_BASE_URL}/events`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({
      experiment_id: experimentId,
      user_id: userId,
      variant,
      event_type: eventType,
    }),
  });
  if (!res.ok) throw new Error("Failed to track event");
  return res.json();
}

export async function fetchExperimentResults(id) {
  const res = await fetch(`${API_BASE_URL}/experiments/${id}/results`);
  if (!res.ok) throw new Error(`Failed to load results for experiment ${id}`);
  return res.json();
}
