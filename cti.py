#!/usr/bin/env python3
"""Start native Codex research, or use --wizard for offline case preparation."""
from pathlib import Path
import sys

if __name__ == "__main__":
    repo = Path(__file__).resolve().parent
    args = sys.argv[1:]
    offline = {"--doctor", "--demo", "prepare", "result"}
    if "--wizard" in args or (args and args[0] in offline):
        sys.argv = [sys.argv[0], *[a for a in args if a != "--wizard"]]
        sys.path.insert(0, str(repo / "intel_engine" / "tools"))
        from guided import main
    else:
        sys.path.insert(0, str(repo / "scripts"))
        from start_codex import main
    raise SystemExit(main())
