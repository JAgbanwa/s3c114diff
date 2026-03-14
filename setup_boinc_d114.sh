#!/usr/bin/env bash
# setup_boinc_d114.sh
# ─────────────────────────────────────────────────────────────────────
# One-shot setup for the s3c114diff BOINC/Charity Engine project.
#
# Prerequisites:
#   - BOINC server stack installed (see boinc.berkeley.edu/trac/wiki/ServerIntro)
#   - BOINC_PROJECT_DIR set to the project root, e.g. /home/boincadm/projects/d114
#   - Run as the boincadm user
#
# Usage:
#   export BOINC_PROJECT_DIR=/home/boincadm/projects/d114
#   bash setup_boinc_d114.sh
# ─────────────────────────────────────────────────────────────────────
set -euo pipefail

APP_NAME="d114"
APP_VERS="1.00"
PLATFORM="x86_64-pc-linux-gnu"
PROJ="${BOINC_PROJECT_DIR:?Set BOINC_PROJECT_DIR first}"
SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"

echo "=== s3c114diff BOINC setup ==="
echo "Project dir: $PROJ"
echo "App name:    $APP_NAME  v$APP_VERS"

# ── 1. App directory ──────────────────────────────────────────────────
mkdir -p "$PROJ/apps/$APP_NAME/$APP_VERS/$PLATFORM"

# ── 2. Copy worker files ────────────────────────────────────────────
DEST="$PROJ/apps/$APP_NAME/$APP_VERS/$PLATFORM"
cp "$SCRIPT_DIR/worker_d114.py"  "$DEST/worker_d114"
cp "$SCRIPT_DIR/worker_d114.gp"  "$DEST/worker_d114.gp"
chmod +x "$DEST/worker_d114"

# ── 3. Templates ──────────────────────────────────────────────────────
mkdir -p "$PROJ/templates"
cat > "$PROJ/templates/d114_wu.xml" <<'WUXML'
<file_info>
    <number>0</number>
</file_info>
<workunit>
    <file_ref>
        <file_number>0</file_number>
        <open_name>wu.txt</open_name>
        <copy_file/>
    </file_ref>
    <command_line> wu.txt result.txt checkpoint_d114.json</command_line>
    <rsc_fpops_est>1e13</rsc_fpops_est>
    <rsc_fpops_bound>1e15</rsc_fpops_bound>
    <rsc_memory_bound>5.36e8</rsc_memory_bound>
    <rsc_disk_bound>5.24e7</rsc_disk_bound>
    <delay_bound>1209600</delay_bound>
</workunit>
WUXML

cat > "$PROJ/templates/d114_result.xml" <<'RXML'
<file_info>
    <name><OUTFILE_0/></name>
    <generated_locally/>
    <upload_when_present/>
    <max_nbytes>10485760</max_nbytes>
    <url><UPLOAD_URL/></url>
</file_info>
<result>
    <file_ref>
        <file_number>0</file_number>
        <open_name>result.txt</open_name>
    </file_ref>
</result>
RXML

# ── 4. Register app with BOINC project ───────────────────────────────
cd "$PROJ"
python3 bin/xadd 2>/dev/null || true    # update project.xml with new app

echo ">>> Setting app state to 'present'..."
cat >> "$PROJ/project.xml" <<APPXML || true
<!-- d114 elliptic curve search -->
<app>
  <name>$APP_NAME</name>
  <user_friendly_name>d114 Elliptic Curve Search</user_friendly_name>
</app>
APPXML

# ── 5. Directories ────────────────────────────────────────────────────
mkdir -p "$PROJ/results_d114"

# ── 6. Work generator + assimilator (systemd units) ──────────────────
if command -v systemctl &>/dev/null; then
    UNIT_DIR="/etc/systemd/system"

    # Work generator
    cat > "$UNIT_DIR/d114_wg.service" <<SVC
[Unit]
Description=d114 Work Generator
After=network.target

[Service]
Type=simple
User=boincadm
WorkingDirectory=$SCRIPT_DIR
ExecStart=$(which python3) $SCRIPT_DIR/work_generator_d114.py \
    --boinc_project_dir $PROJ \
    --app_name $APP_NAME \
    --daemon \
    --wu_dir $SCRIPT_DIR/wu_queue
Restart=always
RestartSec=30

[Install]
WantedBy=multi-user.target
SVC

    # Assimilator
    cat > "$UNIT_DIR/d114_assimilator.service" <<SVC2
[Unit]
Description=d114 Assimilator
After=network.target

[Service]
Type=simple
User=boincadm
WorkingDirectory=$SCRIPT_DIR
ExecStart=$(which python3) $SCRIPT_DIR/assimilator_d114.py \
    --results_dir $PROJ/results_d114 \
    --master $SCRIPT_DIR/output/solutions_d114.txt
Restart=always
RestartSec=10

[Install]
WantedBy=multi-user.target
SVC2

    systemctl daemon-reload
    systemctl enable d114_wg d114_assimilator
    systemctl start  d114_wg d114_assimilator
    echo "Systemd services started: d114_wg  d114_assimilator"
fi

echo "=== Setup complete ==="
echo "To monitor:"
echo "    journalctl -fu d114_wg"
echo "    journalctl -fu d114_assimilator"
echo "    tail -f $SCRIPT_DIR/output/search_log_d114.txt"
echo "    cat $SCRIPT_DIR/output/solutions_d114.txt"
