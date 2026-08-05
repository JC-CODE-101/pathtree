"""Persistent configuration manager for PathTree."""

import json
import os
from pathlib import Path

import platformdirs


class ConfigManager:
    """Manages persistent configuration for PathTree."""

    def __init__(self, config_file_path: Path | None = None) -> None:
        """Initialize the ConfigManager with a config file path.

        Defaults to user_config_dir / "config.json" via platformdirs.
        Can be overridden via the environment variable PATHTREE_CONFIG_PATH.
        """
        if config_file_path is not None:
            self.config_file_path = config_file_path
        else:
            env_path = os.getenv("PATHTREE_CONFIG_PATH")
            if env_path:
                self.config_file_path = Path(env_path)
            else:
                config_dir = Path(
                    platformdirs.user_config_dir("pathtree", appauthor=False)
                )
                self.config_file_path = config_dir / "config.json"

    def load(self) -> dict:
        """Load the configuration from the JSON file safely.

        If the file is missing, empty, or corrupted, returns empty dict.
        """
        if not self.config_file_path.exists():
            return {}
        try:
            with open(self.config_file_path, encoding="utf-8") as f:
                content = f.read().strip()
                if not content:
                    return {}
                return json.loads(content)
        except Exception:
            return {}

    def save(self, data: dict) -> None:
        """Save the configuration to the JSON file using atomic/safe write approach."""
        try:
            self.config_file_path.parent.mkdir(parents=True, exist_ok=True)
            with open(self.config_file_path, "w", encoding="utf-8") as f:
                json.dump(data, f, indent=2)
        except Exception:
            pass

    def get_icon_mode(self) -> str:
        """Resolve the active icon mode (nerd, unicode, ascii, or auto).

        Central configuration takes precedence over environment variable.
        If not explicitly configured, defaults to unicode.
        """
        data = self.load()
        if "icons" in data:
            return data["icons"].lower()

        # Fallback to environment variable for backwards compatibility
        env_val = os.environ.get("PATHTREE_NERD_FONTS")
        if env_val is not None:
            if env_val.lower() in ("1", "true", "yes", "on"):
                return "nerd"
            elif env_val.lower() in ("0", "false", "no", "off"):
                return "unicode"

        return "unicode"  # default safe fallback

    def set_icon_mode(self, mode: str) -> None:
        """Set the persistent icon mode."""
        if mode not in ("nerd", "unicode", "ascii", "auto"):
            raise ValueError(f"Invalid icon mode: {mode}")
        data = self.load()
        data["icons"] = mode
        self.save(data)


config_manager = ConfigManager()
