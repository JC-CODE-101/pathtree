# PathTree Action System

Version: 0.1 (Draft)

---

# Overview

Actions define behavior.

Nodes describe objects.

Actions describe what can be done with those objects.

A node may have zero or more actions.

Actions are independent of node types.

---

# Design Goals

The Action system should be:

- modular
- extensible
- reusable
- platform independent

Actions should be attachable to any node.

---

# Core Concept

Nodes never execute anything directly.

Instead:

Node

↓

Action

↓

Execution

This separation keeps the architecture flexible.

---

# Common Properties

Every action contains:

- UUID
- Node UUID
- Name
- Description
- Enabled
- Sort Order
- Created
- Modified

---

# Execution

An action may execute:

- Open directory
- Open file
- Open URL
- Run command
- Start application

Future versions may support additional execution types.

---

# Working Directory

An action may define a working directory.

If omitted, the current shell directory is used.

---

# Arguments

Actions may define command-line arguments.

Arguments are stored separately from the executable.

Example

Executable

python

Arguments

script.py

--debug

This improves portability and security.

---

# Environment Variables

Future versions may allow actions to define environment variables.

These are intentionally postponed.

---

# Multiple Actions

A node may have multiple actions.

Example

Blender

Actions

- Open Folder
- Start Blender
- Factory Startup
- Open Documentation

---

# Confirmation

Actions may require user confirmation before execution.

Examples

Delete backup

Remove node

Shutdown server

---

# Execution Rules

Actions never execute automatically.

The user must explicitly choose an action.

---

# Security

Executable and arguments should remain separated.

Avoid shell execution whenever possible.

Validation belongs inside the service layer.

---

# Future Action Types

Future versions may introduce:

- Docker actions
- Git actions
- SSH actions
- Plugin actions
- User-defined actions

The Action architecture should support these additions without redesign.

---

# Summary

Nodes describe resources.

Actions describe behavior.

Keeping both concepts separated results in a flexible and maintainable architecture.
