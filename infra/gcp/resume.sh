#!/usr/bin/env bash
# Run this FIRST every time you sit down to work (office <-> home, after a reboot, next day).
# It makes the pieces line up, then tells you what to run next:
#   1. gcloud account / project
#   2. VM is RUNNING (starts it if stopped)
#   3. SSH tunnel localhost:27018 -> VM:27017 is running in tmux session "tunnel"
#   4. .env MONGO_URI points at the tunnel (127.0.0.1:27018)
#   5. Mongo answers, and how far the crawl has got
# Safe to run any number of times. It never deletes data.
source "$(dirname "$0")/lib.sh"
cd "$REPO_ROOT"

ok()   { echo "  ✅ $*"; }
warn() { echo "  ⚠️  $*"; }

echo "1. gcloud"
ok "account=$(gcloud config get-value account 2>/dev/null)  project=$(gcloud config get-value project 2>/dev/null)"

echo "2. VM $VM_NAME"
status="$(gcloud compute instances describe "$VM_NAME" --zone="$GCP_ZONE" --format='value(status)')"
if [[ "$status" != RUNNING ]]; then
  warn "status=$status, starting it"
  gcloud compute instances start "$VM_NAME" --zone="$GCP_ZONE" >/dev/null
  sleep 20
fi
ok "RUNNING, external IP $(gcloud compute instances describe "$VM_NAME" --zone="$GCP_ZONE" \
  --format='value(networkInterfaces[0].accessConfigs[0].natIP)') (changes after stop/start; the tunnel does not care)"

echo "3. SSH tunnel"
if tmux has-session -t tunnel 2>/dev/null && pgrep -f "infra/gcp/tunnel.sh" >/dev/null; then
  ok "tmux session 'tunnel' is running"
else
  tmux kill-session -t tunnel 2>/dev/null || true
  tmux new-session -d -s tunnel "bash infra/gcp/tunnel.sh"
  ok "started tmux session 'tunnel' (bash infra/gcp/tunnel.sh); waiting 15s for it to open"
  sleep 15
fi

echo "4. .env MONGO_URI"
host="$(grep -E '^MONGO_URI=' .env | sed -E 's#.*@([^/]+)/.*#\1#')"
if [[ "$host" == "127.0.0.1:27018" ]]; then
  ok "uses the tunnel (127.0.0.1:27018)"
else
  warn "MONGO_URI host is '$host'. For the tunnel it must be 127.0.0.1:27018."
  warn "Edit .env line MONGO_URI=mongodb://glamira_app:<pass>@127.0.0.1:27018/glamira?authSource=admin"
  exit 1
fi

echo "5. Mongo + crawl progress"
uv run python - <<'PY'
from src.config import Settings
from src.db import get_client

s = Settings.from_env()
db = get_client(s)[s.mongo_db]
db.command("ping")
p = db.products
named = p.count_documents({"name": {"$type": "string", "$ne": ""}})
missing = p.count_documents({"not_found": True, "name": {"$in": [None, ""]}})
seed = sum(1 for _ in open("data/exports/product_urls.csv", encoding="utf-8")) - 1
left = seed - named - missing
print(f"  ✅ ping ok | glamira_raw {db.glamira_raw.estimated_document_count():,} | ip_geo {db.ip_geo.estimated_document_count():,}")
print(f"  ✅ products: named {named:,} + not_found {missing:,} of seed {seed:,} -> {left:,} left (~{left / 1600:.1f} h)")
PY

echo
if tmux has-session -t react 2>/dev/null; then
  echo "Next: tmux attach -t react   (if it shows a prompt, run the crawl command below there)"
else
  echo "Next: tmux new -s react"
fi
echo "  systemd-inhibit --what=sleep:idle uv run python -m src.enrich.reactdata --limit 0 2>&1 | tee -a data/staging/crawl_react.log"
