#!/usr/bin/env bash
# tutor — one-line installer (offline Python course with a local TTS coach)
set -euo pipefail

BASE="https://raw.githubusercontent.com/arthurperch/Python_course/main"
DEST="$HOME/.local/share/tutor"

PY="${PYTHON:-python3}"
if ! command -v "$PY" >/dev/null 2>&1; then
    echo "✗ python3 is required. Install it first (e.g. sudo apt install python3)." >&2
    exit 1
fi

echo "→ fetching tutor…"
mkdir -p "$DEST" "$HOME/.local/bin" "$HOME/.learning"
curl -fsSL "$BASE/tutor.py" -o "$DEST/tutor.py"
# optional piper daemon (faster neural TTS if piper is installed)
curl -fsSL "$BASE/assets/piper_daemon.py" -o "$HOME/.learning/piper_daemon.py" 2>/dev/null || true

# bundled media: keypress "thock" samples, win/fail stings, and the cat clip
echo "→ fetching sounds, keypress samples, and the cat clip…"
if curl -fsSL "$BASE/assets/media.tar.gz" -o "$HOME/.learning/media.tar.gz"; then
    tar -xzf "$HOME/.learning/media.tar.gz" -C "$HOME/.learning"
    rm -f "$HOME/.learning/media.tar.gz"
else
    echo "⚠  media download failed — tutor still works (synthesized fallback sounds)." >&2
fi

echo "→ creating a private virtualenv + installing deps (textual, rich)…"
if [ ! -x "$DEST/venv/bin/python" ]; then
    "$PY" -m venv "$DEST/venv"
fi
"$DEST/venv/bin/pip" install --quiet --upgrade pip
"$DEST/venv/bin/pip" install --quiet "textual>=8.0" "rich>=13.0"

echo "→ installing the tutor command…"
cat > "$HOME/.local/bin/tutor" <<EOF
#!/usr/bin/env bash
exec "$DEST/venv/bin/python" "$DEST/tutor.py" "\$@"
EOF
chmod +x "$HOME/.local/bin/tutor"

case ":$PATH:" in
    *":$HOME/.local/bin:"*) ;;
    *) echo "⚠  add $HOME/.local/bin to your PATH:  export PATH=\"\$HOME/.local/bin:\$PATH\"" >&2 ;;
esac

echo
echo "✅ Done. Run it with:  tutor"
echo
echo "   Voice (optional but recommended):"
echo "     espeak-ng  →  sudo apt install espeak-ng      (Debian/Ubuntu)"
echo "                    sudo pacman -S espeak-ng       (Arch)"
echo "     natural    →  curl -fsSL $BASE/voices.sh | bash   (neural voice, ~60 MB)"
