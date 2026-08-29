from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def test_memory_warning_starts_at_85_percent() -> None:
    template = (ROOT / "app/web/templates/system.html").read_text(encoding="utf-8")

    assert (
        "{% set memory_state = 'critical' if resources.memory.percent >= 97 "
        "else 'high' if resources.memory.percent >= 92 "
        "else 'warning' if resources.memory.percent >= 85 else 'normal' %}"
    ) in template
    assert (
        "{% set memory_label = 'Критично' if resources.memory.percent >= 97 "
        "else 'Мало свободной памяти' if resources.memory.percent >= 92 "
        "else 'Предупреждение' if resources.memory.percent >= 85 else 'Норма' %}"
    ) in template
    assert 'class="sv1-state-pill {{ memory_state }}">{{ memory_label }}</span>' in template


def test_disk_thresholds_are_calibrated_for_small_vps_disks() -> None:
    template = (ROOT / "app/web/templates/system.html").read_text(encoding="utf-8")

    assert (
        "{% set disk_state = 'critical' if resources.disk.percent >= 95 "
        "else 'high' if resources.disk.percent >= 90 "
        "else 'warning' if resources.disk.percent >= 80 else 'normal' %}"
    ) in template
    assert (
        "{% set disk_label = 'Критично' if resources.disk.percent >= 95 "
        "else 'Мало свободного места' if resources.disk.percent >= 90 "
        "else 'Предупреждение' if resources.disk.percent >= 80 else 'Норма' %}"
    ) in template
    assert 'class="sv1-state-pill {{ disk_state }}">{{ disk_label }}</span>' in template


def test_cpu_keeps_existing_independent_state() -> None:
    template = (ROOT / "app/web/templates/system.html").read_text(encoding="utf-8")

    assert 'class="sv1-state-pill {{ resources.cpu.state }}">{{ resources.cpu.state_label }}</span>' in template
