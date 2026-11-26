"""Read-only discovery of active repair incidents across occurrence branches."""
from __future__ import annotations

from . import github
from .ledger import branch_matches
from .models import commit_sha
from ..release_trigger import automatic_pr


def open_repairs(target: str, signature: str) -> list[dict]:
    repo = github.repository()
    rows = github.collection(f"repos/{repo}/pulls?state=open&base=main", "pulls")
    result = []
    for pr in rows:
        try:
            if (pr.get("state") != "open" or automatic_pr(pr, repo) != (target, "repair")
                    or not branch_matches(pr["head"]["ref"], target, signature)):
                continue
            commit_sha(pr["head"]["sha"])
            if type(pr.get("number")) is not int or pr["number"] < 1:
                raise ValueError("Invalid repair PR number")
            result.append(pr)
        except (KeyError, ValueError):
            continue
    return result
