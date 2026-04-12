# Layout Editor Reconstruction Plan for Skill System

## 1. Overview & Goals

Reconstruct the visualization confirmation function (currently a separate React frontend + Python backend) into a self-contained system that:

1. **Preserves identical UI/UX** - same LayoutEditor controls and functions
2. **Runs within the skill system** - no dependency on external `anthropic-gui` project
3. **Claude Code can invoke it** - proper CLI integration

## 2. Current Architecture Analysis

### 2.1 Backend (Python, already in skill system)

| File | Role |
|------|------|
| `editor_confirm_merge.py` | Pure merge/normalize helpers (component templates, runtime field stripping, instance merging, confirmed payload building) |
| `confirmed_config_builder.py` | Orchestrates the pipeline: prepares T28 components, inserts fillers, exports intermediate JSON, **polls for confirmed JSON** (GUI wait loop) or auto-generates (CLI skip mode) |
| `editor_utils.py` | Exports layout to editor-compatible JSON format with position parsing and side bucketing |

### 2.2 Frontend (React/TypeScript, in `history_code/anthropic-gui/`)

| File | Role |
|------|------|
| `index.tsx` | Main LayoutEditor entry, loads pending editor file from localStorage, keyboard shortcuts |
| `store/useIORingStore.ts` | Zustand state store: CRUD, history (undo/redo), selection, copy/paste, move/reorder, pin config, auto chip size |
| `components/RingCanvas.tsx` | SVG canvas: dynamic layout calc, drag-drop reorder, box selection, pan/zoom, device color coding, legend |
| `components/InspectorPanel.tsx` | Property inspector: instance/ring config editing, auto-save, multi-select batch pin editing |
| `components/PropertyEditor.tsx` | Field-level editor: device selector, pin connection rows, domain/direction selectors, chip size composite |
| `components/Toolbar.tsx` | Toolbar: import/export JSON, undo/redo, add device, delete, confirm & submit |
| `utils/ioAdapter.ts` | Import/export adapter: external JSON <-> internal GUI format conversion |
| `utils/pinConfigTemplates.ts` | Pin config templates for T28/T180, device classification |
| `types/index.ts` | TypeScript type definitions |

### 2.3 Communication Protocol (Current)

```
Backend (Python)                              Frontend (React app)
     |                                              |
     |-- exports _intermediate_editor.json --------->|  (via localStorage URL)
     |                                              |
     |          [User edits in browser UI]           |
     |                                              |
     |<-- writes _confirmed.json -------------------|  (via submitEditorConfirm API)
     |
     |-- polls for confirmed.json mtime change -----|
     |-- loads confirmed.json, continues pipeline   |
```

## 3. Proposed Architecture

### 3.1 Strategy: Standalone HTML + Python Launcher

Replace the React+API-server approach with a **single self-contained HTML file** served by a lightweight Python HTTP launcher:

```
Claude Code (Skill)
     |
     |-- 1. Export intermediate JSON
     |-- 2. Run: python3 layout_editor_launcher.py <intermediate_path> <confirmed_path>
     |       |
     |       |-- starts local HTTP server (port auto-assigned)
     |       |-- opens browser with HTML editor
     |       |-- watches for confirmed.json file write
     |       |-- returns exit 0 when confirmed
     |
     |-- 3. Load confirmed JSON and continue pipeline
```

### 3.2 File Structure (within skill assets)

```
.claude/skills/io-ring-orchestrator-T28/
├── assets/
│   ├── core/layout/             # (existing backend - unchanged)
│   │   ├── editor_confirm_merge.py
│   │   ├── confirmed_config_builder.py
│   │   ├── editor_utils.py
│   │   └── ...
│   └── layout_editor/           # NEW: self-contained editor
│       ├── layout_editor.html   # Single self-contained HTML file (all JS/CSS inlined)
│       └── layout_editor_launcher.py  # Python launcher script
└── SKILL.md                     # Updated workflow (Step 6 now uses GUI editor)
```

## 4. Detailed Implementation Plan

### Phase 1: Build Standalone HTML Editor

**File: `assets/layout_editor/layout_editor.html`**

A single HTML file containing:

#### 4.1.1 HTML Shell
- Minimal HTML5 boilerplate
- Inline `<style>` block (Tailwind-like utility classes replicated or CDN fallback)
- Single `<div id="root">` mount point

#### 4.1.2 Inlined JavaScript Libraries
- **React 18** (from CDN or inline minimal bundle ~45KB)
- **ReactDOM 18** (from CDN or inline ~45KB)
- **Zustand** (inline minimal ~3KB - only `create` function needed)
- **clsx** (inline ~1KB)

> Note: Use CDN `<script>` tags with fallback error handling. The launcher's local HTTP server can also serve these if offline operation is needed.

#### 4.1.3 Application Code (inlined `<script>`)

All the following modules must be transpiled/inlined into a single `<script type="module">` or UMD bundle:

1. **`types.ts` -> JS** - Type definitions converted to JSDoc comments
2. **`pinConfigTemplates.ts` -> JS** - Pin config logic, device classification (pure functions, no dependencies)
3. **`ioAdapter.ts` -> JS** - Import/export adapters (pure functions)
4. **`useIORingStore.ts` -> JS** - Zustand store with all actions
5. **`PropertyEditor.tsx` -> JS** - React component
6. **`InspectorPanel.tsx` -> JS** - React component
7. **`RingCanvas.tsx` -> JS** - React component (SVG canvas)
8. **`Toolbar.tsx` -> JS** - Modified toolbar (see 4.1.4)
9. **`index.tsx` -> JS** - Modified entry point (see 4.1.5)

#### 4.1.4 Modified Toolbar
The Toolbar's `handleConfirmAndContinue` must change from calling `submitEditorConfirm()` API to a **file-based write protocol**:

```typescript
const handleConfirmAndContinue = async () => {
  const externalGraph = exportAdapter(graph);
  const payload = {
    ...externalGraph,
    ring_config: {
      ...externalGraph.ring_config,
      process_node: graph.ring_config.process_node || processNode,
    },
  };

  // NEW: POST to the local launcher's /confirm endpoint
  const response = await fetch('/confirm', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(payload),
  });

  if (response.ok) {
    // Show success and close tab or show "done" state
    document.title = '[CONFIRMED] Layout Editor';
    setIsConfirming(false);
    alert('Confirmation saved. You can close this tab.');
  } else {
    alert('Failed to save confirmation.');
  }
};
```

#### 4.1.5 Modified Entry Point

Replace `localStorage`-based file loading with a **fetch from local server**:

```typescript
useEffect(() => {
  const loadData = async () => {
    try {
      const res = await fetch('/data');
      if (!res.ok) throw new Error(`HTTP ${res.status}`);
      const json = await res.json();
      const internalGraph = importAdapter(json);
      setGraph(internalGraph);
      setEditorSourcePath(json._source_path || null);
      setEditorProcessNode(
        json.ring_config?.process_node?.toUpperCase() || null
      );
    } catch (err) {
      console.error('Failed to load editor data:', err);
    }
  };
  loadData();
}, []);
```

- Remove: `IO_EDITOR_PENDING_KEY`, localStorage, `StorageEvent` listener
- Remove: `ArrowLeft` / `handleBackToChat` (no routing back to chat)
- Remove: `react-router-dom` dependency

#### 4.1.6 CSS/Styling Strategy

Option A (Recommended): Inline all Tailwind utility classes used by the components into a `<style>` block. The editor uses a bounded set of Tailwind classes (~80 unique). Extract these from the components and inline them.

Option B: Include Tailwind CDN `<script src="https://cdn.tailwindcss.com">`. Simpler but requires internet.

### Phase 2: Build Python Launcher Script

**File: `assets/layout_editor/layout_editor_launcher.py`**

```python
#!/usr/bin/env python3
"""Launch the self-contained Layout Editor in a browser and wait for confirmation."""

import argparse
import json
import socket
import subprocess
import sys
import threading
import time
import webbrowser
from http.server import HTTPServer, BaseHTTPRequestHandler
from pathlib import Path

# ... implementation details below ...
```

#### Key Responsibilities:

1. **Parse CLI arguments**:
   - `intermediate_json_path` - path to the `_intermediate_editor.json`
   - `confirmed_json_path` - path where `_confirmed.json` should be written
   - `--port` - optional port override
   - `--no-open` - skip browser auto-open

2. **Start HTTP server** with 3 endpoints:
   - `GET /` - serve `layout_editor.html`
   - `GET /data` - serve the intermediate JSON file
   - `POST /confirm` - receive the confirmed payload, write to disk, signal completion

3. **Open browser** to `http://localhost:<port>/`

4. **Wait for confirmation**:
   - Use a `threading.Event` signaled by the `/confirm` handler
   - Print status messages to stdout (for Claude Code to see)
   - Shutdown server after confirmation

5. **Exit cleanly** with exit code 0 on success, 1 on failure

#### HTTP Handler Pseudocode:

```python
class EditorHandler(BaseHTTPRequestHandler):
    confirmation_event: threading.Event
    confirmed_path: str
    intermediate_path: str
    html_path: str

    def do_GET(self):
        if self.path == '/':
            # Serve layout_editor.html
            self.serve_file(self.html_path, 'text/html')
        elif self.path == '/data':
            # Serve intermediate JSON
            self.serve_file(self.intermediate_path, 'application/json')
        else:
            self.send_error(404)

    def do_POST(self):
        if self.path == '/confirm':
            content_length = int(self.headers['Content-Length'])
            body = self.rfile.read(content_length)
            data = json.loads(body)

            with open(self.confirmed_path, 'w') as f:
                json.dump(data, f, indent=2, ensure_ascii=False)

            self.send_response(200)
            self.end_headers()
            self.wfile.write(b'{"status":"ok"}')

            print(f"Confirmation saved to {self.confirmed_path}")
            self.confirmation_event.set()
        else:
            self.send_error(404)
```

### Phase 3: Modify Backend Pipeline

#### 4.3.1 Update `confirmed_config_builder.py`

Modify `run_t28_editor_confirmation_pipeline()` to use the new launcher:

```python
# In GUI mode, replace the polling loop with:
if not skip_editor_confirmation:
    try:
        from .launcher import launch_layout_editor  # new module
        confirmed_path_str = launch_layout_editor(
            intermediate_json=str(editor_path),
            confirmed_json=str(confirmed_path),
        )
        # Load the confirmed result
        with open(confirmed_path_str, 'r') as f:
            idx_data = json.load(f)
        # ... rest of the processing remains the same
    except Exception as e:
        print(f"Editor failed: {e}")
        raise
```

#### 4.3.2 Add `launcher.py` Wrapper (in `assets/core/layout/`)

```python
def launch_layout_editor(intermediate_json: str, confirmed_json: str) -> str:
    """Launch the standalone layout editor and block until confirmed."""
    import subprocess, sys
    launcher_script = Path(__file__).parent.parent / "layout_editor" / "layout_editor_launcher.py"

    result = subprocess.run(
        [sys.executable, str(launcher_script), intermediate_json, confirmed_json],
        capture_output=False,  # Let output flow to terminal
        text=True,
    )

    if result.returncode != 0:
        raise RuntimeError(f"Layout editor exited with code {result.returncode}")

    return confirmed_json
```

### Phase 4: Update Skill Workflow (SKILL.md)

Modify **Step 6: Build Confirmed Config** to offer GUI editor mode:

```markdown
### Step 6: Build Confirmed Config

#### Option A: With GUI Editor Confirmation (recommended)

\```bash
python3 $SCRIPTS_PATH/build_confirmed_config.py \
  {output_dir}/io_ring_intent_graph.json \
  {output_dir}/io_ring_confirmed.json \
  T28
\```

This will:
1. Insert fillers and generate intermediate JSON
2. **Open a browser-based Layout Editor** for visual review and editing
3. Wait for user to confirm (click "Confirm & Continue" button)
4. Merge editor changes back into the confirmed config

#### Option B: Skip Editor (CLI-only mode)

\```bash
python3 $SCRIPTS_PATH/build_confirmed_config.py \
  {output_dir}/io_ring_intent_graph.json \
  {output_dir}/io_ring_confirmed.json \
  T28 \
  --skip-editor
\```
```

## 5. Feature Parity Checklist

Ensure the reconstructed editor supports all existing features:

| Feature | Status |
|---------|--------|
| SVG ring visualization with dynamic layout | Preserved |
| Drag-and-drop reorder within same side | Preserved |
| Drag-and-drop move across sides | Preserved |
| Multi-select with box selection | Preserved |
| Ctrl+click additive selection | Preserved |
| Pan (middle mouse) / Zoom (scroll wheel) | Preserved |
| Color coding by device type (T28 + T180) | Preserved |
| Color legend overlay | Preserved |
| Undo/Redo (Ctrl+Z / Ctrl+Y) | Preserved |
| Add device (Pad, Filler, Corner, CUT, Blank) | Preserved |
| Delete selected (Delete key / button) | Preserved |
| Copy (Ctrl+C) / Paste (Ctrl+V) | Preserved |
| Property inspector (left panel) | Preserved |
| Pin connection editor with auto-fill | Preserved |
| Device selector with dropdown suggestions | Preserved |
| Domain selector (analog/digital) | Preserved |
| Direction selector (input/output) | Preserved |
| Chip size composite field | Preserved |
| Side counts display | Preserved |
| Import/Export JSON | Preserved |
| Confirm & Continue (save confirmed JSON) | Adapted to local server |
| T28 vs T180 process node awareness | Preserved |

## 6. Dependencies & Requirements

### 6.1 Python Dependencies (Launcher)
- Python 3.7+ (stdlib only - uses `http.server`, `json`, `threading`, `webbrowser`)
- No external pip packages needed

### 6.2 Browser Requirements
- Modern browser (Chrome 90+, Firefox 90+, Edge 90+)
- JavaScript enabled
- Network: localhost access only

### 6.3 Optional CDN Dependencies (for HTML)
- React 18 (CDN: `unpkg.com/react@18`)
- ReactDOM 18 (CDN: `unpkg.com/react-dom@18`)
- If offline, these need to be bundled inline (~90KB total)

## 7. Implementation Order

| Step | Task | Effort |
|------|------|--------|
| 1 | Create `assets/layout_editor/` directory | 5 min |
| 2 | Transpile `pinConfigTemplates.ts` -> plain JS | 30 min |
| 3 | Transpile `ioAdapter.ts` -> plain JS | 20 min |
| 4 | Transpile `useIORingStore.ts` -> plain JS (Zustand inlined) | 45 min |
| 5 | Transpile `types/index.ts` -> JSDoc | 10 min |
| 6 | Convert `RingCanvas.tsx` to plain JS React.createElement | 60 min |
| 7 | Convert `PropertyEditor.tsx` to plain JS | 40 min |
| 8 | Convert `InspectorPanel.tsx` to plain JS | 20 min |
| 9 | Convert `Toolbar.tsx` to plain JS (modified confirm logic) | 30 min |
| 10 | Build `layout_editor.html` combining all above | 30 min |
| 11 | Build `layout_editor_launcher.py` | 30 min |
| 12 | Test end-to-end: export -> editor -> confirm -> load | 30 min |
| 13 | Update `confirmed_config_builder.py` integration | 20 min |
| 14 | Update `SKILL.md` workflow | 15 min |
| 15 | Apply same pattern for T180 skill | 30 min |

## 8. Alternative Approaches Considered

### 8.1 Pre-built React Bundle
- Run `npm run build` in the existing frontend project
- Copy the built `dist/` folder into skill assets
- Serve with Python HTTP server
- **Pros**: Preserves all React/TSX code unchanged
- **Cons**: Requires Node.js build step; multi-file bundle harder to maintain

### 8.2 Python-only Terminal UI (textual/rich)
- Rebuild the editor as a terminal TUI application
- **Pros**: No browser needed; runs entirely in CLI
- **Cons**: Cannot preserve the same SVG-based visual ring layout; loses drag-drop UX

### 8.3 Jupyter Notebook
- Use ipywidgets/ipytree for interactive editing
- **Pros**: Fits into notebook workflow
- **Cons**: Requires Jupyter; different UX from the current editor

**Chosen approach** (Standalone HTML + Python launcher) best satisfies all three goals:
- Same UI/UX (it IS the same React code, just bundled differently)
- Self-contained (single HTML file + single Python script)
- Claude Code compatible (subprocess call, blocking wait, file-based output)
