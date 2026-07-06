# Usage

## Create a backup

```bash
aicv backup --message "before refactor navbar"
```

You can also pass the message as an argument:

```bash
aicv backup "before refactor navbar"
```

## Index a turn

```bash
aicv index \
  --turn 1 \
  --request "Change login button color" \
  --files "src/components/Navbar.tsx" \
  --validation "lint + tests OK"
```

The index command stores:

- the request
- optional description
- changed files
- validation result
- backup references
- keyword index entries
- optional embedding vector for the turn

If both `backup_before` and `backup_after` are provided, the stored backup is compacted down to the files that actually changed.

## Search

```bash
aicv list
aicv list --kind turns
aicv list --kind backups
aicv list --json
aicv search "navbar login"
aicv search --turn turn-1
aicv search --file Navbar.tsx
```

Search ranking is hybrid when embeddings are enabled.
If embeddings are disabled or unavailable, the CLI falls back to keyword matching.

## Revert

```bash
aicv revert --turn turn-1
aicv revert --turn turn-1 --file src/components/Navbar.tsx
```

The CLI asks for confirmation before overwriting files.
Use `--yes` in automated contexts.

## Inspect configuration

```bash
aicv config
aicv embeddings status
aicv embeddings rebuild
```

This prints the resolved project root and all active configuration values, including the embedding provider and model.

## Embedding configuration

Example `.aicv.config.yaml`:

```yaml
embedding_provider: sentence-transformers
embedding_model: BAAI/bge-base-en-v1.5
embedding_weight: 0.7
keyword_weight: 0.3
backup_retention: 20
```

If the provider package is not installed, `aicv` keeps working in keyword-only mode.

Legacy `.aicv.yaml` files are still supported for existing repos, but new projects should use `.aicv.config.yaml`.
