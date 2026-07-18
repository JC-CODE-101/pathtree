# PathTree Implementation Plan - Milestone 0.0.2 (Daily Navigation)

This document outlines the detailed implementation plan, technical specifications, and progressive pull request sequence for **Milestone 0.0.2 (Daily Navigation)** of PathTree.

The primary goal of Milestone 0.0.2 is to make PathTree indispensable for everyday developer directory navigation by introducing **Search**, **Favorites**, **Temporary Entries**, **Category/Workspace Nesting**, and **Interactive Node Management (CRUD)**, while strictly preserving core architectures and Bash/Zsh shell integrations from Milestone 0.0.1.

---

## 1. Architectural Guidelines & Strategy

To maintain scalability and enable smooth feature rollouts in subsequent versions, Milestone 0.0.2 implements a clean separation of concerns and documents future architectural placeholders.

### A. Conceptual Layers: Structural Nodes vs. Resource Types
Do not model every node as a plain directory. Instead, we introduce a clear architectural distinction between **structural kinds** and **resource types**.

1. **Structural Node Kinds**:
   - **workspace**: Conceptual organizational groupings (no execution metadata, acts as a container).
   - **folder**: Conceptual visual directory separator/container in the tree view.
   - **resource**: An executable or interactive element in the tree which possesses an associated resource type and target action.

2. **Resource Types**:
   - **directory** (*Implemented in Milestone 0.0.2*): Represents a filesystem folder.
   - **file** (*Placeholder only*): Represents a single local filesystem file.
   - **url** (*Placeholder only*): Represents an external web address link.
   - **application** (*Placeholder only*): Represents an executable system binary.
   - **script** (*Placeholder only*): Represents a local script file with an interpreter.
   - **shell_environment** (*Placeholder only*): Represents a shell configuration/sourcing environment.
   - **ssh** (*Placeholder only*): Represents a secure remote terminal bookmark.
   - *(Future: Command, Docker, Git, Variables...)*

> **Milestone 0.0.2 Scope Limit**: Only the **directory** resource type is implemented in Milestone 0.0.2. The other resource types are defined and documented as architecture placeholders only; no execution or runtime support is added for them in this release.

### B. Valid Combinations and Service Boundary Validation
To ensure data integrity, the `NodeService` enforces strict validation on node attributes.
Only the following specific combinations of `node_kind` and `resource_type` are valid in Milestone 0.0.2:
- `node_kind = "workspace"` and `resource_type = None`
- `node_kind = "folder"` and `resource_type = None`
- `node_kind = "resource"` and `resource_type = "directory"`

> **Rejection Rule**: Any other combination (e.g. `node_kind = "workspace"` with a resource_type, or `node_kind = "resource"` with a null resource_type) is **strictly rejected** at the `NodeService` boundary, raising a `ValidationError`.

---

## 2. Technical Specifications & Behavioral Rules

### A. Permanent vs. Temporary Entries
- **Permanent Entries (Bookmarks)**: Standard nodes persisted long-term in the database (`is_temporary = False`). They can be created, edited, moved, nested, and favorited.
- **Temporary Entries**: Lightweight session bookmarks created dynamically (`is_temporary = True`).
  - **Persistence**: Unlike transient session arrays, temporary entries **persist across multiple `pb` invocations**. They are not purged on every application startup or exit.
  - **Lifecycle**: Temporary nodes are deleted only through explicit delete/clear operations, or when "promoted" to permanent.
  - **Promotion**: A temporary node becomes permanent when `is_temporary` is toggled to `False` (via the editing dialog or an interactive shortcut).
  - **Demotion Restriction**: To preserve node integrity, **a permanent node is never allowed to become temporary** through a simple `t` toggle or shortcut; demotions are strictly blocked.
  - **Keybinding**: Pressing `t` on a node toggles/creates a temporary bookmark if the active node is temporary or directory, or prompts to mark/create a temporary resource.

### B. Category & Sibling Management
- Categories represent logical groupings of projects. Following `docs/ROADMAP.md` and `docs/NODE_TYPES.md`, categories are modeled as container nodes of kind `"workspace"` or `"folder"`.
- **Relocation and Nesting**: Users can create, edit, rename, and delete container nodes. Nodes can be nested to an arbitrary depth (supporting unlimited hierarchy). Move dialogs allow selecting a new parent node.
- **Validation Rules**:
  - **Circular Relocation Check**: `NodeService.validate_parent` rejects operations where a parent node is moved inside its own descendant.
  - **Self-Parenting**: A node can never be set as its own parent.
- **Sibling Uniqueness**:
  - **Uniqueness Boundary**: Uniqueness is enforced within the **same parent only**. Sibling nodes under different parent nodes are allowed to share identical names.
  - **Normalization**: Node names are normalized using a trim operation (stripping leading and trailing whitespace) followed by a case-insensitive comparison.
  - **Rejection of Empty Names**: Sibling uniqueness checks strictly reject names that resolve to an empty string after normalization.

### C. Search Behavior & Keyboard Interaction
- **UI State**: A `SearchInput` (Textual `Input` widget) is positioned at the top of the main layout, above the workspace tree.
- **Case-insensitive Substring Search**: Real-time filtering is executed using **case-insensitive substring matching only**. Fuzzy search is deferred to future releases.
- **Filtering Logic**: Only nodes matching the query AND their complete parent ancestor chains are rendered. This preserves tree structural context. Sibling nodes that do not match and are not ancestors of matches are hidden.
- **Type Filtering**:
  - In Milestone 0.0.2, search type filters are restricted to: `type:workspace`, `type:folder`, and `type:directory`.
  - Future executable filters (such as `type:file`, `type:url`, `type:application`, `type:script`, `type:ssh`) and activation shortcuts (`x`, `xa`, `xs`, `xe`, `xh`) remain documented design guidelines only and are not implemented.
- **Focus Switching & Keybindings**:
  - `/` or `s`: From the Tree View, focuses the Search Input.
  - `Escape`: From the Search Input, clears the query and returns focus to the Tree View.
  - `Down` or `Enter` (when search is focused): Moves focus down to the first matched node in the Tree View.

### D. Favorites
- Any node can be marked as a favorite (`is_favorite = True`).
- **Visual Indicator**: Favorites display a special visual indicator (e.g., a star `★` icon) next to their name in the tree.
- **Virtual Favorites View**: A virtual, expandable workspace folder named `★ Favorites` is pinned at the absolute top of the tree view.
  - **Referential Mapping**: The virtual `★ Favorites` workspace only references original node IDs. It **never duplicates** database nodes.
  - **Routing Actions**: All activation, edit, and delete actions performed inside the virtual Favorites view are routed directly to the original node.
  - **Exclusion Boundaries**: The virtual Favorites container is entirely excluded from persistence, cycle validation, and can never be selected as a parent during move operations.
- **Keybinding**: Pressing `f` on any node in the Tree View toggles its `is_favorite` attribute in the database and refreshes the UI.

### E. Creation Dialogs (Milestone 0.0.2)
- To maintain clean separation while building the foundation, the type selector for node creation exposes exactly three choices in Milestone 0.0.2:
  - **Workspace** (Structural kind)
  - **Folder** (Structural kind)
  - **Directory** (Resource type)
- Other resource types (such as File, URL, Application, Script, Shell Environment, SSH) are clearly labeled as non-implemented design examples and do not appear as functioning options in the selector.
- **Path Saving & Verification**:
  - When saving a path, if the directory is currently unavailable, the dialog displays a **non-blocking warning message** but allows the user to save the node path successfully.
  - At execution/activation time, the application continues to **strictly reject** unavailable paths to ensure terminal stability.

### F. Recursive Deletion
- When deleting a node that contains nested child descendants:
  - The deletion screen displays an explicit, non-destructive confirmation prompt.
  - The prompt clearly displays the **affected descendant count** (e.g., "This will delete this node and its 5 nested children. Proceed?").
  - The cascading recursive deletion is executed **transactionally** as a single atomic database unit.

### G. Shell Adapter Responsibilities
The separate Bash/Zsh shell adapters have minimized responsibilities. They are strictly restricted to operations that **must** happen inside the active shell context:
- Changing directories (`cd`)
- Sourcing environment configurations (`source`)
- Exporting environment variables (`export`)
- Establishing shell aliases

All other metadata validations, filesystem checks, and UI rendering are handled strictly inside the Python application.

---

## 3. Database Schema Migration (user_version 2)

### A. SQLite Schema Evolution
To support the conceptual structural/resource separation and favorites, the schema evolves from `user_version 1` to `user_version 2`.

#### Python Model Attribute Map
`src/pathtree/models/node.py` is updated to include the new fields. To maintain architectural flexibility, `resource_type` defaults to `None` in SQLModel:

```python
node_kind: str = Field(default="resource", index=True, nullable=False) # workspace | folder | resource
resource_type: str | None = Field(default=None, index=True, nullable=True) # directory | null (for other types in future)
is_favorite: bool = Field(default=False, index=True, nullable=False)
is_temporary: bool = Field(default=False, index=True, nullable=False)
```

> **Explicit Assignment**: When creating or saving a `"resource"` kind node, the `NodeService` explicitly assigns the value `"directory"` to `resource_type`.

### B. Legacy `node_type` Transition Strategy
The old `node_type` column is completely phased out of the domain:
- **Sole Source of Truth**: After the migration is applied, `node_kind` and `resource_type` represent the **sole domain source of truth** for all application logic.
- **Code Constraint**: New application code and CRUD methods must **not read or write** the legacy `node_type` column.
- **Backward Compatibility**: The physical column `node_type` remains physically present in the SQLite schema database for safety during Milestone 0.0.2 but is marked as explicitly deprecated.
- **Future Rebuild**: A future schema cleanup migration (such as Milestone 0.1.0) may perform a table rebuild (`ALTER TABLE ... DROP COLUMN` or temporary copy rebuild) to remove the deprecated column entirely.

### C. Detailed Migration Specification
1. **Fresh Database Creation**:
   - If the database file is newly created, tables are initialized directly with the current user_version 2 schema, and `PRAGMA user_version = 2;` is run. No legacy migrations are applied.
2. **Version 1 Migration**:
   - If an existing database has `user_version == 1`, migration updates are executed inside a **single transaction**:
     - Columns `node_kind` (NOT NULL DEFAULT 'resource'), `resource_type` (DEFAULT NULL), `is_favorite` (NOT NULL DEFAULT 0), and `is_temporary` (NOT NULL DEFAULT 0) are added.
     - Indexes are created idempotently (`CREATE INDEX IF NOT EXISTS`).
     - Data migration rules:
       - If `node_type == "Workspace"` ──► Set `node_kind = "workspace"`, `resource_type = NULL`.
       - If `node_type == "Folder"` AND `path` is NULL/empty ──► Set `node_kind = "folder"`, `resource_type = NULL`.
       - If `node_type == "Folder"` AND `path` is not empty ──► Set `node_kind = "resource"`, `resource_type = "directory"`.
3. **Repeated Startup**:
   - Booting the application when `user_version == 2` results in a clean, immediate no-op.
4. **Rejection of Newer Versions**:
   - If the database reports `user_version > 2`, the application must immediately halt and refuse execution to prevent newer schema corruption.
5. **Transactional Rollback**:
   - Every migration step is bound within a database transaction. Any migration failure triggers an immediate rollback, leaving the user's database intact.
6. **Execution Ordering**:
   - The DDL altering steps, index creation, and data transformations must complete successfully *before* writing `PRAGMA user_version = 2;`.

---

## 4. UI Layout Hierarchy (Milestone 0.0.2)

```
+--------------------------------------------------------------+
| Search: [ Type here to filter...                           ] |
+--------------------------------------------------------------+
|                                                              |
|  NodeTreeView (65% width)        | NodeDetailsPanel (35%)    |
|  - ★ Favorites                   |                           |
|    - ★ Src Folder                | - Name: Src Folder        |
|  - Root Workspace                | - Kind: resource          |
|    - ★ Src Folder [path: /src]   | - Resource Type: directory|
|    - Tests Folder [path: /tests] | - Path: /src              |
|                                  | - Favorite: Yes [★]       |
|                                  | - Temporary: No           |
+--------------------------------------------------------------+
| Footer (Keybindings Status Bar)                              |
| a: Add  e: Edit  d: Del  m: Move  f: Favorite  t: Temp  q: Quit|
+--------------------------------------------------------------+
```

---

## 5. Incremental Pull Request Sequence

Milestone 0.0.2 is structured into five sequential, highly focused, and reviewable pull requests.

---

### PR 1: Schema Migration & Persistent Model Evolution

- **Dependency Order**: First PR (No dependencies).
- **Scope**: Database schema evolution to `user_version 2`.
- **Deliverables**:
  - Update `Node` model with `node_kind`, `resource_type`, `is_favorite`, and `is_temporary`.
  - Implement full schema migration logic in `database/connection.py` covering legacy transition strategies, valid combination constraints, and transactional safety.
- **Verification & Tests**:
  - Write migration tests verifying version 1 upgrade logic, data conversion rules, and rollback states.
- **Definition of Done**:
  - SQLite schema migrations are completely transactional, idempotent, and pass 100% of test cases.

---

### PR 2: Service Layer CRUD Logic & Sibling Constraints

- **Dependency Order**: Depends on PR 1.
- **Scope**: Business logic layer of node management, sibling validations, search filters, and recursive transaction deletions.
- **Deliverables**:
  - Add `create_node()`, `update_node()`, `delete_node()`, and `move_node()` to `NodeService`.
  - Implement sibling uniqueness check (normalization using trim and case-insensitive check; reject empty strings).
  - Implement recursive cascaded node deletion inside a secure database transaction.
  - Implement search filter logic (case-insensitive substring only).
- **Verification & Tests**:
  - Unit tests asserting sibling clash rejections under the same parent.
  - Test suite checking recursive transaction deletions and verifying descendant counts.
- **Definition of Done**:
  - Validations, transactions, and filters are structurally covered. Service layers remain cleanly decoupled from UI state.

---

### PR 3: Search Input Widget & Real-time Substring Filter

- **Dependency Order**: Depends on PR 2.
- **Scope**: UI Search Input addition and real-time substring tree filtering.
- **Deliverables**:
  - Create `SearchInput` widget in `ui/widgets/search.py`.
  - Bind search query edits to live substring-only matches on the tree.
  - Implement focus-switching shortcuts (`/`, `s`, `Escape`, `Down`, `Enter`).
  - Wire type filters: `type:workspace`, `type:folder`, and `type:directory`.
- **Verification & Tests**:
  - Async UI tests verifying search focus, substring pruning, and ancestor visibility preservation.
- **Definition of Done**:
  - Real-time search runs smoothly without rendering delays. Keyboard transitions work reliably.

---

### PR 4: Interactive Creation, Editing, & Relocation UI Dialogs

- **Dependency Order**: Depends on PR 3.
- **Scope**: Form dialogues, warning validation screens, relocation selectors, and deletion confirmations.
- **Deliverables**:
  - **Add Node**: Multi-stage dialogue (Workspace, Folder, Directory only; disallow unimplemented types).
  - **Edit Node**:
    - Accessible via shortcut `e`.
    - Fully supports editing Name, Description, and Directory Path where applicable.
    - Fully supports toggling Favorite state and Promoting a temporary node to permanent (updating `is_temporary` to `False`).
    - **Strict Limitation**: Prohibit any arbitrary conversion between structural kinds (`workspace`/`folder`) and resource types.
  - **Move Node**:
    - Accessible via shortcut `m`.
    - Allows choosing the Root (`None`), a Workspace, or a Folder as the new parent.
    - **Parent Restraints**: Explicitly exclude Resource nodes and the virtual Favorites container as parent choices.
    - Cycle validation check and sibling uniqueness validation check are strictly run.
    - Immediate tree refresh executes upon successful movement.
  - **Delete Node**: Confirms cascading deletions showing the affected descendant counts.
- **Verification & Tests**:
  - Write detailed UI tests using Textual `App.run_test()` to verify:
    - Successful Editing and Relocating interactions.
    - Verification of keyboard shortcuts `e` and `m` triggering respective modals.
    - Cancellation handling for all dialogs (ensuring no database mutations on escape/cancel).
    - Validation error rendering (circular parent check and sibling name clashes).
- **Definition of Done**:
  - Modals are fully keyboard-navigable. Interactive operations update the tree immediately.

---

### PR 5: Referential Virtual Favorites & Temporary Persistent Entries

- **Dependency Order**: Depends on PR 4.
- **Scope**: Pinned virtual folder routing and persistent temporary bookmarks.
- **Deliverables**:
  - Implement virtual `★ Favorites` tree element (mapping original node IDs, bypassed from validation and persistence).
  - Bind `f` shortcut to toggle favorites in the DB.
  - Bind `t` shortcut to handle temporary bookmark creation/toggling (strictly blocking permanent demotions).
- **Verification & Tests**:
  - Test suites verifying referential favorites routing, virtual move parent exclusion, and temporary node persistence across runs.
- **Definition of Done**:
  - 100% of Milestone 0.0.2 tests pass with zero regression in standard `pb` shell directory navigation mechanics.
