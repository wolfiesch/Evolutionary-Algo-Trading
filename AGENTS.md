# Repository Guidelines

This repository hosts the Oil‑Stonks multi‑asset trading platform, with asset‑specific apps in `/crypto` and `/forex` and shared infrastructure in `/shared`. Plans and design docs live in `/docs`, and run / chat logs in `/logs`.

## Project Structure & Modules
- `/crypto`: Crypto trading engine, data, execution, and tests.
- `/forex`: Forex trading entry point and config (early stage).
- `/shared`: Cross‑asset engine, evolution, and risk modules.
- `/docs/plans`: Architecture, phase plans, and research notes.
- `/logs`: Runtime and agent interaction logs (do not commit secrets).

## Build, Test, and Development
- From repo root, develop per system:
  - `cd crypto && python -m pytest`: Run crypto unit tests.
  - `cd crypto && python main.py`: Start the crypto trading app (dev/shadow mode per config).
  - `cd forex && python main.py`: Run the forex placeholder app.
- Use a Python 3.11+ virtualenv and install requirements from each sub‑project (for crypto see `crypto/requirements.txt`).

## Coding Style & Naming
- Python only; use 4‑space indentation and type hints where practical.
- Prefer explicit, descriptive names (`strategy_config`, `backtest_results`) over abbreviations.
- Keep asset‑agnostic logic in `/shared`, and asset‑specific behavior in `/crypto` or `/forex`.

## Testing Guidelines
- Use `pytest` for all tests; crypto tests live in `crypto/tests`.
- Add tests alongside new modules and keep them fast and deterministic (no live network calls).
- When touching shared evolution or risk logic, add or update tests that cover both bullish and bearish regimes where possible.

## Commit & PR Guidelines
- Write clear, present‑tense commit messages (e.g., `Add regime fitness calculator`, `Refactor shared backtester config`).
- Keep PRs scoped: one feature or refactor per PR, with a short summary, key changes, and any risk or rollout notes.
- Link to relevant docs in `/docs/plans` when implementing or changing planned work.

