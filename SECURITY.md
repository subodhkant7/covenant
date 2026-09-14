# Security Policy

## Reporting Security Vulnerabilities

The Covenant engineering team takes security seriously. If you discover a potential vulnerability, please do **not** disclose it publicly via a GitHub issue or discussion.

Instead, please report security vulnerabilities privately via **[GitHub Private Security Advisories](https://github.com/subodhkant7/covenant/security/advisories/new)**.

When reporting an issue, please include:
- A description of the vulnerability and potential impact
- Clear steps to reproduce or a minimal proof of concept
- Any potential mitigations you have identified

We appreciate your cooperation in practicing coordinated disclosure.

---

## Supported Versions

Only the latest commit on the `main` branch of the canonical public repository (`https://github.com/subodhkant7/covenant`) is actively supported for security updates and bug fixes:

| Version / Branch | Supported | Notes |
| :--- | :---: | :--- |
| `main` | :white_check_mark: | Active development & hackathon submission branch |
| Prior release tags | :x: | Not actively backported |

---

## Security Architecture & Runtime Invariants

Covenant is built with strict runtime governance separating agentic intelligence from authority:

1. **Authority Separation**: Strands LLM agents do not execute actions or transition state machines directly. They propose structured remediation actions to a deterministic, non-bypassable runtime.
2. **Policy Invariants**: High-risk or destructive actions (such as counterparty outreach or contractual breach notices) are non-bypassably gated behind human approval (`HumanApprovalRequest`).
3. **Execution is Not Fulfillment**: Completing an outbound action (e.g. sending an email or dispatching an API call) does not mark a commitment as resolved. Resolution strictly requires independent counterparty proof timestamped *after* action dispatch ($T_{\text{proof}} > T_{\text{exec}}$).
4. **Sanitization**: Inbound external evidence and tool parameters are sanitized to prevent secret leaks, shell injection, or prompt injection from altering policy evaluations.

---

## Synthetic Data & Zero-Credential Guarantee

- **Synthetic Dataset**: All enterprise data included in this repository (emails, Jira tickets, contracts, and vendor logs for **Northstar Studio**, **Meridian Global**, **Apex Industrial**, and other counterparties) is **100% synthetic**. All names, email addresses, project codes, and financial amounts are fictional.
- **Credential Hygiene**: This repository does not contain real cloud credentials, API keys, private keys, or internal network tokens.
- **Offline Safety**: Covenant executes in an offline-first deterministic mode by default. Zero external network calls or cloud services are required to run the application, test suite, or demonstration scenarios.
