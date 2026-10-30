---
inclusion: always
---
# Tech conventions

- Language: TypeScript (strict) unless a feature clearly needs otherwise.
- Keep dependencies minimal and well-known; record any new dependency and why in the relevant spec's design.md.
- Every feature starts as a spec in `.kiro/specs/<feature>/` (requirements.md → design.md → tasks.md) before code is written.
- Write tests alongside code; use property-based tests (fast-check) for any state machine, parser or transformation logic.
- No secrets in the repo. Use `.env` (gitignored) and document variables in `.env.example`.
- Never add `.kiro/` to `.gitignore`.
