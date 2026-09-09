from pathlib import Path

path = Path("tools/apply_awg31_only_cleanup.py")
body = path.read_text(encoding="utf-8")
old = "body = replace_once(body, '    awg_private=\"$(awg genkey)\"\\n    awg_public=\"$(printf \\\'%s\\\\n\\\' \"$awg_private\" | awg pubkey)\"\\n', \"\", \"AWG2 keygen\")"
new = "keygen = '    awg_private=\"$(awg genkey)\"\\n    awg_public=\"$(printf \\\'%s\\\\n\\\' \"$awg_private\" | awg pubkey)\"\\n'\nif body.count(keygen) < 1:\n    raise SystemExit(\"AWG2 keygen: no matches\")\nbody = body.replace(keygen, \"\")"
if old not in body:
    raise SystemExit("target applicator line not found")
path.write_text(body.replace(old, new, 1), encoding="utf-8", newline="\n")
print("applicator repaired")
