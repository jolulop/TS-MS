def safe_local_path(raw_value: str | None, *, default: str) -> str:
    if raw_value and raw_value.startswith("/") and not raw_value.startswith("//"):
        return raw_value
    return default
