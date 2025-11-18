from __future__ import annotations

import csv
import json
from dataclasses import dataclass, asdict
from typing import Dict, List, Optional


@dataclass
class AccountInfo:
    company_normalized: str
    twitter_id: Optional[str]
    username: Optional[str]
    name: Optional[str]
    verified: Optional[bool]


def save_accounts_csv(accounts: List[AccountInfo], path: str) -> None:
    rows = [asdict(a) for a in accounts]
    if not rows:
        fieldnames = ["company_normalized", "twitter_id", "username", "name", "verified"]
    else:
        fieldnames = list(rows[0].keys())
    with open(path, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        for r in rows:
            writer.writerow(r)


def load_accounts_csv(path: str) -> List[AccountInfo]:
    results: List[AccountInfo] = []
    with open(path, "r", newline="", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        for row in reader:
            results.append(
                AccountInfo(
                    company_normalized=row.get("company_normalized", ""),
                    twitter_id=row.get("twitter_id"),
                    username=row.get("username"),
                    name=row.get("name"),
                    verified=row.get("verified", "").lower() == "true" if row.get("verified") else None,
                )
            )
    return results


def save_mapping_json(mapping: Dict[str, str], path: str) -> None:
    with open(path, "w", encoding="utf-8") as f:
        json.dump(mapping, f, ensure_ascii=False, indent=2)


def load_mapping_json(path: str) -> Dict[str, str]:
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)



