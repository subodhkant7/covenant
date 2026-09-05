-- Agent Organization Runtime SQLite Schema (V1 Hardened)
-- Independent of Covenant domain schemas.

CREATE TABLE IF NOT EXISTS runtime_schema_version (
    version INTEGER PRIMARY KEY,
    applied_at TEXT NOT NULL
);

-- Operational Tasks
CREATE TABLE IF NOT EXISTS tasks (
    id TEXT PRIMARY KEY,
    organization_id TEXT NOT NULL,
    intent TEXT NOT NULL,
    required_role TEXT NOT NULL,
    scope_json TEXT NOT NULL,
    input_payload_json TEXT NOT NULL,
    workflow_run_id TEXT,
    parent_task_id TEXT,
    priority INTEGER DEFAULT 0,
    deadline TEXT,
    status TEXT NOT NULL,
    assigned_agent_id TEXT,
    attempt_count INTEGER DEFAULT 0,
    max_retries INTEGER DEFAULT 3,
    requires_verification INTEGER DEFAULT 0,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
);

-- Operational Agent Runs
CREATE TABLE IF NOT EXISTS agent_runs (
    id TEXT PRIMARY KEY,
    task_id TEXT NOT NULL,
    agent_id TEXT NOT NULL,
    attempt_number INTEGER NOT NULL,
    status TEXT NOT NULL,
    turn_count INTEGER DEFAULT 0,
    started_at TEXT NOT NULL,
    completed_at TEXT,
    error TEXT,
    output_payload_json TEXT,
    completion_summary TEXT,
    FOREIGN KEY(task_id) REFERENCES tasks(id) ON DELETE CASCADE
);

-- Operational Tool Executions (With strict foreign keys for both Task and AgentRun)
CREATE TABLE IF NOT EXISTS tool_executions (
    id TEXT PRIMARY KEY,
    agent_run_id TEXT NOT NULL,
    task_id TEXT NOT NULL,
    tool_name TEXT NOT NULL,
    arguments_json TEXT NOT NULL,
    status TEXT NOT NULL,
    result_json TEXT,
    error TEXT,
    idempotency_key TEXT,
    started_at TEXT NOT NULL,
    completed_at TEXT,
    FOREIGN KEY(task_id) REFERENCES tasks(id) ON DELETE CASCADE,
    FOREIGN KEY(agent_run_id) REFERENCES agent_runs(id) ON DELETE CASCADE
);

-- Operational Human Approvals (Single-use tokens)
CREATE TABLE IF NOT EXISTS human_approvals (
    approval_id TEXT PRIMARY KEY,
    organization_id TEXT NOT NULL,
    task_id TEXT NOT NULL,
    agent_run_id TEXT NOT NULL,
    tool_request_json TEXT NOT NULL,
    policy_decision_id TEXT NOT NULL,
    status TEXT NOT NULL,
    requested_at TEXT NOT NULL,
    timeout_at TEXT,
    modified_arguments_json TEXT,
    reviewed_by TEXT,
    reviewed_at TEXT,
    reviewer_notes TEXT,
    FOREIGN KEY(task_id) REFERENCES tasks(id) ON DELETE CASCADE
);

-- Durable Idempotency Reservations and Results
CREATE TABLE IF NOT EXISTS idempotency_records (
    idempotency_key TEXT PRIMARY KEY,
    tool_name TEXT NOT NULL,
    execution_id TEXT NOT NULL,
    status TEXT NOT NULL, -- 'RESERVED', 'SUCCEEDED', 'FAILED', 'UNKNOWN'
    observation_json TEXT,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
);

-- Immutable Event Audit Stream
CREATE TABLE IF NOT EXISTS events (
    sequence_number INTEGER PRIMARY KEY AUTOINCREMENT,
    event_id TEXT UNIQUE NOT NULL,
    trace_id TEXT NOT NULL,
    parent_event_id TEXT,
    organization_id TEXT NOT NULL,
    task_id TEXT,
    agent_run_id TEXT,
    execution_id TEXT,
    event_type TEXT NOT NULL,
    summary TEXT NOT NULL,
    payload_json TEXT NOT NULL,
    timestamp TEXT NOT NULL
);

-- Indexes for performance, isolation, and causal audit trails
CREATE INDEX IF NOT EXISTS idx_tasks_status ON tasks(status);
CREATE INDEX IF NOT EXISTS idx_tasks_org ON tasks(organization_id);
CREATE INDEX IF NOT EXISTS idx_agent_runs_task ON agent_runs(task_id);
CREATE INDEX IF NOT EXISTS idx_tool_executions_task ON tool_executions(task_id);
CREATE INDEX IF NOT EXISTS idx_tool_executions_run ON tool_executions(agent_run_id);
CREATE INDEX IF NOT EXISTS idx_approvals_task ON human_approvals(task_id);
CREATE INDEX IF NOT EXISTS idx_approvals_status ON human_approvals(status);
CREATE INDEX IF NOT EXISTS idx_events_trace ON events(trace_id);
CREATE INDEX IF NOT EXISTS idx_events_task ON events(task_id);
CREATE INDEX IF NOT EXISTS idx_events_run ON events(agent_run_id);
CREATE INDEX IF NOT EXISTS idx_events_execution ON events(execution_id);
CREATE INDEX IF NOT EXISTS idx_events_timestamp ON events(timestamp);
