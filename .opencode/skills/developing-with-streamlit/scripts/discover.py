#!/usr/bin/env python3
"""Discover the Streamlit package's bundled agent-skills SKILL.md.

Vendored from https://github.com/streamlit/agent-skills
(developing-with-streamlit/scripts/discover.py) so Qagro works offline.

Usage:
    python scripts/discover.py [--project-dir PATH]

Exit codes:
    0 - success; prints the absolute path to the bundled SKILL.md on stdout.
    1 - Streamlit is not installed in the detected interpreter.
    2 - Streamlit is installed but predates bundled skills (no .agents/skills/).
        EXPECTED for Qagro (pins streamlit==1.49.1 < 1.57): fall back to
        https://docs.streamlit.io/llms-full.txt and the Qagro appendix in SKILL.md.
    3 - no usable Python interpreter was found.
    4 - .agents/skills/ exists but developing-with-streamlit/SKILL.md is missing.
    5 - invalid script argument.
"""
from __future__ import annotations

import argparse
import os
import shutil
import subprocess
import sys
from pathlib import Path
from typing import List, Optional, Tuple


def find_venv_python(venv_root: Path) -> Optional[Path]:
    for candidate in (
        venv_root / "bin" / "python",
        venv_root / "Scripts" / "python.exe",
    ):
        if candidate.is_file():
            return candidate
    return None


def find_git_root(start: Path) -> Optional[Path]:
    for ancestor in [start, *start.parents]:
        if (ancestor / ".git").exists():
            return ancestor
    return None


def detect_interpreter(project_dir: Path) -> Optional[Tuple[List[str], str]]:
    venv = os.environ.get("VIRTUAL_ENV")
    if venv:
        py = find_venv_python(Path(venv))
        if py:
            return [str(py)], "virtual-env"

    py = find_venv_python(project_dir / ".venv")
    if py:
        return [str(py)], "venv-local"

    py = find_venv_python(project_dir.parent / ".venv")
    if py:
        return [str(py)], "venv-parent"

    git_root = find_git_root(project_dir)
    if (
        git_root is not None
        and git_root != project_dir
        and git_root != project_dir.parent
    ):
        py = find_venv_python(git_root / ".venv")
        if py:
            return [str(py)], "venv-git-root"

    conda = os.environ.get("CONDA_PREFIX")
    if conda:
        py = find_venv_python(Path(conda))
        if py:
            return [str(py)], "conda"

    if shutil.which("pipenv") and (project_dir / "Pipfile").is_file():
        return ["pipenv", "run", "python"], "pipenv"

    if shutil.which("poetry") and (project_dir / "poetry.lock").is_file():
        return ["poetry", "run", "python"], "poetry"

    if shutil.which("pdm") and (project_dir / "pdm.lock").is_file():
        return ["pdm", "run", "python"], "pdm"

    if shutil.which("uv") and (project_dir / "uv.lock").is_file():
        return ["uv", "run", "--quiet", "python"], "uv"

    for name in ("python3", "python"):
        if shutil.which(name):
            return [name], "system"

    return None


def install_advice(cmd: List[str], tag: str) -> str:
    if tag in {"virtual-env", "venv-local", "venv-parent", "venv-git-root"}:
        return f"{cmd[0]} -m pip install streamlit"
    if tag == "conda":
        return "conda install -c conda-forge streamlit"
    if tag == "pipenv":
        return "pipenv install streamlit"
    if tag == "poetry":
        return "poetry add streamlit"
    if tag == "pdm":
        return "pdm add streamlit"
    if tag == "uv":
        return "uv add streamlit"
    return (
        f"{cmd[0]} -m pip install streamlit\n"
        "    (better: create a project venv first with "
        "`python -m venv .venv && source .venv/bin/activate`)"
    )


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Discover the bundled developing-with-streamlit SKILL.md.",
    )
    parser.add_argument(
        "--project-dir",
        default=None,
        help="Absolute path to the user's project directory. Defaults to cwd.",
    )
    try:
        args = parser.parse_args()
    except SystemExit as e:
        return 5 if e.code else 0

    if args.project_dir is not None:
        project_dir = Path(args.project_dir)
        if not project_dir.is_dir():
            print(
                f"ERROR: --project-dir is not a directory: {project_dir}",
                file=sys.stderr,
            )
            return 5
    else:
        project_dir = Path.cwd()
    project_dir = project_dir.resolve()

    detection = detect_interpreter(project_dir)
    if detection is None:
        print(
            "ERROR: No Python interpreter found.\n"
            "Install Python 3.10+, then install Streamlit and re-run.",
            file=sys.stderr,
        )
        return 3

    cmd, tag = detection
    py_display = " ".join(cmd)

    probe = "import streamlit; print(streamlit.__path__[0])"
    try:
        result = subprocess.run(
            [*cmd, "-c", probe],
            capture_output=True,
            text=True,
            cwd=project_dir,
            timeout=30,
        )
    except subprocess.TimeoutExpired:
        print(
            f"ERROR: import streamlit timed out (interpreter: {py_display})",
            file=sys.stderr,
        )
        return 1
    except FileNotFoundError:
        print(
            f"ERROR: detected interpreter not found on PATH: {py_display}",
            file=sys.stderr,
        )
        return 3

    if result.returncode != 0:
        combined = (result.stderr or "") + (result.stdout or "")
        if "ModuleNotFoundError" in combined:
            advice = install_advice(cmd, tag)
            print(
                "ERROR: Streamlit is not installed in the detected Python environment.\n"
                f"Interpreter:   {py_display}\n"
                f"Detected via:  {tag}\n"
                "\n"
                f"Install with:  {advice}\n"
                "\n"
                "Then re-run this script.",
                file=sys.stderr,
            )
            return 1
        print(
            "ERROR: Failed to import streamlit.\n"
            f"Interpreter: {py_display}\n"
            "Output:\n"
            f"{combined}",
            file=sys.stderr,
        )
        return 1

    streamlit_path = Path(result.stdout.strip()).resolve()
    agents_skills_dir = streamlit_path / ".agents" / "skills"
    primary_skill = agents_skills_dir / "developing-with-streamlit" / "SKILL.md"

    if primary_skill.is_file():
        print(primary_skill)
        return 0

    if agents_skills_dir.is_dir():
        print(
            "ERROR: Streamlit's bundled skills directory exists, but the expected\n"
            "developing-with-streamlit/SKILL.md is missing.\n"
            f"Streamlit path: {streamlit_path}\n"
            f"Bundled skills directory: {agents_skills_dir}\n",
            file=sys.stderr,
        )
        return 4

    print(
        "ERROR: Streamlit is installed but predates bundled skills (< 1.57).\n"
        f"Interpreter: {py_display}\n"
        f"Streamlit path: {streamlit_path}\n"
        "\n"
        "For Qagro this is EXPECTED (pins streamlit==1.49.1).\n"
        "Fall back to https://docs.streamlit.io/llms-full.txt and the\n"
        "Qagro appendix in developing-with-streamlit/SKILL.md.",
        file=sys.stderr,
    )
    return 2


if __name__ == "__main__":
    sys.exit(main())
