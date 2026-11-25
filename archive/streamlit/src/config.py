"""config/indicators.yaml을 읽어 지표 목록을 돌려준다."""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[1]
CONFIG_PATH = ROOT / "config" / "indicators.yaml"
RAW_DIR = ROOT / "data" / "raw"
MANUAL_DIR = ROOT / "data" / "manual"

SOURCES = {"fred", "manual", "nyfed", "treasury"}
SECTIONS = {"curve", "policy", "growth", "inflation", "supply_tp", "liquidity_vol"}
FREQS = {"d", "w", "m", "q"}


@dataclass(frozen=True)
class Indicator:
    id: str
    name: str
    source: str
    section: str
    unit: str
    freq: str
    ticker: str | None = None
    strategies: tuple[str, ...] = field(default_factory=tuple)
    note: str | None = None

    @property
    def path(self) -> Path:
        """이 지표의 CSV 저장 위치 (date,value)."""
        if self.source == "manual":
            return MANUAL_DIR / f"{self.id}.csv"
        return RAW_DIR / self.source / f"{self.id}.csv"


def load_config(path: Path = CONFIG_PATH) -> tuple[dict, list[Indicator]]:
    raw = yaml.safe_load(path.read_text(encoding="utf-8"))
    defaults = raw.get("defaults", {})
    indicators: list[Indicator] = []
    seen: set[str] = set()
    for item in raw["indicators"]:
        ind = Indicator(
            id=item["id"],
            name=item["name"],
            source=item["source"],
            section=item["section"],
            unit=item["unit"],
            freq=item["freq"],
            ticker=item.get("ticker"),
            strategies=tuple(item.get("strategies", [])),
            note=item.get("note"),
        )
        _validate(ind, seen)
        seen.add(ind.id)
        indicators.append(ind)
    return defaults, indicators


def _validate(ind: Indicator, seen: set[str]) -> None:
    where = f"indicators.yaml의 '{ind.id}'"
    if ind.id in seen:
        raise ValueError(f"{where}: id가 중복된다")
    if ind.source not in SOURCES:
        raise ValueError(f"{where}: source는 {sorted(SOURCES)} 중 하나여야 한다")
    if ind.section not in SECTIONS:
        raise ValueError(f"{where}: section은 {sorted(SECTIONS)} 중 하나여야 한다")
    if ind.freq not in FREQS:
        raise ValueError(f"{where}: freq는 {sorted(FREQS)} 중 하나여야 한다")
    if ind.source == "fred" and not ind.ticker:
        raise ValueError(f"{where}: FRED 지표는 ticker가 필요하다")
