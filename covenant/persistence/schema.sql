-- Covenant SQLite Relational Schema V0.1

CREATE TABLE IF NOT EXISTS commitments (
    id TEXT PRIMARY KEY,
    title TEXT NOT NULL,
    description TEXT NOT NULL,
    category TEXT NOT NULL,
    promisor_json TEXT NOT NULL,
    promisee_json TEXT NOT NULL,
    source_references_json TEXT NOT NULL DEFAULT '[]',
    evidence_references_json TEXT NOT NULL DEFAULT '[]',
    created_at TEXT NOT NULL,
    promised_at TEXT,
    due_date TEXT,
    resolution_timestamp TEXT,
    status TEXT NOT NULL,
    risk TEXT NOT NULL,
    confidence REAL NOT NULL DEFAULT 0.9,
    dependencies_json TEXT NOT NULL DEFAULT '[]',
    next_action_json TEXT,
    required_human_approval INTEGER NOT NULL DEFAULT 0,
    action_history_json TEXT NOT NULL DEFAULT '[]',
    verification_requirements_json TEXT NOT NULL DEFAULT '[]',
    verification_result_json TEXT,
    tags_json TEXT NOT NULL DEFAULT '[]',
    metadata_json TEXT NOT NULL DEFAULT '{}',
    obligation_direction TEXT NOT NULL,
    updated_at TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_commitments_status ON commitments(status);
CREATE INDEX IF NOT EXISTS idx_commitments_direction ON commitments(obligation_direction);
CREATE INDEX IF NOT EXISTS idx_commitments_risk ON commitments(risk);
CREATE INDEX IF NOT EXISTS idx_commitments_due_date ON commitments(due_date);

CREATE TABLE IF NOT EXISTS agent_events (
    id TEXT PRIMARY KEY,
    event_id TEXT NOT NULL,
    timestamp TEXT NOT NULL,
    workflow_id TEXT,
    commitment_id TEXT,
    agent_name TEXT NOT NULL,
    event_type TEXT NOT NULL DEFAULT 'ACTION',
    tool_name TEXT,
    action_name TEXT,
    summary TEXT NOT NULL,
    result_status TEXT NOT NULL DEFAULT 'SUCCESS',
    inputs_summary TEXT,
    result_summary TEXT,
    previous_state TEXT,
    new_state TEXT,
    confidence REAL,
    risk TEXT,
    human_required INTEGER NOT NULL DEFAULT 0,
    correlation_id TEXT,
    rationale TEXT,
    metadata_json TEXT NOT NULL DEFAULT '{}'
);

CREATE INDEX IF NOT EXISTS idx_events_timestamp ON agent_events(timestamp DESC);
CREATE INDEX IF NOT EXISTS idx_events_commitment ON agent_events(commitment_id);
CREATE INDEX IF NOT EXISTS idx_events_agent ON agent_events(agent_name);
CREATE INDEX IF NOT EXISTS idx_events_workflow ON agent_events(workflow_id);

CREATE TABLE IF NOT EXISTS monitoring_cycles (
    cycle_id TEXT PRIMARY KEY,
    status TEXT NOT NULL,
    started_at TEXT NOT NULL,
    completed_at TEXT,
    commitments_scanned INTEGER NOT NULL DEFAULT 0,
    commitments_changed INTEGER NOT NULL DEFAULT 0,
    actions_proposed INTEGER NOT NULL DEFAULT 0,
    approval_requests INTEGER NOT NULL DEFAULT 0,
    executions INTEGER NOT NULL DEFAULT 0,
    verifications INTEGER NOT NULL DEFAULT 0,
    resolved INTEGER NOT NULL DEFAULT 0,
    failed INTEGER NOT NULL DEFAULT 0,
    errors_json TEXT NOT NULL DEFAULT '[]',
    summary TEXT,
    metadata_json TEXT NOT NULL DEFAULT '{}'
);

CREATE INDEX IF NOT EXISTS idx_monitoring_cycles_status ON monitoring_cycles(status);
CREATE INDEX IF NOT EXISTS idx_monitoring_cycles_started ON monitoring_cycles(started_at DESC);
