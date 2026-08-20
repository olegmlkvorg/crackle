#!/bin/sh
# Point this repo at the TRACKED hooks directory. It does not copy.
#
# It used to `cp hooks/pre-push .git/hooks/pre-push`, following senku, and on 2026-08-20 senku's
# copy was found three weeks stale: the tracked hook had gained a flag and the copy git actually ran
# had not, so a shipped change to the gate was inert and nothing said so. crackle had the same
# pattern and no `core.hooksPath` set, so it was one hook edit away from the same failure.
#
# A copy is a second source of truth that goes stale silently. core.hooksPath has none: the file in
# the repo IS the file git runs, so editing the hook is installing it.
set -eu
cd "$(dirname "$0")/.."
git config core.hooksPath hooks
rm -f .git/hooks/pre-push
chmod +x hooks/pre-push
echo "pre-push gate installed: core.hooksPath=hooks, any stale copy removed"
