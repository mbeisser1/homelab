#!/usr/bin/env bash
set -euo pipefail

# -------------------------------------------------------------------
# pool-fix.sh
# Normalize /pool permissions for "hosted" group policy + git repos.
#
# - Strips ACLs under /pool (setfacl -Rb / -kR)
# - Converts any old numeric group GID (e.g., 1002) to HOSTED_GID
# - Sets group=HOSTED_GROUP across /pool
# - Directories: 2775 (setgid so children inherit group)
# - Files: 664
# - Executable files: 775
# - Special-case /pool/repo for Git collaboration:
#     Owner=$REPO_OWNER, Group=$HOSTED_GROUP, dir=2775, file=664, exec=775
#     git config core.sharedRepository=group and safe.directory
#
# Re-run anytime; it’s safe and idempotent.
# -------------------------------------------------------------------

# === Tweak these if needed ===
POOL_ROOT="${POOL_ROOT:-/pool}"
HOSTED_GROUP="${HOSTED_GROUP:-hosted}"
HOSTED_GID="${HOSTED_GID:-20250}"          # your chosen unique GID
OLD_NUMERIC_GID="${OLD_NUMERIC_GID:-1002}" # seen earlier on your tree

REPO_DIR="${REPO_DIR:-/pool/repo}"
REPO_OWNER="${REPO_OWNER:-mbeisser}"

# Use sudo if not root
SUDO=""
if [[ $EUID -ne 0 ]]; then
  SUDO="sudo"
fi

say() { echo -e "==> $*"; }
warn() { echo -e "!!  $*" >&2; }

# --- sanity checks ---
[[ -d "$POOL_ROOT" ]] || { warn "POOL_ROOT not found: $POOL_ROOT"; exit 1; }

# Ensure group exists and has the expected GID (create/update if needed)
if ! getent group "$HOSTED_GROUP" >/dev/null; then
  say "Creating group $HOSTED_GROUP (gid $HOSTED_GID)"
  $SUDO groupadd -g "$HOSTED_GID" "$HOSTED_GROUP"
else
  CURRENT_GID="$(getent group "$HOSTED_GROUP" | cut -d: -f3)"
  if [[ "$CURRENT_GID" != "$HOSTED_GID" ]]; then
    say "Adjusting $HOSTED_GROUP gid $CURRENT_GID -> $HOSTED_GID"
    $SUDO groupmod -g "$HOSTED_GID" "$HOSTED_GROUP"
  fi
fi

say "Stripping ACLs under $POOL_ROOT (recursive)"
$SUDO setfacl -Rb "$POOL_ROOT" || true
$SUDO setfacl -kR "$POOL_ROOT" || true

say "Converting any lingering files with group GID $OLD_NUMERIC_GID -> $HOSTED_GID"
$SUDO find "$POOL_ROOT" -group "$OLD_NUMERIC_GID" -exec chgrp -h "$HOSTED_GID" {} + || true

say "Setting group=$HOSTED_GROUP across $POOL_ROOT"
$SUDO chgrp -R "$HOSTED_GROUP" "$POOL_ROOT"

say "Directory perms -> 2775 (setgid) across $POOL_ROOT"
$SUDO find "$POOL_ROOT" -type d -exec chmod 2775 {} +

say "File perms -> 664 across $POOL_ROOT"
$SUDO find "$POOL_ROOT" -type f -exec chmod 664 {} +

say "Preserving executable bits -> 775 for files with user-exec"
$SUDO find "$POOL_ROOT" -type f -perm -u=x -exec chmod 775 {} +

# --- Special handling for /pool/repo (git-friendly ownership + config) ---
if [[ -d "$REPO_DIR" ]]; then
  say "Fixing $REPO_DIR for Git collaboration (owner=$REPO_OWNER group=$HOSTED_GROUP)"
  $SUDO chown -R "$REPO_OWNER:$HOSTED_GROUP" "$REPO_DIR"
  $SUDO find "$REPO_DIR" -type d -exec chmod 2775 {} +
  $SUDO find "$REPO_DIR" -type f -exec chmod 664 {} +
  $SUDO find "$REPO_DIR" -type f -perm -u=x -exec chmod 775 {} +

  # Configure each repo
  mapfile -t GIT_DIRS < <(find "$REPO_DIR" -type d -name ".git")
  if (( ${#GIT_DIRS[@]} )); then
    for gitdir in "${GIT_DIRS[@]}"; do
      repo="$(dirname "$gitdir")"
      say "Configuring git repo: $repo"
      $SUDO chown -R "$REPO_OWNER:$HOSTED_GROUP" "$gitdir"
      # shared by group
      sudo -u "$REPO_OWNER" git -C "$repo" config core.sharedRepository group || true
      # mark safe
      sudo -u "$REPO_OWNER" git -C "$repo" config --add safe.directory "$repo" || true
    done
  elif [[ -d "$REPO_DIR/.git" || -f "$REPO_DIR/.git" ]]; then
    say "Configuring git repo: $REPO_DIR"
    sudo -u "$REPO_OWNER" git -C "$REPO_DIR" config core.sharedRepository group || true
    sudo -u "$REPO_OWNER" git -C "$REPO_DIR" config --add safe.directory "$REPO_DIR" || true
  fi
else
  warn "Repo dir not found: $REPO_DIR (skipping git-specific fixes)"
fi

say "Done."
echo "Verify a few paths with:"
echo "  stat -c '%A %a %U:%G %n' $POOL_ROOT /pool/hosted /pool/Media $REPO_DIR"

