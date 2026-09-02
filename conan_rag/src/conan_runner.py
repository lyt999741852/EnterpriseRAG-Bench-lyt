"""Conan-only entry point with isolation and read-only index checks."""

from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path
from typing import Any

from .pipeline import load_config, run_pipeline


PROJECT_ROOT = Path(__file__).resolve().parents[1]
CONFIG_DIR = PROJECT_ROOT / "configs"
CONAN_MARKERS = ("conan", "qwen3")


def _is_within(path: Path, root: Path) -> bool:
    try:
        path.relative_to(root)
        return True
    except ValueError:
        return False


def _has_conan_marker(value: Any) -> bool:
    normalized = str(value or "").lower()
    return any(marker in normalized for marker in CONAN_MARKERS)


def _load_local_env() -> None:
    """Load a small .env file without adding a runtime dependency."""
    env_path = PROJECT_ROOT / ".env"
    if not env_path.is_file():
        return
    for raw_line in env_path.read_text(encoding="utf-8-sig").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        key = key.strip()
        if not key or not key.replace("_", "a").isalnum():
            continue
        value = value.strip()
        if len(value) >= 2 and value[0] == value[-1] and value[0] in "\"'":
            value = value[1:-1]
        os.environ.setdefault(key, value)


def validate_conan_config(config_path: str | Path) -> tuple[Path, dict]:
    """Reject configurations that could cross-write the BGE experiment."""
    path = Path(config_path).expanduser().resolve()
    errors: list[str] = []

    if path.parent != CONFIG_DIR.resolve():
        errors.append(f"config must be directly inside {CONFIG_DIR}")
    if not path.is_file():
        errors.append(f"config does not exist: {path}")
    if errors:
        raise ValueError("\n- ".join(["Conan isolation check failed:", *errors]))

    cfg = load_config(str(path))
    pipeline = cfg.get("pipeline", {})
    elasticsearch = cfg.get("elasticsearch", {})

    if cfg.get("index_backend") != "elasticsearch":
        errors.append("index_backend must be elasticsearch")
    if pipeline.get("read_existing_index") is not True:
        errors.append("pipeline.read_existing_index must be true")
    if pipeline.get("overwrite_index") is not False:
        errors.append("pipeline.overwrite_index must be false")
    if not _has_conan_marker(elasticsearch.get("index_name")):
        errors.append("elasticsearch.index_name must contain conan or qwen3")
    if not _has_conan_marker(cfg.get("index_dir")):
        errors.append("index_dir must contain conan or qwen3")
    if not _has_conan_marker(pipeline.get("name")):
        errors.append("pipeline.name must contain conan or qwen3")

    # Runtime-writable paths must remain inside this extracted folder.
    writable_paths = {
        "output_dir": cfg.get("output_dir", "outputs"),
        "pageindex.cache_dir": cfg.get("pageindex", {}).get("cache_dir", ""),
        "chunking.tokenizer_local_dir": cfg.get("chunking", {}).get(
            "tokenizer_local_dir", ""
        ),
    }
    for label, value in writable_paths.items():
        if not value:
            continue
        candidate = Path(str(value))
        resolved = (
            candidate.resolve()
            if candidate.is_absolute()
            else (PROJECT_ROOT / candidate).resolve()
        )
        if not _is_within(resolved, PROJECT_ROOT.resolve()):
            errors.append(f"{label} must stay inside Conan root; got {value}")

    if errors:
        raise ValueError("\n- ".join(["Conan isolation check failed:", *errors]))
    return path, cfg


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Safely run an isolated Conan RAG test")
    parser.add_argument("config", help="Conan config directly under conan_rag/configs")
    parser.add_argument(
        "--check",
        action="store_true",
        help="validate isolation only; do not connect to models or Elasticsearch",
    )
    args = parser.parse_args(argv)

    try:
        config_path, cfg = validate_conan_config(args.config)
    except (OSError, ValueError, TypeError) as exc:
        print(exc, file=sys.stderr)
        return 2

    print("Conan isolation check passed")
    print(f"  config: {config_path}")
    print(f"  pipeline: {cfg['pipeline']['name']}")
    print(f"  ES index: {cfg['elasticsearch']['index_name']}")
    print(f"  output: {PROJECT_ROOT / cfg.get('output_dir', 'outputs')}")
    if args.check:
        return 0
    _load_local_env()
    return run_pipeline(str(config_path))


if __name__ == "__main__":
    raise SystemExit(main())
