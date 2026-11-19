#!/bin/bash
# Makes the waitlist watcher run by itself every morning at 8:00.
#
#   Turn it on:    bash schedule.sh
#   Turn it off:   bash schedule.sh off
#
# It uses launchd, the scheduler built into macOS. If the Mac is asleep
# at 8:00, the watcher runs when the Mac next wakes up.

set -e

LABEL="com.waitlist-watcher.daily"
FOLDER="$(cd "$(dirname "$0")" && pwd)"
PLIST="$HOME/Library/LaunchAgents/$LABEL.plist"
PYTHON="$FOLDER/.venv/bin/python"

# Always remove the old schedule first, so running this twice is safe.
launchctl bootout "gui/$(id -u)/$LABEL" 2>/dev/null || true

if [ "$1" = "off" ]; then
    if [ -f "$PLIST" ]; then
        mv "$PLIST" "$FOLDER/schedule-removed.plist"
    fi
    echo "Schedule turned off. The watcher will only run when you run it."
    exit 0
fi

if [ ! -x "$PYTHON" ]; then
    echo "Could not find $PYTHON"
    echo "Run this from the waitlist-watcher folder, after creating .venv."
    exit 1
fi

mkdir -p "$HOME/Library/LaunchAgents"
cat > "$PLIST" <<EOF
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
    <key>Label</key>
    <string>$LABEL</string>
    <key>ProgramArguments</key>
    <array>
        <string>$PYTHON</string>
        <string>$FOLDER/watcher.py</string>
    </array>
    <key>WorkingDirectory</key>
    <string>$FOLDER</string>
    <key>StartCalendarInterval</key>
    <dict>
        <key>Hour</key>
        <integer>8</integer>
        <key>Minute</key>
        <integer>0</integer>
    </dict>
    <key>StandardOutPath</key>
    <string>$FOLDER/watcher.log</string>
    <key>StandardErrorPath</key>
    <string>$FOLDER/watcher.log</string>
</dict>
</plist>
EOF

launchctl bootstrap "gui/$(id -u)" "$PLIST"

echo "Schedule is on. The watcher will run every day at 8:00 AM."
echo "Each run adds its report to: $FOLDER/watcher.log"
echo "To run it right now as a test:  launchctl kickstart gui/$(id -u)/$LABEL"
echo "To turn it off:                 bash schedule.sh off"
