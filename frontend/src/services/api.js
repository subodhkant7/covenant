const API_BASE = '/api';

export async function fetchStats() {
  const res = await fetch(`${API_BASE}/stats`);
  if (!res.ok) throw new Error('Failed to fetch stats');
  return res.json();
}

export async function fetchCommitments(filters = {}) {
  const params = new URLSearchParams();
  if (filters.status) params.append('status', filters.status);
  if (filters.direction) params.append('direction', filters.direction);
  if (filters.risk) params.append('risk', filters.risk);
  if (filters.q) params.append('q', filters.q);

  const res = await fetch(`${API_BASE}/commitments?${params.toString()}`);
  if (!res.ok) throw new Error('Failed to fetch commitments');
  return res.json();
}

export async function fetchCommitment(id) {
  const res = await fetch(`${API_BASE}/commitments/${id}`);
  if (!res.ok) throw new Error('Failed to fetch commitment');
  return res.json();
}

export async function fetchCommitmentTrace(id) {
  const res = await fetch(`${API_BASE}/commitments/${id}/trace`);
  if (!res.ok) throw new Error('Failed to fetch commitment decision trace');
  return res.json();
}

export async function fetchCommitmentMap() {
  const res = await fetch(`${API_BASE}/map`);
  if (!res.ok) throw new Error('Failed to fetch commitment map');
  return res.json();
}

export async function fetchPendingDecisions() {
  const res = await fetch(`${API_BASE}/decisions`);
  if (!res.ok) throw new Error('Failed to fetch decisions');
  return res.json();
}

export async function approveDecision(actionId, notes = '', editedPayload = null) {
  const res = await fetch(`${API_BASE}/decisions/${actionId}/approve`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ notes, edited_payload: editedPayload }),
  });
  if (!res.ok) throw new Error('Failed to approve decision');
  return res.json();
}

export async function rejectDecision(actionId, notes = '') {
  const res = await fetch(`${API_BASE}/decisions/${actionId}/reject`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ notes }),
  });
  if (!res.ok) throw new Error('Failed to reject decision');
  return res.json();
}

export async function triggerVerification(commitmentId, simulatedParams = {}) {
  const res = await fetch(`${API_BASE}/commitments/${commitmentId}/verify`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ simulated_params: simulatedParams }),
  });
  if (!res.ok) throw new Error('Failed to trigger verification');
  return res.json();
}

export async function simulateReply(commitmentId) {
  const res = await fetch(`${API_BASE}/simulate/reply/${commitmentId}`, {
    method: 'POST',
  });
  if (!res.ok) throw new Error('Failed to simulate client reply');
  return res.json();
}

export async function fetchEvents(limit = 40) {
  const res = await fetch(`${API_BASE}/events?limit=${limit}`);
  if (!res.ok) throw new Error('Failed to fetch events');
  return res.json();
}

export async function triggerScan() {
  const res = await fetch(`${API_BASE}/scan`, { method: 'POST' });
  if (!res.ok) throw new Error('Failed to trigger scan');
  return res.json();
}

export async function triggerMonitoringCycle() {
  const res = await fetch(`${API_BASE}/monitoring/cycles`, { method: 'POST' });
  if (!res.ok) {
    const errorData = await res.json().catch(() => ({}));
    throw new Error(errorData.detail || 'Failed to trigger monitoring cycle');
  }
  return res.json();
}

export async function fetchMonitoringCycle(cycleId) {
  const res = await fetch(`${API_BASE}/monitoring/cycles/${cycleId}`);
  if (!res.ok) throw new Error('Failed to fetch monitoring cycle');
  return res.json();
}

export async function fetchMonitoringCycles(limit = 20) {
  const res = await fetch(`${API_BASE}/monitoring/cycles?limit=${limit}`);
  if (!res.ok) throw new Error('Failed to fetch monitoring cycles');
  return res.json();
}

export async function triggerSeed() {
  const res = await fetch(`${API_BASE}/seed`, { method: 'POST' });
  if (!res.ok) throw new Error('Failed to trigger seed');
  return res.json();
}
