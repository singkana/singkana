#!/usr/bin/env bash
# ================================================================
# SingKANA Full Backup (Encrypted)
# - Code + data + runtime config を tgz 化
# - gpg(AES256) で暗号化
# - sha256 を保存
#
# Usage:
#   sudo /var/www/singkana/ops/backup_full_encrypted.sh
#   sudo BACKUP_GPG_PASSPHRASE='your-pass' /var/www/singkana/ops/backup_full_encrypted.sh
# ================================================================
set -euo pipefail

REPO_DIR="/var/www/singkana"
DATA_DIR="/var/lib/singkana"
BACKUP_DIR="/var/backups/singkana"
NAME_PREFIX="singkana_FULL"
PASS_ENV_NAME="BACKUP_GPG_PASSPHRASE"
KEEP_PLAIN=0
RETENTION_DAYS=14

usage() {
  cat <<'EOF'
Usage:
  backup_full_encrypted.sh [options]

Options:
  --repo-dir <path>        Repo path (default: /var/www/singkana)
  --data-dir <path>        Data path (default: /var/lib/singkana)
  --backup-dir <path>      Output dir (default: /var/backups/singkana)
  --name-prefix <name>     Archive prefix (default: singkana_FULL)
  --retention-days <days>  Delete backups older than this many days (default: 14, 0=disable)
  --passphrase-env <name>  Env var name for non-interactive gpg passphrase
                           (default: BACKUP_GPG_PASSPHRASE)
  --keep-plain             Keep plain .tgz after encryption (default: remove)
  -h, --help               Show this help
EOF
}

while [[ $# -gt 0 ]]; do
  case "$1" in
    --repo-dir)
      REPO_DIR="${2:-}"; shift 2 ;;
    --data-dir)
      DATA_DIR="${2:-}"; shift 2 ;;
    --backup-dir)
      BACKUP_DIR="${2:-}"; shift 2 ;;
    --name-prefix)
      NAME_PREFIX="${2:-}"; shift 2 ;;
    --retention-days)
      RETENTION_DAYS="${2:-}"; shift 2 ;;
    --passphrase-env)
      PASS_ENV_NAME="${2:-}"; shift 2 ;;
    --keep-plain)
      KEEP_PLAIN=1; shift ;;
    -h|--help)
      usage; exit 0 ;;
    *)
      echo "[backup] Unknown option: $1" >&2
      usage
      exit 1 ;;
  esac
done

if [[ "$(id -u)" -ne 0 ]]; then
  echo "[backup] ERROR: run as root (sudo)." >&2
  exit 1
fi

for cmd in tar gpg sha256sum date chmod; do
  if ! command -v "$cmd" >/dev/null 2>&1; then
    echo "[backup] ERROR: required command not found: $cmd" >&2
    exit 1
  fi
done

if ! [[ "$RETENTION_DAYS" =~ ^[0-9]+$ ]]; then
  echo "[backup] ERROR: --retention-days must be a non-negative integer." >&2
  exit 1
fi

TS="$(date +%Y%m%d-%H%M%S)"
umask 077
mkdir -p "$BACKUP_DIR"
chmod 700 "$BACKUP_DIR"

PLAIN_PATH="$BACKUP_DIR/${NAME_PREFIX}_${TS}.tgz"
ENC_PATH="${PLAIN_PATH}.gpg"
ENC_SHA_PATH="${ENC_PATH}.sha256"
MANIFEST_PATH="$BACKUP_DIR/${NAME_PREFIX}_${TS}.manifest.txt"

cleanup_plain_on_error() {
  local exit_code=$?
  if [[ $exit_code -ne 0 && "$KEEP_PLAIN" -eq 0 && -f "$PLAIN_PATH" ]]; then
    echo "[backup] WARN: script failed, removing plain archive." >&2
    if command -v shred >/dev/null 2>&1; then
      shred -u "$PLAIN_PATH" || rm -f "$PLAIN_PATH"
    else
      rm -f "$PLAIN_PATH"
    fi
  fi
}
trap cleanup_plain_on_error EXIT

TAR_ITEMS=()
for p in \
  "${REPO_DIR#/}" \
  "${DATA_DIR#/}" \
  "etc/nginx" \
  "etc/systemd/system/singkana.service" \
  "etc/systemd/system/singkana.service.d"
do
  if [[ -e "/$p" ]]; then
    TAR_ITEMS+=("$p")
  else
    echo "[backup] WARN: missing path skipped: /$p"
  fi
done

if [[ ${#TAR_ITEMS[@]} -eq 0 ]]; then
  echo "[backup] ERROR: no target paths found." >&2
  exit 1
fi

echo "[backup] Creating plain archive: $PLAIN_PATH"
tar -czf "$PLAIN_PATH" \
  --exclude="${REPO_DIR#/}/.git" \
  --exclude="${REPO_DIR#/}/node_modules" \
  --exclude="${REPO_DIR#/}/.cache" \
  --exclude="${REPO_DIR#/}/Logs" \
  -C / "${TAR_ITEMS[@]}"

PASS_VALUE="${!PASS_ENV_NAME:-}"
if [[ -n "$PASS_VALUE" ]]; then
  echo "[backup] Encrypting with env passphrase (\$$PASS_ENV_NAME)"
  printf '%s' "$PASS_VALUE" | gpg --batch --yes --pinentry-mode loopback \
    --passphrase-fd 0 \
    --symmetric --cipher-algo AES256 \
    --output "$ENC_PATH" \
    "$PLAIN_PATH"
  unset PASS_VALUE
else
  echo "[backup] Encrypting interactively (gpg prompt)"
  gpg --symmetric --cipher-algo AES256 \
    --output "$ENC_PATH" \
    "$PLAIN_PATH"
fi

sha256sum "$ENC_PATH" > "$ENC_SHA_PATH"
chmod 600 "$ENC_PATH" "$ENC_SHA_PATH"

if [[ "$KEEP_PLAIN" -eq 0 ]]; then
  if command -v shred >/dev/null 2>&1; then
    shred -u "$PLAIN_PATH" || rm -f "$PLAIN_PATH"
  else
    rm -f "$PLAIN_PATH"
  fi
else
  chmod 600 "$PLAIN_PATH"
fi

if [[ "$RETENTION_DAYS" -gt 0 ]]; then
  echo "[backup] Rotating backups older than ${RETENTION_DAYS} days"
  find "$BACKUP_DIR" -maxdepth 1 -type f -name "${NAME_PREFIX}_*.tgz.gpg" -mtime +"$RETENTION_DAYS" -delete
  find "$BACKUP_DIR" -maxdepth 1 -type f -name "${NAME_PREFIX}_*.tgz.gpg.sha256" -mtime +"$RETENTION_DAYS" -delete
  find "$BACKUP_DIR" -maxdepth 1 -type f -name "${NAME_PREFIX}_*.manifest.txt" -mtime +"$RETENTION_DAYS" -delete
  find "$BACKUP_DIR" -maxdepth 1 -type f -name "${NAME_PREFIX}_*.tgz" -mtime +"$RETENTION_DAYS" -delete
fi

{
  echo "timestamp=$TS"
  echo "repo_dir=$REPO_DIR"
  echo "data_dir=$DATA_DIR"
  echo "backup_dir=$BACKUP_DIR"
  echo "plain_path=$PLAIN_PATH"
  echo "encrypted_path=$ENC_PATH"
  echo "encrypted_sha_path=$ENC_SHA_PATH"
  echo "keep_plain=$KEEP_PLAIN"
  echo "retention_days=$RETENTION_DAYS"
  echo "repo_head=$(git -C "$REPO_DIR" rev-parse HEAD 2>/dev/null || echo unknown)"
  echo "repo_short=$(git -C "$REPO_DIR" rev-parse --short HEAD 2>/dev/null || echo unknown)"
} > "$MANIFEST_PATH"
chmod 600 "$MANIFEST_PATH"

trap - EXIT

echo "[backup] DONE"
echo "[backup] encrypted: $ENC_PATH"
echo "[backup] sha256:    $ENC_SHA_PATH"
echo "[backup] manifest:  $MANIFEST_PATH"
