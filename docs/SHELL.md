# PathTree Shell Integration

Version: 0.1 (Draft)

---

# Overview

PathTree integrates with the user's shell through a lightweight shell adapter.

The shell adapter is responsible only for communication between the shell and the Python application.

Business logic always remains inside the Python application.

---

# Design Goals

The shell integration should be:

- lightweight
- shell independent
- easy to maintain
- easy to extend

The adapter should contain as little logic as possible.

---

# Responsibilities

The shell adapter is responsible for:

- launching PathTree
- receiving the selected result
- changing the current directory
- returning control to the shell

Nothing else.

---

# Python Responsibilities

The Python application is responsible for:

- loading the database
- displaying the user interface
- tree navigation
- searching
- selecting nodes
- selecting actions
- validating user input

Python never changes the shell directory directly.

---

# Shell Responsibilities

The shell is responsible for:

- executing cd
- executing shell-specific commands
- maintaining the current shell session

---

# Communication Flow

```
User

↓

pb

↓

Shell Adapter

↓

Python Application

↓

Selected Path

↓

Shell Adapter

↓

cd

↓

User continues working
```

---

# Directory Changes

The Python application never executes:

```bash
cd
```

Instead, it returns the selected directory to the shell adapter.

The adapter performs the directory change.

---

# Supported Shells

The architecture is designed to support:

- Bash
- Zsh

Future support may include:

- Fish
- PowerShell

Support for additional shells should only require writing a new adapter.

The Python application should remain unchanged.

---

# Adapter Design

Shell adapters should remain extremely small.

Typical responsibilities include:

- launching PathTree
- reading the selected path
- changing directories

Business rules must never be duplicated inside adapters.

---

# Error Handling

If PathTree exits without selecting a path:

- the current directory remains unchanged

If the selected path does not exist:

- display an error
- remain in the current directory

The shell adapter should never terminate the user's shell session.

---

# Future Extensions

Future shell integration may support:

- aliases
- shell completion
- shell history integration
- startup hooks

These features are intentionally postponed.

---

# Design Rules

The Python application must remain independent from any shell.

Every shell-specific implementation belongs inside an adapter.

No business logic should exist inside shell scripts.

---

# Summary

The shell adapter acts only as a bridge between the shell and the Python application.

Keeping the adapter minimal makes PathTree portable, maintainable, and easy to extend to additional shells.
