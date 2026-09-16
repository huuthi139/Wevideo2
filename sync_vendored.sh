#!/usr/bin/env bash
# sync_vendored.sh — đồng bộ CODE engine + skill vào repo để nút Update (app /api/update) kéo được.
# CHẠY TRƯỚC KHI COMMIT mỗi khi bạn sửa engine (flow-agent) hoặc skill (video-nguoi-que),
# nếu không Update sẽ ship bản engine/skill CŨ. config.env + venv là theo-máy (gitignore) → không đụng.
set -e
cd "$(dirname "$0")"
ENGINE_SRC="${WEVIDEO_ENGINE_SRC:-/Volumes/DATA/AI-APP/flow-agent}"
ENGINE_BRANCH="${WEVIDEO_ENGINE_BRANCH:-flow-v2-ui-transport}"
SKILL_SRC="${WEVIDEO_SKILL_SRC:-$HOME/.claude/skills/video-nguoi-que}"

# engine: CHỈ file đã COMMIT của branch (git archive → không lẫn venv/working-tree drift)
[ -d "$ENGINE_SRC/flow-agent" ] || { echo "✗ Không thấy engine tại $ENGINE_SRC"; exit 1; }
rm -rf engine && mkdir -p engine
git -C "$ENGINE_SRC" archive --format=tar "$ENGINE_BRANCH" -- flow-agent flow-chrome-extension | tar -x -C engine
echo "→ engine @ $(git -C "$ENGINE_SRC" rev-parse --short "$ENGINE_BRANCH") ($(du -sh engine | cut -f1))"

# skill: rsync code (bỏ venv-tts/output/pyc)
[ -d "$SKILL_SRC/scripts" ] || { echo "✗ Không thấy skill tại $SKILL_SRC"; exit 1; }
rsync -a --delete --exclude='.venv-tts/' --exclude='output/' --exclude='__pycache__/' \
      --exclude='*.pyc' --exclude='.DS_Store' "$SKILL_SRC/" skill/video-nguoi-que/
echo "→ skill: $(find skill/video-nguoi-que/scripts -name '*.py' | wc -l | tr -d ' ') script"
echo "✅ Vendored. Giờ:  git add -A && git commit -m '...' && git push   (Update sẽ kéo được bản mới)"
