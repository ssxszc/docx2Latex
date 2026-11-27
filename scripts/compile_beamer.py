#!/usr/bin/env python3
"""Compile a Beamer project safely and verify its PDF page count and TeX log."""

import argparse
from pathlib import Path
import re
import shutil
import subprocess
import sys

LOCAL_IMAGE = "ghcr.io/ayaka-notes/texlive-basic:2026.1-thesis"
LAYOUT_ERRORS = re.compile(r"Overfull\s*\\[hv]box|Missing character:|^!", re.M)


def compile_deck(source, build, image):
    args = [
        "-norc", "-xelatex", "-latexoption=-no-shell-escape", "-halt-on-error",
        "-interaction=nonstopmode", "-file-line-error", "-jobname=defense",
    ]
    if not image and shutil.which("latexmk") and shutil.which("xelatex"):
        command = ["latexmk", *args, f"-outdir={build}", f"./{source.name}"]
    else:
        image = image or LOCAL_IMAGE
        if not shutil.which("docker"):
            raise RuntimeError("XeLaTeX/latexmk and Docker are unavailable.")
        if subprocess.run(
            ["docker", "image", "inspect", image], capture_output=True
        ).returncode:
            raise RuntimeError(f"Compatible local Docker image unavailable: {image}")
        command = [
            "docker", "run", "--rm", "--pull=never", "--network=none",
            "--entrypoint", "latexmk", "-v", f"{source.parent}:/project:ro",
            "-v", f"{build}:/build", "-w", "/project", image, *args,
            "-outdir=/build", f"./{source.name}",
        ]
    terminal_log = build / "compiler-output.txt"
    with terminal_log.open("w", encoding="utf-8") as log:
        result = subprocess.run(command, cwd=source.parent, stdout=log, stderr=subprocess.STDOUT)
    if result.returncode:
        print("\n".join(terminal_log.read_text(errors="replace").splitlines()[-42:]), file=sys.stderr)
        raise RuntimeError(f"XeLaTeX failed. See {terminal_log}")


def page_count(pdf):
    if shutil.which("pdfinfo"):
        report = subprocess.check_output(["pdfinfo", str(pdf)], text=True)
        pages = re.search(r"^Pages:\s*(\d+)", report, re.M)
        if pages:
            return int(pages[1])
    try:
        from pypdf import PdfReader
    except ImportError as exc:
        raise RuntimeError("PDF page verification needs pdfinfo or pypdf.") from exc
    return len(PdfReader(pdf).pages)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("source", type=Path)
    parser.add_argument("--pages", type=int, default=13)
    parser.add_argument("--build-dir", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--docker-image", help="Use this already-installed image instead of host TeX.")
    opts = parser.parse_args()
    source, build, output = (p.resolve() for p in (opts.source, opts.build_dir, opts.output))
    if source.suffix.lower() != ".tex" or not source.is_file():
        parser.error("source must be an existing .tex file")
    if output.suffix.lower() != ".pdf" or opts.pages < 1:
        parser.error("output must be a .pdf path and --pages must be positive")
    if build == source.parent or build in source.parents:
        parser.error("put --build-dir in a dedicated temporary folder")
    build.mkdir(parents=True, exist_ok=True)
    compile_deck(source, build, opts.docker_image)
    texlog = build / "defense.log"
    problems = [line for line in texlog.read_text(errors="replace").splitlines() if LAYOUT_ERRORS.search(line)]
    if problems:
        raise RuntimeError(f"TeX layout problems in {texlog}\n" + "\n".join(problems))
    pdf = build / "defense.pdf"
    pages = page_count(pdf)
    if pages != opts.pages:
        raise RuntimeError(f"Expected {opts.pages} PDF pages, found {pages}.")
    if pdf != output:
        output.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(pdf, output)
    print(f"Verified {pages} XeLaTeX PDF pages with no overfull boxes or missing glyphs: {output}")


if __name__ == "__main__":
    try:
        main()
    except (OSError, RuntimeError, subprocess.CalledProcessError) as error:
        sys.exit(str(error))
