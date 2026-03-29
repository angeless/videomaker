#!/bin/bash
export PATH="/usr/local/bin:$PATH"
cd "$(dirname "$0")/../apps/desktop/ui-vue"
exec npx vite --port 5173
