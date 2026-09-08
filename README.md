# tutor — learn Python by building, in a real editor

A hands-on Python course that runs in your terminal. **No AI, no account, no
network** — you learn by *writing real code* in a Neovim-style editor, with a
local TTS voice coaching you through every step.

- 🧑‍🏫 guided, hold-your-hand workflow — a bar always tells you the next step
- ⌨️ a real modal (vim-style) editor to type and edit your code
- 🗣️ everything is read aloud by a **local** voice (Piper or espeak-ng)
- 🧱 drills, worked examples, a VIM dojo, and an animated "watch it run" tracer
- 🛠️ **BUILD STUFF** — a real bash terminal + live folder tree: make folders and
  files, then run your own program (`pwd` → `mkdir` → `python3 hello.py`)
- ☁️ **CLOUD & DEVOPS** — go from noob to engineer in 8 modules / 71 lessons:
  version control with **git**, packaging with **docker**, **AWS S3 + EC2** (CLI
  *and* real **boto3** Python), infrastructure-as-code with **terraform**,
  server automation with **ansible** (idempotency + handlers), and a **CI/CD**
  pipeline that goes red/green — all in a simulated, offline cloud
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

## Update (bring everything up to date)

Re-run the same installer — it's idempotent and pulls the latest code **and**
the media pack (sounds, keypress samples, cat clip):

```bash
curl -fsSL https://raw.githubusercontent.com/arthurperch/Python_course/main/install.sh | bash
```

Your progress (XP, level, streak, volume) is untouched — it lives in
`~/.learning/progress.json`.

---

## Voice (optional, but recommended)

`tutor` reads everything aloud with a **local** voice — it auto-detects what's
installed:

| Voice | Install | Notes |
|-------|---------|-------|
| **espeak-ng** | `sudo apt install espeak-ng` (Debian/Ubuntu) · `sudo pacman -S espeak-ng` (Arch) | easiest, robotic, works everywhere |
| **piper** | `curl -fsSL https://raw.githubusercontent.com/arthurperch/Python_course/main/voices.sh \| bash` | natural neural voice, nicer (see below) |

No voice? Everything still works, just silently. Toggle the voice with `F6`.

## Sound

Uses `aplay` + `paplay` (ALSA / PulseAudio — preinstalled on most desktops) for
key sounds and win/fail stings. The installer also bundles the full media pack —
32 mechanical-keypress "thock" samples, the win/fail sting library, and the
tier-complete cat clip — into `~/.learning/`, so it's all there on day one.

Press **`F4`** (or click the **`(♪)` icon** in the top-right corner) to open the
volume bar at the bottom — two faders, one for the **voice** and one for **sound
effects** (keypresses, win/fail stings). Click an icon to mute that channel,
click a meter to jump to a level, or use `↑`/`↓` to switch rows and `←`/`→` to
nudge. It auto-closes after a few seconds, and both levels are remembered
between sessions.

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
         F12 quick check · F2 cheat sheet · F7 review · F8 examples ·
         F4 volume · F6 voice · m music
```

## Why "no AI"

Everything — the lessons, drills, explanations, and the voice — is pre-authored
and generated locally. There is no model call and no network access, so it works
fully offline and never phones home.

## License

MIT
