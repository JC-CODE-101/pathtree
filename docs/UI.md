# PathTree User Interface

Version: 0.1 (Draft)

---

# Overview

PathTree provides a keyboard-first terminal user interface built with Textual.

The interface should remain:

- fast
- simple
- predictable
- responsive

The primary purpose of the interface is to allow users to organize and navigate their development workspace with as few keystrokes as possible.

---

# Design Goals

The interface should:

- minimize keyboard input
- avoid unnecessary dialogs
- provide immediate feedback
- remain responsive
- work well in terminals of different sizes

---

# Main Window

The application starts with a single main window.

The window consists of three logical areas.

```
+------------------------------------------------------+
| Search                                                |
+------------------------------------------------------+
|                                                      |
| Tree                          Details                |
|                                                      |
|                                                      |
|                                                      |
+------------------------------------------------------+
| Status Bar                                           |
+------------------------------------------------------+
```

---

# Search Area

The search field is always available.

Typing immediately filters the visible tree.

Search should never require opening a separate dialog.

---

# Tree View

The tree view is the primary navigation component.

It displays:

- workspaces
- folders
- files
- notes
- documentation
- websites

The tree supports unlimited depth.

Collapsed and expanded nodes should be clearly distinguishable.

---

# Details Panel

The details panel displays information about the currently selected node.

Examples:

- Name
- Description
- Path
- Node Type
- Favorite
- Temporary
- Available Actions

The details panel never modifies data directly.

---

# Status Bar

The status bar provides context-sensitive help.

Examples:

```
Enter  Open

A  Add

E  Edit

D  Delete

F  Favorite

Q  Quit
```

The displayed shortcuts may change depending on the current context.

---

# Dialogs

Dialogs should remain minimal.

Examples:

- Add Node
- Edit Node
- Delete Confirmation

Avoid multi-page dialogs whenever possible.

---

# Navigation

Navigation is entirely keyboard driven.

Primary navigation:

- Up
- Down
- Left
- Right
- Enter
- Escape

The user should never need a mouse.

---

# Search Workflow

User starts typing.

↓

Tree updates immediately.

↓

User presses Enter.

↓

Selected node becomes active.

---

# Action Workflow

Select node

↓

Open Action Menu

↓

Choose Action

↓

Execute

---

# Editing Workflow

Select node

↓

Edit

↓

Modify values

↓

Save

The tree updates immediately.

---

# Startup

Launching

```
pb
```

opens the main application.

The previously selected node may be restored in future versions.

---

# Shutdown

Closing the application should:

- save settings
- save UI state
- preserve persistent nodes

Temporary session nodes may be removed.

---

# Error Handling

Errors should be displayed inside the interface.

Avoid printing stack traces directly to the terminal.

Messages should be short and understandable.

---

# Accessibility

The interface should remain usable in:

- dark terminals
- light terminals
- small terminal windows

The application should not rely solely on colors.

Icons should improve readability but must remain optional.

---

# Future UI Features

Future versions may introduce:

- Mouse support
- Multiple panes
- Configurable layouts
- Themes
- Custom icons

These features are intentionally postponed until after the first stable release.

---

# User Experience Principles

The interface should always feel:

- lightweight
- responsive
- intuitive
- keyboard-first

The user should spend time navigating projects, not learning the interface.

---

# Summary

The user interface is designed around one central principle:

The shortest path between opening the application and reaching the desired resource should require the fewest possible keystrokes.
