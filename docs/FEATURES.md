# PathTree Features

Documents the supported core features of PathTree.

## Global Pinned Resources

Allows users to pin frequently used nodes from any workspace and access them quickly through both the TUI and the shell CLI.

### Concept

Pins are global shortcuts to existing nodes. They provide fast access without duplicating node paths, data, or resources. Deleting a node automatically invalidates or cascades to remove its associated pin. Remaining pins' position numbers are always kept compacted (1..N contiguous).

### Supported Actions

- **Pin Node**: Mark a node as pinned.
- **Unpin Node**: Remove a node's pin, shifting remaining pin positions deterministically.
- **Reorder Pins**: Shift pins up or down inside the pins list.
- **Activate Pin**: Locate and select the original node inside the TUI, or execute its default action inside the CLI.

---

# Pin vs. Bridge

- **Pin**: Fast access/shortcut to one existing node globally.
- **Bridge**: (Future concept) A connection between input and resource workflows.
