import re


READ_OPERATIONS = {"SELECT"}
WRITE_OPERATIONS = {"INSERT", "UPDATE", "DELETE"}
KNOWN_OPERATIONS = READ_OPERATIONS | WRITE_OPERATIONS


def classify_sql_operation(query_text):
    compact = " ".join((query_text or "").strip().split())
    if not compact:
        return "UNKNOWN"

    compact = re.sub(r"^/\*.*?\*/\s*", "", compact)
    match = re.match(r"^(WITH\s+)?([A-Za-z]+)", compact, flags=re.IGNORECASE)
    if not match:
        return "UNKNOWN"

    operation = match.group(2).upper()
    if operation == "WITH":
        return "SELECT"
    if operation in KNOWN_OPERATIONS:
        return operation
    return "OTHER"


def is_read_operation(operation_type):
    return (operation_type or "").upper() in READ_OPERATIONS


def is_write_operation(operation_type):
    return (operation_type or "").upper() in WRITE_OPERATIONS
