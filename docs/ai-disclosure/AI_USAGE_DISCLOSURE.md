# AI Usage Disclosure

## Project context

DocIntel is an AI-powered document-intelligence application. Its application-level AI
functionality uses the OpenAI API for invoice extraction and, where configured, semantic
embeddings. This is separate from the AI-assisted development process described below.

## AI-assisted development

AI-assisted coding support was used during development for code exploration, debugging,
implementation suggestions, test generation, and documentation drafting. The assistant did
not receive API keys, `.env` files, or other secrets, and no secrets were committed.

The developer remained responsible for:

- interpreting requirements and deciding the implementation scope;
- reviewing source code and proposed changes;
- integrating changes into the existing architecture;
- running and interpreting focused and complete tests;
- verifying benchmark and deployment-readiness results; and
- making final security, reliability, and design decisions.

AI-generated suggestions were not treated as authoritative. Changes were retained only after
review against the repository, its tests, and the required behavior.

## Transparency

The repository includes representative prompt examples and a work log in:

- [`AI_PROMPTS.md`](AI_PROMPTS.md)
- [`AI_ASSISTED_WORK_LOG.md`](AI_ASSISTED_WORK_LOG.md)

The prompt examples are reconstructed summaries unless explicitly identified otherwise; they
are not claimed to be a complete or verbatim transcript.
