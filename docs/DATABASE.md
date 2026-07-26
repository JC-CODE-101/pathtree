# PathTree Database Design

Version: 0.1 (Draft)

---

# Overview

PathTree stores all persistent application data in a local SQLite database.

The database is designed to be:

- lightweight
- portable
- maintainable
- extensible

The schema should support future expansion without requiring major redesign.

SQLite was chosen because it is reliable, fast, requires no server, and is available on all supported platforms.

---

# Design Goals

The database should:

- remain simple
- avoid duplicated data
- support unlimited tree depth
- allow future node types
- allow future plugins
- remain migration friendly

Business logic must never be stored inside the database.

The database stores data only.

---

# Core Entities

The first version of PathTree is built around five core entities.

## Node

Represents one object inside the tree.

Examples:

- Workspace
- Folder
- File
- Documentation
- Website
- Note

Every node belongs to exactly one parent except the root node.

---

## Pin

Represents a global shortcut pin/reference to an existing node.

Fields:
- `id`: Unique identifier (UUID).
- `node_id`: References the target node (`nodes.id`).
- `position`: Numeric ordering / stable index of the pin (1-based, contiguous).
- `custom_label`: Optional label to override the original node's display name.
- `created_at`: Creation timestamp.
- `updated_at`: Modification timestamp.

Deleting a node cascade-deletes its associated pin.

---

## Action

Represents an executable action attached to a node.

Examples:

- Open folder
- Start application
- Execute command

A node may contain zero or more actions.

---

## Settings

Stores application configuration.

Examples:

- Theme
- Preferred shell
- Startup options
- UI preferences

---

## Session

Stores temporary runtime information.

Examples:

- Expanded tree nodes
- Recently opened items
- Last selected node

Session data is optional and may be cleared without affecting user data.

---

# Relationships

The first version contains the following relationships.

Node

↓

Node

(parent-child)

Node

↓

Action

(one-to-many)

Application

↓

Settings

(one)

Application

↓

Session

(one)

---

# Identifiers

Every persistent object should use a UUID.

Reasons:

- globally unique
- import friendly
- export friendly
- future proof

Sequential integer IDs should be avoided.

---

# Persistence Rules

Only persistent user data belongs in the database.

Examples:

- Nodes
- Actions
- Settings

Transient runtime state should only be stored when necessary.

---

# Migrations

Database schema changes should always use migrations.

Existing user data must never be silently destroyed.

Migration scripts should remain small and reversible whenever possible.

---

# Future Expansion

The database should allow future support for:

- Tags
- Favorites
- Variables
- Plugins
- Resource metadata

These features should be added without redesigning the existing schema.

---

# Design Rules

The database should never contain business logic.

The database should never execute commands.

Validation belongs inside the service layer.

The database stores information only.

---

# Summary

The first version of the database is intentionally small.

The focus is stability rather than feature completeness.

Additional entities should only be introduced when a real use case exists.
