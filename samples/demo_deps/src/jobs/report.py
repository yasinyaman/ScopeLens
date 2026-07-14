"""Reporting job — dependency-impact test fixture (pandas usage)."""

import pandas


def render() -> str:
    frame = pandas.DataFrame({"a": [1, 2, 3]})
    return frame.to_csv(index=False)
