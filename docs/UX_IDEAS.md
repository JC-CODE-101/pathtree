# UX Ideas

This document collects small UX improvements and quality-of-life ideas for PathTree. These are intentionally kept separate from the implementation roadmap.

## Input & Editing
- Shortcut to select the entire contents of the active input field.
- Ctrl+J / Ctrl+K navigation through autocomplete suggestions.
- Automatic scrolling while moving the highlighted autocomplete entry.
- Automatic default icons based on node/resource type.

## Tree Navigation
- `W` jumps to the next Workspace.
- `Shift+W` jumps to the previous Workspace.
- `F` jumps to the next Folder.
- `Shift+F` jumps to the previous Folder.
- Consider Home/End style navigation within Folder groups or within the current Workspace.
- Preserve the tree expansion/collapse state for the duration of a terminal session so reopening `pb` restores the previous navigation state.

## Path Handling
- File-system browser instead of manually typing paths.
- Better directory/file filtering depending on node type.

## Shell & Navigation
- Temporary anchors (e.g. `pb -a`).
- Workspace-local numeric shortcuts (`pb 1`, `pb 2`, `pb -l`).
- Workspace profiles.

## Future
- Executable, Script, URL and Command resource types.
- Snapshot/restore of temporary session entries.
