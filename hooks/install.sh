#!/bin/sh
# Install the tracked pre-push gate into this checkout, following senku/hooks/install.sh.
set -eu
cd "$(dirname "$0")/.."
cp hooks/pre-push .git/hooks/pre-push
chmod +x .git/hooks/pre-push
echo "pre-push hook installed"
