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
