from __future__ import annotations

from dataclasses import dataclass, field
from html.parser import HTMLParser


@dataclass(frozen=True)
class FormContract:
    action: str
    method: str = "get"
    names: frozenset[str] = field(default_factory=frozenset)
    ids: frozenset[str] = field(default_factory=frozenset)
    data_hooks: frozenset[str] = field(default_factory=frozenset)


@dataclass(frozen=True)
class HtmlContract:
    forms: tuple[FormContract, ...]
    ids: frozenset[str]
    data_hooks: frozenset[str]


class _ContractParser(HTMLParser):
    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.forms: list[dict[str, object]] = []
        self._form_stack: list[dict[str, object]] = []
        self.ids: set[str] = set()
        self.data_hooks: set[str] = set()

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        values = dict(attrs)
        element_id = values.get("id")
        if element_id:
            self.ids.add(element_id)
        element_data_hooks = {name for name, _value in attrs if name.startswith("data-")}
        self.data_hooks.update(element_data_hooks)

        if tag == "form":
            current: dict[str, object] = {
                "action": values.get("action") or "",
                "method": (values.get("method") or "get").lower(),
                "names": set(),
                "ids": set(),
                "data_hooks": set(),
            }
            self.forms.append(current)
            self._form_stack.append(current)

        if not self._form_stack:
            return

        current = self._form_stack[-1]
        name = values.get("name")
        if name:
            current["names"].add(name)  # type: ignore[union-attr]
        if element_id:
            current["ids"].add(element_id)  # type: ignore[union-attr]
        current["data_hooks"].update(element_data_hooks)  # type: ignore[union-attr]

    def handle_startendtag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        self.handle_starttag(tag, attrs)
        if tag == "form" and self._form_stack:
            self._form_stack.pop()

    def handle_endtag(self, tag: str) -> None:
        if tag == "form" and self._form_stack:
            self._form_stack.pop()


def extract_html_contract(html: str) -> HtmlContract:
    parser = _ContractParser()
    parser.feed(html)
    parser.close()

    forms = tuple(
        FormContract(
            action=str(item["action"]),
            method=str(item["method"]),
            names=frozenset(item["names"]),  # type: ignore[arg-type]
            ids=frozenset(item["ids"]),  # type: ignore[arg-type]
            data_hooks=frozenset(item["data_hooks"]),  # type: ignore[arg-type]
        )
        for item in parser.forms
    )
    return HtmlContract(
        forms=forms,
        ids=frozenset(parser.ids),
        data_hooks=frozenset(parser.data_hooks),
    )


def _form_matches(actual: FormContract, expected: FormContract) -> bool:
    return (
        actual.action == expected.action
        and actual.method == expected.method
        and expected.names <= actual.names
        and expected.ids <= actual.ids
        and expected.data_hooks <= actual.data_hooks
    )


def require_contract(
    actual: HtmlContract,
    *,
    forms: tuple[FormContract, ...] = (),
    ids: tuple[str, ...] = (),
    data_hooks: tuple[str, ...] = (),
) -> None:
    missing_ids = sorted(set(ids) - actual.ids)
    assert not missing_ids, f"missing required ids: {missing_ids}; available={sorted(actual.ids)}"

    missing_hooks = sorted(set(data_hooks) - actual.data_hooks)
    assert not missing_hooks, (
        f"missing required data hooks: {missing_hooks}; available={sorted(actual.data_hooks)}"
    )

    missing_forms = [
        expected
        for expected in forms
        if not any(_form_matches(candidate, expected) for candidate in actual.forms)
    ]
    assert not missing_forms, (
        "missing required form contracts: "
        f"{missing_forms}; available={list(actual.forms)}"
    )
