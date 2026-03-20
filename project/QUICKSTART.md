# VideoEditor Quickstart

## Prerequisites

- **Python 3.10+** (tested on 3.13)
- **Node.js 18+** (for Vue frontend dev server)
- **FFmpeg** (optional, for real video processing)
- macOS / Linux (Windows: untested)

---

## 1. Install Dependencies

```bash
cd videoeditor

# Python
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt

# Node (frontend)
cd apps/desktop/ui-vue
npm install
cd ../../..
```

---

## 2. Seed Demo Data (Optional)

```bash
source .venv/bin/activate
python tools/seed_demo_library.py
```

Creates 5 demo assets (3 video + 2 image), one duplicate pair, and a Jianying draft file for relink demo.

---

## 3. Start the App

### Option A: Desktop GUI (Recommended)

```bash
source .venv/bin/activate
python apps/desktop/launcher.py
```

Opens a native window at 1280x820. Flask backend starts on port 9527.

### Option B: Headless + Vue Dev Server

```bash
# Terminal 1: Backend
source .venv/bin/activate
VIDEOEDITOR_REQUIRE_LOCAL_TOKEN=0 python apps/desktop/launcher.py --debug

# Terminal 2: Frontend (hot reload)
cd apps/desktop/ui-vue
npm run dev
# Open http://localhost:5173
```

Vite dev server proxies `/api` requests to Flask on port 9527.

### Option C: One-click (macOS)

```bash
./start.command
```

---

## 4. Key Pages

| Page | URL Path | Description |
|------|----------|-------------|
| Library | `/library` | Media browser, search, ingest, health |
| Production | `/production` | Workflow hub, capabilities |
| Settings | `/settings` | AI config, UI preferences |

---

## 5. Demo Walkthrough

After seeding demo data and starting the app:

### Search & Browse
1. Go to **Library** page
2. See 5 assets in the grid
3. Search "sunset" — should find 2 results
4. Toggle between grid/list views
5. Filter by video/image type

### Duplicate Detection
1. Click **Maintenance** tab in the panel switcher
2. Use **Duplicate Groups** panel
3. Click detect — finds the sunset_beach duplicate pair
4. Set primary → resolve or ignore

### Project Relink
1. Click **Project Repair** tab
2. Use **Project Relink** panel
3. Enter path: `demo/draft_content.json`
4. Analyze → see 2 matched + 1 missing items
5. Try manual bind for the missing item

---

## 6. Run Tests

```bash
source .venv/bin/activate
pytest tests/ -q
# Expected: 587 passed, 2 skipped, 0 failed
```

### Test Categories

| Pattern | Count | Description |
|---------|-------|-------------|
| `test_e2e_*.py` | 15 | Flow-level integration tests |
| `test_*_api.py` | ~150 | API endpoint tests |
| `test_*.py` (other) | ~420 | Unit + module tests |

---

## 7. Project Structure

```
videoeditor/
├── apps/desktop/
│   ├── launcher.py              # Desktop app entry point
│   └── ui-vue/                  # Vue 3 frontend (Vite)
├── modules/
│   ├── app_api/server.py        # Flask backend (all routes)
│   ├── library/                 # Media library engine
│   └── capabilities/            # Feature modules (20+)
├── tests/                       # 587 tests
├── tools/
│   └── seed_demo_library.py     # Demo data seeder
├── demo/                        # Demo project files
├── requirements.txt             # Python dependencies
└── QUICKSTART.md                # This file
```

---

## 8. Environment Variables

| Variable | Default | Description |
|----------|---------|-------------|
| `VIDEOEDITOR_REQUIRE_LOCAL_TOKEN` | `1` | Disable with `0` for CLI/headless |
| `VIDEOEDITOR_REQUIRE_CSRF` | `1` | CSRF protection |
| `VIDEOEDITOR_UI_DIR` | auto | Custom frontend dist path |

---

## 9. Commit History (Recent)

```
79f1563  fix: test_publish_prep_api env-independent
1085f34  usability: panel grouping, empty-state, flow-level E2E tests
52ff856  fix: test fixtures self-contained
16f9bad  feat: project_relink phase 1 (frozen)
```
