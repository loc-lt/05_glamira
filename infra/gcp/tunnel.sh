#!/usr/bin/env bash
# Keep an SSH tunnel from this machine to MongoDB on the VM, and reopen it when it drops.
# localhost:27018 (your machine) -> 127.0.0.1:27017 (inside the VM).
# SSH (port 22) is open to any IP via default-allow-ssh, so a new home IP does not
# break the tunnel the way it breaks the tcp:27017 firewall rule.
# Use: run in its own terminal / tmux window, then set in .env:
#   MONGO_URI=mongodb://glamira_app:<pass>@127.0.0.1:27018/glamira?authSource=admin
source "$(dirname "$0")/lib.sh"

LOCAL_PORT="${LOCAL_PORT:-27018}"
while true; do
  echo "[tunnel] $(date '+%F %T') opening localhost:${LOCAL_PORT} -> ${VM_NAME}:27017"
  gcloud compute ssh "$VM_NAME" --zone="$GCP_ZONE" -- -N \
    -L "${LOCAL_PORT}:127.0.0.1:27017" \
    -o ServerAliveInterval=30 -o ServerAliveCountMax=3 -o ExitOnForwardFailure=yes || true
  echo "[tunnel] $(date '+%F %T') closed; reopening in 10s (Ctrl+C to stop)"
  sleep 10
done
