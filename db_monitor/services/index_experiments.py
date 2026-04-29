from django.db import connection


EXPERIMENT_INDEXES = [
    {
        "name": "shop_product_created_at_idx",
        "table": "shop_product",
        "columns": "created_at DESC",
        "description": "Recent product filtering and newest-product sorting",
    },
    {
        "name": "shop_product_name_trgm_idx",
        "table": "shop_product",
        "using": "USING gin",
        "columns": "name gin_trgm_ops",
        "extensions": ["pg_trgm"],
        "description": "ILIKE search on Product.name",
    },
]


def _index_sql(index_definition):
    using = f" {index_definition['using']}" if index_definition.get("using") else ""
    return (
        f"CREATE INDEX {index_definition['name']} "
        f"ON {index_definition['table']}{using} ({index_definition['columns']})"
    )


def _extension_exists(cursor, extension_name):
    cursor.execute("SELECT EXISTS(SELECT 1 FROM pg_extension WHERE extname = %s)", [extension_name])
    return bool(cursor.fetchone()[0])


def _index_exists(cursor, index_name):
    cursor.execute("SELECT to_regclass(%s)", [index_name])
    return bool(cursor.fetchone()[0])


def _collect_index_state(cursor):
    state = []
    for definition in EXPERIMENT_INDEXES:
        state.append(
            {
                "name": definition["name"],
                "table": definition["table"],
                "columns": definition["columns"],
                "description": definition["description"],
                "present": _index_exists(cursor, definition["name"]),
            }
        )
    return state


def get_experiment_index_state():
    if connection.vendor != "postgresql":
        return {
            "database_vendor": connection.vendor,
            "mode": "unsupported",
            "indexes": [],
            "notes": ["Index experiment tooling requires PostgreSQL."],
        }

    with connection.cursor() as cursor:
        state = _collect_index_state(cursor)

    return {
        "database_vendor": connection.vendor,
        "mode": "with_indexes" if any(item["present"] for item in state) else "without_indexes",
        "indexes": state,
        "notes": [],
    }


def configure_experiment_indexes(mode):
    if mode not in {"with_indexes", "without_indexes"}:
        raise ValueError("Mode must be either `with_indexes` or `without_indexes`.")

    if connection.vendor != "postgresql":
        raise ValueError("Index experiment tooling requires PostgreSQL.")

    notes = []
    changed = []
    with connection.cursor() as cursor:
        for definition in EXPERIMENT_INDEXES:
            if mode == "with_indexes":
                missing_extensions = [
                    extension
                    for extension in definition.get("extensions", [])
                    if not _extension_exists(cursor, extension)
                ]
                if missing_extensions:
                    notes.append(
                        f"Skipped {definition['name']} because missing extension(s): {', '.join(missing_extensions)}."
                    )
                    continue

                if _index_exists(cursor, definition["name"]):
                    notes.append(f"Index {definition['name']} already present.")
                    continue

                cursor.execute(_index_sql(definition))
                changed.append({"name": definition["name"], "action": "created"})
            else:
                if not _index_exists(cursor, definition["name"]):
                    notes.append(f"Index {definition['name']} already absent.")
                    continue

                cursor.execute(f"DROP INDEX {definition['name']}")
                changed.append({"name": definition["name"], "action": "dropped"})

        state = _collect_index_state(cursor)

    return {
        "database_vendor": connection.vendor,
        "mode": mode,
        "indexes": state,
        "changed": changed,
        "notes": notes,
    }
