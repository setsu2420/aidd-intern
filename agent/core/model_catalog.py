"""Shared model catalog loading and persistence.

The catalog is intentionally a small JSON file so CLI and web model pickers
can stay aligned without baking model lists into Python modules.
"""

from __future__ import annotations

import json
import os
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any


PROJECT_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_MODELS_CONFIG = PROJECT_ROOT / "configs" / "models.json"
_LOCAL_PROVIDERS = {"ollama", "vllm", "lm_studio", "llamacpp"}


@dataclass(frozen=True)
class ModelEntry:
    id: str
    label: str
    provider: str = "custom"
    tier: str = "external"
    aliases: tuple[str, ...] = ()
    recommended: bool = False

    def as_dict(self) -> dict[str, Any]:
        data: dict[str, Any] = {
            "id": self.id,
            "label": self.label,
            "provider": self.provider,
            "tier": self.tier,
        }
        if self.recommended:
            data["recommended"] = True
        if self.aliases:
            data["aliases"] = list(self.aliases)
        return data


@dataclass(frozen=True)
class ModelCatalog:
    path: Path
    default: str | None
    models: tuple[ModelEntry, ...] = field(default_factory=tuple)

    def available_models(
        self, configured_model: str | None = None
    ) -> list[dict[str, Any]]:
        entries = [entry.as_dict() for entry in self.models]
        if configured_model and configured_model not in {
            entry["id"] for entry in entries
        }:
            provider = _provider_from_model_id(configured_model)
            entries.insert(
                0,
                {
                    "id": configured_model,
                    "label": configured_model,
                    "provider": provider,
                    "tier": "local" if provider in _LOCAL_PROVIDERS else "configured",
                    "recommended": True,
                },
            )
        return entries

    def resolve(self, selector: str) -> str | None:
        value = selector.strip()
        if not value:
            return None
        if value.isdigit():
            index = int(value)
            if 1 <= index <= len(self.models):
                return self.models[index - 1].id
        lowered = value.lower()
        for entry in self.models:
            if lowered == entry.id.lower() or lowered == entry.label.lower():
                return entry.id
            if lowered in {alias.lower() for alias in entry.aliases}:
                return entry.id
        return value


def model_catalog_path(config: Any | None = None) -> Path:
    raw = (
        os.environ.get("AIDD_INTERN_MODELS_CONFIG")
        or getattr(config, "models_config", None)
        or DEFAULT_MODELS_CONFIG
    )
    return _resolve_path(raw)


def load_model_catalog(config: Any | None = None) -> ModelCatalog:
    path = model_catalog_path(config)
    if not path.exists():
        return ModelCatalog(path=path, default=None, models=())

    with path.open("r", encoding="utf-8") as handle:
        payload = json.load(handle)
    if not isinstance(payload, dict):
        raise ValueError(f"Model catalog {path} must contain a JSON object")

    default = _substitute_env(payload.get("default"))
    models: list[ModelEntry] = []
    for item in payload.get("models") or []:
        if not isinstance(item, dict):
            continue
        model_id = _substitute_env(item.get("id"))
        if not isinstance(model_id, str) or not model_id.strip():
            continue
        label = _substitute_env(item.get("label")) or model_id
        aliases = item.get("aliases") or []
        if not isinstance(aliases, list):
            aliases = []
        models.append(
            ModelEntry(
                id=model_id.strip(),
                label=str(label).strip() or model_id.strip(),
                provider=str(item.get("provider") or _provider_from_model_id(model_id)),
                tier=str(item.get("tier") or "external"),
                aliases=tuple(
                    str(alias).strip() for alias in aliases if str(alias).strip()
                ),
                recommended=bool(item.get("recommended", False)),
            )
        )
    return ModelCatalog(path=path, default=default, models=tuple(models))


def configured_default_model(config: Any | None = None) -> str | None:
    env_default = os.environ.get("AIDD_INTERN_DEFAULT_MODEL_ID")
    if env_default:
        return env_default.strip()
    catalog = load_model_catalog(config)
    if catalog.default:
        return catalog.default.strip()
    return None


def apply_catalog_default(config: Any) -> None:
    default = configured_default_model(config)
    if default:
        config.model_name = default


def resolve_model_selector(selector: str, config: Any | None = None) -> str:
    catalog = load_model_catalog(config)
    return catalog.resolve(selector) or selector


def set_default_model(model_id: str, config: Any | None = None) -> Path:
    path = model_catalog_path(config)
    payload: dict[str, Any]
    if path.exists():
        with path.open("r", encoding="utf-8") as handle:
            loaded = json.load(handle)
        payload = loaded if isinstance(loaded, dict) else {}
    else:
        payload = {}
    payload["default"] = model_id
    payload.setdefault("models", [])
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as handle:
        json.dump(payload, handle, indent=2)
        handle.write("\n")
    return path


def _resolve_path(path: str | Path) -> Path:
    candidate = Path(path).expanduser()
    if candidate.is_absolute():
        return candidate
    return PROJECT_ROOT / candidate


def _substitute_env(value: Any) -> Any:
    if not isinstance(value, str):
        return value
    pattern = r"\$\{([^}:]+)(?::(-)?([^}]*))?\}"

    def replacer(match: re.Match[str]) -> str:
        env_name = match.group(1)
        has_default = match.group(2) is not None
        default = match.group(3) if has_default else None
        env_value = os.environ.get(env_name)
        if env_value is not None:
            return env_value
        return default or "" if has_default else match.group(0)

    return re.sub(pattern, replacer, value)


def _provider_from_model_id(model_id: str) -> str:
    if "/" not in model_id:
        return "custom"
    prefix = model_id.split("/", 1)[0]
    if prefix in {"openai", "anthropic", "bedrock", "openrouter", "siliconflow"}:
        return prefix
    if prefix in {"ollama", "vllm", "lm_studio", "llamacpp"}:
        return prefix
    return "huggingface"
