#!/usr/bin/env bash
# Run ON THE VM. Installs MongoDB 8.0, creates two users, then turns on auth and listens on all interfaces.
# The firewall (04_vm.sh) is what limits who reaches port 27017.
# Usage: bash infra/gcp/vm/install_mongo.sh   (asks for two passwords)
set -euo pipefail

sudo apt-get update
sudo apt-get install -y gnupg curl git tmux

if ! command -v mongod >/dev/null 2>&1; then
  curl -fsSL https://www.mongodb.org/static/pgp/server-8.0.asc \
    | sudo gpg -o /usr/share/keyrings/mongodb-server-8.0.gpg --dearmor --yes
  echo "deb [ arch=amd64,arm64 signed-by=/usr/share/keyrings/mongodb-server-8.0.gpg ] https://repo.mongodb.org/apt/ubuntu noble/mongodb-org/8.0 multiverse" \
    | sudo tee /etc/apt/sources.list.d/mongodb-org-8.0.list
  sudo apt-get update
  sudo apt-get install -y mongodb-org
fi
sudo systemctl enable --now mongod
sleep 3

if grep -q "^  authorization: enabled" /etc/mongod.conf; then
  echo "auth already enabled. Users are not touched."
  exit 0
fi

read -r -s -p "password for Mongo user admin (root): " MONGO_ADMIN_PASSWORD; echo
read -r -s -p "password for Mongo user glamira_app (readWrite on glamira): " MONGO_APP_PASSWORD; echo
export MONGO_ADMIN_PASSWORD MONGO_APP_PASSWORD

mongosh --quiet admin --eval '
if (!db.getUser("admin")) {
  db.createUser({user: "admin", pwd: process.env.MONGO_ADMIN_PASSWORD, roles: ["root"]});
}
if (!db.getUser("glamira_app")) {
  db.createUser({user: "glamira_app", pwd: process.env.MONGO_APP_PASSWORD,
                 roles: [{role: "readWrite", db: "glamira"}]});
}
printjson(db.getUsers().users.map(u => u.user));
'

sudo cp /etc/mongod.conf /etc/mongod.conf.bak
sudo sed -i 's/^  bindIp: 127.0.0.1$/  bindIp: 0.0.0.0/' /etc/mongod.conf
sudo sed -i 's/^#security:$/security:\n  authorization: enabled/' /etc/mongod.conf
sudo systemctl restart mongod
sleep 3
sudo systemctl --no-pager status mongod | head -5
grep -A1 -E "^(net|security):" /etc/mongod.conf
