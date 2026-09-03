from __future__ import annotations

import hashlib
import importlib.util
import json
from pathlib import Path
from types import ModuleType
from typing import Any


ROOT = Path(__file__).resolve().parents[2]
DEFAULT_CONFIG = ROOT / "configs" / "runtime-modern-v1-2026-07-20.json"


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


class ModernRuntime:
    def __init__(self, config_path: Path = DEFAULT_CONFIG) -> None:
        self.config_path = config_path.resolve()
        self.config = json.loads(self.config_path.read_text(encoding="utf-8"))
        self.runtime_snapshot_path = self._required_file("runtime_snapshot")
        self.extension = self._required_file("extension")
        self.cdb = self._required_file("cdb")
        self.cardscripts = self._required_directory("cardscripts")
        self.code_list = self._required_file("code_list")
        self.asset_manifest_path = self._required_file("asset_manifest")
        self.decks = {
            name: str(self._resolve_file(path))
            for name, path in self.config["decks"].items()
        }
        if not self.decks:
            raise ValueError("Modern runtime config must contain at least one deck")
        self.asset_manifest = json.loads(
            self.asset_manifest_path.read_text(encoding="utf-8")
        )
        self.runtime_snapshot = json.loads(
            self.runtime_snapshot_path.read_text(encoding="utf-8")
        )
        self._validate_manifest()
        self._validate_profiles()
        self._extension_module: ModuleType | None = None
        self._initialized = False

    def _resolve(self, value: str) -> Path:
        path = Path(value)
        return path if path.is_absolute() else ROOT / path

    def _resolve_file(self, value: str) -> Path:
        path = self._resolve(value).resolve()
        if not path.is_file():
            raise FileNotFoundError(f"Required runtime file not found: {path}")
        return path

    def _required_file(self, key: str) -> Path:
        value = self.config.get(key)
        if not isinstance(value, str) or not value:
            raise ValueError(f"Runtime config field '{key}' must be a non-empty path")
        return self._resolve_file(value)

    def _required_directory(self, key: str) -> Path:
        value = self.config.get(key)
        if not isinstance(value, str) or not value:
            raise ValueError(f"Runtime config field '{key}' must be a non-empty path")
        path = self._resolve(value).resolve()
        if not path.is_dir():
            raise FileNotFoundError(f"Required runtime directory not found: {path}")
        return path

    def _validate_manifest(self) -> None:
        expected_id = self.config["runtime_snapshot_id"]
        if self.runtime_snapshot.get("runtime_snapshot_id") != expected_id:
            raise ValueError("Runtime config and runtime snapshot IDs do not match")
        if self.asset_manifest.get("runtime_snapshot_id") != expected_id:
            raise ValueError("Runtime config and asset manifest IDs do not match")
        cdb = self.asset_manifest["cdb"]
        if sha256_file(self.cdb) != cdb["sha256"]:
            raise ValueError(f"CDB hash does not match asset manifest: {self.cdb}")
        code_list = self.asset_manifest["code_list"]
        if sha256_file(self.code_list) != code_list["sha256"]:
            raise ValueError(
                f"Code list hash does not match asset manifest: {self.code_list}"
            )
        manifest_decks = {item["name"]: item for item in self.asset_manifest["decks"]}
        if set(manifest_decks) != set(self.decks):
            raise ValueError("Runtime config and asset manifest deck names do not match")
        for name, deck_path in self.decks.items():
            expected_hash = manifest_decks[name]["sha256"]
            if sha256_file(Path(deck_path)) != expected_hash:
                raise ValueError(f"Deck hash does not match asset manifest: {deck_path}")

    def _validate_profiles(self) -> None:
        environments = self.config.get("environments")
        if not isinstance(environments, dict) or set(environments) != {"tcg", "ocg"}:
            raise ValueError("Modern runtime must define exactly the TCG and OCG profiles")
        for name, profile in environments.items():
            if not isinstance(profile, dict):
                raise ValueError(f"Runtime profile '{name}' must be an object")
            snapshot_id = profile.get("snapshot_id")
            if not isinstance(snapshot_id, str) or not snapshot_id:
                raise ValueError(
                    f"Runtime profile '{name}' must define a non-empty snapshot_id"
                )
            spec = profile.get("spec")
            if not isinstance(spec, dict):
                raise ValueError(f"Runtime profile '{name}' must define a spec object")
            for key in ("deck1", "deck2"):
                deck = spec.get(key)
                if deck not in self.decks:
                    raise ValueError(
                        f"Runtime profile '{name}' references unknown {key}: {deck}"
                    )

    def profile(self, name: str) -> dict[str, Any]:
        environments = self.config["environments"]
        if name not in environments:
            raise ValueError(
                f"Unknown runtime profile '{name}'; expected one of {sorted(environments)}"
            )
        return environments[name]

    def load_extension(self) -> ModuleType:
        if self._extension_module is not None:
            return self._extension_module
        spec = importlib.util.spec_from_file_location("edopro_ygoenv", self.extension)
        if spec is None or spec.loader is None:
            raise RuntimeError(f"Unable to load extension spec: {self.extension}")
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        required = {"_EDOProEnvPool", "_EDOProEnvSpec", "init_module"}
        missing = sorted(required.difference(dir(module)))
        if missing:
            raise RuntimeError(f"Modern extension is missing exports: {missing}")
        self._extension_module = module
        return module

    def initialize(self) -> None:
        if self._initialized:
            raise RuntimeError("ModernRuntime.initialize() may only be called once")
        module = self.load_extension()
        module.init_module(
            str(self.cdb),
            str(self.code_list),
            self.decks,
            str(self.cardscripts),
        )
        self._initialized = True

    def environment_spec(
        self,
        profile: str,
        overrides: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        environment_spec = dict(self.profile(profile)["spec"])
        if overrides is None:
            return environment_spec
        unknown = sorted(set(overrides).difference(environment_spec))
        if unknown:
            raise ValueError(
                f"Runtime profile '{profile}' overrides unknown fields: {unknown}"
            )
        environment_spec.update(overrides)
        if environment_spec["num_envs"] != environment_spec["batch_size"]:
            raise ValueError("Runtime num_envs and batch_size must match")
        if environment_spec["num_threads"] > environment_spec["num_envs"]:
            raise ValueError("Runtime num_threads cannot exceed num_envs")
        return environment_spec

    def make_spec(
        self,
        profile: str,
        overrides: dict[str, Any] | None = None,
    ) -> tuple[Any, tuple[type[Any], ...]]:
        if not self._initialized:
            raise RuntimeError("Initialize the modern runtime before creating a spec")
        from ygoenv.python.api import py_env

        module = self.load_extension()
        classes = py_env(module._EDOProEnvSpec, module._EDOProEnvPool)
        spec_class = classes[0]
        config = spec_class.gen_config(**self.environment_spec(profile, overrides))
        return spec_class(config), classes

    def construct_gymnasium_pool(
        self,
        profile: str,
        overrides: dict[str, Any] | None = None,
    ) -> Any:
        spec, classes = self.make_spec(profile, overrides)
        gymnasium_pool_class = classes[3]
        return gymnasium_pool_class(spec)
