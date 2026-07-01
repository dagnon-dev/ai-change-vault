# AI Change Vault

AI Change Vault (`aicv`) is a local-first CLI for versioning AI-generated code changes.
It does not require Git, GitHub, or an external AI API to work in its default mode.

## What it solves

When an AI changes code, the result is not always what the user expected.
`aicv` gives every AI turn a local backup, a structured index entry, searchable metadata, and a reversible snapshot.

## Install

Base install:

```bash
pip install -e .
```

Developer install:

```bash
pip install -e ".[dev]"
```

Semantic search install:

```bash
pip install -e ".[dev,embeddings]"
```

Local embeddings only:

```bash
pip install -e ".[dev,embeddings-local]"
```

OpenAI embeddings only:

```bash
pip install -e ".[dev,embeddings-openai]"
```

## Core flow

1. Create a snapshot before touching files.
2. Make the AI-driven code changes.
3. Validate with tests, lint, or build.
4. Create a second snapshot after validation.
5. Index the turn with request, changed files, and validation result.
6. Search later by turn, file, or request.
7. Revert the full project or a single file if needed.

## Commands

```bash
aicv --version
aicv init
aicv doctor
aicv backup --message "before refactor navbar"
aicv index --turn 1 --request "Change login button color" --files "src/components/Navbar.tsx" --validation "lint + tests OK"
aicv list
aicv search "navbar login"
aicv search --turn turn-1
aicv search --file Navbar.tsx
aicv revert --turn turn-1
aicv revert --turn turn-1 --file src/components/Navbar.tsx
aicv config
aicv embeddings status
aicv embeddings rebuild
```

## What it stores

- Snapshots in `.aicv/backups/`
- Turn documents in `.aicv/rag/turns/`
- Keyword index in `.aicv/rag/index.json`
- Optional turn, diff, and snippet embedding vectors in `.aicv/rag/embeddings.json`
- Human-readable session log in `AI_SESSION_LOG.md`

## How AI agents should use it

Any coding agent can adopt the same protocol:

1. Read `scripts/AI_INSTRUCTIONS.md` before editing.
2. Run `aicv backup --message "before: <task>"`.
3. Make the requested changes.
4. Validate the result.
5. Run `aicv backup --message "after: <summary>"`.
6. Run `aicv index ...` with the original request, files changed, validation, and backup paths.
7. Use `aicv search` to find earlier changes and `aicv revert` to restore a prior state.

## Search modes

`aicv` uses a hybrid retrieval model:

- **Keyword search** is always available.
- **Embeddings** are optional and only used when configured.

Keyword search is exact and fast.
Embeddings improve semantic recall, for example when the user asks for "header spacing" and the turn was indexed as "navbar layout".

## Embeddings

Embeddings are opt-in. The default install uses keyword search only.

### Providers

- `none`: keyword-only mode
- `sentence-transformers`: local semantic embeddings
- `openai`: hosted embeddings
- `ollama`: local HTTP embedding endpoint

### Recommended models

Use the model name configured in `.aicv.config.yaml` or `AICV_EMBEDDING_MODEL`.
Good starting points are modern retrieval-oriented models from the BGE, E5, or OpenAI embeddings families.

### Example config

```yaml
backup_dir: .aicv/backups
rag_dir: .aicv/rag
embedding_provider: sentence-transformers
embedding_model: BAAI/bge-base-en-v1.5
embedding_weight: 0.7
keyword_weight: 0.3
auto_index: false
excludes:
  - .git/
  - .aicv/
  - node_modules/
  - dist/
  - build/
```

### Behavior

- Each turn stores a canonical text representation in the embedding index.
- Changed files also generate diff and snippet payloads when a before snapshot is available.
- Search ranks results using keywords first and semantic similarity second.
- If embeddings are misconfigured or unavailable, `aicv` falls back to keyword search.

## Reverting

Full project:

```bash
aicv revert --turn turn-1
```

Single file:

```bash
aicv revert --turn turn-1 --file src/components/Navbar.tsx
```

Use `--state after` to restore the post-change backup when available.

## Configuration

Create `.aicv.config.yaml` in the project root:

```yaml
backup_dir: .aicv/backups
rag_dir: .aicv/rag
embedding_provider: none
embedding_model: sentence-transformers/all-MiniLM-L6-v2
embedding_base_url: http://localhost:11434
embedding_endpoint: /api/embed
embedding_batch_size: 16
embedding_weight: 0.65
keyword_weight: 0.35
auto_index: false
```

Environment variables with the `AICV_` prefix override config values:

```bash
AICV_BACKUP_DIR=.vault/backups aicv backup "custom dir"
```

If you are migrating an older project, `.aicv.yaml` is still accepted as a legacy fallback.

## List stored data

```bash
aicv list
aicv list --kind turns
aicv list --kind backups
aicv list --json
```
