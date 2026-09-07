# tutor — learn Python by building, in a real editor

A hands-on Python course that runs in your terminal. **No AI, no account, no
network** — you learn by *writing real code* in a Neovim-style editor, with a
local TTS voice coaching you through every step.

- 🧑‍🏫 guided, hold-your-hand workflow — a bar always tells you the next step
- ⌨️ a real modal (vim-style) editor to type and edit your code
- 🗣️ everything is read aloud by a **local** voice (Piper or espeak-ng)
- 🧱 drills, worked examples, a VIM dojo, and an animated "watch it run" tracer
- 💾 progress saved to `~/.learning/progress.json`

---

## Install (one line)

```bash
curl -fsSL https://raw.githubusercontent.com/arthurperch/Python_course/main/install.sh | bash
```

Then run it:

```bash
tutor
```

> If `tutor` isn't found, make sure `~/.local/bin` is on your `PATH`
> (`export PATH="$HOME/.local/bin:$PATH"`).

The installer downloads the app to `~/.local/share/tutor/`, creates a private
virtualenv, installs the two Python deps (`textual`, `rich`), and drops a
`tutor` launcher in `~/.local/bin/`.

### Alternative: pip

```bash
pip install "git+https://github.com/arthurperch/Python_course.git"
tutor
```

(or with `pipx install "git+https://github.com/arthurperch/Python_course.git"`)

---

## Voice (optional, but recommended)

`tutor` reads everything aloud with a **local** voice — it auto-detects what's
installed:

| Voice | Install | Notes |
|-------|---------|-------|
| **espeak-ng** | `sudo apt install espeak-ng` (Debian/Ubuntu) · `sudo pacman -S espeak-ng` (Arch) | easiest, robotic, works everywhere |
| **piper** | `pip install piper-tts` + a voice model | natural neural voice, nicer |

No voice? Everything still works, just silently. Toggle the voice with `F6`.

## Sound

Uses `aplay` + `paplay` (ALSA / PulseAudio — preinstalled on most desktops) for
key sounds and win/fail stings. For mechanical-keypress "thock" sounds, drop
your own samples in `~/.learning/keypress/keypress-*.wav`.

---

## The loop (what you do)

1. **Read** the challenge
2. Press **`i`** to start typing your answer
3. Press **`Esc`**, then **`:!python3 %`** (or `Ctrl+Enter`) to run + submit
4. **PASS** → next challenge · **FAIL** → fix it, run again

## Keys

```
NORMAL   h/j/k/l move · i/a/A/I/o/O insert · x del char · dd del line ·
         yy yank · p paste · u undo · 0/$ edges · gg/G top/bottom
INSERT   type normally · Esc = NORMAL · Ctrl+Enter = run
COURSE   Enter dive in · w watch lesson · l listen · e lesson ·
         F12 quick check · F2 cheat sheet · F7 review · F8 examples · m music
```

## Why "no AI"

Everything — the lessons, drills, explanations, and the voice — is pre-authored
and generated locally. There is no model call and no network access, so it works
fully offline and never phones home.

## License

MIT
