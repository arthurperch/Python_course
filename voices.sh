#!/usr/bin/env bash
# tutor — add a natural (non-robotic) neural voice. Run once.
#   bash voices.sh           → natural female voice (default)
#   bash voices.sh ryan      → natural male voice
set -euo pipefail

VOICE="${1:-lessac}"   # lessac = female (default), ryan = male
QUALITY="high"
case "$VOICE" in
    lessac|ryan) ;;
    *) echo "usage: bash voices.sh [lessac|ryan]" >&2; exit 1 ;;
esac

NAME="en_US-${VOICE}-${QUALITY}"
HF="https://huggingface.co/rhasspy/piper-voices/resolve/main/en/en_US/${VOICE}/${QUALITY}"
V_DIR="$HOME/.local/share/piper"

# 1) uv — isolated tool installer (avoids pip --user / PEP 668 breakage)
if ! command -v uv >/dev/null 2>&1; then
    echo "→ installing uv…"
    curl -LsSf https://astral.sh/uv/install.sh | sh
    export PATH="$HOME/.local/bin:$PATH"
    command -v uv >/dev/null 2>&1 || { echo "✗ uv install failed" >&2; exit 1; }
fi

# 2) piper engine — the `piper` binary + the fast in-memory daemon env
echo "→ installing piper-tts…"
uv tool install piper-tts

# 3) the voice model (~60 MB)
echo "→ downloading the ${NAME} voice…"
mkdir -p "$V_DIR"
curl -fL --retry 3 -o "$V_DIR/${NAME}.onnx" "$HF/${NAME}.onnx"
curl -fL --retry 3 -o "$V_DIR/${NAME}.onnx.json" "$HF/${NAME}.onnx.json"

echo
echo "✅ Done. Restart tutor — it will use the natural voice automatically (F6 toggles)."
echo "   Want the other voice? Run:  bash voices.sh $([ "$VOICE" = lessac ] && echo ryan || echo lessac)"
