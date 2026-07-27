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

---

## Launch Profiles

Allows users to create multiple reusable execution profiles for an existing Script or Executable node.

### Concept

- **Resource**: Describes what the target script or executable is and where it is located.
- **Launch Profile**: Describes one concrete way to execute that target, storing custom safe arguments (as explicit argv) and execution settings.
- **Multi-Launcher**: (Future concept) Will combine multiple Launch Profiles and resources together.

### Features

- **Lazily Managed Sections**: Automatically creates system group sections under the originating Workspace:
  - **Launch Profiles** (`system_role: launch_profiles`) for active profiles.
  - **Detached Profiles** (`system_role: detached_launch_profiles`) for detached profiles.
- **Target Deletion and Detaching**: If the target Script or Executable is deleted, its profiles are preserved as "detached" nodes under the "Detached Profiles" system group with their previous name/path saved. Detached profiles block execution until reconnected.
- **Optional Working Directory**: Profiles can refer to an existing Directory resource node. If the Directory path changes, the profile uses the new path automatically. If the Directory node is deleted, the profile remains active and falls back to target parent directory default behavior.
- **Terminal Modes**: Supports running in `inherit` mode (standard background launch) or `new_terminal` mode (running inside a platform-safe, visible terminal window).
- **Argparse CLI Support**: List profiles with `pb --profiles` and run active ones with `pb --profile <number>`.
