#!/usr/bin/env bash
# One-time provisioning of a fresh Ubuntu 24.04 VPS (TECH_SPEC §20.3). Run as root:
#   curl -fsSL https://raw.githubusercontent.com/<you>/gitmgf/main/deploy/setup-vps.sh | bash -s -- <deploy-user> "<ssh-public-key>"
# Read it first. It installs Docker, enables a firewall (22/80/443), automatic security updates and
# key-only SSH, and creates a non-root deploy user in the docker group.
set -euo pipefail

DEPLOY_USER="${1:-deploy}"
SSH_KEY="${2:-}"

apt-get update
apt-get -y upgrade
apt-get install -y ca-certificates curl git ufw unattended-upgrades fail2ban

# Docker Engine + compose plugin (official repository)
install -m 0755 -d /etc/apt/keyrings
curl -fsSL https://download.docker.com/linux/ubuntu/gpg -o /etc/apt/keyrings/docker.asc
chmod a+r /etc/apt/keyrings/docker.asc
echo "deb [arch=$(dpkg --print-architecture) signed-by=/etc/apt/keyrings/docker.asc] https://download.docker.com/linux/ubuntu $(. /etc/os-release && echo "$VERSION_CODENAME") stable" \
    > /etc/apt/sources.list.d/docker.list
apt-get update
apt-get install -y docker-ce docker-ce-cli containerd.io docker-buildx-plugin docker-compose-plugin

# Deploy user
id -u "$DEPLOY_USER" >/dev/null 2>&1 || adduser --disabled-password --gecos "" "$DEPLOY_USER"
usermod -aG docker "$DEPLOY_USER"
if [ -n "$SSH_KEY" ]; then
    install -d -m 700 -o "$DEPLOY_USER" -g "$DEPLOY_USER" "/home/$DEPLOY_USER/.ssh"
    echo "$SSH_KEY" >> "/home/$DEPLOY_USER/.ssh/authorized_keys"
    chown "$DEPLOY_USER:$DEPLOY_USER" "/home/$DEPLOY_USER/.ssh/authorized_keys"
    chmod 600 "/home/$DEPLOY_USER/.ssh/authorized_keys"
fi

# Firewall: SSH + HTTP(S) only
ufw default deny incoming
ufw default allow outgoing
ufw allow 22/tcp
ufw allow 80/tcp
ufw allow 443/tcp
ufw allow 443/udp
ufw --force enable

# Key-only SSH (only once a key is installed, so we never lock you out)
if [ -n "$SSH_KEY" ]; then
    sed -i 's/^#\?PasswordAuthentication .*/PasswordAuthentication no/' /etc/ssh/sshd_config
    sed -i 's/^#\?PermitRootLogin .*/PermitRootLogin prohibit-password/' /etc/ssh/sshd_config
    systemctl reload ssh || systemctl reload sshd
fi

dpkg-reconfigure -f noninteractive unattended-upgrades
echo "Done. Log in as $DEPLOY_USER, clone the repo and follow docs/RUNBOOK.md."
