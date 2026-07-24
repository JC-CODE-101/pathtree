# PathTree Node Types

Version: 0.1 (Draft)

---

# Overview

Everything inside PathTree is represented by a Node.

A node is the fundamental building block of the application.

All resources, folders, workspaces, and objects inherit the same basic behavior while defining their own purpose.

The tree consists entirely of nodes.

---

# Design Goals

Node types should remain:

- simple
- extensible
- easy to understand
- independent

Adding a new node type should require minimal changes to the existing code.

---

# Common Properties

Every node shares the following properties.

- UUID
- Parent
- Name
- Description
- Icon
- Favorite
- Temporary
- Sort Order
- Created
- Modified

These properties exist regardless of node type.

---

# Workspace

Purpose

Organizes projects and resources into logical groups.

Examples

Python

Linux

Blender

Game Development

A workspace is used for organization only.

---

# Folder

Purpose

Represents a directory on the local filesystem.

Examples

/home/user/projects

/home/user/downloads

---

# File

Purpose

Represents a single file.

Examples

README.md

notes.txt

scene.blend

Semantics

A File resource represents a concrete regular file on the local filesystem. Unlike workspaces or folders, File resources are terminal/leaf nodes and cannot have any child nodes.

Hierarchy Rules

- File resources may be children of:
  - Workspace
  - Folder
- File resources may **not** be parent nodes to any other node.
- A File resource must have a non-empty path, which is strictly validated during node creation and update. This path must:
  - resolve to an existing filesystem entry;
  - resolve to a regular file (directories are rejected);
  - resolve relative paths consistently through the service layer.

Icon & Customization

The default Unicode symbol for File resources is `▤` (Document), with customization options like `📄` (Page) or `🗎` (File Icon) selectable via the Icon Picker dialog.

---

# Script

Purpose

Represents an executable script file.

Examples

run.py

deploy.sh

build.js

Semantics

A Script resource represents a concrete script or executable on the local filesystem. Unlike workspaces or folders, Script resources are terminal/leaf nodes and cannot have any child nodes.

Hierarchy Rules

- Script resources may be children of:
  - Workspace
  - Folder
- Script resources may **not** be parent nodes to any other node.
- A Script resource must have a non-empty path, which is strictly validated during node creation and update. This path must:
  - resolve to an existing filesystem entry;
  - resolve to a regular file (directories are rejected);
  - resolve relative paths consistently through the service layer.

Note on Permissions: The script file does not require its executable bit to be set, because scripts such as Python files may be launched through an interpreter.

Icon & Customization

The default Unicode symbol for Script resources is `⚡` (Lightning), with customization options like `⌁` (Electric), `⚙` (Gear), or `⌬` (Hexagon) selectable via the Icon Picker dialog.

---

# Executable

Purpose

Allows users to register installed applications and command-line programs as workspace resources and launch them.

Examples

- /usr/bin/blender
- /usr/bin/xournalpp
- /usr/bin/ffmpeg
- /usr/bin/git
- Windows application executables (.exe, .com)
- macOS application binaries

Semantics

An Executable resource represents a compiled binary or launcher on the local filesystem. Unlike workspaces or folders, Executable resources are terminal/leaf nodes and cannot have any child nodes.

Hierarchy Rules

- Executable resources may be children of:
  - Workspace
  - Folder
- Executable resources may **not** be parent nodes to any other node.
- An Executable resource must have a non-empty path, which is strictly validated during node creation, editing, and activation.

Validation Rules

- Path is present and non-empty.
- Target exists on the filesystem.
- Target is a regular file (directories are strictly rejected).
- Target is launchable on the current platform:
  - On POSIX systems (Linux, macOS): The target file must have executable permission set (verified using `X_OK`). An explicit validation error is shown if permission is missing.
  - On Windows: The target file must end with a valid executable file extension (such as `.exe` or `.com`), avoiding raw reliance on POSIX permission checks.

Icon & Customization

The default Unicode symbol for Executable resources is `⚙` (Gear), with customization options like `⚒` (Hammer), `❖` (Accent Diamond), or `✦` (Star) selectable via the Icon Picker dialog.

---

# Documentation

Purpose

Represents documentation resources.

Examples

Official documentation

Wiki

PDF manuals

Local documentation

---

# Website

Purpose

Represents a web resource.

Examples

GitHub

Python.org

Blender Docs

---

# Note

Purpose

Stores small pieces of text.

Examples

Todo

Reminder

Cheat Sheet

Useful command

---

# Separator

Purpose

Visually separates groups of nodes.

Contains no data.

Used only for organization.

---

# Disabled

Nodes may be temporarily disabled.

Disabled nodes remain in the tree but cannot execute actions.

---

# Hidden

Hidden nodes remain stored but are not displayed during normal navigation.

---

# Favorite

Any node may become a favorite.

Favorites are displayed separately for quick access.

---

# Temporary

Temporary nodes exist only for the current session.

They are automatically removed when the session ends.

---

# Future Node Types

The following node types are intentionally postponed.

- Command
- Launcher
- SSH
- Docker
- Git
- Variables

These types may be added after the core application has matured.

---

# Design Rules

Node types define meaning.

Behavior belongs to Actions.

Business logic belongs to Services.

Persistence belongs to the Repository.

---

# Summary

Node types describe what something is.

They do not define what happens when the user activates the node.

Execution is handled separately by the Action system.
