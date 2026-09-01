from pathlib import Path
import sys
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from mizulauncher.security.integrity import write_manifest

if len(sys.argv) != 2:
    raise SystemExit("usage: python tools/write_exe_manifest.py <exe>")
print(write_manifest(Path(sys.argv[1])))
