#!/usr/bin/env bash
# Checkpoint 6a: Ubuntu 24.04 VM for MongoDB, firewall 27017 open to this machine's IPv4 only.
source "$(dirname "$0")/lib.sh"

if gcloud compute instances describe "$VM_NAME" --zone="$GCP_ZONE" >/dev/null 2>&1; then
  echo "vm exists: $VM_NAME"
else
  gcloud compute instances create "$VM_NAME" \
    --zone="$GCP_ZONE" \
    --machine-type="$VM_MACHINE_TYPE" \
    --image-family=ubuntu-2404-lts-amd64 \
    --image-project=ubuntu-os-cloud \
    --boot-disk-size="$VM_DISK_SIZE" \
    --boot-disk-type=pd-balanced \
    --service-account="$SA_EMAIL" \
    --scopes=cloud-platform \
    --tags="$VM_TAG"
fi

MY_IP="$(curl -4 -fsS https://api.ipify.org)"
RULE="${VM_TAG}-from-my-ip"
if gcloud compute firewall-rules describe "$RULE" >/dev/null 2>&1; then
  gcloud compute firewall-rules update "$RULE" --source-ranges="${MY_IP}/32"
else
  gcloud compute firewall-rules create "$RULE" \
    --network=default \
    --direction=INGRESS \
    --action=ALLOW \
    --rules=tcp:27017 \
    --source-ranges="${MY_IP}/32" \
    --target-tags="$VM_TAG"
fi

echo "firewall $RULE allows tcp:27017 from ${MY_IP}/32"
gcloud compute instances describe "$VM_NAME" --zone="$GCP_ZONE" \
  --format="value(networkInterfaces[0].accessConfigs[0].natIP)"
