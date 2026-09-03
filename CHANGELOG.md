# Changelog

All notable changes to **Chargeback Sentinel** will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [1.0.0] - 2026-08-31
### Added
- Enterprise repository restructuring into modular `src/`, `docs/`, `tests/`, and `.github/` directories.
- Synthetic ML dataset generator with 50000 stratified dispute records and 48 tagged edge cases.
- Explainable Logistic Regression win probability scorer with coefficient transparency.
- Deterministic 3DS/AVS/CVV evidence completeness verifier.
- Node.js Express REST API server providing `/api/disputes`, `/api/metrics`, `/score-dispute`, `/verify-evidence`, and `/draft-response`.
- Web-based dispute analyst copilot dashboard with real-time margin recovery metrics.
- Automated GitHub Actions CI workflow for Node.js and Python test execution.
- Comprehensive Makefile and documentation (`architecture.md`, `api_reference.md`, `ml_pipeline.md`).
