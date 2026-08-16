from pathlib import Path

helper_path = Path("deploy/sg-gateway-awg3-userspace.sh")
helper = helper_path.read_text(encoding="utf-8")
wanted = 'export PATH="$AWG3_ROOT/bin:$PATH"'
if wanted not in helper:
    anchor = 'AWG3_ROOT="/opt/sg-gateway/awg3"\n'
    if helper.count(anchor) != 1:
        raise SystemExit("AWG3_ROOT helper anchor is not unique")
    helper = helper.replace(anchor, anchor + wanted + "\n", 1)
if helper.count(wanted) != 1:
    raise SystemExit("AWG3 isolated PATH must appear exactly once")
helper_path.write_text(helper, encoding="utf-8", newline="\n")

main_path = Path("app/main.py")
main = main_path.read_text(encoding="utf-8")
context = '            awg3_settings=get_connection_settings("amneziawg3"),\n'
conn_start = main.index('    @app.get("/connections")\n')
before, after = main[:conn_start], main[conn_start:]
if context in before:
    before = before.replace(context, "", 1)
main = before + after
conn_start = main.index('    @app.get("/connections")\n')
conn_end = main.index('    @app.post("/connections/amneziawg")\n', conn_start)
block = main[conn_start:conn_end]
if context not in block:
    anchor = '            awg_settings=get_connection_settings("amneziawg"),\n'
    if block.count(anchor) != 1:
        raise SystemExit("Connections AWG context anchor is not unique")
    block = block.replace(anchor, anchor + context, 1)
    main = main[:conn_start] + block + main[conn_end:]
if main.count(context) != 1:
    raise SystemExit("AWG3 settings context must exist only in Connections")
if main.count('@app.post("/connections/amneziawg3")') != 1:
    raise SystemExit("AWG3 Connections update route must exist exactly once")
main_path.write_text(main, encoding="utf-8", newline="\n")

print("FIX29_POSTPATCH_APPLIED")
