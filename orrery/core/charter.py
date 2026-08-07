"""
Charter integrity.

The 10 Laws are written out in full in three separate documents. That is a drift machine,
and it has already drifted: when the Fourth Law's "conforms to" was corrected to "violates"
— a wording that, as written, forbade compliance — the fix landed in two documents and not
the third, leaving the charter internally contradictory with nothing to notice.

So one document is designated canonical, the others are checked against it Law by Law, and
every charter file's digest is pinned in a manifest. Editing a Law now fails the build
until somebody re-pins it deliberately, and the pinned digest is folded into the
configuration attestation, so approving a configuration approves the charter it runs under.

Comparison is deliberately tolerant of presentation and intolerant of meaning: whitespace,
letter case, curly quotes, and dash style are normalized away, because "An intelligence
System" and "An Intelligence System" are the same Law. "Conforms to" and "violates" are not.

This detects disagreement between documents and unreviewed edits to them. It says nothing
about whether the Laws are *followed* — that is what GOVERNANCE.md is for, and it is
candid that 2 of the 10 have no runtime control at all.
"""

from __future__ import annotations

import hashlib
import json
import logging
import re
import unicodedata
from pathlib import Path
from typing import Dict, List, Optional, Tuple

from pydantic import BaseModel

logger = logging.getLogger(__name__)

REPO_ROOT = Path(__file__).resolve().parents[2]

CANONICAL_DOCUMENT = "AGENTIC_PRIME_DIRECTIVE.md"
CHARTER_DOCUMENTS: Tuple[str, ...] = (
    "AGENTIC_PRIME_DIRECTIVE.md",
    "AGENTIC_SACRED_COVENANT.md",
    "Permanent_Active_Directives.txt",
)
MANIFEST_PATH = "config/charter_manifest.json"

LAW_ORDINALS: Tuple[str, ...] = (
    "First",
    "Second",
    "Third",
    "Fourth",
    "Fifth",
    "Sixth",
    "Seventh",
    "Eighth",
    "Ninth",
    "Tenth",
)
_ORDINAL_TO_NUMBER = {name.lower(): index + 1 for index, name in enumerate(LAW_ORDINALS)}

_LAW_PATTERN = re.compile(
    r"^\s*\d{1,2}\.\s+\*\*(?P<ordinal>"
    + "|".join(LAW_ORDINALS)
    + r")\s+Law:?\*\*\s*(?P<text>.+?)\s*$",
    re.MULTILINE | re.IGNORECASE,
)

_QUOTES = {"\u2018": "'", "\u2019": "'", "\u201c": '"', "\u201d": '"'}
_DASHES = ("\u2013", "\u2014", "\u2212")


def normalize_law(text: str) -> str:
    """
    Strips presentation, keeps meaning. Case, curly quotes, dash style, and whitespace are
    noise; word choice is not.
    """
    normalized = unicodedata.normalize("NFKC", text)
    for fancy, plain in _QUOTES.items():
        normalized = normalized.replace(fancy, plain)
    for dash in _DASHES:
        normalized = normalized.replace(dash, " ")
    return " ".join(normalized.lower().split())


def extract_laws(text: str) -> Dict[int, str]:
    laws: Dict[int, str] = {}
    for match in _LAW_PATTERN.finditer(text):
        number = _ORDINAL_TO_NUMBER[match.group("ordinal").lower()]
        laws[number] = match.group("text").strip()
    return laws


def document_digest(path: Path) -> Optional[str]:
    """
    Digests the document's *content*, with line endings normalised.

    Hashing raw bytes would make the manifest depend on how git checked the file out: these
    documents are stored LF and appear CRLF on Windows, so a manifest pinned on one platform
    fails on the other. A charter does not change meaning because a checkout added carriage
    returns.
    """
    try:
        text = Path(path).read_text(encoding="utf-8")
    except OSError:
        return None
    normalized = text.replace("\r\n", "\n").replace("\r", "\n")
    return hashlib.sha256(normalized.encode("utf-8")).hexdigest()


class CharterDrift(BaseModel):
    document: str
    law: int
    canonical_text: str
    document_text: str


class CharterVerification(BaseModel):
    verified: bool
    canonical: str = CANONICAL_DOCUMENT
    laws_checked: int = 0
    missing_documents: List[str] = []
    missing_laws: List[str] = []
    drift: List[CharterDrift] = []
    digest_mismatches: List[str] = []
    unpinned_documents: List[str] = []

    @property
    def summary(self) -> str:
        if self.verified:
            return (
                f"{self.laws_checked} Law(s) agree across "
                f"{len(CHARTER_DOCUMENTS) - len(self.missing_documents)} document(s), "
                f"digests match the manifest."
            )
        problems: List[str] = []
        problems.extend(f"{d} is missing" for d in self.missing_documents)
        problems.extend(self.missing_laws)
        problems.extend(
            f"{item.document} Law {item.law} disagrees with {self.canonical}"
            for item in self.drift
        )
        problems.extend(
            f"{name} has changed since it was pinned" for name in self.digest_mismatches
        )
        problems.extend(f"{name} is not pinned in the manifest" for name in self.unpinned_documents)
        return "; ".join(problems)


def build_manifest(root: Optional[Path] = None) -> Dict[str, object]:
    base = Path(root or REPO_ROOT)
    return {
        "canonical": CANONICAL_DOCUMENT,
        "documents": {
            name: digest
            for name in CHARTER_DOCUMENTS
            if (digest := document_digest(base / name)) is not None
        },
    }


def load_manifest(root: Optional[Path] = None) -> Dict[str, object]:
    base = Path(root or REPO_ROOT)
    try:
        return json.loads((base / MANIFEST_PATH).read_text(encoding="utf-8"))
    except FileNotFoundError:
        return {}
    except (OSError, json.JSONDecodeError) as exc:
        logger.error("Charter manifest is unreadable: %s", exc)
        return {}


def save_manifest(manifest: Dict[str, object], root: Optional[Path] = None) -> Path:
    base = Path(root or REPO_ROOT)
    target = base / MANIFEST_PATH
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")
    return target


def charter_digest(root: Optional[Path] = None) -> str:
    """
    One digest over every charter document, folded into the configuration attestation so
    that approving a configuration also pins the charter it runs under. The filenames are
    part of the digest, so a document going missing changes it rather than passing quietly.
    """
    base = Path(root or REPO_ROOT)
    payload = {name: document_digest(base / name) for name in CHARTER_DOCUMENTS}
    encoded = json.dumps(payload, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(encoded.encode("utf-8")).hexdigest()


def verify_charter(root: Optional[Path] = None) -> CharterVerification:
    """
    Checks that every charter document states the same 10 Laws as the canonical one, and
    that none of them has changed since it was pinned.
    """
    base = Path(root or REPO_ROOT)
    result = CharterVerification(verified=True)

    texts: Dict[str, str] = {}
    for name in CHARTER_DOCUMENTS:
        try:
            texts[name] = (base / name).read_text(encoding="utf-8")
        except OSError:
            result.verified = False
            result.missing_documents.append(name)

    canonical_text = texts.get(CANONICAL_DOCUMENT)
    if canonical_text is None:
        result.verified = False
        return result

    canonical_laws = extract_laws(canonical_text)
    result.laws_checked = len(canonical_laws)
    if len(canonical_laws) != len(LAW_ORDINALS):
        result.verified = False
        result.missing_laws.append(
            f"{CANONICAL_DOCUMENT} states {len(canonical_laws)} of {len(LAW_ORDINALS)} Laws"
        )

    for name, text in texts.items():
        if name == CANONICAL_DOCUMENT:
            continue
        laws = extract_laws(text)
        for number, canonical_law in canonical_laws.items():
            stated = laws.get(number)
            if stated is None:
                result.verified = False
                result.missing_laws.append(f"{name} does not state Law {number}")
                continue
            if normalize_law(stated) != normalize_law(canonical_law):
                result.verified = False
                result.drift.append(
                    CharterDrift(
                        document=name,
                        law=number,
                        canonical_text=canonical_law,
                        document_text=stated,
                    )
                )

    pinned = load_manifest(base).get("documents") or {}
    for name in CHARTER_DOCUMENTS:
        if name in result.missing_documents:
            continue
        expected = pinned.get(name)
        if expected is None:
            result.verified = False
            result.unpinned_documents.append(name)
        elif expected != document_digest(base / name):
            result.verified = False
            result.digest_mismatches.append(name)

    return result
