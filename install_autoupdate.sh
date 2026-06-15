#!/bin/bash
# Install the nightly 1 AM auto-update LaunchAgent (runs at next login if the Mac was off).
# Usage:  bash install_autoupdate.sh        (install / reinstall)
#         bash install_autoupdate.sh remove (uninstall)
set -e
LABEL="com.drew.ma-map-update"
DIR="$(cd "$(dirname "$0")" && pwd)"
PLIST="$DIR/$LABEL.plist"
DST="$HOME/Library/LaunchAgents/$LABEL.plist"
UID_NUM="$(id -u)"

if [ "$1" = "remove" ]; then
  launchctl bootout "gui/$UID_NUM/$LABEL" 2>/dev/null || true
  rm -f "$DST"
  echo "Removed $LABEL."
  exit 0
fi

mkdir -p "$HOME/Library/LaunchAgents"
cp "$PLIST" "$DST"
launchctl bootout "gui/$UID_NUM/$LABEL" 2>/dev/null || true
launchctl bootstrap "gui/$UID_NUM" "$DST"
echo "Installed $LABEL."
echo "  • Runs update_listings.py at 1:00 AM daily."
echo "  • If the Mac is asleep/off at 1 AM, it runs at the next wake/login (once per day)."
echo "  • Logs:   $DIR/data/raw/update.log"
echo "  • Tune:   edit MAP_TARGET_HOMES / MAP_MAX_REGIONS in $LABEL.plist, then re-run this script."
echo "  • Remove: bash install_autoupdate.sh remove"
echo
echo "Run once now to seed data:  MAP_FORCE=1 /usr/bin/python3 $DIR/update_listings.py"
