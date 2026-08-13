#!/usr/bin/env bash
# Provision the Bangkok box (Z.com, 2 vCPU / 4 GB) to run this repo's CI.
#
# Run as ROOT, once. Idempotent — safe to re-run.
#
#   REG_TOKEN=<token from the repo's Settings > Actions > Runners page> \
#     bash deploy/provision_selfhosted_runner.sh
#
# WHAT THIS BOX IS FOR, AND WHY IT EXISTS AT ALL
# ----------------------------------------------
# Two jobs, for two unrelated reasons:
#
#   `thai` runner  — the five feeds pull_swarm.py fences behind --include-thai are geoblocked from
#                    every datacenter IP, so they had never once run on a schedule. This box is in
#                    Bangkok on a Thai ASN, so they can. (.github/workflows/data-thai-swarm.yml)
#
#   `ci` runner    — QA was 3,050 of the repo's 3,849 Actions job-minutes over a measured 29-hour
#                    window: 79% of a metered private-repo bill. Almost all of it was toolchain, not
#                    testing — a fresh ~150MB Chromium download on every one of 136 runs. Here the
#                    browser is provisioned once, below, and every run after that skips it.
#
# WHY EXACTLY ONE `ci` RUNNER. 4 GB. The render phase drives software-WebGL Chromium over deck.gl
# scenes and can pass 1.5 GB by itself; a second concurrent job would OOM rather than parallelise.
# Two runner processes total (thai + ci) on 2 cores is fine — they are idle pollers except when a
# job is actually running, and the thai feed pull is a once-daily 02:20 window.
#
# WHY THE RUNNER ACCOUNT DOES NOT GET PASSWORDLESS SUDO. A self-hosted runner executes whatever the
# workflow file says, so handing it NOPASSWD:ALL would make every push a root shell on this box.
# Instead everything needing root is done HERE, once, and qa.yml detects the result and skips. If
# provisioning is ever incomplete the workflow fails with one legible line instead of hanging on a
# password prompt nothing can answer.

set -euo pipefail

RUNNER_USER="${RUNNER_USER:-runner}"
RUNNER_HOME="/home/${RUNNER_USER}"
REPO_URL="${REPO_URL:-https://github.com/kaustavb2101/competitive-intel}"
RUNNER_VERSION="${RUNNER_VERSION:-2.336.0}"
PW_VERSION="${PW_VERSION:-1.49.1}"

if [ "$(id -u)" -ne 0 ]; then
  echo "run this as root" >&2; exit 1
fi

# ---------------------------------------------------------------- 1. swap
# 4 GB with no swap is where Chromium gets OOM-killed mid-render rather than merely being slow.
# The render phases are non-blocking in qa.yml, so an OOM would not fail the build — it would just
# silently stop producing the render/health/visual artifacts, which is the worst of both worlds.
if ! swapon --show | grep -q '/swapfile'; then
  echo "== creating 4G swapfile =="
  fallocate -l 4G /swapfile || dd if=/dev/zero of=/swapfile bs=1M count=4096
  chmod 600 /swapfile
  mkswap /swapfile
  swapon /swapfile
  grep -q '^/swapfile' /etc/fstab || echo '/swapfile none swap sw 0 0' >> /etc/fstab
  # Chromium benefits from swap existing, not from the kernel eagerly using it.
  sysctl -w vm.swappiness=10
  grep -q '^vm.swappiness' /etc/sysctl.conf || echo 'vm.swappiness=10' >> /etc/sysctl.conf
else
  echo "== swap already present, skipping =="
fi

# ---------------------------------------------------------------- 2. toolchain
echo "== base packages =="
apt-get update -qq
apt-get install -y -qq curl git jq unzip ca-certificates gnupg python3 python3-pip python3-venv

if ! command -v node >/dev/null 2>&1 || [ "$(node -v | cut -c2- | cut -d. -f1)" -lt 22 ]; then
  echo "== node 22 =="
  mkdir -p /etc/apt/keyrings
  curl -fsSL https://deb.nodesource.com/gpgkey/nodesource-repo.gpg.key \
    | gpg --dearmor -o /etc/apt/keyrings/nodesource.gpg
  echo "deb [signed-by=/etc/apt/keyrings/nodesource.gpg] https://deb.nodesource.com/node_22.x nodistro main" \
    > /etc/apt/sources.list.d/nodesource.list
  apt-get update -qq && apt-get install -y -qq nodejs
fi
node -v

if ! command -v gh >/dev/null 2>&1; then
  echo "== github cli (data workflows open their own draft PRs) =="
  curl -fsSL https://cli.github.com/packages/githubcli-archive-keyring.gpg \
    -o /usr/share/keyrings/githubcli-archive-keyring.gpg
  chmod a+r /usr/share/keyrings/githubcli-archive-keyring.gpg
  echo "deb [arch=amd64 signed-by=/usr/share/keyrings/githubcli-archive-keyring.gpg] https://cli.github.com/packages stable main" \
    > /etc/apt/sources.list.d/github-cli.list
  apt-get update -qq && apt-get install -y -qq gh
fi
gh --version | head -1

# ---------------------------------------------------------------- 3. chromium, once
# Two halves with different privilege needs: the system libraries are apt packages and need root;
# the browser bundle itself must be readable by the runner account. Installing the bundle AS the
# runner puts it under that account's cache, then a world-readable copy under /opt is what
# render.sh actually looks for.
if ls -d /opt/pw-browsers/chromium-*/chrome-linux/chrome >/dev/null 2>&1; then
  echo "== chromium already provisioned, skipping =="
else
  echo "== chromium + system deps (this is the ~150MB that every CI run used to repeat) =="
  npx --yes playwright@"${PW_VERSION}" install-deps chromium
  sudo -u "${RUNNER_USER}" -H bash -lc \
    "npx --yes playwright@${PW_VERSION} install chromium"
  PW_DIR="${RUNNER_HOME}/.cache/ms-playwright"
  CH="$(ls -d "${PW_DIR}"/chromium-*/chrome-linux/chrome 2>/dev/null | head -1)"
  if [ -z "$CH" ]; then echo "chromium not found under ${PW_DIR}" >&2; exit 1; fi
  VER="$(basename "$(dirname "$(dirname "$CH")")")"
  mkdir -p /opt/pw-browsers
  cp -r "${PW_DIR}/${VER}" "/opt/pw-browsers/${VER}"
  chmod -R a+rX /opt/pw-browsers
  ls -d /opt/pw-browsers/chromium-*/chrome-linux/chrome
fi

# ---------------------------------------------------------------- 4. the ci runner
# A second runner PROCESS beside the existing `thai` one, in its own directory. Same box, different
# label, so QA can never queue in front of the nightly Thai feed pull or vice versa.
if [ -d "${RUNNER_HOME}/actions-runner-ci/.runner" ]; then
  echo "== ci runner already configured, skipping registration =="
else
  if [ -z "${REG_TOKEN:-}" ]; then
    echo "REG_TOKEN is not set. Get a fresh one from:" >&2
    echo "  ${REPO_URL}/settings/actions/runners/new" >&2
    echo "then re-run:  REG_TOKEN=<token> bash $0" >&2
    exit 1
  fi
  echo "== registering the ci runner =="
  sudo -u "${RUNNER_USER}" -H bash -lc "
    set -e
    mkdir -p ${RUNNER_HOME}/actions-runner-ci
    cd ${RUNNER_HOME}/actions-runner-ci
    if [ ! -f ./config.sh ]; then
      curl -fsSL -o runner.tar.gz \
        https://github.com/actions/runner/releases/download/v${RUNNER_VERSION}/actions-runner-linux-x64-${RUNNER_VERSION}.tar.gz
      tar xzf runner.tar.gz && rm -f runner.tar.gz
    fi
    ./config.sh --url ${REPO_URL} --token ${REG_TOKEN} --name ci-bkk --labels ci --unattended --replace
  "
  cd "${RUNNER_HOME}/actions-runner-ci"
  ./svc.sh install "${RUNNER_USER}"
  ./svc.sh start
fi

# ---------------------------------------------------------------- 5. disk hygiene
# A hosted runner is thrown away after every job; this one is not. Old job workspaces and the
# runner's own diagnostic logs accumulate until the disk fills, and a full disk on a CI box fails
# every job at once with an error that points nowhere near the cause.
cat > /etc/cron.daily/gh-runner-cleanup <<'CRON'
#!/bin/sh
find /home/runner/actions-runner*/_work -maxdepth 2 -type d -mtime +7 -exec rm -rf {} + 2>/dev/null
find /home/runner/actions-runner*/_diag -type f -mtime +14 -delete 2>/dev/null
CRON
chmod +x /etc/cron.daily/gh-runner-cleanup

echo
echo "== done =="
systemctl list-units 'actions.runner.*' --no-pager --no-legend || true
free -h
df -h /
