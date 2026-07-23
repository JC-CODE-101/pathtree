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

## Resource Actions
- `Enter` performs the default action for the selected resource.
- Directory/path resources switch the current shell directory through the existing shell adapter.
- Executable and Script resources may run their configured default action.
- URL resources open through the configured browser or URL handler.
- `O` opens a context-sensitive action menu for the selected resource.
- The action menu only shows operations valid for that resource type.
- Example Script actions: Run, Edit, Open containing directory, Copy path, View details.
- Example Directory actions: Change directory, Open in file manager, Open terminal here, Copy path, View details.
- Example URL actions: Open, Copy URL, Edit, View details.
- Allow multiple editors or runners to be configured.
- One editor/runner may be selected as the default action used by `Enter`.
- The context menu may allow choosing a different configured editor/runner for a single action without changing the default.

## Open Containing Folder
- Provide a generic cross-platform action named `open_containing_folder`.
- Directory resources may open directly in the system file manager in addition to changing the current shell directory.
- File, Script and Executable resources may open their parent directory instead of opening or running the resource itself.
- Reveal/select the resource in the file manager when the platform supports it.
- Linux: use the default file manager via `xdg-open <directory>`.
- Windows: open the directory with Explorer and support revealing a file with `explorer /select,<file>` where appropriate.
- macOS: use `open <directory>` and `open -R <file>` for reveal behavior.
- Keep the implementation provider-driven through the existing Resource Action Framework.
- Do not add resource-specific branching to `MainScreen`.

## Context-sensitive Status Bar
- Show only shortcuts valid for the currently selected node and active UI mode.
- Display different shortcuts for Workspace, Folder and Resource nodes.
- Prefix commands such as `R` temporarily replace the normal status bar with context-specific shortcuts.
- When a resource is selected, show `Enter` for its default action and `O` for additional actions.
- Restore the normal status bar after the action completes or after `Esc`.

## Key Profiles
- Define the default keyboard shortcuts as a named Standard profile.
- Allow users to create one or more custom key profiles.
- Allow switching between the Standard profile and a selected custom profile.
- Custom profiles may override only selected shortcuts and inherit all remaining bindings from Standard.
- Provide a settings/options view for inspecting, changing and resetting shortcut assignments.
- Detect conflicting assignments before saving a profile.

## Reusable Structure Templates
- Save frequently used Folder/Resource arrangements as reusable named templates.
- Templates are not tied to Blender or programming projects; they may represent general structures such as `System -> Resources`, `Web -> Resources`, `Development -> Resources` or any custom workflow.
- Apply a template inside a new or existing Workspace so common structures do not need to be rebuilt manually.
- Preserve hierarchy, names, node kinds, resource types and optionally icons/descriptions.
- Leave environment-specific values empty by default, including paths, commands, URLs, credentials and machine-specific configuration.
- Allow a template to contain only part of a Workspace, not necessarily the whole Workspace.
- Keep one-time subtree duplication and reusable templates as separate concepts.
- Consider template variables/placeholders for future use, such as `${PROJECT_ROOT}`, `${HOME}`, `${VENV}` or `${REPO}`.
- Treat this as an experimental future feature until repeated real-world use confirms the need.

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
