# AGENTS.md

# PathTree

## Project Overview

PathTree is a modern terminal workspace manager.

The project is **not** just a path bookmark manager.

The long-term goal is to create a central productivity hub for developers that combines:

- Directory navigation
- Hierarchical workspaces
- Bookmarks
- Temporary session paths
- Commands
- Project launchers
- Documentation links
- Notes
- Plugins

The application must remain modular and easily extensible.

---

# Core Philosophy

Every object inside PathTree is a **Node**.

A Node can represent different resources.

Examples:

- Folder
- Workspace
- Command
- Website
- Documentation
- Git Repository
- SSH Connection
- Docker Project
- Python Project
- Note
- Launcher

Nodes are organized in a tree.

Tree depth is unlimited.

---

# Technology Stack

Primary language:

Python 3.13+

UI:

Textual

Database:

SQLite

ORM:

SQLModel or SQLAlchemy
(Choose the simplest solution that keeps the project maintainable.)

Configuration:

JSON

Testing:

pytest

Formatting:

ruff

---

# Shell Integration

Python MUST NEVER directly change the shell working directory.

Instead:

Python returns a selected path.

A small shell adapter executes:

cd <selected_path>

Shell adapters must stay separated from the Python application.

Supported shells in the future:

- Bash
- Zsh
- Fish
- PowerShell

---

# Architecture Rules

Keep responsibilities separated.

Example:

UI

↓

Services

↓

Database

Never mix these layers.

Business logic must never live inside UI widgets.

---

# Development Strategy

Never implement the whole application in one Pull Request.

Every PR should implement exactly one feature or one sprint.

Small PRs are preferred.

Example:

PR 1

Project structure

PR 2

Database

PR 3

Node model

PR 4

Tree widget

PR 5

Navigation

etc.

---

# Pull Request Rules

Before implementing:

1. Read this AGENTS.md
2. Read the documentation inside /docs
3. Explain the planned implementation
4. Keep changes minimal
5. Do not refactor unrelated code

---

# Code Quality

Prefer readability over clever code.

Avoid unnecessary abstractions.

Avoid premature optimization.

Write maintainable code.

Document public classes and functions.

Use type hints.

---

# Database

The database should be designed for future expansion.

Initial entities will likely include:

Node

Action

Workspace

Settings

Do not over-engineer the schema before requirements exist.

---

# Future Features

The architecture should allow adding:

- Tags
- Favorites
- Icons
- Descriptions
- Multiple actions per node
- Multiple launch configurations
- Environment variables
- Plugins
- Themes
- Search
- History
- Import / Export
- Cloud synchronization

without requiring major redesign.

---

# Security

Never execute arbitrary shell commands automatically.

Commands must always be explicitly stored as Actions.

Separate executable from arguments whenever possible.

Avoid shell=True unless absolutely necessary.

---

# Performance

The application should remain responsive even with thousands of nodes.

Avoid loading unnecessary data.

Lazy loading is preferred where appropriate.

---

# Documentation

Whenever architecture changes:

Update documentation.

Whenever database changes:

Update DATABASE.md

Whenever keyboard shortcuts change:

Update KEYBINDINGS.md

---

# User Experience

Keyboard-first.

Mouse support is optional.

Navigation should require as few keystrokes as possible.

Fast search is mandatory.

Tree navigation should feel similar to a file manager.

---

# Project Scope

This project is intended to become a long-term developer productivity tool.

When making implementation decisions, always prefer solutions that improve extensibility and maintainability over short-term convenience.

---

# Important

If a requested implementation conflicts with this architecture,
do not silently change the architecture.

Instead:

- explain the conflict
- propose alternatives
- wait for approval

--- 

## Git Workflow

- Use Conventional Commits.
- Keep commits small and focused.
- One logical change per commit.
- One feature per pull request.
- Never mix documentation, refactoring and new features in the same commit.

Architecture decisions are intentional.

Do not redesign the project without explicit permission.
