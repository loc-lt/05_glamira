#!/usr/bin/env bash
# After a network change (home ↔ office): start the VM, allow this IPv4 on 27017,
# put the current VM external IP into .env MONGO_URI.
source "$(dirname "$0")/lib.sh"

gcloud compute instances start "$VM_NAME" --zone="$GCP_ZONE" >/dev/null 2>&1 || true
for _ in $(seq 1 20); do
  status="$(gcloud compute instances describe "$VM_NAME" --zone="$GCP_ZONE" --format='value(status)')"
  if [[ "$status" == RUNNING ]]; then
    break
  fi
  sleep 3
done

bash "$(dirname "$0")/04_vm.sh"
VM_IP="$(gcloud compute instances describe "$VM_NAME" --zone="$GCP_ZONE" \
  --format='value(networkInterfaces[0].accessConfigs[0].natIP)')"

DOTENV="$REPO_ROOT/.env"
if [[ -f "$DOTENV" && -n "$VM_IP" ]]; then
  python3 - "$DOTENV" "$VM_IP" << 'PY'
from pathlib import Path
import re
import sys

path = Path(sys.argv[1])
ip = sys.argv[2]
text = path.read_text(encoding="utf-8")
if re.search(r"^MONGO_URI=.*@127\.0\.0\.1:", text, flags=re.M):
    print("MONGO_URI uses 127.0.0.1 (SSH tunnel). Left unchanged.")
    raise SystemExit(0)
new, n = re.subn(
    r"(^MONGO_URI=mongodb://[^@\n]+@)[^:/\n]+(:27017)",
    rf"\g<1>{ip}\2",
    text,
    count=1,
    flags=re.M,
)
if n:
    path.write_text(new, encoding="utf-8")
    print(f"updated .env MONGO_URI host -> {ip}")
else:
    print("no MONGO_URI host to patch in .env")
PY
fi

echo "reconnect: VM $VM_NAME is RUNNING at $VM_IP"
echo "ssh:  gcloud compute ssh \"$VM_NAME\" --zone=\"$GCP_ZONE\""
echo "ping: uv run python -c \"from src.config import Settings; from src.db import get_client; c=get_client(Settings.from_env()); print(c.admin.command('ping'))\""
