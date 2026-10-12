"""Диалог сопоставления полей шаблона с колонками данных."""

from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (QComboBox, QDialog, QFrame, QGridLayout, QHBoxLayout, QScrollArea,
                               QVBoxLayout, QWidget)

from ..core.models import DataSet, TemplateInfo
from ..core.money import parse_decimal
from ..core.template_engine import to_date
from ..core.templates import field_label, flat_item_mapping
from .documents import display_value
from .widgets import button, icon_label, label

NONE_TEXT = "— не выбрано —"


class MappingDialog(QDialog):
    def __init__(self, info: TemplateInfo, dataset: DataSet, mapping: dict[str, str], parent=None):
        super().__init__(parent)
        self.setWindowTitle("Сопоставление полей")
        self.setModal(True)
        self.setMinimumWidth(760)
        self.dataset = dataset
        self.combos: dict[str, QComboBox] = {}
        self.samples: dict[str, object] = {}

        root = QVBoxLayout(self)
        root.setContentsMargins(24, 22, 24, 20)
        root.setSpacing(14)
        root.addWidget(label("Сопоставление полей", "PageTitle"))
        root.addWidget(label(
            f"Укажите, из каких колонок файла «{dataset.name}» брать данные для шаблона "
            f"«{info.name}». Если подходящей колонки нет, лучше выбрать другой файл. "
            "Выбор запоминается для этой пары.", "Muted", wrap=True))

        card = QFrame()
        card.setObjectName("Card")
        grid = QGridLayout(card)
        grid.setContentsMargins(18, 14, 18, 14)
        grid.setHorizontalSpacing(14)
        grid.setVerticalSpacing(10)
        grid.addWidget(label("Поле шаблона", "Small"), 0, 0)
        grid.addWidget(label("Колонка в данных", "Small"), 0, 2)
        grid.addWidget(label("Пример из первой записи", "Small"), 0, 3)
        first = dataset.records[0].values if dataset.records else {}
        self.info = info
        for row, name in enumerate(info.required, start=1):
            names = QVBoxLayout()
            names.setSpacing(0)
            names.addWidget(label(field_label(name), "CardTitle"))
            hint = label(name + (" · список или колонки товар и цена" if name in info.lists else
                                 {"date": " · дата", "number": " · число"}.get(info.types.get(name, ""), "")),
                         "Faint")
            names.addWidget(hint)
            grid.addLayout(names, row, 0)
            grid.addWidget(icon_label("chevron-right", "text3", 14), row, 1)
            combo = QComboBox()
            combo.addItem(NONE_TEXT, "")
            for col in dataset.columns:
                combo.addItem(col, col)
            current = mapping.get(name, "")
            combo.setCurrentIndex(max(combo.findData(current), 0))
            combo.setMinimumWidth(200)
            sample = label("", "Faint")
            sample.setMinimumWidth(180)
            sample.setWordWrap(True)
            combo.currentIndexChanged.connect(
                lambda _=0, c=combo, s=sample, n=name: self._update_sample(s, first, n, c.currentData()))
            self._update_sample(sample, first, name, current)
            self.combos[name] = combo
            grid.addWidget(combo, row, 2)
            grid.addWidget(sample, row, 3)
        grid.setColumnStretch(3, 1)

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.Shape.NoFrame)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        holder = QWidget()
        hl = QVBoxLayout(holder)
        hl.setContentsMargins(0, 0, 0, 0)
        hl.addWidget(card)
        hl.addStretch(1)
        scroll.setWidget(holder)
        root.addWidget(scroll, 1)

        actions = QHBoxLayout()
        actions.addStretch(1)
        cancel = button("Отмена")
        cancel.clicked.connect(self.reject)
        save = button("Сохранить", "check", "primary")
        save.setDefault(True)
        save.clicked.connect(self.accept)
        actions.addWidget(cancel)
        actions.addWidget(save)
        root.addLayout(actions)
        self.resize(780, min(250 + 66 * len(info.required), 640))

    def _update_sample(self, sample, values: dict, name: str, column: str) -> None:
        """Показывает пример значения и предупреждает, если тип явно не подходит."""
        text = self._sample(values, column)
        value = values.get(column) if column else None
        kind = self.info.types.get(name)
        bad = False
        if value not in (None, "") and kind == "date":
            bad = to_date(value) is None
        elif value not in (None, "") and kind == "number":
            try:
                parse_decimal(value)
            except ValueError:
                bad = True
        elif name in self.info.lists and column:
            bad = not isinstance(value, list)
        if name in self.info.lists and not column:
            flat = flat_item_mapping(list(values))
            if {"product", "price"} <= flat.keys():
                text = "Соберётся из колонок " + ", ".join(flat.values())
        if bad:
            what = {"date": "не похоже на дату", "number": "не похоже на число"}.get(
                kind or "", "нужен список позиций")
            sample.setText(f"{what.capitalize()}: {text}" if text else what.capitalize())
            sample.setObjectName("Warning")
        else:
            sample.setText(text)
            sample.setObjectName("Faint")
        sample.style().unpolish(sample)
        sample.style().polish(sample)

    @staticmethod
    def _sample(values: dict, column: str) -> str:
        if not column:
            return ""
        text = display_value(values.get(column))
        return text if len(text) <= 32 else text[:31] + "…"

    def mapping(self) -> dict[str, str]:
        return {name: combo.currentData() for name, combo in self.combos.items() if combo.currentData()}

