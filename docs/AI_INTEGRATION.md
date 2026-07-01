# AI Integration

Use `aicv` as the local change log for any coding agent.

## Minimal workflow

1. Read this file.
2. Run `aicv doctor` if this is the first time in the repo.
3. Run a backup before editing.
4. Make the requested change.
5. Validate it.
6. Run a second backup after validation.
7. Index the turn.
8. Search or revert later if needed.

## Commands

```bash
aicv backup --message "before: <task>"
aicv backup --message "after: <summary>"
aicv index --turn 1 --request "<request>" --files "src/components/Navbar.tsx" --validation "lint + tests OK"
aicv search "navbar login"
aicv revert --turn turn-1
```

## Embeddings

`aicv` supports hybrid retrieval:

- Keyword search works always.
- Embeddings are optional.
- `sentence-transformers` is the recommended local option.
- `openai` and `ollama` are supported when configured.

If the embedding model changes, run:

```bash
aicv embeddings rebuild
```

## Agent rules

- Keep requests short and specific.
- Include changed files in the index step.
- Include validation status.
- Do not store secrets in requests or descriptions.
- Use `aicv revert` instead of manually undoing a known bad turn.
