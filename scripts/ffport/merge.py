"""Deep merge for YAML document chains.

Semantics:
  - override[key] is None  → delete key from result
  - both are dict          → recursive merge
  - else                   → replace (list, scalar, empty dict/list)
"""


def deep_merge(base: dict, override: dict) -> dict:
    """Recursively merge *override* into *base*, returning a new dict."""
    result = dict(base)
    for k, v in override.items():
        if v is None:
            result.pop(k, None)
        elif k in result and isinstance(result[k], dict) and isinstance(v, dict):
            result[k] = deep_merge(result[k], v)
        else:
            result[k] = v
    return result
