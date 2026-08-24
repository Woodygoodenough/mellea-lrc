#!/usr/bin/env bash
# Spend one day's CourtListener allowance filling the shared response cache.
#
# This runs on a machine that can reach the Modal proxy. It deliberately does
# not run in a cloud agent: the sandbox's egress policy denies *.modal.run with
# a 403 on CONNECT, so a cloud-scheduled version of this job fails before it
# sends a single request.
#
# It calls no model and makes no repository changes. The cache behind the proxy
# is the whole deliverable, and it is what carries progress between runs -- a
# locator already fetched is served from R2 at no quota cost, so starting from
# scratch each day is cheap and the checkpoint is only a convenience.
#
# The run waits for the daily allowance rather than assuming it has arrived,
# so the schedule only has to be roughly right. See MAX_WAIT_SECONDS below.
#
# On macOS install the launchd agent, which fires on wake if the machine was
# asleep at the appointed time -- cron does not, and on a laptop that is the
# difference between running and not:
#
#   cp scripts/courtlistener/com.mellea-lrc.cache-fill.plist ~/Library/LaunchAgents/
#   launchctl load ~/Library/LaunchAgents/com.mellea-lrc.cache-fill.plist
#
# Check it took:   launchctl list | grep mellea-lrc
# Read the log:    tail -n 40 <repo>/local/cache-fill.log
# Remove it:       launchctl unload ~/Library/LaunchAgents/com.mellea-lrc.cache-fill.plist
#
# On Linux, cron is fine because the machine is not asleep:
#
#   (crontab -l 2>/dev/null; echo "15 3 * * * $PWD/scripts/courtlistener/daily_cache_fill.sh") | crontab -

set -uo pipefail

REPO="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
cd "$REPO" || exit 1

LOG_DIR="$REPO/local"
LOG="$LOG_DIR/cache-fill.log"
mkdir -p "$LOG_DIR"

say() { printf '%s %s\n' "$(date '+%Y-%m-%d %H:%M:%S')" "$*" >> "$LOG"; }

say "=== run starting ==="

# cron gets almost no PATH, so uv has to be found rather than assumed.
export PATH="$HOME/.local/bin:/opt/homebrew/bin:/usr/local/bin:$PATH"
if ! command -v uv > /dev/null; then
  say "FAILED: uv is not on PATH"
  exit 1
fi

if [ ! -f "$REPO/.env" ]; then
  say "FAILED: no .env, so the proxy address is unknown"
  exit 1
fi
set -a; . "$REPO/.env"; set +a
BASE="${COURTLISTENER_BASE_URL%/}"

# A failed health check means the day would be spent on errors, so stop here.
HEALTH="$(curl -s -m 60 "$BASE/health" 2>&1)"
case "$HEALTH" in
  *'"status":"ok"'*) say "proxy healthy: $HEALTH" ;;
  *) say "FAILED: proxy health check did not return ok: $HEALTH"; exit 1 ;;
esac

# The allowance is 24 hours from each token's FIRST USE, not from midnight, so
# the moment it returns drifts later every day the job starts later. A fixed
# schedule therefore cannot stay on the right side of it: whatever hour is
# chosen, within days the run starts a few minutes early and spends itself on
# refusals. The proxy says exactly how long is left, so wait rather than guess.
#
# Bounded, because waiting is only correct when the allowance is about to
# return. A refusal with hours on it means this is the second run of the day,
# and the right answer then is to stop and let tomorrow's fire have it.
MAX_WAIT_SECONDS=${MAX_WAIT_SECONDS:-5400}

# The probe has to MISS the cache. A cached answer comes back 200 with no
# mention of the allowance, so probing a citation that has been asked for
# before reports "available" whatever the allowance is actually doing -- which
# sent a run straight into a refusal it had just been told to wait for. A
# random volume and page is never cached, so the answer is always about the
# allowance. It costs one request when the allowance is up, out of 375.
probe_allowance() {
  curl -s -m 60 -X POST "$BASE/citation-lookup/" \
    --data-urlencode "volume=$(( (RANDOM % 800) + 100 ))" \
    --data-urlencode "reporter=F.2d" \
    --data-urlencode "page=$(( (RANDOM % 9000) + 1000 ))" 2>/dev/null
}

WAITED=0
while :; do
  REPLY_BODY="$(probe_allowance)"
  case "$REPLY_BODY" in
    *retry_after_seconds*) ;;
    *) break ;;
  esac
  LEFT="$(printf '%s' "$REPLY_BODY" | sed -n 's/.*"retry_after_seconds": *\([0-9]*\).*/\1/p')"
  [ -n "$LEFT" ] || break
  if [ "$LEFT" -gt "$MAX_WAIT_SECONDS" ]; then
    say "allowance returns in ${LEFT}s, beyond the ${MAX_WAIT_SECONDS}s this run will wait; stopping"
    say "=== run finished ==="
    exit 0
  fi
  say "allowance returns in ${LEFT}s; waiting"
  sleep "$((LEFT + 15))"
  WAITED=$((WAITED + LEFT + 15))
  if [ "$WAITED" -gt "$((MAX_WAIT_SECONDS * 2))" ]; then
    say "waited ${WAITED}s without the allowance returning; stopping"
    say "=== run finished ==="
    exit 0
  fi
done
say "allowance is available"

DATASET="$REPO/data/lephantomcite/eval.jsonl"
if [ ! -f "$DATASET" ]; then
  say "dataset missing, downloading"
  uv run hf download ai-law-society-lab/Legal_Phantom_Citation \
    --repo-type dataset --local-dir "$REPO/data/lephantomcite" >> "$LOG" 2>&1 \
    || { say "FAILED: dataset download"; exit 1; }
fi

say "running the locator probe"
uv run --env-file "$REPO/.env" python -m evaluations.lephantomcite.run_locator_probe \
  --dataset "$DATASET" \
  --output "$LOG_DIR/locator-probe.json" \
  --checkpoint "$LOG_DIR/locator-probe.checkpoint.jsonl" >> "$LOG" 2>&1
STATUS=$?

# Exhausting the allowance is the expected ending, not a failure: the job's
# purpose is to spend the day's budget and stop.
ANSWERED=$(wc -l < "$LOG_DIR/locator-probe.checkpoint.jsonl" 2>/dev/null | tr -d ' ')
say "probe exited $STATUS; checkpoint now holds ${ANSWERED:-0} answered locators"

# Whatever allowance the locators left goes to the opinion documents the
# checking stage reads. Those are a different endpoint and are not stored by
# the probe, so until they are warm that stage needs a live service and cannot
# be re-run offline. Enumerating them costs nothing -- it reads the locator
# answers back out of the cache -- so this is safe to attempt every night even
# when the probe has just spent everything.
# An opinion is the whole text of a decision, and on a cache miss the proxy
# fetches it upstream and stores it before answering. At the default timeout
# 2 of 12 gave up; the document is usually reachable, just slow.
say "warming opinion documents with whatever allowance is left"
MELLEA_LRC_COURTLISTENER_TIMEOUT=120 \
uv run --env-file "$REPO/.env" python -m evaluations.lephantomcite.warm_opinions \
  --dataset "$DATASET" >> "$LOG" 2>&1
say "opinion warming exited $?"
say "=== run finished ==="
exit 0
