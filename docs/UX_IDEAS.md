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

## Resource Type Navigation
- Use `R` as a prefix for resource navigation.
- `R` + `D` selects Directory navigation.
- `R` + `F` selects File navigation.
- `R` + `S` selects Script navigation.
- `R` + `E` selects Executable navigation.
- `R` + `U` selects URL navigation.
- `.` jumps to the next resource of the selected type.
- `Shift+.` jumps to the previous resource of the selected type.

## Context-sensitive Status Bar
- Show only shortcuts valid for the currently selected node and active UI mode.
- Display different shortcuts for Workspace, Folder and Resource nodes.
- Prefix commands such as `R` temporarily replace the normal status bar with context-specific shortcuts.
- Restore the normal status bar after the action completes or after `Esc`.

## Key Profiles
- Define the default keyboard shortcuts as a named Standard profile.
- Allow users to create one or more custom key profiles.
- Allow switching between the Standard profile and a selected custom profile.
- Custom profiles may override only selected shortcuts and inherit all remaining bindings from Standard.
- Provide a settings/options view for inspecting, changing and resetting shortcut assignments.
- Detect conflicting assignments before saving a profile.

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
