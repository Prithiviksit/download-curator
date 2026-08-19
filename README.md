# download-curator 📥

A safe, local macOS application for organizing and renaming downloaded files in `~/Downloads` following a strict **Propose → Review → Approve** architecture.

---

## 🛡️ Core Safety Invariant

**NEVER rename, move, delete, overwrite, or otherwise modify any downloaded file without an explicit approval action from the user.**

* **No Auto-Moves**: Background scanning and notifications ONLY create proposals in a local SQLite database. The original files remain 100% untouched until you approve.
* **No Overwrites**: Detects filename collisions and automatically increments filenames (`file (1).pdf`, `file (2).pdf`).
* **Path Traversal Guards**: Strictly enforces operations within configured boundaries. Rejects symlinks pointing outside.
* **Safe Atomic Operations**: Uses atomic moves on the same filesystem and verified copy-then-unlink across volumes. Preserves original creation/modification timestamps.
* **Immutable Audit Trail**: Logs every discovery, proposal, approval, move, and undo in SQLite.
* **Collision-Safe Undo**: Any operation can be reverted safely without overwriting newer files.

---

## 🏗️ Architecture

```
                                      ┌────────────────────────┐
                                      │       ~/Downloads      │
                                      └───────────┬────────────┘
                                                  │
                                          [FSEvents Watcher]
                                         (Filters temp files)
                                                  │
                                                  ▼
                                      ┌────────────────────────┐
                                      │   Content Extractors   │
                                      │ (PDF, Office, Images,  │
                                      │  Code, Archives, etc.) │
                                      └───────────┬────────────┘
                                                  │
                                                  ▼
                                      ┌────────────────────────┐
                                      │  AI / Rule Classifier  │
                                      │ (Heuristics or Gemini/ │
                                      │  OpenAI/Claude/Ollama) │
                                      └───────────┬────────────┘
                                                  │
                                                  ▼
                                      ┌────────────────────────┐
                                      │  SQLite State Database │
                                      │  (Status: Pending)     │
                                      └───────────┬────────────┘
                                                  │
                         ┌────────────────────────┴────────────────────────┐
                         │                                                 │
                         ▼                                                 ▼
             ┌───────────────────────┐                         ┌───────────────────────┐
             │ Terminal Review (TUI) │                         │ macOS Menu Bar App    │
             │ download-curator      │                         │ Native Swift / Popover│
             │ review                │                         │ Queue & Shortcuts     │
             └───────────┬───────────┘                         └───────────┬───────────┘
                         │                                                 │
                         └────────────────────────┬────────────────────────┘
                                                  │
                                       [EXPLICIT APPROVAL]
                                                  │
                                                  ▼
                                      ┌────────────────────────┐
                                      │ Safe Atomic Mover      │
                                      │ (~/Downloads/Category/)│
                                      └────────────────────────┘
```

---

## 🚀 Quick Start

### 1. Installation

```bash
# Clone and setup environment using uv
git clone https://github.com/user/download-curator.git
cd download-curator
uv sync

# Build Native Menu Bar App (Optional)
./macos-menubar/build.sh
```

### 2. CLI Commands

| Command | Description |
| :--- | :--- |
| `download-curator scan` | Scan `~/Downloads` read-only and create proposals |
| `download-curator scan --dry-run` | Preview proposals in terminal without saving to DB |
| `download-curator pending` | List all pending proposals awaiting review |
| `download-curator pending --json` | Output pending queue as structured JSON |
| `download-curator review` | Interactive Rich terminal review interface |
| `download-curator review --all` | Fast approval for entire pending queue |
| `download-curator approve <id>` | Explicitly approve a specific proposal by ID |
| `download-curator reject <id>` | Reject a proposal (file stays untouched) |
| `download-curator ignore <id>` | Permanently ignore a file |
| `download-curator history` | View immutable audit log |
| `download-curator undo` | Safely reverse the last executed move |
| `download-curator serve` | Run background watcher & local API daemon |
| `download-curator launchd status` | Check background LaunchAgent daemon status |

---

## 🖥️ Interactive Terminal Review

Run `download-curator review`:

```
╭────────────────────────────── Proposal 1 of 3 ──────────────────────────────╮
│                Current:  ~/Downloads/2408.12345.pdf                         │
│      Proposed Filename:  Acemoglu_Smith_2026_Credit_Markets_And_Dynamics.pdf│
│   Proposed Destination:  Academic Papers/                                   │
│               Category:  Academic Papers                                    │
│             Confidence:  0.94                                               │
│                 Reason:  Identified arXiv paper with authors and title      │
╰─────────────────────────────────────────────────────────────────────────────╯

Available Actions:
  [a] Approve         [A] Approve All     [e] Edit
  [r] Reject          [s] Skip            [i] Ignore File
  [p] Preview/Open    [q] Quit

Action [a]:
```

---

## 🍏 Native macOS Menu Bar UI

The native Swift menu bar application (`DownloadCurator.app`) lives in your status bar:

* Displays pending proposal badge count `📥 3`
* Shows visual card queue with filename, proposed name, category, confidence, and reasoning
* **Quick Actions**:
  * `[Open File]` (Space)
  * `[Reveal in Finder]`
  * `[Approve]` (Return)
  * `[Edit]` (E)
  * `[Ignore]` (I)
  * `[Skip]`
* **Consolidated Notifications**: Sends non-blocking macOS notifications when new downloads finish processing.

---

## ⚙️ Configuration (`config.yaml`)

Configuration is stored in `~/.download-curator/config.yaml`.

```yaml
watch_directory: ~/Downloads
destination_root: ~/Downloads

categories:
  Academic Papers: "Academic Papers"
  Books: "Books"
  Slides: "Presentations"
  Invoices & Receipts: "Financial/Invoices"
  Financial Statements: "Financial/Statements"
  Datasets: "Datasets"
  Installers: "Installers"
  Images: "Images"
  Archives: "Archives"
  Code & Scripts: "Code"
  Documents: "Documents"
  Spreadsheets: "Spreadsheets"
  Audio & Video: "Media"
  Unclassified: "Unclassified"

naming_rules:
  academic_papers: "{authors}_{year}_{short_title}.{ext}"
  books: "{authors}_{year}_{title}.{ext}"
  slides: "{topic_or_title}.{ext}"
  invoices: "{merchant}_{date}_{description}.{ext}"
  statements: "{institution}_{date}_Statement.{ext}"
  installers: "{app_name}_{version}_{arch}.{ext}"
  datasets: "{dataset_name}_{version}_{date}.{ext}"

ai:
  provider: rule_based   # rule_based (offline), gemini, openai, anthropic, ollama
  api_key: null
  model: null

safety:
  allowed_source_directories:
    - ~/Downloads
  allowed_destination_roots:
    - ~/Downloads
    - ~/Documents
  collision_strategy: rename_increment  # rename_increment or abort
  preserve_metadata: true
  atomic_moves: true
```

---

## 🧪 Testing

Run test suite:

```bash
uv run pytest -v
```
