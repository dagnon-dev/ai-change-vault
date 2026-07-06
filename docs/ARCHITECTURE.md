# Architecture

AI Change Vault is intentionally local, deterministic, and small enough to run inside a repo.

## Modules

- `aicv.backup`: creates filtered project snapshots in `.aicv/backups`.
- `aicv.index`: writes turn JSON documents, updates the keyword index, and stores optional embeddings.
- `aicv.search`: combines keyword ranking with optional semantic similarity.
- `aicv.revert`: restores a full project or a single file from a snapshot.
- `aicv.config`: merges defaults, `.aicv.config.yaml` (with `.aicv.yaml` fallback), and `AICV_*` environment variables.
- `aicv.embeddings`: provider abstraction plus embedding store helpers.
- `aicv.models`: Pydantic v2 contracts for turns, backups, search results, and embeddings.
- `aicv.cli`: Typer command interface.

## Data flow

1. `backup` copies project files while respecting excludes.
2. `index` writes `.aicv/rag/turns/<turn>.json`.
3. `index` rebuilds `.aicv/rag/index.json`.
4. `index` optionally stores a turn summary vector plus diff/snippet vectors in `.aicv/rag/embeddings.json`.
5. `search` loads turn JSON documents and ranks them.
6. `search` uses embeddings only when the configured provider and model match stored vectors.
7. `index` can compact a turn into a per-file backup bundle when both before and after snapshots are available.
8. `revert` resolves the turn document and restores from `backup_before` or `backup_after`.

## Retrieval design

The search stack is hybrid:

- **Lexical layer**: token matching over request, description, files, validation, and status.
- **Semantic layer**: cosine similarity over turn and query embeddings.
- **Final score**: a weighted blend of lexical and semantic signals.

The default weights favor keywords to keep exact file and turn lookup fast and predictable.

## Embedding store

Embedding vectors are stored locally in:

```text
.aicv/rag/embeddings.json
```

Each record stores:

- `turn_id`
- `kind`
- `chunk_id`
- `provider`
- `model`
- `source_path`
- `title`
- `line_start`
- `line_end`
- `text`
- `vector`
- `text_hash`
- `updated_at`

This allows multiple providers or models to coexist in the same project history.

## Compact backups

When both `backup_before` and `backup_after` are indexed, `aicv` can collapse the full snapshots into a compact turn bundle that stores only changed files plus a manifest. This keeps revert support while avoiding repeated copies of the full repository.

## Retention

`backup_retention` controls how many backup directories are kept under `.aicv/backups`. Older directories are pruned automatically after new backups or compaction.

## Provider options

- `none`: keyword-only mode
- `sentence-transformers`: local semantic embeddings
- `openai`: hosted semantic embeddings
- `ollama`: local HTTP embedding endpoint

The provider is chosen from config and can be changed without altering the rest of the tool.

## No Git requirement

The tool does not read Git history and does not assume the project is a Git repository.
`.git/` is excluded by default when present.
