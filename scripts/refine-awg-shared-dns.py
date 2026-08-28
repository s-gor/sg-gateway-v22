from pathlib import Path


def replace_once(path: str, old: str, new: str) -> None:
    target = Path(path)
    text = target.read_text(encoding="utf-8")
    count = text.count(old)
    if count != 1:
        raise SystemExit(f"{path}: expected one match, found {count}")
    target.write_text(text.replace(old, new, 1), encoding="utf-8")


def replace_count(path: str, old: str, new: str, expected: int) -> None:
    target = Path(path)
    text = target.read_text(encoding="utf-8")
    count = text.count(old)
    if count != expected:
        raise SystemExit(f"{path}: expected {expected} matches, found {count}")
    target.write_text(text.replace(old, new), encoding="utf-8")


replace_count(
    "app/main.py",
    '        config["dns"] = request.form.get("dns", config.get("dns", "1.1.1.1"))\n',
    '',
    2,
)
replace_once(
    "app/web/templates/connections.html",
    '<label><span>DNS</span><input type="text" name="dns" value="{{ awg_settings.config.get(\'dns\', \'1.1.1.1\') }}"></label>',
    '<label><span>DNS</span><input type="text" value="{{ awg_settings.config.get(\'dns\', \'1.1.1.1\') }}" disabled></label>',
)
replace_once(
    "app/web/templates/connections.html",
    '<label><span>DNS</span><input type="text" name="dns" value="{{ awg3_settings.config.get(\'dns\', \'1.1.1.1\') }}"></label>',
    '<label><span>DNS</span><input type="text" value="{{ awg3_settings.config.get(\'dns\', \'1.1.1.1\') }}" disabled></label>',
)
replace_once(
    "app/web/templates/connections.html",
    ' inputmode="decimal"',
    '',
)
print("shared DNS authority refinement applied")
