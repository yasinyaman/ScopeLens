"""HTTP handlers — dependency-impact test fixture (third-party imports)."""

import requests
import yaml

from jobs import report


def fetch(url: str) -> str:
    return requests.get(url, timeout=5).text


def load_config(path: str) -> dict:
    with open(path, encoding="utf-8") as f:
        return yaml.safe_load(f)


def weekly() -> str:
    return report.render()
