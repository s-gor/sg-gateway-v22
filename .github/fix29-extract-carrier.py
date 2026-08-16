from pathlib import Path

source = Path("/tmp/fix29-carrier.yml").read_text(encoding="utf-8").splitlines()
begin = next(i for i, line in enumerate(source) if line == "          python3 - <<'PY'")
end = next(i for i, line in enumerate(source[begin + 1 :], begin + 1) if line == "          PY")
out: list[str] = []
in_triple = False
for raw in source[begin + 1 : end]:
    line = raw if in_triple else (raw[10:] if raw.startswith("          ") else raw)
    out.append(line)
    if line.count("'''") % 2:
        in_triple = not in_triple
if in_triple:
    raise SystemExit("unterminated triple-quoted literal in Fix29 carrier")
script = "\n".join(out) + "\n"
compile(script, "/tmp/fix29_patch.py", "exec")
Path("/tmp/fix29_patch.py").write_text(script, encoding="utf-8", newline="\n")
print(f"FIX29_PATCH_COMPILED lines={len(out)}")
