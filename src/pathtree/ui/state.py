"""Module to handle persistence and restoration of the terminal UI tree state."""

import json
import logging
import os
import tempfile
import uuid
from dataclasses import dataclass, field
from pathlib import Path

import platformdirs

logger = logging.getLogger(__name__)


@dataclass
class TreeState:
    """Represents the UI tree state to be persisted."""

    expanded_node_ids: set[uuid.UUID] = field(default_factory=set)
    selected_node_id: uuid.UUID | None = None


class TreeStateStore:
    """Responsible for loading and saving TreeState to a file."""

    def __init__(self, state_file_path: Path | None = None) -> None:
        """Initialize the TreeStateStore with a state file path.

        Defaults to user_state_dir / "tree-state.json" via platformdirs.
        Can be overridden via the environment variable PATHTREE_STATE_PATH.
        """
        if state_file_path is not None:
            self.state_file_path = state_file_path
        else:
            env_path = os.getenv("PATHTREE_STATE_PATH")
            if env_path:
                self.state_file_path = Path(env_path)
            else:
                state_dir = Path(
                    platformdirs.user_state_dir("pathtree", appauthor=False)
                )
                self.state_file_path = state_dir / "tree-state.json"

    def load(self) -> TreeState:
        """Load the tree state from the JSON file safely.

        If the file is missing, empty, or corrupted, returns empty TreeState.
        """
        if not self.state_file_path.exists():
            return TreeState()

        try:
            with open(self.state_file_path, encoding="utf-8") as f:
                content = f.read().strip()
                if not content:
                    return TreeState()
                data = json.loads(content)
        except (OSError, UnicodeError, json.JSONDecodeError) as e:
            logger.warning("Failed to read or parse tree state file: %s", e)
            return TreeState()

        if not isinstance(data, dict):
            logger.warning("Invalid tree state file content: expected a JSON object.")
            return TreeState()

        expanded_node_ids = set()
        expanded_list = data.get("expanded_node_ids", [])
        if isinstance(expanded_list, list):
            for item in expanded_list:
                try:
                    expanded_node_ids.add(uuid.UUID(str(item)))
                except (ValueError, TypeError):
                    # Ignore invalid UUIDs
                    pass

        selected_node_id = None
        sel_val = data.get("selected_node_id")
        if sel_val is not None:
            try:
                selected_node_id = uuid.UUID(str(sel_val))
            except (ValueError, TypeError):
                # Ignore invalid UUID
                pass

        return TreeState(
            expanded_node_ids=expanded_node_ids,
            selected_node_id=selected_node_id,
        )

    def save(self, state: TreeState) -> None:
        """Save the tree state to the JSON file using an atomic/safe write approach."""
        temp_file_path = None
        try:
            # Ensure the parent directory exists
            self.state_file_path.parent.mkdir(parents=True, exist_ok=True)

            # Convert state to dict, converting UUIDs to strings
            serialized_data = {
                "expanded_node_ids": [str(uid) for uid in state.expanded_node_ids],
                "selected_node_id": (
                    str(state.selected_node_id)
                    if state.selected_node_id is not None
                    else None
                ),
            }

            # Atomic write using a temporary file in the same directory
            temp_dir = self.state_file_path.parent
            with tempfile.NamedTemporaryFile(
                "w", dir=temp_dir, delete=False, encoding="utf-8", suffix=".tmp"
            ) as temp_file:
                json.dump(serialized_data, temp_file, indent=2)
                temp_file_path = Path(temp_file.name)

            # Atomic replace
            os.replace(temp_file_path, self.state_file_path)
        except (OSError, TypeError, ValueError) as e:
            logger.error("Failed to save tree state: %s", e)
            # Cleanup temp file if it still exists
            if temp_file_path is not None and temp_file_path.exists():
                try:
                    temp_file_path.unlink()
                except OSError:
                    pass
