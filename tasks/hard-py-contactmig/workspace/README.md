# contactmig

Migrates the contact store from the v1 record files to the v2 SQLite database.
Python 3.13, standard library only.

```
python -m contactmig migrate --source samples/v1 --db /tmp/contacts.db
python -m unittest -v
```

- `docs/MIGRATION.md`: the specification of the migration (the v1 format and all rules).
- `contactmig/schema.sql`: the v2 schema. Other services read these tables, so it does not change.
- `samples/v1/`: a small v1 store with the three encodings of the export jobs.
