"""Conservative, versioned FFmpeg distribution compatibility policy.

SPDX syntax is handled by license-expression. This policy is not a legal
opinion or a complete SPDX license database. ALLOW identifies a usable
licensing branch, subject to fulfillment of all applicable obligations.
REVIEW and DENY both block the distribution.
"""
from __future__ import annotations

import re
from pathlib import Path

import yaml
from dataclasses import dataclass
from enum import IntEnum
from functools import lru_cache

from license_expression import AND, OR, ExpressionError, LicenseSymbol, LicenseWithExceptionSymbol, Licensing

POLICY_VERSION = 4
# Exact IDs, not name prefixes. Unlisted terms require review. GNU FSF
# license-list and GPL FAQ are the basis for these conservative rules.
# https://www.gnu.org/licenses/license-list.html
# https://www.gnu.org/licenses/gpl-faq.html
_PERMISSIVE = frozenset(x.lower() for x in (
    "0BSD", "MIT", "MIT-0", "BSD-2-Clause", "BSD-3-Clause", "ISC", "Zlib",
    "BSL-1.0", "X11", "bzip2-1.0.6", "IJG", "Libpng", "libpng-2.0",
    "FTL", "Unicode-DFS-2016", "Unicode-3.0", "WTFPL", "Unlicense",
    "curl", "libtiff", "MIT-Khronos-old", "CC0-1.0", "MIT-Modern-Variant", "BSD-3-Clause-Clear",  # Standard SPDX permissive terms, not package-name exceptions.
))
_GNU = re.compile(r"(a?gpl|lgpl)-(1\.0|2\.0|2\.1|3\.0)(-only|-or-later|\+)?$", re.I)
_ID = re.compile(r"(?:DocumentRef-[A-Za-z0-9.-]+:)?[A-Za-z0-9.-]+\+?$")
_PARSER = Licensing()  # Never canonicalize an unreviewed LicenseRef to a standard ID.


class Status(IntEnum):
    ALLOW = 0
    REVIEW = 1
    DENY = 2


@dataclass(frozen=True)
class Decision:
    status: Status
    selected: tuple[str, ...]
    reasons: tuple[str, ...]

    def as_dict(self) -> dict:
        return {"status": self.status.name.lower(),
                "selected": list(self.selected), "reasons": list(self.reasons)}


def _decision(status: Status, license: str, reason: str) -> Decision:
    return Decision(status, (license,) if status == Status.ALLOW else (), (reason,))


@lru_cache(maxsize=512)
def _parse(expression: str):
    if not isinstance(expression, str) or not expression.strip() or len(expression) > 16384:
        raise ValueError("Empty or excessive SPDX expression")
    try:
        parsed = _PARSER.parse(expression, validate=False, strict=False)
    except ExpressionError as exc:
        raise ValueError(f"Invalid SPDX expression: {expression}") from exc
    if parsed is None:
        raise ValueError("Empty SPDX expression")
    def check(node):
        if isinstance(node, (AND, OR)):
            for child in node.args:
                check(child)
        elif isinstance(node, LicenseWithExceptionSymbol):
            check(node.license_symbol)
            check(node.exception_symbol)
        elif not isinstance(node, LicenseSymbol) or not _ID.fullmatch(node.key):
            raise ValueError(f"Invalid SPDX identifier: {node}")
    check(parsed)
    return parsed


def same_expression(left: str, right: str) -> bool:
    """Compare exact syntax trees, ignoring AND/OR order and association."""
    def canonical(node):
        if isinstance(node, (AND, OR)):
            kind = "AND" if isinstance(node, AND) else "OR"
            children = []
            for child in node.args:
                value = canonical(child)
                if value[0] == kind:
                    children.extend(value[1])
                else:
                    children.append(value)
            return kind, tuple(sorted(children))
        return "TERM", str(node)
    return canonical(_parse(left)) == canonical(_parse(right))


def _gnu(value: str):
    match = _GNU.fullmatch(value)
    if not match:
        return None
    family, version, suffix = match.groups()
    family = family.lower()
    if version not in ({"2.0", "2.1", "3.0"} if family == "lgpl" else
                       {"1.0", "2.0", "3.0"} if family == "gpl" else {"1.0", "3.0"}):
        return None
    return family, version, suffix in ("-or-later", "+")


def _atom(key: str, main: tuple, reviewed: frozenset[str]) -> Decision:
    target, version, _ = main
    lowered = key.lower()
    if lowered in _PERMISSIVE:
        return _decision(Status.ALLOW, key, "Permissive terms; retain notices")
    if lowered == "mpl-2.0":
        return _decision(Status.ALLOW, key,
                         "MPL file-level copyleft; section 3.3 permits a Larger Work under GNU terms where Secondary Licenses apply. Retain MPL notices and make covered source available; not a source-delivery certification")
    if lowered == "apache-2.0":
        return _decision(Status.ALLOW if version == "3.0" else Status.DENY, key,
                         "Apache-2.0 requires GNU GPL/LGPL version 3 for this combined distribution")
    if lowered in ("bsd-4-clause", "sspl-1.0"):
        return _decision(Status.DENY, key, "Not compatible with the selected GNU distribution policy")
    gnu = _gnu(key)
    if gnu:
        family, dep_version, later = gnu
        if family == "agpl":
            return _decision(Status.DENY, key, "AGPL terms are outside the GPL/LGPL release profiles")
        if family == "gpl":
            if target == "lgpl":
                return _decision(Status.DENY, key, "GPL-only installed dependency cannot enter LGPL profile")
            if dep_version == version or (later and dep_version in ("1.0", "2.0") and version == "3.0") or (later and dep_version == "1.0" and version == "2.0"):
                return _decision(Status.ALLOW, key, "GPL terms permit the selected GNU version")
            return _decision(Status.DENY, key, "GPL version is incompatible with selected GNU version")
        # LGPL library terms permit linking without relicensing the calling
        # work. Distinguish this from merging the library's source into FFmpeg.
        if dep_version == "3.0" and version != "3.0":
            return _decision(Status.DENY, key, "LGPLv3 is not accepted in a GNU v2 profile")
        return _decision(Status.ALLOW, key,
                         "LGPL library linking: preserve its terms and fulfill source/relink obligations; not permission to merge source")
    if key in reviewed:
        return _decision(Status.ALLOW, key, "Explicitly reviewed terms for this exact distribution")
    return _decision(Status.REVIEW, key, f"No reviewed compatibility rule for {key}")


def evaluate(expression: str, ffmpeg_license: str, *, reviewed: frozenset[str] = frozenset(),
             build_only: bool = False) -> Decision:
    main = _gnu(ffmpeg_license)
    if not main or main[0] not in ("gpl", "lgpl"):
        raise ValueError(f"Unsupported FFmpeg GNU profile: {ffmpeg_license}")
    node = _parse(expression)
    if build_only:
        # This is the scope of linkage screening only, not permission to
        # redistribute the tool or its generated code.
        return Decision(Status.ALLOW, (), ("Build-only dependency; no target linkage assumed; separate tool/output obligations remain",))

    def visit(current):
        if isinstance(current, AND):
            children = [visit(child) for child in current.args]
            status = max(child.status for child in children)
            return Decision(status, tuple(sorted({x for child in children for x in child.selected})) if status == Status.ALLOW else (),
                            tuple(dict.fromkeys(reason for child in children for reason in child.reasons)))
        if isinstance(current, OR):
            children = [visit(child) for child in current.args]
            # At least one complete compatible branch suffices. Do not
            # silently pick fragments of distinct alternatives.
            best = min(children, key=lambda item: (item.status, item.selected, item.reasons))
            return best
        if isinstance(current, LicenseWithExceptionSymbol):
            # A WITH exception is scoped to particular use/conditions.
            # Do not assume it allows arbitrary FFmpeg linkage.
            if str(current) in reviewed:
                return _decision(Status.ALLOW, str(current), "Explicitly reviewed exception for this exact distribution")
            return _decision(Status.REVIEW, str(current), f"Exception requires scope-specific review: {current}")
        return _atom(current.key, main, reviewed)

    return visit(node)


def require_compatible(expression: str, ffmpeg_license: str, package: str, *,
                       reviewed: frozenset[str] = frozenset(), build_only: bool = False) -> dict:
    result = evaluate(expression, ffmpeg_license, reviewed=reviewed, build_only=build_only)
    if result.status != Status.ALLOW:
        raise ValueError(f"License {result.status.name.lower()} for {package}: {expression} vs "
                         f"{ffmpeg_license}: {'; '.join(result.reasons)}")
    return result.as_dict()


# Manual approval is deliberately narrow: package version/revision, original
# copyright hash, full SPDX expression, selected GNU profile, and linkage.
# Policy DENY cannot be overridden by an approval.
REVIEW_FILE = Path(__file__).with_name("license_reviews.yaml")
_REVIEW_FIELDS = frozenset(("id", "package", "version", "port_revision",
                            "copyright_sha256", "expression", "term", "profile",
                            "linkage", "source", "reason"))


@lru_cache(maxsize=1)
def load_reviews() -> tuple[dict, ...]:
    doc = yaml.safe_load(REVIEW_FILE.read_text(encoding="utf-8"))
    if not isinstance(doc, dict) or set(doc) != {"reviews"} or not isinstance(doc["reviews"], list):
        raise ValueError("Invalid license review registry")
    result = []
    ids = set()
    for row in doc["reviews"]:
        if not isinstance(row, dict) or set(row) != _REVIEW_FIELDS:
            raise ValueError("Invalid license review entry fields")
        if any(not isinstance(row[k], str) or not row[k].strip() for k in _REVIEW_FIELDS - {"port_revision"}):
            raise ValueError("Invalid license review text")
        if type(row["port_revision"]) is not int or row["port_revision"] < 0:
            raise ValueError("Invalid license review Port revision")
        if not re.fullmatch(r"[0-9a-f]{64}", row["copyright_sha256"]) or row["linkage"] not in ("static", "shared"):
            raise ValueError("Invalid license review scope")
        if not row["source"].startswith("https://") or row["id"] in ids:
            raise ValueError("Invalid license review reference")
        _parse(row["expression"])
        term = _parse(row["term"])
        if not isinstance(term, (LicenseSymbol, LicenseWithExceptionSymbol)):
            raise ValueError("A review must approve exactly one license or WITH term")
        if _gnu(row["profile"]) is None:
            raise ValueError("Invalid review GNU profile")
        ids.add(row["id"])
        result.append(row)
    return tuple(result)


def scoped_compatibility(expression: str, ffmpeg_license: str, package: str, *,
                         name: str, version: str, port_revision: int,
                         copyright_sha256: str, linkage: str, build_only: bool,
                         reviewed: frozenset[str] = frozenset(), system_dependency: bool = False) -> dict:
    if system_dependency:
        if expression != "NOASSERTION":
            raise ValueError("External system dependency must not assert an unverified SDK license")
        return {"status": "allow", "selected": [],
                "reasons": ["Verified external Windows system import dependency; SDK files are excluded from distribution. This is not a grant to redistribute SDK files."],
                "review_ids": [], "reviews": []}
    identity = {"package": name, "version": version, "port_revision": port_revision,
                "copyright_sha256": copyright_sha256, "expression": expression,
                "profile": ffmpeg_license, "linkage": linkage}
    matches = [row for row in load_reviews() if all(row[key] == value for key, value in identity.items())]
    approved = frozenset(row["term"] for row in matches)
    decision = require_compatible(expression, ffmpeg_license, package,
                                  reviewed=reviewed | approved, build_only=build_only)
    used = sorted((row for row in matches if row["term"] in decision["selected"]), key=lambda row: row["id"])
    decision["review_ids"] = [row["id"] for row in used]
    decision["reviews"] = [{key: row[key] for key in ("id", "term", "source", "reason")} for row in used]
    return decision
