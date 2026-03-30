"""Frontend helper for loading setup content via shared backend parser."""

from __future__ import annotations

from app.core.telemetry_parser import parse_svm_file


def parse_svm_content(file_path: str):
    return parse_svm_file(file_path)
