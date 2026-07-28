# Generated references

Only reproducible generated documentation belongs here, such as schema or API
references. Every generated artifact must identify its source and regeneration
command. Do not edit generated outputs by hand.

Current references:

- `api-routes.md`: FastAPI decorators in the composition root and routers;
- `configuration.md`: `app.config.Settings`;
- `data-dictionary.md`: SQLAlchemy table metadata.

Regenerate:

```bash
python -m scripts.generate_docs
```

Verify without writing:

```bash
python -m scripts.generate_docs --check
```
