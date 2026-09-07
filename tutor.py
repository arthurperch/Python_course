#!/usr/bin/env python3
"""
tutor — hands-on Python learning with a REAL nvim-style modal editor and a
guided, hold-your-hand workflow.

GUIDED FLOW (the key part):
  A big guide bar at the bottom always tells you the NEXT step:
    "read the challenge" -> "press i to type" -> ":!python3 % to run" ->
    "PASSED — press Enter for next" / "NOT APPROVED — fix it and run again".
  You are never left guessing what to do.

First launch shows a welcome that walks you through the loop, then every
lesson auto-guides you through it.

Keys:
  NORMAL:  h/j/k/l move · i/a/A/I/o/O insert · x del char · dd del line ·
           yy yank · p paste · u undo · 0/$ edges · gg/G top/bottom
  LESSON:  r run+check · w watch lesson · n/N next/prev · c cheat ·
           v voice · q quit
  INSERT:  type normally · Esc = NORMAL · Ctrl+Enter = run

Progress (XP, level, streak) saved to ~/.learning/progress.json.
Voice: espeak-ng or piper-tts (auto-detected). No AI — fully offline.
"""

from __future__ import annotations

import ast
import json
import math
import re
import random
import shutil
import struct
import subprocess
import tempfile
import threading
import wave
from pathlib import Path

from rich.text import Text
from textual import events
from textual.app import App, ComposeResult
from textual.binding import Binding
from textual.containers import Horizontal, Vertical, VerticalScroll
from textual.message import Message
from textual.widgets import Checkbox, Header, Input, Markdown, Static

WELCOME = """## Welcome to tutor

You're going to learn Python by **writing** it — in a real nvim-style editor.

**The loop, every time:**

1. **Read** the challenge (this pane)
2. **Press `i`** to start typing your answer (right pane)
3. **Press `Esc`**, then **`:!python3 %`** (or `:submit`, or Ctrl+Enter) to run + submit it
4. **PASS** → next challenge · **FAIL** → fix it, run again

That's it. The guide bar below tells you the next step, always.

Press `i` or `Enter` to begin.
"""

# Your Neovim dashboard art — milli "fire" splash, frame 1 (static).
# Animated pixel cat banner (blinks + winks). Replaced the old fire ASCII.
# Rows use: / \ _ ( ) • ‿ > < █ — the eyes row changes per frame.
CAT_FRAMES = [
    ["   /\\___/\\    ",
     "  (  •   •  ) ",
     "   >   ‿  <   ",
     "    ██████    ",
     "   ████████   "],
    ["   /\\___/\\    ",
     "  (  —   —  ) ",
     "   >   ‿  <   ",
     "    ██████    ",
     "   ████████   "],
    ["   /\\___/\\    ",
     "  (  •   •  ) ",
     "   >   ‿  <   ",
     "    ██████    ",
     "   ████████   "],
    ["   /\\___/\\    ",
     "  (  •   —  ) ",
     "   >   ‿  <   ",
     "    ██████    ",
     "   ████████   "],
]
CAT_STYLE = "bold #ff9d00"

# Challenges are grouped by difficulty. Each challenge:
#   expect = substrings that must appear in the (lowercased) OUTPUT
#   need   = substrings that must appear in the CODE (a technique to use)
#   stdin  = text fed to input() during the run/check
# Both expect and need are lenient — any way that produces the right output
# and uses the named technique passes. The rules bend, but not fully.
GROUPS = [
    {
        "id": "basic",
        "name": "BASIC PYTHON",
        "challenges": [
            {"title": "say hello", "topic": "print",
             "prompt": "Print exactly `hello world` to the screen.",
             "starter": "", "expect": ["hello world"], "need": [], "stdin": "",
             "example": "Like this, different words:\n```python\nprint(\"goodbye world\")\n```\n> print() shows text. Quotes make a string."},
            {"title": "print a number", "topic": "print",
             "prompt": "Print the number `42` to the screen — no quotes, just the number.",
             "starter": "", "expect": ["42"], "need": [], "stdin": "",
             "example": "Same idea, a different number:\n```python\nprint(7)\n```\n> numbers go in print() WITHOUT quotes — quotes make it a word, not a number."},
            {"title": "print two things", "topic": "print",
             "prompt": "Use ONE `print()` with a comma to show both `hello` and `world` on one line.",
             "starter": "", "expect": ["hello", "world"], "need": ["print"], "stdin": "",
             "example": "Same comma trick, different words:\n```python\nprint(\"good\", \"morning\")\n```\n> a comma inside print() shows two things on one line, with a space between."},
            {"title": "your name", "topic": "name",
             "prompt": "Make a variable called `name` with your name in it, then print it.",
             "starter": "", "expect": [], "need": ["name", "print"], "stdin": "",
             "example": "Same idea, different variable:\n```python\ncity = \"Portland\"\nprint(city)\n```\n> x = y stores y in x. print(x) shows it."},
            {"title": "change a variable", "topic": "name",
             "prompt": "Store `7` in a variable `x`, then change `x` to `9` and print it.",
             "starter": "", "expect": ["9"], "need": ["x", "print"], "stdin": "",
             "example": "Same idea, different values:\n```python\nn = 1\nn = 2\nprint(n)\n```\n> the LAST store wins — print(x) shows the newest value, not the old one."},
            {"title": "basic math", "topic": "math",
             "prompt": "Print the result of `2 + 2`.",
             "starter": "", "expect": ["4"], "need": [], "stdin": "",
             "example": "Same idea, different sum:\n```python\nprint(1 + 5)\n```\n> print() can show numbers and the result of math."},
            {"title": "ask and answer", "topic": "input",
             "prompt": "Use `input()` to ask the user their age. Print how old they will be in 10 years.",
             "starter": "", "expect": ["35"], "need": ["input"], "stdin": "25\n",
             "example": "Similar, asks a different thing:\n```python\nyears = input(\"How many years? \")\nyears = int(years)\nprint(years * 365, \"days\")\n```\n> input() waits for typed text. int() turns text into a number."},
            {"title": "fancy strings", "topic": "fstrings",
             "prompt": "Using the `name` variable already given, print `Hello, Bean!` with an f-string.",
             "starter": "name = \"Bean\"\n", "expect": ["hello, bean"], "need": [], "stdin": "",
             "example": "Same f-string, different greeting:\n```python\ncity = \"Portland\"\nprint(f\"Welcome to {city}!\")\n```\n> f\"...\" fills {variable} into the string."},
            {"title": "f-string math", "topic": "fstrings",
             "prompt": "Use an f-string to print `3 + 4 = 7`, where the 3 and 4 come from variables.",
             "starter": "a = 3\nb = 4\n", "expect": ["3 + 4 = 7"], "need": ["f"], "stdin": "",
             "example": "Same f-string math, different numbers:\n```python\nx = 5\ny = 2\nprint(f\"{x} * {y} = {x * y}\")\n```\n> an f-string can do the math inside the { } before it prints."},
            {"title": "even or odd", "topic": "conditionals",
             "prompt": "Check if the number is even or odd and print the result. Use `%` and `if`/`else`.",
             "starter": "n = 7\n", "expect": ["odd"], "need": ["%", "if"], "stdin": "",
             "example": "Same check, different number:\n```python\nn = 4\nif n % 2 == 0:\n    print(\"even\")\nelse:\n    print(\"odd\")\n```\n> n % 2 is 0 when even. % gives the remainder."},
            {"title": "count to ten", "topic": "loops",
             "prompt": "Use a `for` loop to print the numbers 1 through 10.",
             "starter": "", "expect": ["1", "10"], "need": ["for", "range"], "stdin": "",
             "example": "Same loop, counting by twos:\n```python\nfor i in range(2, 12, 2):\n    print(i)\n```\n> for i in range(...) repeats. range(1, 11) is 1..10."},
            {"title": "count zero to four", "topic": "loops",
             "prompt": "Use a `for` loop with `range(5)` to print the numbers 0 through 4.",
             "starter": "", "expect": ["0", "1", "2", "3", "4"], "need": ["for", "range"], "stdin": "",
             "example": "Same loop, a bigger range:\n```python\nfor i in range(4):\n    print(i)\n```\n> range(5) starts at 0 and stops before 5 — so 0, 1, 2, 3, 4."},
            {"title": "countdown", "topic": "while",
             "prompt": "Use a `while` loop to print the numbers 5 down to 1.",
             "starter": "n = 5\n", "expect": ["5", "4", "3", "2", "1"], "need": ["while"], "stdin": "",
             "example": "A while loop counting DOWN from 3:\n```python\nn = 3\nwhile n >= 1:\n    print(n)\n    n -= 1\n```\n> while keeps going until the condition is false. n -= 1 counts down."},
            {"title": "while count up", "topic": "while",
             "prompt": "Use a `while` loop to print the numbers 1 up to 4.",
             "starter": "n = 1\n", "expect": ["1", "2", "3", "4"], "need": ["while"], "stdin": "",
             "example": "Same while loop, counting up to 3:\n```python\nn = 1\nwhile n <= 3:\n    print(n)\n    n += 1\n```\n> n += 1 adds one each lap, so the loop eventually stops instead of running forever."},
            {"title": "fruit basket", "topic": "lists",
             "prompt": "Append `\"cherry\"` to the list, then print the whole list.",
             "starter": "fruits = [\"apple\", \"banana\"]\n", "expect": ["cherry"], "need": ["append"], "stdin": "",
             "example": "Same pattern, numbers instead:\n```python\nnums = [1, 2, 3]\nnums.append(4)\nprint(nums)\n```\n> .append(x) adds x to the end of a list."},
            {"title": "list index", "topic": "lists",
             "prompt": "Print the FIRST fruit using its index.",
             "starter": "fruits = [\"apple\", \"banana\", \"cherry\"]\n", "expect": ["apple"], "need": [], "stdin": "",
             "example": "Print the second item:\n```python\nprint(fruits[1])\n```\n> lists start at 0, so [0] is the first item."},
            {"title": "people and ages", "topic": "dicts",
             "prompt": "Print Bob's age from the dictionary.",
             "starter": "people = {\"alice\": 30, \"bob\": 25}\n", "expect": ["25"], "need": [], "stdin": "",
             "example": "Read a different key:\n```python\nprint(people[\"alice\"])\n```\n> d[\"key\"] reads a value from a dictionary."},
            {"title": "second key", "topic": "dicts",
             "prompt": "Print Alice's age from the dictionary.",
             "starter": "people = {\"alice\": 30, \"bob\": 25}\n", "expect": ["30"], "need": [], "stdin": "",
             "example": "Read a different key:\n```python\nprint(people[\"bob\"])\n```\n> d[\"key\"] reaches in and grabs that value by name."},
            {"title": "your first function", "topic": "functions",
             "prompt": "Finish `add(a, b)` so it returns the sum, and call it with 3 and 4.",
             "starter": "def add(a, b):\n    pass\n\nprint(add(3, 4))",
             "expect": ["7"], "need": ["def", "return"], "stdin": "",
             "example": "Same idea, subtracts instead:\n```python\ndef minus(a, b):\n    return a - b\n\nprint(minus(9, 4))\n```\n> def makes a reusable block. return hands a value back."},
            {"title": "double it with a function", "topic": "functions",
             "prompt": "Write a function `double(n)` that returns `n * 2`, then print `double(7)`.",
             "starter": "def double(n):\n    pass\n\nprint(double(7))",
             "expect": ["14"], "need": ["def", "return"], "stdin": "",
             "example": "Same idea, triples instead:\n```python\ndef triple(n):\n    return n * 3\n\nprint(triple(3))\n```\n> return hands the answer back, so print() can show it."},
            {"title": "first letter", "topic": "strings",
             "prompt": "Print the FIRST letter of `s` using its index.",
             "starter": "s = \"hello\"\n", "expect": ["h"], "need": ["[0]"], "stdin": "",
             "example": "The second letter:\n```python\nprint(s[1])\n```\n> s[0] is the first character, s[1] the second."},
            {"title": "string length", "topic": "strings",
             "prompt": "Print how many letters are in `s` using `len()`.",
             "starter": "s = \"hello\"\n", "expect": ["5"], "need": ["len"], "stdin": "",
             "example": "Length of a list:\n```python\nprint(len([1, 2, 3]))\n```\n> len() counts the items in a string or list."},
            {"title": "last letter", "topic": "strings",
             "prompt": "Print the LAST letter of `s` using a negative index.",
             "starter": "s = \"hello\"\n", "expect": ["o"], "need": ["[-1]"], "stdin": "",
             "example": "The second-to-last letter:\n```python\nprint(s[-2])\n```\n> [-1] means 'the last one' — negative indexes count from the end."},
            {"title": "which is bigger", "topic": "conditionals",
             "prompt": "Print the bigger of the two numbers using `if`/`else`.",
             "starter": "a = 7\nb = 10\n", "expect": ["10"], "need": ["if"], "stdin": "",
             "example": "Same, different numbers:\n```python\na = 5\nb = 3\nif a > b:\n    print(a)\nelse:\n    print(b)\n```\n> compare with > and < inside an if. This prints the bigger one."},
            {"title": "grade it", "topic": "conditionals",
             "prompt": "Using `if`/`elif`/`else`, print `A` if score >= 90, `B` if >= 80, else `C`.",
             "starter": "score = 85\n", "expect": ["b"], "need": ["elif"], "stdin": "",
             "example": "Same elif chain, different cutoffs:\n```python\nscore = 72\nif score >= 90:\n    print(\"A\")\nelif score >= 80:\n    print(\"B\")\nelse:\n    print(\"C\")\n```\n> elif chains a second condition after the first if."},
            {"title": "positive or negative", "topic": "conditionals",
             "prompt": "Using `if`/`else`, print `positive` if the number is above 0, else `negative`.",
             "starter": "n = -3\n", "expect": ["negative"], "need": ["if", "else"], "stdin": "",
             "example": "Same check, a positive number:\n```python\nn = 5\nif n > 0:\n    print(\"positive\")\nelse:\n    print(\"negative\")\n```\n> if asks a yes/no question; else is the fallback path."},
            {"title": "stop at three", "topic": "loops",
             "prompt": "Loop upward printing each number, but `break` when you reach 3.",
             "starter": "", "expect": ["1", "2", "3"], "need": ["break"], "stdin": "",
             "example": "Same break, at a different number:\n```python\nfor i in range(1, 6):\n    if i == 4:\n        break\n    print(i)\n```\n> break exits a loop early."},
            {"title": "drop it", "topic": "lists",
             "prompt": "Remove `\"apple\"` from the list using a list method, then print it.",
             "starter": "fruits = [\"apple\", \"banana\", \"cherry\"]\n", "expect": ["banana", "cherry"], "need": ["remove"], "stdin": "",
             "example": "Same .remove(), different fruit:\n```python\nfruits = [\"apple\", \"banana\", \"cherry\"]\nfruits.remove(\"banana\")\nprint(fruits)\n```\n> .remove(x) deletes a specific item."},
            {"title": "double it", "topic": "input",
             "prompt": "Ask the user for a number with `input()`, turn it into an int, and print it doubled.",
             "starter": "", "expect": ["50"], "need": ["input", "int"], "stdin": "25\n",
             "example": "Same idea, add one instead:\n```python\nn = int(input(\"Number? \"))\nprint(n + 1)\n```\n> int(input()) turns typed text into a number you can do math on."},
            {"title": "say my name", "topic": "fstrings",
             "prompt": "Ask for a name with `input()`, then print `Hi, <name>!` using an f-string.",
             "starter": "", "expect": ["hi, bean"], "need": ["input"], "stdin": "Bean\n",
             "example": "Same greeting, different word:\n```python\ncity = input(\"City? \")\nprint(f\"Welcome to {city}!\")\n```\n> an f-string drops a variable into text with {braces}."},
            {"title": "three cheers", "topic": "loops",
             "prompt": "Use a `for` loop to print `hi` exactly 3 times.",
             "starter": "", "expect": ["hi"], "need": ["for"], "stdin": "",
             "example": "Same loop, five times:\n```python\nfor i in range(5):\n    print(\"yo\")\n```\n> range(3) runs the block 3 times."},
            {"title": "sum the fruits", "topic": "lists",
             "prompt": "Print how many fruits are in the list using `len()`.",
             "starter": "fruits = [\"apple\", \"banana\", \"cherry\"]\n", "expect": ["3"], "need": ["len"], "stdin": "",
             "example": "Length of a shorter list:\n```python\nprint(len([1, 2]))\n```\n> len() counts the items in a list."},
            {"title": "how many numbers", "topic": "lists",
             "prompt": "Print how many numbers are in the list using `len()`.",
             "starter": "nums = [10, 20, 30, 40]\n", "expect": ["4"], "need": ["len"], "stdin": "",
             "example": "Length of a shorter list:\n```python\nprint(len([1, 2, 3]))\n```\n> len() counts every item in the list."},
            {"title": "fancy math", "topic": "math",
             "prompt": "Print the result of `(2 + 3) * 4`.",
             "starter": "", "expect": ["20"], "need": [], "stdin": "",
             "example": "A different parenthesized sum:\n```python\nprint((1 + 2) * 10)\n```\n> ( ) forces the addition to happen first."},
            {"title": "power up", "topic": "math",
             "prompt": "Print `2` to the power of `3` using the `**` operator.",
             "starter": "", "expect": ["8"], "need": ["**"], "stdin": "",
             "example": "Same idea, different power:\n```python\nprint(3 ** 2)\n```\n> ** means \"to the power of\". 3 ** 2 is 9."},
            {"title": "remainder", "topic": "math",
             "prompt": "Print the remainder when `17` is divided by `5`, using `%`.",
             "starter": "", "expect": ["2"], "need": ["%"], "stdin": "",
             "example": "A different remainder:\n```python\nprint(10 % 3)\n```\n> % gives the leftover after division. 10 % 3 is 1."},
            {"title": "full name", "topic": "name",
             "prompt": "Print `first` and `last` with a space in between.",
             "starter": "first = \"ada\"\nlast = \"lovelace\"\n", "expect": ["ada lovelace"], "need": ["print"], "stdin": "",
             "example": "Same join, different names:\n```python\nfirst = \"Alan\"\nlast = \"Turing\"\nprint(first, last)\n```\n> print(a, b) puts a space between the two."},
        ],
    },
    {
        "id": "visual",
        "name": "VISUAL PYTHON",
        "challenges": [
            {"title": "count to six", "topic": "loops",
             "prompt": "Use a `for` loop to print 1 through 6. Watch the boxes light up as it runs.",
             "starter": "", "expect": ["1", "2", "3", "4", "5", "6"], "need": ["for", "range"], "stdin": "",
             "visual": {"kind": "counter", "n": 6},
             "example": "Same loop, counting by twos:\n```python\nfor i in range(2, 12, 2):\n    print(i)\n```\n> each print() lights the next box in order."},
            {"title": "countdown lights", "topic": "while",
             "prompt": "Use a `while` loop to print 5 down to 1. Watch the bar fill.",
             "starter": "n = 5\n", "expect": ["5", "4", "3", "2", "1"], "need": ["while"], "stdin": "",
             "visual": {"kind": "progress", "n": 5},
             "example": "A while loop counting up:\n```python\nn = 1\nwhile n <= 5:\n    print(n)\n    n += 1\n```\n> while keeps going until the check is false."},
            {"title": "even lights", "topic": "loops",
             "prompt": "Use a loop to print the even numbers 2 through 10.",
             "starter": "", "expect": ["2", "4", "6", "8", "10"], "need": ["for"], "stdin": "",
             "visual": {"kind": "progress", "n": 5},
             "example": "Odd numbers instead:\n```python\nfor i in range(1, 10, 2):\n    print(i)\n```\n> range(start, stop, step) skips by the step."},
            {"title": "star staircase", "topic": "loops",
             "prompt": "Print a growing staircase: 1 star, then 2, up to 5 stars.",
             "starter": "", "expect": ["*", "**", "***", "****", "*****"], "need": ["for"], "stdin": "",
             "visual": {"kind": "progress", "n": 5},
             "example": "A shrinking staircase:\n```python\nfor i in range(5, 0, -1):\n    print(\"*\" * i)\n```\n> \"*\" * i repeats the star i times."},
            {"title": "running total", "topic": "loops",
             "prompt": "Use a loop to print a running sum: 1, 3, 6, 10, 15.",
             "starter": "total = 0\n", "expect": ["1", "3", "6", "10", "15"], "need": ["for"], "stdin": "",
             "visual": {"kind": "progress", "n": 5},
             "example": "A running product:\n```python\ntotal = 1\nfor i in range(1, 6):\n    total *= i\n    print(total)\n```\n> total += i keeps adding i into the running total."},
            {"title": "cheer three times", "topic": "loops",
             "prompt": "Use a `for` loop to print `hip` exactly 3 times.",
             "starter": "", "expect": ["hip"], "need": ["for"], "stdin": "",
             "visual": {"kind": "progress", "n": 3},
             "example": "Five cheers instead:\n```python\nfor i in range(5):\n    print(\"hip\")\n```\n> range(3) runs the block 3 times."},
        ],
    },
    {
        "id": "intermediate",
        "name": "INTERMEDIATE PYTHON",
        "challenges": [
            {"title": "shout it", "topic": "strings",
             "prompt": "Print `s` in ALL CAPS using a string method.",
             "starter": "s = \"hello world\"\n", "expect": ["hello world"], "need": [".upper()"], "stdin": "",
             "example": "Same .upper(), different word:\n```python\ns = \"quiet\"\nprint(s.upper())\n```\n> .upper() makes every letter a capital."},
            {"title": "reverse it", "topic": "slicing",
             "prompt": "Print `s` backwards using a slice.",
             "starter": "s = \"hello world\"\n", "expect": ["dlrow olleh"], "need": ["[:"], "stdin": "",
             "example": "Same reverse, different word:\n```python\ns = \"abc\"\nprint(s[::-1])\n```\n> s[::-1] steps through a string backwards."},
            {"title": "squares", "topic": "comprehension",
             "prompt": "Use a list comprehension to print the squares of 1 through 5.",
             "starter": "", "expect": ["1", "4", "9", "16", "25"], "need": ["for"], "stdin": "",
             "example": "Cubes instead of squares:\n```python\nprint([i**3 for i in range(1, 6)])\n```\n> [expr for x in ...] builds a list in one line."},
            {"title": "dict loop", "topic": "dicts",
             "prompt": "Loop through the dictionary printing each `name is age`.",
             "starter": "people = {\"alice\": 30, \"bob\": 25}\n",
             "expect": ["alice", "30", "bob", "25"], "need": ["for"], "stdin": "",
             "example": "Same items() loop, different dict:\n```python\nscores = {\"alice\": 90, \"bob\": 85}\nfor k, v in scores.items():\n    print(k, \"is\", v)\n```\n> for k, v in d.items() gives both key and value."},
            {"title": "sum a list", "topic": "lists",
             "prompt": "Print the total of the numbers using `sum()`.",
             "starter": "nums = [1, 2, 3, 4]\n", "expect": ["10"], "need": ["sum"], "stdin": "",
             "example": "Sum a different list:\n```python\nprint(sum([10, 20, 30]))\n```\n> sum() adds every number in a list into one total."},
            {"title": "sort it", "topic": "sorting",
             "prompt": "Sort the list and print it.",
             "starter": "nums = [3, 1, 2]\n", "expect": ["1", "2", "3"], "need": ["sort"], "stdin": "",
             "example": "Sort backwards:\n```python\nnums.sort(reverse=True)\nprint(nums)\n```\n> .sort() reorders a list in place, smallest first."},
            {"title": "greet default", "topic": "functions",
             "prompt": "Write `greet(name=\"Bean\")` that prints `Hello, <name>!`, and call it with NO argument.",
             "starter": "", "expect": ["bean"], "need": ["def"], "stdin": "",
             "example": "A default number:\n```python\ndef double(n=2):\n    print(n * 2)\n\ndouble()\n```\n> a default lets you call the function without that argument."},
            {"title": "safe divide", "topic": "try",
             "prompt": "Use try/except so dividing by zero prints `error` instead of crashing.",
             "starter": "", "expect": ["error"], "need": ["try", "except"], "stdin": "",
             "example": "Catch a different mistake:\n```python\ntry:\n    int(\"hello\")\nexcept ValueError:\n    print(\"error\")\n```\n> try runs risky code; except catches the error."},
            {"title": "times table", "topic": "loops",
             "prompt": "Use nested loops to print the products of 1..3 times 1..3 (so `9` appears).",
             "starter": "", "expect": ["9"], "need": ["for"], "stdin": "",
             "example": "A smaller grid (1..2):\n```python\nfor i in range(1, 3):\n    for j in range(1, 3):\n        print(i * j)\n```\n> a loop inside a loop = a grid of results."},
            {"title": "join words", "topic": "strings",
             "prompt": "Join the words into one string with a space between them using `.join()`.",
             "starter": "words = [\"i\", \"love\", \"python\"]\n", "expect": ["i love python"], "need": ["join"], "stdin": "",
             "example": "Join with a comma instead:\n```python\nprint(\",\".join([\"a\", \"b\", \"c\"]))\n```\n> \"x\".join(list) glues the items together with x in between."},
            {"title": "split it", "topic": "strings",
             "prompt": "Split `s` into a list of words on the space, then print that list.",
             "starter": "s = \"hello world\"\n", "expect": ["hello", "world"], "need": ["split"], "stdin": "",
             "example": "Split on a comma:\n```python\nprint(\"a,b,c\".split(\",\"))\n```\n> .split() cuts a string into a list of pieces."},
            {"title": "is it there", "topic": "lists",
             "prompt": "Print `yes` if `\"apple\"` is in the list, else `no`, using `in`.",
             "starter": "fruits = [\"apple\", \"banana\"]\n", "expect": ["yes"], "need": ["in"], "stdin": "",
             "example": "Check for a missing item:\n```python\nprint(\"kiwi\" in fruits)\n```\n> `x in list` returns True if x is a member."},
            {"title": "count with index", "topic": "loops",
             "prompt": "Use `enumerate()` to print each fruit with its position.",
             "starter": "fruits = [\"apple\", \"banana\"]\n", "expect": ["0", "apple", "1", "banana"], "need": ["enumerate"], "stdin": "",
             "example": "Just the index numbers:\n```python\nfor i, f in enumerate(fruits):\n    print(i)\n```\n> enumerate() gives you the index and the item together."},
            {"title": "no duplicates", "topic": "sets",
             "prompt": "Turn the list into a `set` and print it (duplicates vanish).",
             "starter": "nums = [1, 2, 2, 3]\n", "expect": ["1", "2", "3"], "need": ["set"], "stdin": "",
             "example": "A set of letters:\n```python\nprint(set(\"hello\"))\n```\n> a set keeps only unique values."},
            {"title": "fixed pair", "topic": "tuples",
             "prompt": "Make a tuple `pair = (1, 2)` and print the second value with `pair[1]`.",
             "starter": "", "expect": ["2"], "need": ["[1]"], "stdin": "",
             "example": "A tuple of colors:\n```python\ncolors = (\"red\", \"blue\")\nprint(colors[0])\n```\n> a tuple is a fixed list, made with ( )."},
            {"title": "many args", "topic": "functions",
             "prompt": "Write `total(*nums)` that returns the sum of any number of arguments, then print `total(1, 2, 3)`.",
             "starter": "", "expect": ["6"], "need": ["*"], "stdin": "",
             "example": "Same *args, different numbers:\n```python\ndef total(*nums):\n    return sum(nums)\n\nprint(total(4, 5, 6))\n```\n> *nums packs any number of arguments into a tuple."},
            {"title": "even list", "topic": "comprehension",
             "prompt": "Use a list comprehension to print the even numbers 0, 2, 4, 6, 8.",
             "starter": "", "expect": ["0", "2", "4", "6", "8"], "need": ["for"], "stdin": "",
             "example": "Odd numbers the same way:\n```python\nprint([i for i in range(1, 10, 2)])\n```\n> [expr for x in ...] builds the list in one line."},
            {"title": "word count", "topic": "lists",
             "prompt": "Count how many times `hi` appears in the list using a list method.",
             "starter": "words = [\"hi\", \"yo\", \"hi\", \"hi\"]\n", "expect": ["3"], "need": ["count"], "stdin": "",
             "example": "Count a different list:\n```python\nnums = [1, 1, 2]\nprint(nums.count(1))\n```\n> .count(x) tells you how many of x are in the list."},
            {"title": "largest number", "topic": "lists",
             "prompt": "Print the biggest number in the list using `max()`.",
             "starter": "nums = [3, 9, 2, 7]\n", "expect": ["9"], "need": ["max"], "stdin": "",
             "example": "The biggest of a different list:\n```python\nprint(max([1, 5, 3]))\n```\n> max() finds the biggest item; min() finds the smallest."},
            {"title": "biggest of three", "topic": "conditionals",
             "prompt": "Print the biggest of three numbers using `if`/`elif`/`else`.",
             "starter": "a, b, c = 3, 7, 5\n", "expect": ["7"], "need": ["if"], "stdin": "",
             "example": "Same logic, two numbers:\n```python\nx, y = 9, 4\nif x > y:\n    print(x)\nelse:\n    print(y)\n```\n> compare with > to find the bigger one."},
            {"title": "title case", "topic": "strings",
             "prompt": "Print `s` with the first letter of each word capitalized using a string method.",
             "starter": "s = \"hello world\"\n", "expect": ["hello world"], "need": [".title()"], "stdin": "",
             "example": "Lowercase everything instead:\n```python\nprint(\"HELLO\".lower())\n```\n> .title() capitalizes each word's first letter."},
            {"title": "safe input", "topic": "try",
             "prompt": "Use try/except so a non-number typed into `int(input())` prints `bad` instead of crashing.",
             "starter": "", "expect": ["bad"], "need": ["try", "input"], "stdin": "abc\n",
             "example": "Catch a divide by zero:\n```python\ntry:\n    print(1 / 0)\nexcept ZeroDivisionError:\n    print(\"bad\")\n```\n> try runs risky code; except catches the crash."},
            {"title": "count the e's", "topic": "strings",
             "prompt": "Print how many times the letter `e` appears in `s` using `.count()`.",
             "starter": "s = \"hello there\"\n", "expect": ["3"], "need": ["count"], "stdin": "",
             "example": "Count a different letter:\n```python\nprint(\"banana\".count(\"a\"))\n```\n> .count(x) tells you how many of x are inside."},
            {"title": "first three", "topic": "slicing",
             "prompt": "Print the first 3 letters of `s` using a slice.",
             "starter": "s = \"python\"\n", "expect": ["pyt"], "need": ["[:"], "stdin": "",
             "example": "First 2 letters instead:\n```python\nprint(\"hello\"[:2])\n```\n> s[:3] takes the first three characters."},
            {"title": "triple list", "topic": "comprehension",
             "prompt": "Use a list comprehension to print `[3, 6, 9, 12, 15]`.",
             "starter": "", "expect": ["3", "6", "9", "12", "15"], "need": ["for"], "stdin": "",
             "example": "Double each item instead:\n```python\nprint([i * 2 for i in range(1, 6)])\n```\n> [expr for x in ...] builds the list in one line."},
        ],
    },
    {
        "id": "advanced",
        "name": "ADVANCED PYTHON",
        "challenges": [
            {"title": "make a class", "topic": "class",
             "prompt": "Write a class `Dog` with a method `bark` that prints `woof`. Make one and call bark().",
             "starter": "", "expect": ["woof"], "need": ["class"], "stdin": "",
             "example": "A class with a different method:\n```python\nclass Cat:\n    def meow(self):\n        print(\"meow\")\n\nCat().meow()\n```\n> class bundles data + methods. self is the object itself."},
            {"title": "factorial", "topic": "recursion",
             "prompt": "Write a recursive `fact(n)` and print `fact(5)` (should be 120).",
             "starter": "", "expect": ["120"], "need": ["def"], "stdin": "",
             "example": "Recursion that counts down:\n```python\ndef count(n):\n    if n == 0:\n        return\n    print(n)\n    count(n - 1)\n```\n> recursion = a function that calls itself."},
            {"title": "lambda square", "topic": "lambda",
             "prompt": "Use a `lambda` to square 3 and print the result.",
             "starter": "", "expect": ["9"], "need": ["lambda"], "stdin": "",
             "example": "A lambda that doubles:\n```python\ndouble = lambda x: x * 2\nprint(double(5))\n```\n> lambda is a tiny anonymous function."},
            {"title": "generator", "topic": "generator",
             "prompt": "Write a generator that `yield`s 1, 2, 3, and print each value.",
             "starter": "", "expect": ["1", "2", "3"], "need": ["yield"], "stdin": "",
             "example": "A generator that yields evens:\n```python\ndef evens():\n    yield 2\n    yield 4\n\nfor n in evens():\n    print(n)\n```\n> yield makes a function produce values one at a time."},
            {"title": "decorator", "topic": "decorator",
             "prompt": "Write a decorator that prints `before` and `after` around a function call.",
             "starter": "", "expect": ["before", "after"], "need": ["def"], "stdin": "",
             "example": "A decorator wrapper:\n```python\ndef wrap(fn):\n    def inner():\n        print(\"start\")\n        fn()\n        print(\"end\")\n    return inner\n```\n> a decorator wraps a function to add behavior around it."},
            {"title": "custom error", "topic": "error",
             "prompt": "Raise a `ValueError` with the message `nope`, catch it, and print the message.",
             "starter": "", "expect": ["nope"], "need": ["raise"], "stdin": "",
             "example": "Raise a different error:\n```python\ntry:\n    raise ValueError(\"bad\")\nexcept ValueError as e:\n    print(e)\n```\n> raise throws an error; except catches it."},
            {"title": "pet with a name", "topic": "class",
             "prompt": "Write a class `Dog` whose `__init__` stores a `name`. Make one named `Rex` and print its name.",
             "starter": "", "expect": ["rex"], "need": ["__init__"], "stdin": "",
             "example": "A class storing an age:\n```python\nclass Cat:\n    def __init__(self, age):\n        self.age = age\n\nprint(Cat(3).age)\n```\n> __init__ runs when you create the object; self holds its data."},
            {"title": "a louder dog", "topic": "class",
             "prompt": "Make a class `LoudDog` that inherits `Dog` and overrides `bark` to print `WOOF`. Call `LoudDog().bark()`.",
             "starter": "class Dog:\n    def bark(self):\n        print(\"woof\")\n",
             "expect": ["woof"], "need": ["LoudDog"], "stdin": "",
             "example": "Same override, on a Cat:\n```python\nclass Cat:\n    def speak(self):\n        print(\"meow\")\n\nclass LoudCat(Cat):\n    def speak(self):\n        print(\"MEOW\")\n\nLoudCat().speak()\n```\n> class Child(Parent) inherits; redefining a method overrides it."},
            {"title": "safe file", "topic": "file",
             "prompt": "Use `with open(...)` to write `hello` to a file, then read it back and print it.",
             "starter": "", "expect": ["hello"], "need": ["with", "open"], "stdin": "",
             "example": "Write then read a file:\n```python\nwith open(\"x.txt\", \"w\") as f:\n    f.write(\"hi\")\nwith open(\"x.txt\") as f:\n    print(f.read())\n```\n> with open() auto-closes the file for you."},
            {"title": "rows of data", "topic": "dicts",
             "prompt": "Print the age of the first person in the list of dictionaries.",
             "starter": "people = [{\"name\": \"alice\", \"age\": 30}, {\"name\": \"bob\", \"age\": 25}]\n",
             "expect": ["30"], "need": ["[0]"], "stdin": "",
             "example": "Read a nested value:\n```python\nprint(people[1][\"age\"])\n```\n> people[0] is a dict; [\"age\"] reads a key inside it."},
            {"title": "lazy sum", "topic": "generator",
             "prompt": "Use a generator expression to print the sum of squares 1..5 (should be 55).",
             "starter": "", "expect": ["55"], "need": ["for"], "stdin": "",
             "example": "A generator expression in sum():\n```python\nprint(sum(i for i in range(6)))\n```\n> sum(expr for x in ...) adds values without building a list."},
            {"title": "always runs", "topic": "try",
             "prompt": "Use `try`/`except`/`finally` so `done` always prints, even though an error happens in the middle.",
             "starter": "", "expect": ["done"], "need": ["finally"], "stdin": "",
             "example": "finally runs no matter what:\n```python\ntry:\n    raise ValueError(\"x\")\nexcept ValueError:\n    pass\nfinally:\n    print(\"cleanup\")\n```\n> finally always runs, error or not."},
            {"title": "static counter", "topic": "class",
             "prompt": "Make a class `Counter` with a `bump` method that prints `up`. Make one and call `bump()` twice.",
             "starter": "", "expect": ["up"], "need": ["class"], "stdin": "",
             "example": "A different class method:\n```python\nclass Greeter:\n    def hello(self):\n        print(\"hi\")\n\nGreeter().hello()\n```\n> a method is a function inside a class, called with the dot."},
            {"title": "fibonacci", "topic": "recursion",
             "prompt": "Write a recursive `fib(n)` and print `fib(6)` (should be 8).",
             "starter": "", "expect": ["8"], "need": ["def"], "stdin": "",
             "example": "Recursive sum instead:\n```python\ndef add_up(n):\n    if n == 1:\n        return 1\n    return n + add_up(n - 1)\n\nprint(add_up(5))\n```\n> recursion = a function calling itself with a base case."},
            {"title": "map with lambda", "topic": "lambda",
             "prompt": "Use `map` with a `lambda` to double `[1, 2, 3]` and print the result as a list.",
             "starter": "", "expect": ["2", "4", "6"], "need": ["lambda", "map"], "stdin": "",
             "example": "Square instead:\n```python\nprint(list(map(lambda x: x * x, [1, 2, 3])))\n```\n> map(fn, list) runs fn on every item; list() collects it."},
            {"title": "double with lambda", "topic": "lambda",
             "prompt": "Make a `lambda` that doubles a number, then print doubling 7.",
             "starter": "", "expect": ["14"], "need": ["lambda"], "stdin": "",
             "example": "A lambda that squares:\n```python\nsq = lambda x: x * x\nprint(sq(5))\n```\n> lambda makes a tiny one-line function."},
            {"title": "safe divide", "topic": "try",
             "prompt": "Divide two numbers but catch the `ZeroDivisionError` and print `nope`.",
             "starter": "", "expect": ["nope"], "need": ["try", "except"], "stdin": "",
             "example": "Catch a bad conversion:\n```python\ntry:\n    int(\"abc\")\nexcept ValueError:\n    print(\"bad\")\n```\n> try runs risky code; except catches the crash."},
            {"title": "sum to n", "topic": "recursion",
             "prompt": "Write a recursive `add_up(n)` that returns 1 + 2 + ... + n, then print `add_up(5)`.",
             "starter": "def add_up(n):\n    pass\n", "expect": ["15"], "need": ["def", "return"], "stdin": "",
             "example": "Recursive countdown instead:\n```python\ndef count(n):\n    if n == 0:\n        return\n    print(n)\n    count(n - 1)\n```\n> recursion = a function calling itself with a base case."},
        ],
    },
    {
        "id": "mastery",
        "name": "MASTERY MIX",
        "challenges": [
            {"title": "fizz buzz", "topic": "custom",
             "prompt": "Loop 1 through 15. Print `fizz` for multiples of 3, `buzz` for multiples of 5, and the number otherwise.",
             "starter": "", "expect": ["fizz", "buzz", "1", "2"], "need": ["for", "%"], "stdin": "",
             "example": "A smaller fizz loop:\n```python\nfor i in range(1, 7):\n    if i % 3 == 0:\n        print(\"fizz\")\n    else:\n        print(i)\n```\n> % gives the remainder; combine if/else with a loop."},
            {"title": "name length map", "topic": "custom",
             "prompt": "Given a list of names, print a list of their lengths using `map` and `len`.",
             "starter": "names = [\"ann\", \"bob\", \"charlie\"]\n", "expect": ["3", "7"], "need": ["map", "len"], "stdin": "",
             "example": "Map str.upper instead:\n```python\nprint(list(map(str.upper, [\"a\", \"b\"])))\n```\n> map(fn, list) applies fn to every item."},
            {"title": "dict of squares", "topic": "custom",
             "prompt": "Build a dictionary mapping 1..4 to their squares, then print the dict.",
             "starter": "", "expect": ["1: 1", "16"], "need": ["for"], "stdin": "",
             "example": "A list of squares first:\n```python\nprint([i*i for i in range(1, 5)])\n```\n> combine a loop with {key: value} to build a dict."},
            {"title": "only evens", "topic": "custom",
             "prompt": "Filter `[1, 2, 3, 4, 5, 6]` down to just the even numbers and print the result.",
             "starter": "", "expect": ["2", "4", "6"], "need": ["for", "%"], "stdin": "",
             "example": "Filter with a comprehension:\n```python\nprint([x for x in range(10) if x % 2 == 0])\n```\n> a comprehension with an `if` filters as it builds."},
            {"title": "unique letters", "topic": "sets",
             "prompt": "Print the unique letters of `\"hello\"` using a set.",
             "starter": "", "expect": ["h", "e", "l", "o"], "need": ["set"], "stdin": "",
             "example": "A set of another word:\n```python\nprint(set(\"banana\"))\n```\n> a set keeps only unique values."},
            {"title": "swap it", "topic": "tuples",
             "prompt": "Swap the values of `a` and `b` using tuple unpacking, then print both.",
             "starter": "a = 1\nb = 2\n", "expect": ["2", "1"], "need": [], "stdin": "",
             "example": "The tuple swap trick:\n```python\na, b = b, a\nprint(a, b)\n```\n> a, b = b, a swaps two values in one line."},
            {"title": "dict size", "topic": "dicts",
             "prompt": "Print how many items are in the dictionary using `len()`.",
             "starter": "d = {\"a\": 1, \"b\": 2, \"c\": 3}\n", "expect": ["3"], "need": ["len"], "stdin": "",
             "example": "Length of a shorter dict:\n```python\nprint(len({\"x\": 1, \"y\": 2}))\n```\n> len() counts the key-value pairs in a dict."},
        ],
    },
    {
        "id": "readcode",
        "name": "READ THE CODE",
        "challenges": [
            {"title": "trace: first print", "topic": "read", "predict": True,
             "code": 'print(2 + 2)',
             "read_hint": 'print() does the math FIRST — 2 + 2 is 4, so it shows 4.',
             "prompt": "**Predict** what this prints, then type the exact output and run.",
             "starter": "", "expect": [], "need": [], "stdin": "",
             "example": 'Trace a different sum:\n```python\nprint(5 + 3)\n```\n> 5 + 3 is 8, so it prints 8.'},
            {"title": "trace: last one wins", "topic": "read", "predict": True,
             "code": 'x = 1\nx = 2\nprint(x)',
             "read_hint": 'The LAST assignment wins. x was 1, then x became 2 — print(x) shows 2.',
             "prompt": "**Predict** what this prints, then type the exact output and run.",
             "starter": "", "expect": [], "need": [], "stdin": "",
             "example": 'Trace a different reassign:\n```python\nn = 5\nn = 9\nprint(n)\n```\n> n ends as 9, so it prints 9.'},
            {"title": "trace: glue words", "topic": "read", "predict": True,
             "code": 'print("a" + "b")',
             "read_hint": '+ between two words STICKS them together — "a" + "b" is "ab" (no space).',
             "prompt": "**Predict** what this prints, then type the exact output and run.",
             "starter": "", "expect": [], "need": [], "stdin": "",
             "example": 'Trace a different join:\n```python\nprint("hi" + "!")\n```\n> "hi" + "!" is "hi!", so it prints hi!.'},
            {"title": "trace: f-string fill", "topic": "read", "predict": True,
             "code": 'name = "Bean"\nprint(f"hi {name}")',
             "read_hint": 'The f-string drops the value of name into the { }. name is "Bean", so it prints "hi Bean".',
             "prompt": "**Predict** what this prints, then type the exact output and run.",
             "starter": "", "expect": [], "need": [], "stdin": "",
             "example": 'Trace a different f-string:\n```python\ncity = "Portland"\nprint(f"go {city}")\n```\n> {city} fills in Portland, so it prints "go Portland".'},
            {"title": "trace: even or odd", "topic": "read", "predict": True,
             "code": 'n = 7\nif n % 2 == 0:\n    print("even")\nelse:\n    print("odd")',
             "read_hint": '7 % 2 is 1, not 0 — so the if is FALSE and the else runs: it prints "odd".',
             "prompt": "**Predict** what this prints, then type the exact output and run.",
             "starter": "", "expect": [], "need": [], "stdin": "",
             "example": 'Trace a different number:\n```python\nn = 4\nif n % 2 == 0:\n    print("even")\nelse:\n    print("odd")\n```\n> 4 % 2 is 0, so it prints "even".'},
            {"title": "trace: count a loop", "topic": "read", "predict": True,
             "code": 'for i in range(3):\n    print(i)',
             "read_hint": 'range(3) gives 0, 1, 2 — the loop body runs once per value, printing each on its own line.',
             "prompt": "**Predict** what this prints (one line per printed line), then type it and run.",
             "starter": "", "expect": [], "need": [], "stdin": "",
             "example": 'Trace a different loop:\n```python\nfor i in range(2):\n    print(i)\n```\n> range(2) gives 0 and 1, printed on two lines.'},
            {"title": "trace: list item", "topic": "read", "predict": True,
             "code": 'fruits = ["apple", "banana"]\nprint(fruits[1])',
             "read_hint": 'Indexes start at 0: [0] is "apple", [1] is "banana" — so it prints banana.',
             "prompt": "**Predict** what this prints, then type the exact output and run.",
             "starter": "", "expect": [], "need": [], "stdin": "",
             "example": 'Trace a different index:\n```python\nfruits = ["apple", "banana"]\nprint(fruits[0])\n```\n> [0] is the FIRST item, so it prints apple.'},
            {"title": "trace: dict read", "topic": "read", "predict": True,
             "code": 'ages = {"alice": 30, "bob": 25}\nprint(ages["bob"])',
             "read_hint": 'ages["bob"] reads the value for key "bob", which is 25 — so it prints 25.',
             "prompt": "**Predict** what this prints, then type the exact output and run.",
             "starter": "", "expect": [], "need": [], "stdin": "",
             "example": 'Trace a different key:\n```python\nages = {"alice": 30, "bob": 25}\nprint(ages["alice"])\n```\n> ages["alice"] is 30, so it prints 30.'},
            {"title": "trace: function call", "topic": "read", "predict": True,
             "code": 'def double(x):\n    return x * 2\nprint(double(4))',
             "read_hint": 'double(4) hands 4 to the function, which returns 4 * 2 = 8, and print() shows 8.',
             "prompt": "**Predict** what this prints, then type the exact output and run.",
             "starter": "", "expect": [], "need": [], "stdin": "",
             "example": 'Trace a different function:\n```python\ndef triple(x):\n    return x * 3\nprint(triple(3))\n```\n> triple(3) returns 9, so it prints 9.'},
            {"title": "trace: countdown", "topic": "read", "predict": True,
             "code": 'n = 3\nwhile n > 0:\n    print(n)\n    n -= 1',
             "read_hint": 'The loop prints n (3, then 2, then 1) and subtracts 1 each lap, stopping when n hits 0.',
             "prompt": "**Predict** what this prints (one line per printed line), then type it and run.",
             "starter": "", "expect": [], "need": [], "stdin": "",
             "example": 'Trace a different countdown:\n```python\nn = 2\nwhile n > 0:\n    print(n)\n    n -= 1\n```\n> It prints 2, then 1 — two lines.'},
            {"title": "trace: running total", "topic": "read", "predict": True,
             "code": 'total = 0\nfor i in range(1, 4):\n    total += i\nprint(total)',
             "read_hint": 'total starts at 0, then 1, 2, and 3 are added one lap at a time: 0+1+2+3 = 6.',
             "prompt": "**Predict** what this prints, then type the exact output and run.",
             "starter": "", "expect": [], "need": [], "stdin": "",
             "example": 'Trace a different total:\n```python\ntotal = 0\nfor i in range(1, 3):\n    total += i\nprint(total)\n```\n> 0+1+2 = 3, so it prints 3.'},
            {"title": "trace: string length", "topic": "read", "predict": True,
             "code": 's = "hello"\nprint(len(s))',
             "read_hint": 'len(s) counts the letters in "hello" — h e l l o is 5, so it prints 5.',
             "prompt": "**Predict** what this prints, then type the exact output and run.",
             "starter": "", "expect": [], "need": [], "stdin": "",
             "example": 'Trace a different length:\n```python\ns = "hi"\nprint(len(s))\n```\n> "hi" has 2 letters, so it prints 2.'},
        ],
    },
]

EXAMPLES = {
    "say hello": [
        {"code": 'print("hello world")', "stdin": ""},
        {"code": 'print(2 + 2)', "stdin": ""},
        {"code": 'print("done", "for", "now")', "stdin": ""},
    ],
    "your name": [
        {"code": 'name = "Bean"\nprint(name)', "stdin": ""},
        {"code": 'city = "Portland"\nprint(city)', "stdin": ""},
        {"code": 'greeting = "hello"\nprint(greeting)', "stdin": ""},
    ],
    "ask and answer": [
        {"code": 'years = int(input("How many years? "))\nprint(years * 365, "days")', "stdin": "25\n"},
        {"code": 'name = input("What is your name? ")\nprint("Hi", name)', "stdin": "Bean\n"},
        {"code": 'age = int(input("Age? "))\nprint("Next year:", age + 1)', "stdin": "30\n"},
    ],
    "even or odd": [
        {"code": 'n = 6\nif n % 2 == 0:\n    print("even")\nelse:\n    print("odd")', "stdin": ""},
        {"code": 'n = 4\nif n % 2 == 0:\n    print("even")\nelse:\n    print("odd")', "stdin": ""},
        {"code": 'score = 85\nif score >= 60:\n    print("pass")\nelse:\n    print("fail")', "stdin": ""},
    ],
    "count to ten": [
        {"code": 'for i in range(1, 11):\n    print(i)', "stdin": ""},
        {"code": 'for i in range(2, 12, 2):\n    print(i)', "stdin": ""},
        {"code": 'for i in range(3):\n    print("hi")', "stdin": ""},
    ],
    "your first function": [
        {"code": 'def add(a, b):\n    return a + b\n\nprint(add(3, 4))', "stdin": ""},
        {"code": 'def minus(a, b):\n    return a - b\n\nprint(minus(9, 4))', "stdin": ""},
        {"code": 'def greet():\n    print("hello")\n\ngreet()', "stdin": ""},
    ],
    "fruit basket": [
        {"code": 'fruits = ["apple", "banana"]\nfruits.append("cherry")\nprint(fruits)', "stdin": ""},
        {"code": 'nums = [1, 2, 3]\nnums.append(4)\nprint(nums)', "stdin": ""},
        {"code": 'colors = ["red", "blue"]\nprint(colors[0])', "stdin": ""},
    ],
    "fancy strings": [
        {"code": 'name = "Bean"\nprint(f"Hello, {name}!")', "stdin": ""},
        {"code": 'city = "Portland"\nprint(f"Welcome to {city}!")', "stdin": ""},
        {"code": 'a, b = 3, 4\nprint(f"{a} + {b} = {a + b}")', "stdin": ""},
    ],
    "people and ages": [
        {"code": 'people = {"alice": 30, "bob": 25}\nprint(people["bob"])', "stdin": ""},
        {"code": 'scores = {"alice": 90, "bob": 85}\nprint(scores["alice"])', "stdin": ""},
        {"code": 'info = {"name": "Bean", "age": 30}\nprint(info["name"])', "stdin": ""},
    ],
    "custom": [
        {"code": 'print("hi")', "stdin": ""},
        {"code": 'for i in range(5):\n    print(i)', "stdin": ""},
        {"code": 'print(7 * 6)', "stdin": ""},
    ],
}


TOPIC_CHEATS = {
    "print": {"title": "print + variables",
              "examples": [("print text", 'print("hello world")'),
                           ("variable", 'name = "Bean"\nprint(name)')],
              "tip": "print() shows stuff. A variable is a named box."},
    "input": {"title": "input()",
              "examples": [("get text", 'age = input("How old? ")'),
                           ("make it a number", 'age = int(input("How old? "))')],
              "tip": "input() returns a STRING. Wrap it in int() to do math."},
    "conditionals": {"title": "if / else",
                     "examples": [("even/odd", 'if n % 2 == 0:\n    print("even")\nelse:\n    print("odd")')],
                     "tip": "4-space indent REQUIRED. n % 2 is 0 when even."},
    "loops": {"title": "for loops",
              "examples": [("1 to 10", 'for i in range(1, 11):\n    print(i)')],
              "tip": "range(1, 11) = 1..10. The stop number is EXCLUSIVE."},
    "functions": {"title": "def functions",
                  "examples": [("define+call", 'def add(a, b):\n    return a + b\n\nprint(add(3, 4))')],
                  "tip": "def NAME(params): then indent. return sends a value back."},
    "lists": {"title": "lists",
              "examples": [("append", 'fruits = ["apple", "banana"]\nfruits.append("cherry")\nprint(fruits)')],
              "tip": ".append() adds to the end."},
    "fstrings": {"title": "f-strings",
                 "examples": [("basic", 'name = "Bean"\nprint(f"Hello, {name}!")')],
                 "tip": 'f"..." drops {variables} into text. The f before the quote matters.'},
    "dicts": {"title": "dictionaries",
              "examples": [("read", 'people = {"alice": 30, "bob": 25}\nprint(people["bob"])')],
              "tip": "Read with dict[\"key\"]."},
    "read": {"title": "reading / tracing code",
             "examples": [("reassign", 'x = 1\nx = 2\nprint(x)  # 2'),
                          ("loop", 'for i in range(3):\n    print(i)  # 0 1 2')],
             "tip": "Trace top to bottom. A variable is whatever it was last set to. print() shows that value."},
    "custom": {"title": "common patterns",
               "examples": [("print", 'print("hi")'),
                            ("loop", 'for i in range(5):\n    print(i)')],
               "tip": "common patterns — you got this. Stuck? Hit F2 for examples, F12 for a quick check."},
}


# One-line, plain-English "why" for each worked example (ordered to match the
# LESSONS[topic]["examples"] list). Written for a 15-year-old — no jargon.
WHYS = {
    "print": [
        "print() is the megaphone: it takes whatever is inside the ( ) and shows it on screen.",
        "print() does the math FIRST, then shows the answer — you only ever see the result.",
        "Commas let print() show several things on one line, with a space between each.",
    ],
    "name": [
        "A variable is a labelled box. name = \"Bean\" puts Bean in the box called name.",
        "Boxes hold numbers too — age = 30 stores 30, and print(age) shows it.",
        "You can empty a box and put something new in it — the last value wins.",
    ],
    "math": [
        "+ adds, and print() shows the result.",
        "* is the times key (x is just a letter), so 3 * 4 is 12.",
        "( ) decides what happens first, exactly like real math.",
    ],
    "input": [
        "input() freezes the program, waits for you to type, then hands back what you typed.",
        "int() turns typed TEXT into a real NUMBER so you can do math on it.",
        "input() always gives text, even if you typed 5 — that's why int() exists.",
    ],
    "fstrings": [
        "The f before the quote is the magic: it fills {name} with what's in the box.",
        "You can put math inside { } and Python works it out before printing.",
        "Mix normal words and {variables} in one string — it all flows together.",
    ],
    "conditionals": [
        "% gives the leftover after dividing — n % 2 is 0 only when n is even.",
        "if/else picks one path; whichever check is True is the path it runs.",
        "elif means 'else if' — a second check after the first one fails.",
    ],
    "loops": [
        "for i in range(1, 11) counts 1 through 10 — the last number is left out.",
        "range(3) just means 'do this 3 times' — you don't even need the i.",
        "range(start, stop, step) skips numbers, like counting by twos.",
    ],
    "while": [
        "while loops as long as the check is True — n -= 1 counts down one each lap.",
        "Same idea counting up: it runs until the condition flips False.",
        "while can run forever, so you need a line that eventually flips the check.",
    ],
    "lists": [
        "A list is numbered boxes. [0] is the FIRST item — counting starts at zero.",
        ".append(x) glues x onto the end of the list.",
        ".remove(x) deletes one specific item by name.",
    ],
    "dicts": [
        "A dict is named boxes: people[\"bob\"] reaches into the box labelled bob.",
        "A dict can hold different types — numbers and words in the same box.",
        "Read two keys and add their numbers together.",
    ],
    "functions": [
        "def makes a recipe, and the ( ) at the end cooks it — that's the call.",
        "A function can run with no inputs at all — the ( ) is just empty.",
        "Write it once, call it many times — that's the whole point.",
    ],
    "strings": [
        "A string is letters in order. [0] grabs the FIRST letter.",
        "len() counts how many letters (or items) are inside.",
        ".upper() shouts every letter into a capital.",
    ],
    "slicing": [
        "s[::-1] walks the string backwards and gives you a mirror copy.",
        "s[:3] takes the first three characters.",
        "s[1:] chops off the first character.",
    ],
    "comprehension": [
        "A list comprehension builds a whole list in one line — [x*x for x in ...].",
        "It runs the expression for every item and stacks the results.",
        "You can change each item as it builds, like .upper() on every word.",
    ],
    "sorting": [
        ".sort() reorders the list smallest-first, right in place.",
        "reverse=True flips it to biggest-first.",
        "It sorts words too — alphabetical order.",
    ],
    "try": [
        "try runs risky code; if it explodes, except catches it so the program survives.",
        "int(\"abc\") crashes, but inside try/except you handle it calmly.",
        "except with no error type catches ANY mistake.",
    ],
    "sets": [
        "A set throws away duplicate copies automatically.",
        "set(...) builds the set from anything list-like.",
        "A set of a string keeps each unique letter once.",
    ],
    "tuples": [
        "A tuple is a list that can't be changed, made with ( ) instead of [ ].",
        "Once made, a tuple stays put — you can't append to it.",
        "a, b = b, a swaps two values using tuples.",
    ],
    "class": [
        "class is a blueprint; the method is the action it can do.",
        "__init__ sets up each new object; self holds that object's own data.",
        "You can make many copies — each one is its own object.",
    ],
    "recursion": [
        "A function that calls itself, shrinking the problem until it's small enough to stop.",
        "The base case (n == 0) is what makes it stop instead of running forever.",
        "Each call adds its piece, and the answers stack back up.",
    ],
    "lambda": [
        "lambda is a tiny one-line function with no name.",
        "Great for quick math: lambda x: x*x squares a number.",
        "It can take two inputs too — lambda a, b: a + b.",
    ],
    "generator": [
        "yield hands back one value at a time instead of all at once.",
        "A generator pauses after each yield and resumes when asked.",
        "It's lazy — only makes the next value when you ask for it.",
    ],
    "decorator": [
        "A decorator wraps a function to add behavior before and after it runs.",
        "You can call the wrapper by hand to see it happen.",
        "The @ syntax is just shorthand for wrapping the function.",
    ],
    "error": [
        "raise throws an error on purpose; except catches it with the message.",
        "You can write your own error message to explain what went wrong.",
        "except with no type catches anything that gets thrown.",
    ],
    "file": [
        "open(..., \"w\") opens a file for writing, and .write() puts text in it.",
        "Numbers must become strings before you write them.",
        "\"a\" means append — add to the end without erasing what's there.",
    ],
    "read": [
        "The LAST assignment wins — x was 1, then x became 2, so print(x) shows 2.",
        "range(3) gives 0, 1, 2 — the loop body runs once per value, printing each on its own line.",
        "total starts at 0, then 1, 2, 3 get added one lap at a time: 0+1+2+3 = 6.",
    ],
    "custom": [
        "print() is the quickest way to see what's happening.",
        "A short loop repeats a line a few times.",
        "Store a value in a variable, then print it.",
    ],
}

# Cache of example outputs so opening the examples panel doesn't re-run them.
_OUT_CACHE: dict = {}


# Canonical "bad code -> good code" pairs, with a one-line reason why the bad
# version breaks. Used by the F7 code review to show what went wrong AND why
# the rule matters (not just "you broke it").
PITFALLS = {
    "print": {"bad": 'print(hello)', "good": 'print("hello")',
              "why": "hello without quotes is read as a variable name that doesn't exist. Quotes make it a word."},
    "name": {"bad": 'name = Bean', "good": 'name = "Bean"',
             "why": "Text needs quotes. Without them Python goes looking for a variable called Bean."},
    "conditionals": {"bad": 'if n % 2 == 0:\nprint("even")', "good": 'if n % 2 == 0:\n    print("even")',
                     "why": "Everything inside an if must be indented 4 spaces, or Python can't tell it's inside the if."},
    "loops": {"bad": 'for i in range(1, 11)\n    print(i)', "good": 'for i in range(1, 11):\n    print(i)',
              "why": "A for line ends with a colon. Forget it and Python can't start the loop."},
    "input": {"bad": 'age = input("age? ")\nprint(age + 1)', "good": 'age = int(input("age? "))\nprint(age + 1)',
              "why": "input() hands back text, and text + number crashes. int() turns it into a real number first."},
    "functions": {"bad": 'def add(a, b):\nprint(add(3, 4))', "good": 'def add(a, b):\n    return a + b\n\nprint(add(3, 4))',
                  "why": "The body must be indented, and return sends the answer back — without it add() gives None."},
    "lists": {"bad": 'fruits.add("cherry")', "good": 'fruits.append("cherry")',
              "why": "It's .append(), not .add() — that's the list method's name."},
    "fstrings": {"bad": 'name = "Bean"\nprint("Hello, {name}!")', "good": 'name = "Bean"\nprint(f"Hello, {name}!")',
                 "why": "The f before the quote is what turns {name} into its value. Forget the f and it prints the letters literally."},
    "while": {"bad": 'n = 5\nwhile n > 0\n    print(n)', "good": 'n = 5\nwhile n > 0:\n    print(n)\n    n -= 1',
              "why": "while needs the colon too, AND a line that changes n — otherwise it loops forever."},
    "strings": {"bad": 'print(s[1])  # wanted the FIRST letter', "good": 'print(s[0])',
                "why": "Indexing starts at 0, so the first letter is [0], not [1]."},
    "dicts": {"bad": 'print(people[bob])', "good": 'print(people["bob"])',
              "why": "The key name goes in quotes — otherwise Python looks for a variable called bob."},
    "comprehension": {"bad": '[i*i for i in range(5)', "good": '[i*i for i in range(5)]',
                      "why": "A list comprehension sits inside one [ ] pair — close the bracket."},
    "read": {"bad": 'x = 1\nprint(x)\nx = 2', "good": 'x = 1\nx = 2\nprint(x)',
             "why": "Order matters. print(x) shows x at THAT line — if print comes before x = 2, it still shows the old 1."},
}


# Pre-written "class intro" lessons, keyed by topic. Each is a scripted,
# funny, dumbed-down explanation with a numbered breakdown and several runnable
# examples — no AI involved, so every lesson is deterministic and always ready.
# The one-time ground-rules prelude every learner hears before their first
# lesson: WHY code is structured the way it is and HOW Python actually runs it.
STRUCTURE_PRELUDE = (
    "Quick ground rules before we write anything. "
    "Rule one: Python runs your code top to bottom, one line at a time, in the exact order you wrote it. "
    "A line only runs after the line above it is finished. "
    "Rule two: a colon at the end of a line means a new block starts here, and the indented lines under it "
    "only run when that condition is true. "
    "Rule three: you have to make a thing before you use it. A variable before you print it. "
    "A function before you call it. "
    "And when you face any challenge: read the prompt twice, do the smallest step first, and run it often. "
    "That's the whole game."
)


# Dumbed-down "what's new" one-liners, keyed by the `need` technique token.
# Used by the W lesson to name the SPECIFIC thing this challenge introduces.
FOCUS_HINTS = {
    "print": "print() shows things on the screen — it's how your code talks back.",
    "name": "a variable is a labelled box you store a value in.",
    "input": "input() asks the user a question and waits for them to type an answer.",
    "int": "int() turns typed text into a real number you can do math on.",
    "%": "the percent sign gives the leftover after dividing — n % 2 is 0 only when n is even.",
    "if": "if asks a yes/no question and only runs its block when the answer is true.",
    "else": "else is the fallback — it runs when the if was false.",
    "elif": "elif chains on a second check after the first if fails.",
    "for": "for loops repeat a block, once for each item.",
    "range": "range() hands out a row of numbers to loop over.",
    "while": "while repeats as long as its check stays true.",
    "break": "break kicks you out of a loop early.",
    "append": ".append() glues a new item onto the end of a list.",
    "remove": ".remove() deletes one specific item from a list.",
    "len": "len() counts how many things are inside.",
    "def": "def makes your own reusable command — a function.",
    "return": "return hands a value back out of a function.",
    "[0]": "square brackets reach into a list or string — [0] is the FIRST item.",
    "[-1]": "a negative index counts from the end — [-1] is the LAST item.",
    "[:": "a slice carves a piece out of a string or list.",
    "set": "set() throws away duplicates, keeping only unique values.",
    "class": "class is a blueprint for making objects.",
    "__init__": "__init__ is the setup that runs when you create a new object.",
    "in": "the word `in` checks whether something is inside a list or string.",
    "f": "the f in front of a quote fills {variables} into the text.",
    "**": "two stars mean 'to the power of'.",
    "split": ".split() chops a string into a list of pieces.",
    "join": ".join() glues a list into one string.",
    "sort": ".sort() puts a list in order, smallest first.",
    "count": ".count() tells you how many of something are inside.",
    "sum": "sum() adds up every number in a list.",
    "max": "max() finds the biggest item.",
    "enumerate": "enumerate() gives you the position AND the item together.",
    "lambda": "lambda is a tiny one-line function with no name.",
    "map": "map() runs a function over every item in a list.",
    "yield": "yield hands out values one at a time instead of all at once.",
    "raise": "raise throws an error on purpose.",
    "with": "with auto-closes a file when you're done with it.",
    "open": "open() opens a file so you can read or write it.",
    "finally": "finally runs no matter what, error or not.",
    "title": ".title() capitalizes the first letter of each word.",
    "upper": ".upper() turns every letter into a CAPITAL.",
}


LESSONS = {
    "print": {
        "title": "print() — Your Voice to the Machine",
        "intro": "print() is how your code talks to you. Before print(), a program just thinks quietly to itself — print() makes it shout the answer out loud.",
        "points": [
            ("What print() does", "print() takes whatever you hand it and shows it on the screen. Text, numbers, math — it does not care, it just displays it."),
            ("Quotes make words", "Words go in quotes, like print(\"hello\"). No quotes and Python thinks you mean a variable name, which is a whole different (confusing) story."),
            ("The #1 trap", "Forgetting quotes around words. print(hello) without quotes makes Python panic. print(\"hello\") makes it happy. Quotes are the difference between a word and a name."),
        ],
        "examples": [
            {"caption": "your first words", "code": 'print("hello world")'},
            {"caption": "math works too", "code": "print(2 + 2)"},
            {"caption": "a few things at once", "code": 'print("hi", "i am", "bean")'},
        ],
        "outro": "That's print(). The single most-used tool in Python — if you can print it, you can see it, and if you can see it, you can fix it.",
    },
    "name": {
        "title": "Variables — Little Labelled Boxes",
        "intro": "A variable is a labelled box you store stuff in. Give it a name, put a value in it, then use the name instead of the value.",
        "points": [
            ("Equals means 'store'", "name = \"Bean\" does NOT mean name equals Bean forever. It means 'take the right side and store it in the box named on the left.' Left = box, right = value."),
            ("Names are your choice", "You name the box — city, age, favorite_pizza, anything clear. Python just wants it to be one word, no spaces."),
            ("Use it by name", "Once stored, the name IS the value. print(name) prints whatever is inside, not the word 'name'."),
        ],
        "examples": [
            {"caption": "store then print", "code": 'name = "Bean"\nprint(name)'},
            {"caption": "a number in a box", "code": "age = 30\nprint(age)"},
            {"caption": "overwrite it", "code": "x = 1\nx = 2\nprint(x)"},
        ],
        "outro": "Variables = named boxes. That's the entire trick. Store it once, use it everywhere.",
    },
    "math": {
        "title": "Python Is a Fancy Calculator",
        "intro": "Python does math like a calculator. Add, subtract, multiply, divide — and print the answer right out.",
        "points": [
            ("The four big ones", "+ adds, - subtracts, * multiplies, / divides. Careful: * is multiply, because x would look like a letter."),
            ("Order of operations", "Python follows normal math rules: 2 + 2 * 3 is 8, not 12, because * goes first. Use ( ) to be explicit."),
            ("It just works", "print(2 + 2) does not print the text '2 + 2', it prints the RESULT. Python does the math first."),
        ],
        "examples": [
            {"caption": "basic add", "code": "print(2 + 2)"},
            {"caption": "multiply", "code": "print(7 * 6)"},
            {"caption": "parentheses matter", "code": "print((2 + 3) * 4)"},
        ],
        "outro": "Math is free. If you can write it as numbers and + - * /, Python will compute it instantly.",
    },
    "input": {
        "title": "input() — Make It a Conversation",
        "intro": "Until now your code did everything by itself. Boring! input() makes the program STOP and ASK the human for a value. Suddenly your programs are conversations.",
        "points": [
            ("input() pauses and asks", "age = input(\"How old? \") shows the question, waits for the user to type, and stores what they typed as a STRING."),
            ("Everything from input is text", "Even if they type 25, Python sees \"25\" — a string, not a number. You cannot do math on text."),
            ("int() converts", "Wrap it: int(input(\"Age? \")) turns the typed text into a real number you can add to."),
        ],
        "examples": [
            {"caption": "ask and store", "code": 'name = input("What is your name? ")\nprint("hi", name)', "stdin": "Bean\n"},
            {"caption": "turn text into a number", "code": 'age = int(input("Age? "))\nprint(age + 10)', "stdin": "25\n"},
            {"caption": "surprise: it is text", "code": 'x = input("type a number: ")\nprint(x * 2)', "stdin": "25\n"},
        ],
        "outro": "input() = ask the human. int() = make it a number. Together they make interactive programs.",
    },
    "fstrings": {
        "title": "f-strings — Glue Variables Into Text",
        "intro": "F-strings are how you glue variables INTO your text without ugly + signs. Drop an f in front of the quotes, then put curly braces around anything you want filled in.",
        "points": [
            ("The f does the magic", "f\"Hello, {name}\" — the f before the quote tells Python 'fill in the braces.' No f, and the braces just sit there looking dumb."),
            ("Braces = fill this in", "Anything in { } gets replaced by its value. {name} becomes the name, {age + 1} becomes the math result."),
            ("So much cleaner", "Compare \"Hi \" + name + \"!\" (ugly) with f\"Hi {name}!\" (clean). Same result, way less punctuation."),
        ],
        "examples": [
            {"caption": "basic", "code": 'name = "Bean"\nprint(f"Hello, {name}!")'},
            {"caption": "do math inside", "code": 'a = 3\nb = 4\nprint(f"{a} + {b} = {a + b}")'},
            {"caption": "mixing", "code": 'city = "Portland"\nprint(f"Welcome to {city}!")'},
        ],
        "outro": "f + braces = the cleanest way to put variables into sentences. You'll use it constantly.",
    },
    "conditionals": {
        "title": "if / else — Code Makes Decisions",
        "intro": "if/else is where code starts making DECISIONS. It's the fork in the road — if this is true, go left; otherwise, go right.",
        "points": [
            ("if asks a yes/no question", "if n > 5: — the colon matters, and everything indented under it only runs when the answer is true."),
            ("else is the fallback", "else: catches everything the if didn't — the 'otherwise, do this' path."),
            ("Percent means remainder", "n % 2 gives the remainder after dividing by 2. Zero remainder = even, one = odd. The classic even/odd trick."),
        ],
        "examples": [
            {"caption": "even or odd", "code": 'n = 7\nif n % 2 == 0:\n    print("even")\nelse:\n    print("odd")'},
            {"caption": "bigger number", "code": "a = 5\nb = 10\nif a > b:\n    print(a)\nelse:\n    print(b)"},
            {"caption": "elif chains", "code": 'score = 85\nif score >= 90:\n    print("A")\nelif score >= 80:\n    print("B")\nelse:\n    print("C")'},
        ],
        "outro": "if = decide, else = fallback, elif = chain more decisions. Indentation is NOT optional — it's how Python knows what belongs inside the if.",
    },
    "loops": {
        "title": "for Loops — Do the Boring Stuff for You",
        "intro": "Loops are how you make the computer do the boring repeated stuff so you don't have to. A for loop says 'do this thing, once for each of these.'",
        "points": [
            ("range() makes the numbers", "range(1, 11) makes 1 through 10 (the stop number is NOT included — classic trap). range(3) makes 0, 1, 2."),
            ("for = each one", "for i in range(...): runs the indented block over and over, and i takes a new value each pass."),
            ("The loop variable is yours", "i is just a name. for potato in range(3) works too. i is just the convention. (And enumerate() gives you the index plus the item, for later.)"),
        ],
        "examples": [
            {"caption": "count to ten", "code": "for i in range(1, 11):\n    print(i)"},
            {"caption": "three times", "code": 'for i in range(3):\n    print("hi")'},
            {"caption": "step by twos", "code": "for i in range(0, 10, 2):\n    print(i)"},
        ],
        "outro": "for + range = repeat. Remember: the stop number is EXCLUSIVE. range(1, 11) is 1 through 10.",
    },
    "while": {
        "title": "while Loops — Repeat Until It's False",
        "intro": "A while loop keeps going WHILE a condition is true. No fixed list — it just checks the condition every lap and stops the moment it's false.",
        "points": [
            ("while + condition", "while n >= 1: — as long as that's true, the block repeats. The moment it's false, it stops."),
            ("You must change something", "Something INSIDE the loop has to move you toward the end (like n -= 1), or it loops forever. That's the infinite-loop nightmare."),
            ("-= is shorthand", "n -= 1 means 'n = n - 1'. Same for +=. Count up, count down, your call."),
        ],
        "examples": [
            {"caption": "count down", "code": "n = 5\nwhile n >= 1:\n    print(n)\n    n -= 1"},
            {"caption": "count up", "code": "i = 1\nwhile i <= 3:\n    print(i)\n    i += 1"},
            {"caption": "double until big", "code": "n = 2\nwhile n < 10:\n    n = n * 2\n    print(n)"},
        ],
        "outro": "while = repeat until the condition is false. ALWAYS make sure something inside changes, or you'll loop until the heat death of the universe.",
    },
    "lists": {
        "title": "Lists — Your Code's Junk Drawer",
        "intro": "Lists are the junk drawer of Python — an ordered collection of stuff, kept in square brackets, separated by commas. Your code's first way to hold MORE than one thing.",
        "points": [
            ("Made with [ ]", "fruits = [\"apple\", \"banana\"] — square brackets, comma between items. Order matters; it stays in the order you put it."),
            ("Grab one by position", "fruits[0] is the FIRST item (lists count from 0, not 1). fruits[1] is the second. Index = position."),
            ("Change it with methods", ".append(x) adds to the end, .remove(x) deletes a specific item. Dot-methods are actions the list already knows."),
        ],
        "examples": [
            {"caption": "read by index", "code": 'fruits = ["apple", "banana", "cherry"]\nprint(fruits[0])'},
            {"caption": "add to the end", "code": 'fruits = ["apple", "banana"]\nfruits.append("cherry")\nprint(fruits)'},
            {"caption": "remove one", "code": 'fruits = ["apple", "banana"]\nfruits.remove("apple")\nprint(fruits)'},
        ],
        "outro": "Lists = ordered [ ] collections. Index with [0], grow with .append(), delete with .remove(). Zero-based indexing is non-negotiable.",
    },
    "dicts": {
        "title": "Dictionaries — The Phonebook of Python",
        "intro": "Dictionaries are like a phonebook: you look up a VALUE by a KEY. Instead of position [0], you ask for things by NAME, in curly braces.",
        "points": [
            ("Key to value pairs", "people = {\"alice\": 30, \"bob\": 25} — \"alice\" is the key, 30 is the value. A colon connects them, a comma separates pairs."),
            ("Look up by key", "people[\"bob\"] gives 25. You ask by name, not position. No such key? It crashes."),
            ("Great for real data", "Names to ages, products to prices. When data has a natural 'label,' a dict is the right tool. (Loop with .items(), and you can nest them inside lists.)"),
        ],
        "examples": [
            {"caption": "read a value", "code": 'people = {"alice": 30, "bob": 25}\nprint(people["bob"])'},
            {"caption": "different types", "code": 'info = {"name": "Bean", "age": 30}\nprint(info["name"])'},
            {"caption": "add two values", "code": 'd = {"x": 1, "y": 2}\nprint(d["x"] + d["y"])'},
        ],
        "outro": "dict = look up values by key with ['key']. Curly braces, colon between key and value. The phonebook of Python.",
    },
    "functions": {
        "title": "Functions — Your Own Reusable Commands",
        "intro": "Functions are your own reusable commands. You write a block of code ONCE, give it a name, and call it whenever you want — like teaching Python a new word.",
        "points": [
            ("def = define", "def add(a, b): — 'def' + name + (inputs) + colon. Everything indented under it is the function body."),
            ("return hands a value back", "return a + b sends the answer back to whoever called it. print() shows it; return GIVES it back (you can store it)."),
            ("Call it by name", "add(3, 4) runs the function with 3 and 4, and the return value shows up. Without the call, the function just sits there. (Defaults and *args come later.)"),
        ],
        "examples": [
            {"caption": "define and call", "code": "def add(a, b):\n    return a + b\n\nprint(add(3, 4))"},
            {"caption": "no inputs", "code": 'def greet():\n    print("hello")\n\ngreet()'},
            {"caption": "reuse it", "code": "def double(n):\n    return n * 2\n\nprint(double(5))\nprint(double(10))"},
        ],
        "outro": "def makes it, return gives it back, name() calls it. Functions are how you stop copy-pasting the same code.",
    },
    "strings": {
        "title": "Strings — Text Is a List of Letters",
        "intro": "Strings are text, and text is a list of characters. You can grab one letter by position, count them, and transform them.",
        "points": [
            ("Each letter has a position", "s = \"hello\" — s[0] is 'h', s[1] is 'e', s[4] is 'o'. Same zero-based indexing as lists."),
            ("len() counts", "len(s) tells you how many characters. len(\"hello\") is 5. Works on lists too."),
            ("Methods transform", ".upper() shouts, .lower() whispers, .split() chops into words. Dot-methods are the string's superpowers."),
        ],
        "examples": [
            {"caption": "first letter", "code": 's = "hello"\nprint(s[0])'},
            {"caption": "how long", "code": 's = "hello"\nprint(len(s))'},
            {"caption": "shout it", "code": 's = "hello world"\nprint(s.upper())'},
        ],
        "outro": "Strings are lists of characters. [0] grabs a letter, len() counts, and dot-methods transform. Reading is free; editing is not allowed.",
    },
    "slicing": {
        "title": "Slicing — Carve Pieces Out of Text",
        "intro": "Slicing is how you carve pieces out of a string (or list) with square brackets and colons. The classic party trick: reversing a word in one move.",
        "points": [
            ("[start:stop] cuts a piece", "s[0:3] gives the first 3 characters (index 0,1,2 — stop is exclusive again). s[1:] = everything from index 1 on."),
            ("[::-1] reverses", "The third slot is the STEP. -1 means 'walk backwards,' so s[::-1] is the whole string in reverse."),
            ("Works on lists too", "Anything indexable can be sliced. Same syntax, same rules."),
        ],
        "examples": [
            {"caption": "reverse it", "code": 's = "hello"\nprint(s[::-1])'},
            {"caption": "first three", "code": 's = "hello"\nprint(s[:3])'},
            {"caption": "skip the first", "code": 's = "hello"\nprint(s[1:])'},
        ],
        "outro": "Slicing = [start:stop:step]. The ::-1 reverse trick is the one everyone remembers. Stop is always exclusive.",
    },
    "comprehension": {
        "title": "List Comprehensions — A Loop in a Tuxedo",
        "intro": "List comprehensions build a list in ONE line, right inside [ ]. Same job as a for loop — way less typing.",
        "points": [
            ("The shape", "[expr for x in range(...)] — the expression first, then the for loop. It runs the loop and collects the results into a list."),
            ("Read it backwards if lost", "[i**2 for i in range(1, 6)] means: for each i in 1..5, compute i**2, and gather them all into a list."),
            ("The expr can be anything", "Square them, double them, transform them — whatever you write before 'for' gets applied to each item."),
        ],
        "examples": [
            {"caption": "squares", "code": "print([i**2 for i in range(1, 6)])"},
            {"caption": "double each", "code": "print([x * 2 for x in [1, 2, 3]])"},
            {"caption": "uppercase them", "code": 'print([w.upper() for w in ["a", "b", "c"]])'},
        ],
        "outro": "Comprehension = [do-stuff for each-item]. One line, loop built-in. Python's most loved shortcut.",
    },
    "sorting": {
        "title": "Sorting — The Neat-Freak Method",
        "intro": ".sort() is the neat-freak method — it puts a list in order, smallest first, right where it stands. Alphabetical for words, ascending for numbers.",
        "points": [
            (".sort() is in-place", "nums.sort() changes the list itself. You don't assign it to anything — just call it and the list is sorted."),
            ("reverse=True flips it", "nums.sort(reverse=True) goes biggest-first. The keyword reverse=True is how you flip it."),
            ("sorted() is the cousin", "sorted(nums) returns a NEW sorted list and leaves the original alone. Two tools, one job."),
        ],
        "examples": [
            {"caption": "smallest first", "code": "nums = [3, 1, 2]\nnums.sort()\nprint(nums)"},
            {"caption": "biggest first", "code": "nums = [3, 1, 2]\nnums.sort(reverse=True)\nprint(nums)"},
            {"caption": "words too", "code": 'words = ["cherry", "apple", "banana"]\nwords.sort()\nprint(words)'},
        ],
        "outro": ".sort() reorders in place, reverse=True flips it. Sorting is one line — the tidy-up of lists.",
    },
    "try": {
        "title": "try / except — The Safety Net",
        "intro": "try/except is the safety net. You wrap risky code in try:, and if it crashes, except: catches the fall instead of letting the whole program die.",
        "points": [
            ("try runs the risky stuff", "Everything in the try block runs normally — until something blows up."),
            ("except catches the explosion", "If an error happens, Python jumps straight to except and runs THAT instead of crashing out."),
            ("finally always runs", "Add a finally: block and it runs no matter what — error or success. The cleanup guarantee."),
        ],
        "examples": [
            {"caption": "divide safely", "code": "try:\n    print(10 / 0)\nexcept ZeroDivisionError:\n    print(\"nope\")"},
            {"caption": "bad conversion", "code": 'try:\n    int("hello")\nexcept ValueError:\n    print("that is not a number")'},
            {"caption": "catch anything", "code": "try:\n    1 / 0\nexcept Exception:\n    print(\"something broke\")"},
        ],
        "outro": "try = attempt, except = if it breaks, do this, finally = no matter what. Your program survives mistakes instead of face-planting.",
    },
    "sets": {
        "title": "Sets — No Duplicates Allowed",
        "intro": "A set is a list that refuses duplicates and doesn't care about order. Toss a list with repeats into set() and the copies vanish like magic.",
        "points": [
            ("No duplicates allowed", "set([1, 2, 2, 3]) becomes {1, 2, 3}. Every item is unique, automatically."),
            ("Made with set() or { }", "set([...]) converts a list; {1, 2, 3} makes one directly. Curly braces, but no key:value pairs (that's a dict)."),
            ("Order isn't guaranteed", "Sets don't keep order. If you need the order, keep the list; use a set when uniqueness is what matters."),
        ],
        "examples": [
            {"caption": "dedupe a list", "code": "nums = [1, 2, 2, 3]\nprint(set(nums))"},
            {"caption": "make one directly", "code": "print({1, 2, 3, 3})"},
            {"caption": "unique letters", "code": 'print(set("hello"))'},
        ],
        "outro": "set = no duplicates, no order. Convert with set(list). Uniqueness in one line.",
    },
    "tuples": {
        "title": "Tuples — The Frozen List",
        "intro": "A tuple is a list you can't change — a fixed, frozen collection in parentheses. Once you make it, it stays exactly as-is.",
        "points": [
            ("Made with ( )", "pair = (1, 2) — parentheses instead of brackets. That's the whole visual difference."),
            ("Index it like a list", "pair[1] gives 2. Reading works exactly the same; only CHANGING is forbidden."),
            ("Why freeze it?", "For data that shouldn't change — coordinates, settings, pairs. Immutability = safety."),
        ],
        "examples": [
            {"caption": "make and read", "code": "pair = (1, 2)\nprint(pair[1])"},
            {"caption": "tuples stay put", "code": 'colors = ("red", "blue")\nprint(colors[0])'},
            {"caption": "swap trick", "code": "a, b = 1, 2\na, b = b, a\nprint(a, b)"},
        ],
        "outro": "tuple = a frozen list in ( ). Read with [ ], but you can't edit it. Great for data that must not move.",
    },
    "class": {
        "title": "Classes — Blueprints for Objects",
        "intro": "A class is a blueprint for making objects — bundles of DATA and BEHAVIOR. You define the shape once, then stamp out as many copies as you want.",
        "points": [
            ("class + __init__", "class Dog: defines the blueprint. __init__ is the setup that runs when you CREATE a Dog — it stores the starting data."),
            ("self = 'this one'", "self.name means THIS object's name. Every method takes self first so it knows which instance you're talking about."),
            ("Inherit to extend", "class LoudDog(Dog): takes everything Dog has and lets you override a method. Parent in the parentheses."),
        ],
        "examples": [
            {"caption": "a class with a method", "code": 'class Dog:\n    def bark(self):\n        print("woof")\n\nDog().bark()'},
            {"caption": "with a name", "code": 'class Dog:\n    def __init__(self, name):\n        self.name = name\n\nprint(Dog("Rex").name)'},
            {"caption": "many instances", "code": 'class Cat:\n    def meow(self):\n        print("meow")\n\nCat().meow()\nCat().meow()'},
        ],
        "outro": "class = blueprint, self = this instance, __init__ = setup, ( ) after the name = make one. Objects are how real programs are built.",
    },
    "recursion": {
        "title": "Recursion — One Twist on Functions You Already Know",
        "intro": "You already know functions — a recipe you write once and call by name. Recursion is ONE new twist: the function calls ITSELF. That's it. Everything else is just making sure it eventually stops.",
        "points": [
            ("Remember a normal function", "greet() runs the greet recipe, top to bottom, then hands control back. You already do this. Recursion is the same idea — a call is a call."),
            ("The one new twist: call itself", "Inside count, the line count(n - 1) calls count AGAIN. Same recipe, a smaller number. A function calling itself is the entire trick."),
            ("It must shrink every time", "count(n - 1) passes n minus one — a SMALLER number each call. That shrinking is what moves it toward the end. If it never shrank, it would never stop."),
            ("The base case is the stop sign", "if n == 0: return is the off-switch. When n reaches 0, it returns instead of calling again, and the whole chain ends. No base case = infinite loop = crash."),
        ],
        "examples": [
            {"caption": "a normal function (recap)", "code": "def greet(name):\n    print(\"hi\", name)\n\ngreet(\"Bean\")"},
            {"caption": "the twist — call itself", "code": "def count(n):\n    if n == 0:\n        return\n    print(n)\n    count(n - 1)\n\ncount(3)"},
            {"caption": "sum to n (return a value)", "code": "def add_up(n):\n    if n == 1:\n        return 1\n    return n + add_up(n - 1)\n\nprint(add_up(4))"},
            {"caption": "factorial (return + multiply)", "code": "def fact(n):\n    if n == 0:\n        return 1\n    return n * fact(n - 1)\n\nprint(fact(5))"},
        ],
        "outro": "Recursion = a function that calls itself, shrinking the problem each time, until the base case stops it. Start by finding the stop sign, then work out what each call does.",
    },
    "lambda": {
        "title": "lambda — A Tiny Nameless Function",
        "intro": "lambda is a tiny, throwaway function written in one line. No def, no name — just 'lambda x: x * 2' — an anonymous little helper.",
        "points": [
            ("The shape", "lambda x: x * 2 — lambda, then the input(s), a colon, then the expression. The expression is the return value."),
            ("No name needed", "You usually stash it in a variable or pass it straight into something. It's a function without the ceremony."),
            ("Great for one-liners", "When you need a quick 'do this to x' and don't want a whole def block."),
        ],
        "examples": [
            {"caption": "double", "code": "double = lambda x: x * 2\nprint(double(5))"},
            {"caption": "square", "code": "sq = lambda x: x * x\nprint(sq(3))"},
            {"caption": "two inputs", "code": "add = lambda a, b: a + b\nprint(add(3, 4))"},
        ],
        "outro": "lambda x: expression = a nameless one-line function. For quick little transforms.",
    },
    "generator": {
        "title": "Generators — Values One at a Time",
        "intro": "A generator produces values ONE AT A TIME using yield, instead of building the whole list at once. It's a lazy factory — ask, and it hands you the next one.",
        "points": [
            ("yield instead of return", "yield hands out a value but the function REMEMBERS where it was, and resumes next time you ask."),
            ("One at a time", "A generator doesn't compute everything up front. It makes each value only when you request it."),
            ("Drop the brackets for lazy", "sum(i for i in range(6)) — a comprehension without [ ] is a generator expression. Same idea, lazier."),
        ],
        "examples": [
            {"caption": "yield values", "code": "def evens():\n    yield 2\n    yield 4\n\nfor n in evens():\n    print(n)"},
            {"caption": "yield a few", "code": "def count():\n    yield 1\n    yield 2\n    yield 3\n\nprint(list(count()))"},
            {"caption": "lazy sum", "code": "print(sum(i * i for i in range(1, 6)))"},
        ],
        "outro": "yield = hand out a value and pause. Generators are lazy — one value at a time, only when asked.",
    },
    "decorator": {
        "title": "Decorators — Wrap a Function",
        "intro": "A decorator wraps a function to add behavior AROUND it — like a bun around a burger. Write the wrapper once, then @decorate any function you want enhanced.",
        "points": [
            ("A function that takes a function", "def wrap(fn): ... return inner — it receives a function and returns a NEW function that calls it, with extra stuff around."),
            ("The @ line applies it", "@wrap above a function is shorthand for 'pass this function through wrap.' The @ does the wiring."),
            ("before/after behavior", "Print before, run the function, print after — that's the classic timing/logging pattern."),
        ],
        "examples": [
            {"caption": "wrap and call", "code": 'def wrap(fn):\n    def inner():\n        print("start")\n        fn()\n        print("end")\n    return inner\n\n@wrap\ndef hi():\n    print("hi")\n\nhi()'},
            {"caption": "manually", "code": 'def wrap(fn):\n    def inner():\n        print("before")\n        fn()\n    return inner\n\ndef bye():\n    print("bye")\n\nwrap(bye)()'},
            {"caption": "run it twice", "code": 'def double(fn):\n    def inner():\n        fn()\n        fn()\n    return inner\n\n@double\ndef ping():\n    print("ping")\n\nping()'},
        ],
        "outro": "Decorator = a function that wraps another. The @ line applies it. Before/after logic around any function.",
    },
    "error": {
        "title": "raise — Throw Your Own Errors",
        "intro": "You can THROW your own errors with raise — like pulling the fire alarm on purpose. Then except catches it, and the error message is YOUR words.",
        "points": [
            ("raise throws", "raise ValueError(\"nope\") creates an error on purpose, with whatever message you want."),
            ("except ... as e captures it", "except ValueError as e: — the 'as e' stores the error object so you can read its message with print(e)."),
            ("Why raise on purpose?", "To signal 'this input is bad' from deep in your code, and let the caller decide what to do."),
        ],
        "examples": [
            {"caption": "throw and catch", "code": 'try:\n    raise ValueError("nope")\nexcept ValueError as e:\n    print(e)'},
            {"caption": "custom message", "code": 'try:\n    raise ValueError("that is not allowed")\nexcept ValueError as e:\n    print("caught:", e)'},
            {"caption": "catch any", "code": 'try:\n    raise Exception("boom")\nexcept Exception as e:\n    print(e)'},
        ],
        "outro": "raise = throw an error, except ... as e = catch it and read the message. Errors become a tool, not a disaster.",
    },
    "file": {
        "title": "Files — Data That Survives",
        "intro": "Files are how your code remembers things after it quits. open() a file, write to it, read it back — and 'with' makes sure it gets closed properly.",
        "points": [
            ("open with a mode", "open(\"x.txt\", \"w\") opens for writing (w = write), open(\"x.txt\") opens for reading. The mode letter matters."),
            ("with handles cleanup", "with open(...) as f: — 'with' auto-closes the file when you're done, even if something breaks. Always use it."),
            (".write() and .read()", "f.write(\"hi\") puts text in, f.read() pulls it all back out. Write then read = a full round trip."),
        ],
        "examples": [
            {"caption": "write and read", "code": 'with open("x.txt", "w") as f:\n    f.write("hello")\nwith open("x.txt") as f:\n    print(f.read())'},
            {"caption": "write a number", "code": 'with open("n.txt", "w") as f:\n    f.write("42")\nwith open("n.txt") as f:\n    print(f.read())'},
            {"caption": "append", "code": 'with open("log.txt", "w") as f:\n    f.write("a")\nwith open("log.txt", "a") as f:\n    f.write("b")\nwith open("log.txt") as f:\n    print(f.read())'},
        ],
        "outro": "with open(...) as f: is the safe way to touch files. 'w' writes, no mode reads, 'a' appends. Data that survives your program.",
    },
    "read": {
        "title": "Reading Code — Trace It Like a Computer",
        "intro": "Writing code is only half the skill — reading it is the other half, and it's the part that separates 'copy-paste' from 'I actually get it'. To read code you play computer: run each line in your head, top to bottom, and keep track of what every variable holds.",
        "points": [
            ("Run top to bottom", "Python reads your code one line at a time, in order. A variable is whatever it was set to LAST — earlier lines don't matter once a later line overwrites them."),
            ("print() shows what's held NOW", "When you hit print(x), ask: what is x RIGHT NOW? Not what it started as — what the lines above just changed it to."),
            ("Loops repeat, values change", "A loop runs its body again and again. If a variable changes inside the loop, every pass sees a new value."),
        ],
        "examples": [
            {"caption": "reassign then print", "code": "x = 1\nx = 2\nprint(x)"},
            {"caption": "loop changes i", "code": "for i in range(3):\n    print(i)"},
            {"caption": "accumulate a total", "code": "total = 0\nfor n in [1, 2, 3]:\n    total += n\nprint(total)"},
        ],
        "outro": "Trace it line by line, keep a running list of what each variable holds, and remember print() is your window into all of it. Master reading and you'll never be stuck staring at your own code again.",
    },
    "custom": {
        "title": "Common Patterns — You Got This",
        "intro": "A custom challenge — but the moves are all ones you already know. Print, loop, store in a variable. Break the problem into small steps.",
        "points": [
            ("Read the prompt twice", "What's the input? What should the output be? Name the pieces before you type anything."),
            ("Smallest step first", "Get ONE thing printing correctly, then build up. Never try to write the whole answer at once."),
            ("Run early, run often", "Test after every small change. Seeing 'hello' print is proof you're on track."),
        ],
        "examples": [
            {"caption": "just print", "code": 'print("hi")'},
            {"caption": "loop a few", "code": "for i in range(5):\n    print(i)"},
            {"caption": "store and print", "code": "x = 7 * 6\nprint(x)"},
        ],
        "outro": "You got this. Read the prompt, take the smallest step, run it, repeat.",
    },
}


# The explicit syntax RULES for each topic, read out during the lesson.
LESSON_RULES = {
    "print": ["print() ALWAYS needs parentheses: print(\"hi\")",
              "words go inside quotes — print(hi) without quotes breaks",
              "use commas to print several things at once"],
    "name": ["= stores the right side into the left-side name",
             "names are one word, no spaces",
             "print(name) prints the value, not the word 'name'"],
    "math": ["* is multiply, not x",
             "normal math order applies — use ( ) to be explicit",
             "print(2 + 2) prints the RESULT, not the text"],
    "input": ["input() always returns TEXT, even if they type a number",
              "wrap int() around it to turn it into a number",
              "the question goes inside the parentheses"],
    "fstrings": ["the f must come right before the quote: f\"...\"",
                 "variables go inside {curly braces}",
                 "no f = the braces stay as literal text"],
    "conditionals": ["if ends with a colon, and the body is indented 4 spaces",
                     "% is remainder — n % 2 == 0 means even",
                     "else catches everything the if did not"],
    "loops": ["range(1, 11) gives 1 through 10 — the stop is EXCLUDED",
              "for i in range(...): the body is indented",
              "i changes to a new value every pass"],
    "while": ["while checks the condition every single loop",
              "something inside MUST change, or it never stops",
              "n -= 1 is shorthand for n = n - 1"],
    "lists": ["lists use [square brackets] with commas between items",
              "indexing starts at 0: [0] is the first item",
              ".append() adds to the end, .remove() deletes one"],
    "dicts": ["dicts use {curly braces} with key: value pairs",
              "read a value with ['key'] in square brackets",
              "a comma separates each pair"],
    "functions": ["def name(inputs): ends with a colon",
                  "return hands a value back to the caller",
                  "call it with name(arguments)"],
    "strings": ["s[0] is the first character — counting starts at 0",
                "len(s) counts the characters",
                "methods hang off with a dot: s.upper()"],
    "slicing": ["[start:stop] — the stop is EXCLUSIVE",
                "a third number is the step",
                "[::-1] reverses the whole thing"],
    "comprehension": ["[expr for x in thing] — the expr comes first",
                      "the loop runs inside the brackets",
                      "the result is a brand new list"],
    "sorting": [".sort() changes the list in place",
                "reverse=True sorts biggest first",
                "words sort alphabetically"],
    "try": ["try: wraps the risky code",
            "except catches the error type",
            "finally runs no matter what"],
    "sets": ["set() removes duplicates",
             "{ } makes a set directly",
             "sets do not keep order"],
    "tuples": ["tuples use (parentheses)",
               "read with [0] exactly like a list",
               "tuples cannot be changed after creation"],
    "class": ["class Name: defines the blueprint",
              "__init__ runs when you create one",
              "self means 'this particular instance'"],
    "recursion": ["the function calls itself",
                  "a base case MUST stop it or it never ends",
                  "each call uses a smaller input"],
    "lambda": ["lambda x: expression — no def, no name",
               "the expression is the return value",
               "stash it in a variable to reuse it"],
    "generator": ["yield hands out a value and pauses",
                  "a generator makes values one at a time",
                  "loop over it with for"],
    "decorator": ["a decorator wraps another function",
                  "@name applies it to the next function",
                  "the wrapper calls the original inside"],
    "error": ["raise throws an error on purpose",
              "except ... as e captures it",
              "print(e) shows the error message"],
    "file": ["open('file', 'w') writes, open('file') reads",
             "with auto-closes the file",
             ".write() puts text in, .read() gets it out"],
    "read": ["run lines top to bottom — a variable is whatever it was LAST set to",
             "print(x) shows the value x holds AT THAT MOMENT",
             "loops run the body again, so values change each pass"],
    "custom": ["read the prompt twice",
               "start with the smallest step",
               "run early and run often"],
}

# Similar mini-challenges to solve after the main one (YOUR TURN).
LESSON_PRACTICE = {
    "print": ["Print the word 'goodbye'", "Print a number like 42", "Print two things on one line"],
    "name": ["Store your favorite color and print it", "Store the number 7 and print it", "Change a variable to a new value and print again"],
    "math": ["Print 10 minus 3", "Print 6 times 7", "Print (2 + 3) times 5"],
    "input": ["Ask for a name and greet them", "Ask for an age and print it plus 1", "Ask for a number and double it"],
    "fstrings": ["f-string with your name", "f-string that adds two numbers", "f-string with a city and a greeting"],
    "conditionals": ["Print 'positive' or 'negative' for a number", "Print the smaller of two numbers", "Print 'adult' if age is 18 or more"],
    "loops": ["Print 1 through 5", "Print 0 through 4", "Print your name 3 times"],
    "while": ["Count down from 3 to 1", "Count up to 4", "Double a number until it is over 20"],
    "lists": ["Make a list of 3 foods and print the second", "Append a new item and print the list", "Remove an item and print the list"],
    "dicts": ["Make a dict of a name and age, print the age", "Add two keys and print one", "Print both values from a dict"],
    "functions": ["Write a function that prints a greeting", "Write add(a, b) that returns a + b", "Write a function that doubles a number"],
    "strings": ["Print the first letter of your name", "Print how long a word is", "Print a word in ALL CAPS"],
    "slicing": ["Print the first 3 letters of a word", "Reverse your name", "Print a word without its first letter"],
    "comprehension": ["Make a list of squares 1..4", "Make a list doubling [1, 2, 3]", "Make a list of the first 5 numbers"],
    "sorting": ["Sort [5, 2, 8] and print it", "Sort it biggest-first", "Sort a list of 3 words"],
    "try": ["Catch a divide-by-zero", "Catch int('hello') failing", "Print 'done' using a finally"],
    "sets": ["Dedupe [1, 1, 2, 3] and print", "Make a set of {1, 2, 2} and print it", "Print the unique letters of 'hello'"],
    "tuples": ["Make (10, 20) and print the second", "Make a tuple of two words and print the first", "Swap two variables using a tuple"],
    "class": ["Make a class with a method and call it", "Add a name to __init__ and print it", "Make two objects and call the method twice"],
    "recursion": ["Write a recursive countdown", "Write a recursive sum of 1..n", "Write factorial with recursion"],
    "lambda": ["A lambda that doubles, print double(4)", "A lambda that squares, print square(6)", "A lambda that adds two numbers"],
    "generator": ["A generator that yields 1, 2, 3", "A generator of even numbers", "sum() a generator expression"],
    "decorator": ["A wrapper that prints 'start' and 'end'", "Apply it with @ to a function", "A wrapper that runs a function twice"],
    "error": ["raise a ValueError and catch it", "raise with your own message", "catch any Exception and print it"],
    "file": ["Write 'hi' to a file and read it back", "Write a number to a file", "Append to a file and read it"],
    "read": ["Predict what print(3 * 4) shows", "Predict what x = 1; x = 5; print(x) shows", "Predict a for loop's output before running it"],
    "custom": ["Print something, then loop it 3 times", "Store a value and print it", "Combine two things you already know"],
}


# The "now write it" transition that ends every lesson, right before the
# mandatory ghost-writing drill kicks in. Replaced the old "YOUR TURN" text list.
GHOST_INTRO_TEXT = (
    "Now the real practice — and it ramps up. First I show you the code already "
    "written and you just press enter to run it, so you see it work. Then I start "
    "each line and you finish it. Then you write the whole thing yourself. A wrong "
    "letter turns red and stays put — keep going, then backspace to the red letters "
    "and fix them before it runs. No skipping: typing it out is how the syntax "
    "becomes second nature."
)

_GHOST_MODE_CUE = {
    "watch": "Watch and run. I already wrote this one — just press enter to see what it does.",
    "finish": "Now you finish it. I started it, you type the rest.",
    "write": "Now the whole thing yourself, no help.",
    "change": "Now a change-it. I edited one thing — type it and watch the output change.",
}


def example_code(example: str) -> tuple[str, str]:
    """Split an example string into (caption, code block)."""
    m = re.search(r"```(?:python)?\s*\n(.*?)\n```", example, re.DOTALL)
    code = m.group(1) if m else ""
    caption = re.sub(r"```.*?```", "", example, flags=re.DOTALL).strip()
    return caption, code


def example_why(example: str) -> str:
    """The '> explanation' tail of a challenge's example field — the challenge-
    SPECIFIC one-liner that says why this exact idea works. Empty if none."""
    for line in (example or "").splitlines():
        s = line.strip()
        if s.startswith(">"):
            return s.lstrip(">").strip()
    return ""


GHOST_TARGET = 8   # how many reps to drill (up to) before a challenge unlocks
_GHOST_WORDS = ["bean", "kiwi", "apple", "delta", "gamma", "thing", "value",
                "city", "item", "name"]


def _ghost_variant(code: str) -> str | None:
    """One syntax-safe value-swap for an extra ghost rep: swap simple string
    literals and bump standalone integer literals (never indices). The structure
    is identical — only the VALUES differ — so it's fresh typing with no new
    rules. Returns None when nothing can safely change."""
    v = code
    v = re.sub(r'"([a-zA-Z_][a-zA-Z0-9_]*)"',
               lambda m: '"' + _GHOST_WORDS[abs(hash(m.group(1))) % len(_GHOST_WORDS)] + '"', v)
    v = re.sub(r"'([a-zA-Z_][a-zA-Z0-9_]*)'",
               lambda m: "'" + _GHOST_WORDS[abs(hash(m.group(1))) % len(_GHOST_WORDS)] + "'", v)
    # bump standalone positive integers, but never slice/index bits: skip digits
    # preceded by '[' (index), ':' (slice step) or '-' (a negative literal's sign).
    # Bumping the -1 in s[::-1] to 0 would emit the invalid s[::0].
    v = re.sub(r'(?<![\w.\[\-:])\d+(?![\w.])',
               lambda m: str(int(m.group(0)) + 1), v)
    return v if v != code else None


def _change_variant(code: str, stdin: str = "") -> tuple[str, dict] | None:
    """One MEANINGFUL edit for a 'change it' rep: alter a single integer literal
    so the OUTPUT visibly changes — teaching that editing THIS bit changes THAT
    result. Returns (new_code, change) or None, where change = {old, new,
    meaning, before, after} and before/after are the run outputs (capped)."""
    try:
        tree = ast.parse(code)
    except Exception:
        return None
    numbers = []
    for node in ast.walk(tree):
        if (isinstance(node, ast.Constant) and isinstance(node.value, int)
                and not isinstance(node.value, bool)):
            seg = ast.get_source_segment(code, node)
            if seg is not None and re.fullmatch(r"-?\d+", seg.strip()):
                numbers.append((node, seg.strip(), node.value))
    if not numbers:
        return None
    # prefer the range STOP (the classic off-by-one confusion) over other numbers
    def prio(entry):
        m = _number_meaning(code, entry[0])
        return (0 if m == "the stop number" else
                1 if m in ("the start number", "the step") else 2)
    numbers.sort(key=lambda e: (prio(e), -e[2]))
    before = (run_lesson_code(code, stdin)[0] or "").rstrip("\n")
    lines = code.split("\n")
    starts = [0]
    for ln in lines:
        starts.append(starts[-1] + len(ln) + 1)
    for node, seg, val in numbers:
        for delta in (-1, 1, -2, 2, -5):
            nv = val + delta
            if nv < 0:
                continue
            s = starts[node.lineno - 1] + node.col_offset
            e = starts[node.end_lineno - 1] + node.end_col_offset
            new_code = code[:s] + str(nv) + code[e:]
            after_out, after_err = run_lesson_code(new_code, stdin)
            if after_err:
                continue   # this edit breaks the code (e.g. step -> 0) — skip it
            after = (after_out or "").rstrip("\n")
            if after != before:
                return (new_code, {
                    "old": seg, "new": str(nv),
                    "meaning": _number_meaning(code, node),
                    "before": before, "after": after,
                })
    return None


def _number_meaning(code: str, node) -> str:
    """A short plain-English name for what an integer literal does, so the
    'change it' explanation can say WHAT was edited, not just the value."""
    line = code.split("\n")[node.lineno - 1]
    before = line[:node.col_offset]
    stripped = before.rstrip()
    if stripped.endswith("["):
        return "the position you reach into"
    if stripped.endswith(":"):
        return "the step"
    if "range(" in before:
        m = re.search(r"range\s*\(([^)]*)\)", line)
        n_args = 1
        if m:
            n_args = m.group(1).count(",") + 1
        inside = before.rsplit("range(", 1)[-1]
        n = inside.count(",")
        if n_args == 1:
            return "the stop number"
        if n == 0:
            return "the start number"
        if n == 1:
            return "the stop number"
        return "the step"
    if "print(" in before:
        return "the number being printed"
    if "=" in before:
        return "the value you stored"
    return "the number"





def run_code(code: str, stdin: str = "25\n") -> tuple[str, str]:
    with tempfile.NamedTemporaryFile("w", suffix=".py", delete=False) as f:
        f.write(code)
        path = f.name
    try:
        r = subprocess.run(["python3", path], capture_output=True, text=True,
                           timeout=15, input=stdin)
        return r.stdout, r.stderr
    except subprocess.TimeoutExpired:
        return "", "[timed out after 15s — infinite loop?]"
    finally:
        Path(path).unlink(missing_ok=True)


def run_lesson_code(code: str, stdin: str = "") -> tuple[str, str]:
    """Run a lesson example in a throwaway temp dir (so file-writing examples
    don't litter the working directory) with stdin fed, returning (stdout, stderr)."""
    with tempfile.TemporaryDirectory() as d:
        try:
            r = subprocess.run(["python3", "-c", code], capture_output=True, text=True,
                               timeout=10, input=stdin, cwd=d)
            return r.stdout, r.stderr
        except subprocess.TimeoutExpired:
            return "", "[timed out]"


# Runs `code`, then dumps the final top-level namespace as JSON — so a pure-math
# or assignment snippet that prints nothing (e.g. `x = 3; x = x + 5`) can still
# show its answer (`x = 8`) instead of a blank console.
_FINAL_STATE_RUNNER = r'''
import sys, json
src = open(sys.argv[1]).read()
code = compile(src, sys.argv[1], "exec")
g = {"__name__": "__main__"}
def render(v):
    if isinstance(v, str): return v
    if isinstance(v, bool): return "true" if v else "false"
    if isinstance(v, (int, float)): return repr(v)
    if isinstance(v, (list, tuple, set)): return ", ".join(render(x) for x in v)
    if isinstance(v, dict): return ", ".join(render(k) + " is " + render(val) for k, val in v.items())
    if v is None: return "nothing"
    return repr(v)
try:
    exec(code, g)
except Exception:
    print(json.dumps({}))
    raise SystemExit(0)
out = {k: render(v) for k, v in g.items()
       if not k.startswith("__") and isinstance(v, (str, int, float, bool, list, tuple, set, dict))}
print(json.dumps(out))
'''


def final_vars_of(code: str, stdin: str = "", timeout: float = 10.0) -> dict[str, str]:
    """The top-level namespace AFTER `code` runs, as {name: spoken_value}. Used
    so snippets that print nothing still show their answer. {} on any failure."""
    with tempfile.TemporaryDirectory() as d:
        cp = Path(d) / "code.py"
        cp.write_text(code)
        try:
            r = subprocess.run(["python3", "-c", _FINAL_STATE_RUNNER, str(cp)],
                               capture_output=True, text=True, timeout=timeout,
                               input=stdin, cwd=d)
            return json.loads(r.stdout.strip() or "{}")
        except Exception:
            return {}


# A self-contained tracing runner: runs the user's code under sys.settrace and
# emits, for every line that executes (top-to-bottom, in real order), the line
# number and a snapshot of the visible variables at that moment. Values are
# pre-rendered as spoken strings so the JSON is trivially serializable. This is
# the engine behind the "watch it run" line-by-line replay that teaches HOW
# Python actually walks through a program (the #1 'top to bottom' confusion).
TRACE_RUNNER = r'''
import sys, json, io
MAX_EVENTS = 120

def render(v):
    if isinstance(v, str):
        return v
    if isinstance(v, bool):
        return "true" if v else "false"
    if isinstance(v, (int, float)):
        return repr(v)
    if isinstance(v, (list, tuple, set)):
        return ", ".join(render(x) for x in v)
    if isinstance(v, dict):
        return ", ".join(render(k) + " is " + render(val) for k, val in v.items())
    if v is None:
        return "nothing"
    return repr(v)

def main():
    code_path, trace_path = sys.argv[1], sys.argv[2]
    with open(code_path) as f:
        src = f.read()
    code = compile(src, code_path, "exec")
    events = []
    # tee stdout so each line-event can snapshot the output printed SO FAR —
    # lets the trace show the real prints accumulating, not just variable state
    out_buf = io.StringIO()
    real_stdout = sys.stdout
    class _Tee:
        def write(self, s):
            real_stdout.write(s)
            out_buf.write(s)
        def flush(self):
            real_stdout.flush()
    sys.stdout = _Tee()
    def tracer(frame, event, arg):
        if event == "line" and frame.f_code.co_filename == code_path:
            if len(events) < MAX_EVENTS:
                locs = {}
                for k, v in list(frame.f_locals.items()):
                    if k.startswith("__") or k == "self":
                        continue
                    if (v is None or isinstance(v, (str, int, float, bool,
                                                    list, tuple, set, dict))):
                        locs[k] = render(v)
                events.append([frame.f_lineno, locs, out_buf.getvalue()])
        return tracer
    sys.settrace(tracer)
    g = {"__name__": "__main__"}
    try:
        exec(code, g)
    finally:
        sys.settrace(None)
    sys.stdout = real_stdout
    with open(trace_path, "w") as out:
        json.dump(events, out)

main()
'''


def trace_code(code: str, stdin: str = "", timeout: float = 10.0):
    """Run `code` under a line tracer and return (stdout, stderr, events) where
    events is a list of [line_no, {var: spoken_value}] snapshots in execution
    order. Falls back gracefully to a plain run if tracing fails."""
    with tempfile.TemporaryDirectory() as d:
        code_path = Path(d) / "code.py"
        trace_path = Path(d) / "trace.json"
        code_path.write_text(code)
        try:
            r = subprocess.run(["python3", "-c", TRACE_RUNNER, str(code_path), str(trace_path)],
                               capture_output=True, text=True, timeout=timeout,
                               input=stdin, cwd=d)
        except subprocess.TimeoutExpired:
            return "", "[timed out]", []
        events: list = []
        if trace_path.exists():
            try:
                events = json.loads(trace_path.read_text())
            except Exception:
                events = []
        return r.stdout, r.stderr, events


def run_code_echo(code: str, stdin: str = "", timeout: float = 15.0) -> str:
    """Run code in a PTY so input() prompts AND the typed value are echoed back,
    giving the interactive (MOOC-style) look. Returns the full transcript."""
    import os
    import pty
    import select
    import time as _time

    m, s = pty.openpty()
    proc = subprocess.Popen(
        ["python3", "-c", code],
        stdin=s, stdout=s, stderr=s,
        close_fds=True, start_new_session=True,
    )
    os.close(s)
    out = b""
    start = _time.time()
    fed = False
    while _time.time() - start < timeout:
        if not fed and stdin and _time.time() - start > 0.4:
            try:
                os.write(m, stdin.encode())
            except OSError:
                pass
            fed = True
        r, _, _ = select.select([m], [], [], 0.05)
        if r:
            try:
                data = os.read(m, 4096)
            except OSError:
                break
            if not data:
                break
            out += data
        elif proc.poll() is not None:
            break
    # drain anything still buffered
    try:
        while True:
            r, _, _ = select.select([m], [], [], 0.15)
            if not r:
                break
            data = os.read(m, 4096)
            if not data:
                break
            out += data
    except OSError:
        pass
    try:
        os.close(m)
    except OSError:
        pass
    try:
        proc.wait(timeout=2)
    except Exception:
        pass
    text = out.decode("utf-8", "replace")
    text = text.replace("\r\n", "\n").replace("\r", "\n")
    text = re.sub(r"\x1b\[[0-9;?]*[a-zA-Z]", "", text)
    return text.rstrip("\n")


def run_demo_session(code: str, stdin: str = "", timeout: float = 10.0) -> str:
    """Run `code` in a PTY, feeding `stdin` so interactive input() is echoed
    back, and return the full terminal transcript (prompt + typed input +
    output). The echo is what makes "type your input" visible in the console."""
    import os
    import pty
    import select
    import time as _time

    m, s = pty.openpty()
    proc = subprocess.Popen(
        ["python3", "-c", code],
        stdin=s, stdout=s, stderr=s,
        close_fds=True, start_new_session=True,
    )
    os.close(s)
    out = b""
    start = _time.time()
    fed = False
    while _time.time() - start < timeout:
        if not fed and stdin and _time.time() - start > 0.5:
            try:
                os.write(m, stdin.encode())
            except OSError:
                pass
            fed = True
        r, _, _ = select.select([m], [], [], 0.05)
        if r:
            try:
                data = os.read(m, 4096)
            except OSError:
                break
            if not data:  # EOF: child closed its side
                break
            out += data
        elif proc.poll() is not None:
            break
    # final drain for any buffered output
    try:
        while True:
            r, _, _ = select.select([m], [], [], 0.15)
            if not r:
                break
            data = os.read(m, 4096)
            if not data:
                break
            out += data
    except OSError:
        pass
    try:
        os.close(m)
    except OSError:
        pass
    try:
        proc.wait(timeout=2)
    except Exception:
        pass
    text = out.decode("utf-8", "replace")
    text = text.replace("\r\n", "\n").replace("\r", "\n")
    return text.rstrip("\n")


def verify(challenge: dict, code: str, stdout: str) -> tuple[bool, str]:
    """Lenient, output-driven check: the result just has to contain the expected
    text (however you wrote it), and use the named technique if one is required.
    There's no single 'right way' — the rules bend, but the key idea must land."""
    out = stdout.lower()
    missing = [e for e in challenge.get("expect", []) if e.lower() not in out]
    if missing:
        return False, "output should contain " + ", ".join(repr(m) for m in missing)
    missing_need = [n for n in challenge.get("need", []) if n not in code]
    if missing_need:
        return False, "try to use " + ", ".join(repr(m) for m in missing_need)
    return True, ""


# ---- plain-English error translation --------------------------------------- #
# The traceback-reading gap: beginners freeze at a red wall of text. These
# turn the LAST line of a crash into "oh, I forgot quotes" — the skill that
# actually teaches someone to READ an error instead of pasting it somewhere.

def _traceback_last_line(hint: str) -> str:
    lines = [ln.strip() for ln in hint.strip().splitlines() if ln.strip()]
    return lines[-1] if lines else hint.strip()


def _looks_like_traceback(hint: str) -> bool:
    """True when `hint` is a Python crash report rather than a verify message."""
    if not hint:
        return False
    h = hint.strip()
    if h.startswith("Traceback"):
        return True
    lines = [ln.strip() for ln in h.splitlines() if ln.strip()]
    return bool(lines and re.match(r"^\w+(Error|Exception)\b", lines[-1]))


def translate_error(stderr: str) -> str:
    """Plain-English meaning of a crash, read from its final traceback line.
    Returns '' when nothing is recognized. Teaches reading, not memorizing."""
    if not stderr:
        return ""
    last = _traceback_last_line(stderr)

    if "did you mean" in last.lower():
        m = re.search(r"name '(\w+)' is not defined", last)
        name = m.group(1) if m else ""
        return (f"You misspelled `{name}`" if name else "You misspelled a name") + \
               ". Python has a suggestion for what you meant — check the exact spelling."

    m = re.search(r"NameError: name '(\w+)' is not defined", last)
    if m:
        name = m.group(1)
        return (f"You used `{name}` before Python knew what it was. Make it first "
                f"(`{name} = ...`) — or if `{name}` was meant to be a WORD, put it in quotes: \"{name}\".")
    if "IndentationError" in last or "expected an indented block" in last or "unexpected indent" in last:
        return ("Your spacing is off. Everything inside an if / else / for / def must be "
                "indented the same amount — usually 4 spaces. The colon says 'a block starts', "
                "the spaces say 'this is inside it'.")
    if "SyntaxError" in last:
        if "EOL while scanning" in last:
            return ("Python hit the end of the line before you closed a quote. "
                    "Check for a missing \" or ' at the end of a string.")
        return ("Python can't read this line. Check for a missing colon : after an "
                "if/else/for/def, a missing quote, or mismatched ( ) [ ] { }.")
    if "ZeroDivisionError" in last:
        return "You divided by zero, which has no answer. Check the denominator — it's probably 0."
    if "invalid literal for int()" in last:
        return ("int() only turns DIGITS into a number. You fed it something that isn't "
                "a number. Check what's inside int(...).")
    if "KeyError" in last:
        return ("You asked for a key that isn't in the dictionary. Check spelling and case — "
                "\"bob\" and \"Bob\" are different keys.")
    if "IndexError" in last or "out of range" in last:
        return ("You pointed past the end. Indexes start at 0, so a 3-item list only has "
                "[0], [1], [2] — [3] is off the edge.")
    if "AttributeError" in last:
        return ("You called something that doesn't exist on that object. Check the spelling "
                "of the method/attribute, or that it's the right kind of object.")
    if "TypeError" in last:
        if "can only concatenate str" in last:
            return ("You tried to glue text and a number with +. Turn the number into text "
                    "with str(...), or use an f-string: f\"total: {x}\".")
        if "unsupported operand" in last:
            return ("You used a math operator on something that can't do math — like adding "
                    "text and a number. Convert it first with int() or str().")
        if "not subscriptable" in last:
            return ("You put [ ] on something you can't index — like a number. Only lists, "
                    "strings and dicts take [ ].")
        if "not callable" in last:
            return ("You put ( ) on something that isn't a function. Did you name a variable "
                    "the same as a function, or forget the function's name?")
        if "not iterable" in last:
            return ("You tried to loop over something that can't be looped. A plain number "
                    "isn't a list — did you forget the range()?")
        if "takes" in last and "argument" in last:
            return ("You called the function with the wrong number of inputs. Check its def "
                    "line to see how many it expects.")
    if "EOFError" in last:
        return "The program asked for input() but you didn't type anything. Give it a value."
    if "UnboundLocalError" in last:
        return ("You're reading a variable inside a function before assigning it there. Set it "
                "first inside the function.")
    if "RecursionError" in last:
        return "Your function calls itself with no way to stop — check the base case (the 'if' that ends it)."
    if "FileNotFoundError" in last:
        return "The file you asked for doesn't exist. Check the path and spelling."
    if "OverflowError" in last:
        return "A number got too big. Check for an accidental huge loop or exponent."
    return ""


def _norm_lines(s: str) -> list[str]:
    out = []
    for ln in s.splitlines():
        ln = re.sub(r"\s+", " ", ln).strip()
        if ln:
            out.append(ln)
    return out


def _match_output(guess: str, actual: str) -> bool:
    """Compare a predicted output against the real one, ignoring extra blank
    lines and stray spaces (but NOT case — 'Even' and 'even' are different)."""
    return _norm_lines(guess) == _norm_lines(actual)


# ---- voice ---------------------------------------------------------------- #

def _piper_bin() -> str | None:
    """The Piper neural-TTS binary. Prefer ~/.local/bin/piper (uv-installed TTS);
    /usr/bin/piper is an unrelated mouse-config GUI, so don't trust that name
    alone on the PATH."""
    local = Path.home() / ".local" / "bin" / "piper"
    if local.exists():
        return str(local)
    for name in ("piper", "piper-tts"):
        p = shutil.which(name)
        if p:
            return p
    return None


def _tts_engine() -> str | None:
    if _piper_bin():
        return "piper"
    if shutil.which("espeak-ng"):
        return "espeak"
    return None


def _piper_voice() -> str | None:
    """Best available English Piper voice. Prefers the most natural (high quality)
    voices first; ryan-high stays as the male fallback."""
    pref = ("lessac-high", "libritts-high", "ljspeech-high", "ryan-high",
            "lessac", "libritts", "ljspeech", "ryan", "alan", "joe", "danny",
            "hfc_male", "en_GB", "en_US", "en")
    found: list[Path] = []
    for base in (Path.home() / ".local/share/piper", Path("/usr/share/piper-voices")):
        if base.exists():
            found.extend(p for p in base.rglob("*.onnx") if not p.name.endswith(".onnx.json"))
    if not found:
        return None
    for tag in pref:
        for p in found:
            if tag.lower() in p.name.lower():
                return str(p)
    return str(found[0])


# Active Piper TTS processes + a generation counter, so a new speak() can
# interrupt the previous one — voices never overlap.
_PIPER_PROCS: list = []
_PIPER_GEN = 0

# Slightly slower "teaching" speech rate for lessons + live feedback (piper
# length_scale: 1.0 = normal, 1.2 = 20% slower). Word-highlight durations are
# measured from the raw audio bytes, so they stay in sync at any rate.
TEACH_RATE = 1.12


def _kill_piper() -> None:
    global _PIPER_PROCS
    for p in _PIPER_PROCS:
        try:
            p.kill()
        except Exception:
            pass
    _PIPER_PROCS = []


def _prep_tts(text: str) -> str:
    """Prepare text for the voice: turn punctuation/operators piper can't pronounce
    (quotes, parens, brackets, braces, =, ==, %, **, +=, ...) into spoken WORDS so
    code reads naturally, then strip leftover markdown noise. Commas/periods/colons
    are left as-is — piper reads them as natural pauses."""
    clean = text
    # operators FIRST (longest match first so "==" isn't split into two "=")
    clean = clean.replace("==", " double equals ")
    clean = clean.replace("!=", " not equal ")
    clean = clean.replace("<=", " less than or equal ")
    clean = clean.replace(">=", " greater than or equal ")
    clean = clean.replace("+=", " plus equals ")
    clean = clean.replace("-=", " minus equals ")
    clean = clean.replace("+", " plus ")
    clean = clean.replace("**", " to the power of ")
    clean = clean.replace("->", " arrow ")
    clean = clean.replace("%", " percent ")
    clean = clean.replace("*", " times ")
    clean = clean.replace("=", " equals ")
    # empty delimiters written out in prose ("{ }", "( )", "[ ]") just name the
    # symbols, so the regex below doesn't turn them into "is between curly braces"
    clean = clean.replace("{ }", " curly braces ")
    clean = clean.replace("{}", " curly braces ")
    clean = clean.replace("[ ]", " square brackets ")
    clean = clean.replace("[]", " square brackets ")
    clean = clean.replace("( )", " parentheses ")
    clean = clean.replace("()", " parentheses ")
    # structural punctuation piper can't say — put the VALUE first so it reads
    # naturally ("name is between curly braces", NOT "between curly braces name").
    # Paired delimiters are reordered via regex: the inner value keeps its place,
    # the delimiter phrase moves after it.
    clean = re.sub(r"\{([^{}]*)\}", r" \1 is between curly braces", clean)
    clean = re.sub(r"\[([^\[\]]*)\]", r" \1 is between brackets", clean)
    clean = re.sub(r"\(([^()]*)\)", r" \1 is between parentheses", clean)
    # quotes: "bob" -> bob is between quotes (value first), then any lone quote
    clean = re.sub(r'"([^"]*)"', r" \1 is between quotes", clean)
    clean = clean.replace('"', " quote ")
    # strip leftover markdown noise
    clean = re.sub(r"[_`#>~|\\]", "", clean)
    clean = re.sub(r"\s+", " ", clean).strip()
    return clean


def speak(text: str, rate: float = 1.0) -> None:
    global _PIPER_GEN
    clean = _prep_tts(text)
    if not clean:
        return
    engine = _tts_engine()
    if engine == "piper":
        _PIPER_GEN += 1
        gen = _PIPER_GEN
        _kill_piper()  # stop whatever was speaking
        # synthesize via the persistent daemon, then play — same backend as the
        # lesson captions, so there's only ONE model load per session.
        threading.Thread(target=_speak_synth, args=(clean, gen, rate), daemon=True).start()
    elif engine == "espeak":
        subprocess.Popen(["espeak-ng", "-s", "150", "-a", "200", clean],
                         stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)


def _speak_synth(text: str, gen: int, rate: float = 1.0) -> None:
    raw = synthesize(text, rate)
    if gen != _PIPER_GEN:
        return  # a newer speak() took over while we were synthesizing
    if raw:
        play_raw(raw)


# Persistent piper process + a lock, so the voice model is loaded ONCE instead
# of paying a ~1.8s model-load on every utterance.
_SERVER = None  # (Popen, Lock) or None
_SERVER_LOCK = threading.Lock()  # guards daemon spawn (double-checked)


def _server_python() -> str | None:
    """Python interpreter that has the `piper` package (the piper-tts uv-tool env)."""
    p = Path.home() / ".local" / "share" / "uv" / "tools" / "piper-tts" / "bin" / "python"
    if p.exists():
        return str(p)
    return None


def _server_script() -> str | None:
    p = Path.home() / ".learning" / "piper_daemon.py"
    return str(p) if p.exists() else None


def _ensure_server():
    global _SERVER
    if _SERVER is not None:
        proc, _ = _SERVER
        if proc.poll() is None:
            return _SERVER
    with _SERVER_LOCK:
        if _SERVER is not None:
            proc, _ = _SERVER
            if proc.poll() is None:
                return _SERVER
        py = _server_python()
        script = _server_script()
        voice = _piper_voice()
        if not (py and script and voice):
            return None
        try:
            proc = subprocess.Popen([py, script, voice],
                                    stdin=subprocess.PIPE, stdout=subprocess.PIPE,
                                    stderr=subprocess.DEVNULL)
        except Exception:
            return None
        _SERVER = (proc, threading.Lock())
        return _SERVER


def _reset_server() -> None:
    global _SERVER
    if _SERVER is not None:
        try:
            _SERVER[0].kill()
        except Exception:
            pass
    _SERVER = None


def _synthesize_cli(text: str, rate: float = 1.0) -> bytes | None:
    voice = _piper_voice()
    bin = _piper_bin()
    if not (voice and bin):
        return None
    try:
        r = subprocess.run([bin, "--model", voice, "--output-raw",
                            "--sentence-silence", "0.2",
                            "--length-scale", f"{rate:.2f}"],
                           input=text.encode(), capture_output=True, timeout=60)
        return r.stdout or None
    except Exception:
        return None


def synthesize(text: str, rate: float = 1.0) -> bytes | None:
    """Synthesize `text` to raw PCM via piper. Uses a persistent process (fast);
    falls back to a one-shot CLI call if the daemon isn't available. Returns the
    raw bytes, or None. Capturing lets us know the EXACT audio duration so the
    caption highlight can stay in sync. `rate` is the length_scale (1.2 = 20% slower)."""
    text = _prep_tts(text)
    srv = _ensure_server()
    if srv is not None:
        proc, lock = srv
        with lock:
            try:
                data = text.encode("utf-8")
                rate_byte = bytes([max(1, min(25, int(round(rate * 10))))])
                proc.stdin.write(rate_byte + struct.pack(">I", len(data)) + data)
                proc.stdin.flush()
                hdr = proc.stdout.read(4)
                if len(hdr) != 4:
                    _reset_server()
                    return _synthesize_cli(text, rate)
                (n,) = struct.unpack(">I", hdr)
                raw = proc.stdout.read(n)
                if len(raw) != n:
                    _reset_server()
                    return _synthesize_cli(text, rate)
                return raw
            except Exception:
                _reset_server()
                return _synthesize_cli(text, rate)
    return _synthesize_cli(text, rate)


def _warmup_server() -> None:
    """Pre-load the piper voice in the background so the first caption isn't
    delayed by the one-time ~1.8s model load. Safe to call repeatedly."""
    try:
        synthesize("ready.")
    except Exception:
        pass


def play_raw(raw: bytes) -> None:
    """Play raw PCM (22050 Hz S16_LE mono) via aplay, tracked so it can be killed.

    The bytes are fed on a background thread: writing them straight into aplay's
    stdin would block for the whole audio duration (aplay consumes the pipe at
    real-time speed), which would delay the caption highlight until the voice is
    already done."""
    global _PIPER_PROCS
    _kill_piper()  # stop any prior sentence's audio before this one starts
    try:
        p = subprocess.Popen(["aplay", "-r", "22050", "-f", "S16_LE", "-t", "raw"],
                             stdin=subprocess.PIPE, stdout=subprocess.DEVNULL,
                             stderr=subprocess.DEVNULL)
        _PIPER_PROCS = [p]

        def _feed():
            try:
                p.stdin.write(raw)
            except Exception:
                pass
            try:
                p.stdin.close()
            except Exception:
                pass

        threading.Thread(target=_feed, daemon=True).start()
    except Exception:
        pass


SUCCESS_SOUND = "/usr/share/sounds/freedesktop/stereo/complete.oga"


def play_complete() -> None:
    """Completion chime at full volume."""
    try:
        subprocess.Popen(["paplay", "--volume=65536", SUCCESS_SOUND],
                         stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    except Exception:
        pass


def play_streak(streak: int) -> None:
    """A rising 'multi-kill' celebration: each correct answer in a row pitches
    the note higher. Streak 1 = low note, 2 = higher, 3+ = rising arpeggio.
    Resets when you fail. Generated as a short WAV at <=50% volume."""
    try:
        rate = 22050
        base = 330.0  # E4
        # climb a minor-pentatonic-ish ladder with each streak
        note = base * (2 ** (min(streak - 1, 8) / 12 * 2))  # 2 semitones per streak, capped
        n = int(rate * 0.18)
        buf = bytearray()
        for i in range(n):
            # small fade to avoid a click
            env = min(1.0, i / (rate * 0.02), (n - i) / (rate * 0.05))
            v = int(30000 * env * math.sin(2 * math.pi * note * i / rate))
            buf += struct.pack("<h", v)
        path = Path(tempfile.gettempdir()) / "tutor_streak.wav"
        with wave.open(str(path), "w") as w:
            w.setnchannels(1); w.setsampwidth(2); w.setframerate(rate)
            w.writeframes(bytes(buf))
        subprocess.Popen(["paplay", "--volume=65536", str(path)],
                         stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    except Exception:
        pass


_KEY_SOUNDS = True


def set_key_sounds(on: bool) -> None:
    """Master switch for the typing 'thock' + menu blips (settings checkbox)."""
    global _KEY_SOUNDS
    _KEY_SOUNDS = on


def key_sounds() -> bool:
    return _KEY_SOUNDS


def play_menu_blip(pitch: int = 0) -> None:
    """Short menu navigation blip. `pitch` = semitones above A3."""
    if not _KEY_SOUNDS:
        return
    try:
        rate = 22050
        note = 220.0 * (2 ** (pitch / 12))
        n = int(rate * 0.05)
        buf = bytearray()
        for i in range(n):
            env = min(1.0, i / (rate * 0.01), (n - i) / (rate * 0.02))
            v = int(30000 * env * math.sin(2 * math.pi * note * i / rate))
            buf += struct.pack("<h", v)
        path = Path(tempfile.gettempdir()) / "tutor_menu.wav"
        with wave.open(str(path), "w") as w:
            w.setnchannels(1); w.setsampwidth(2); w.setframerate(22050)
            w.writeframes(bytes(buf))
        subprocess.Popen(["paplay", "--volume=65536", str(path)],
                         stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    except Exception:
        pass


def play_output_tick() -> None:
    """A soft, quiet 'console print' tick per streamed char — a gentle teletype
    click instead of the old harsh beep. Gated by the key-sounds switch."""
    if not _KEY_SOUNDS:
        return
    try:
        rate = 22050
        n = int(rate * 0.02)   # 20ms
        buf = bytearray()
        for i in range(n):
            env = (n - i) / n
            v = int(9000 * env * math.sin(2 * math.pi * 1800 * i / rate))
            buf += struct.pack("<h", v)
        path = Path(tempfile.gettempdir()) / "tutor_print.wav"
        with wave.open(str(path), "w") as w:
            w.setnchannels(1); w.setsampwidth(2); w.setframerate(rate)
            w.writeframes(bytes(buf))
        subprocess.Popen(["paplay", "--volume=32768", str(path)],
                         stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    except Exception:
        pass


def _sweep(notes, fname, dur=0.12, vol=28000, rate=22050):
    """Synthesize a short multi-note blip into a temp WAV, return its path."""
    n = int(rate * dur)
    seg = n // max(1, len(notes))
    buf = bytearray()
    for k, note in enumerate(notes):
        for i in range(seg):
            j = k * seg + i
            if j >= n:
                break
            env = min(1.0, i / (rate * 0.01), (seg - i) / (rate * 0.03))
            buf += struct.pack("<h", int(vol * env * math.sin(2 * math.pi * note * j / rate)))
    path = Path(tempfile.gettempdir()) / fname
    with wave.open(str(path), "w") as w:
        w.setnchannels(1); w.setsampwidth(2); w.setframerate(rate)
        w.writeframes(bytes(buf))
    return path


def play_console_result(good: bool) -> None:
    """The console 'output' sound — fires ONCE when a run result is stamped.
    Good output gets a clean rising 'ding'; bad (error) output a low buzz."""
    try:
        notes = (659.25, 880.0) if good else (220.0, 164.81)
        path = _sweep(notes, "tutor_good.wav" if good else "tutor_bad.wav")
        subprocess.Popen(["paplay", "--volume=49152", str(path)],
                         stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    except Exception:
        pass


def play_ghost_error() -> None:
    """A comedic 'womp' for a mistyped ghost letter — three quick descending blips."""
    try:
        path = _sweep((392.0, 311.13, 246.94), "tutor_ghost_err.wav", dur=0.16, vol=24000)
        subprocess.Popen(["paplay", "--volume=49152", str(path)],
                         stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    except Exception:
        pass


KEYPRESS_DIR = Path.home() / ".learning" / "keypress"
_KEY_POOL: list[Path] = []


def _load_key_pool() -> None:
    """Shuffle the mechanical keypress samples so no clip repeats in a cycle."""
    global _KEY_POOL
    files = sorted(KEYPRESS_DIR.glob("keypress-*.wav"))
    if not files:                      # soundpack not installed -> fall back below
        return
    random.shuffle(files)
    _KEY_POOL = files


def play_key() -> None:
    """A real mechanical-keyboard keypress (thock) on every key.

    Uses the user's own samples from the unicae_games soundpack. Each sample is
    a distinct physical key, so cycling through them shuffled sounds like real
    typing instead of one repeated tick. Falls back to a tiny synthetic click
    only if the soundpack directory is missing."""
    if not _KEY_SOUNDS:
        return
    global _KEY_POOL
    try:
        if not _KEY_POOL:
            _load_key_pool()
        if _KEY_POOL:
            path = _KEY_POOL.pop()
            subprocess.Popen(["paplay", "--volume=65536", str(path)],
                             stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            return
        # no soundpack — keep a quiet synthetic tick so typing still feels alive
        rate = 22050
        n = int(rate * 0.03)  # 30ms
        buf = bytearray()
        for i in range(n):
            env = (n - i) / n
            v = int(30000 * env * math.sin(2 * math.pi * 2400 * i / rate))
            buf += struct.pack("<h", v)
        path = Path(tempfile.gettempdir()) / "tutor_key.wav"
        with wave.open(str(path), "w") as w:
            w.setnchannels(1); w.setsampwidth(2); w.setframerate(rate)
            w.writeframes(bytes(buf))
        subprocess.Popen(["paplay", "--volume=65536", str(path)],
                         stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    except Exception:
        pass


# ---- celebration music (the user's own win / fail sounds) ----------------- #

MUSIC_DIR = Path.home() / "Music"


def _music_list(*patterns) -> list[Path]:
    """Sorted audio files under ~/Music matching any glob pattern."""
    out: list[Path] = []
    for p in patterns:
        out.extend(sorted(MUSIC_DIR.glob(p)))
    return out


CEL_SOUNDS = _music_list("cel*.mp3")
FAIL_SOUNDS = _music_list("fail*.mp3", "fafil*.mp3")


def play_file(path: Path, volume: float = 0.7) -> None:
    """Play a win/fail mp3 at REDUCED volume (70% — 30% below the TTS voice) so
    the celebration/fail sting never drowns out the coach's spoken feedback."""
    if path is None:
        return
    p = str(path)
    vol100 = int(round(volume * 100))       # ffplay/mpv use 0..100
    vol16 = int(round(volume * 65536))      # paplay uses 0..65536
    for cmd in (["ffplay", "-nodisp", "-autoexit", "-loglevel", "quiet",
                 "-volume", str(vol100), p],
                ["mpv", "--no-video", "--really-quiet", f"--volume={vol100}", p],
                ["paplay", f"--volume={vol16}", p],
                ["pw-play", p]):
        if shutil.which(cmd[0]):
            try:
                subprocess.Popen(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
                return
            except Exception:
                continue


# ---- tier-complete cat clip (real video, not ASCII) ----------------------- #

CAT_VIDEO = Path.home() / "Downloads" / "catmicrowave.mp4"
CAT_VIDEO_S = 5.6   # clip length + mpv window-open latency — timer fires just after it ends


def play_video(path: Path, volume: float = 1.0, mute: bool = False):
    """Play an mp4 FULLSCREEN, borderless, and always-on-top — a centered overlay
    that covers the terminal (a loading screen), not a separate tiled window.
    Returns the process (or None) so the caller can kill it if the user leaves
    early. On Wayland/Hyprland a floating window gets tiled to the side, so
    `--fs` is the reliable way to center it over the terminal."""
    if path is None or not path.exists():
        return None
    p = str(path)
    vol100 = int(round(volume * 100))
    m1 = ["mpv", "--fs", "--really-quiet", "--keep-open=no", "--loop=no",
          "--ontop", "--no-border", f"--volume={vol100}", p]
    if mute:
        m1.insert(-1, "--mute")
    f1 = ["ffplay", "-autoexit", "-loglevel", "quiet", "-fs", "-noborder",
          "-window_title", "tutor", "-volume", str(vol100), p]
    if mute:
        f1.insert(-1, "-an")
    for cmd in (m1, f1):
        if shutil.which(cmd[0]):
            try:
                return subprocess.Popen(cmd, stdout=subprocess.DEVNULL,
                                        stderr=subprocess.DEVNULL)
            except Exception:
                continue
    return None


# --------------------------------------------------------------------------- #
# Python syntax highlighting (VS Code "Dark+" palette)
# --------------------------------------------------------------------------- #

_PY_KW = {"def", "return", "if", "elif", "else", "for", "while", "in", "import",
          "from", "as", "class", "try", "except", "finally", "with", "and", "or",
          "not", "pass", "break", "continue", "lambda", "None", "True", "False",
          "print", "input", "range", "len", "int", "str", "float", "list", "dict"}
_PY_KW_COLOR = "#569cd6"       # blue
_STR_COLOR = "#ce9178"         # orange
_NUM_COLOR = "#b5cea8"         # light green
_COM_COLOR = "#6a9955"         # green
_FUNC_COLOR = "#dcdcaa"        # yellow


def highlight_line(line: str, emph_spans: set | None = None,
                   emph_style: str = "bold #facc15") -> Text:
    """Color one line of Python: keywords blue, strings orange, numbers green,
    comments green, function calls yellow. Numbers that overlap an `emph_span`
    are drawn with `emph_style` instead (used to spotlight range boundaries)."""
    t = Text()
    emph_spans = emph_spans or set()
    i = 0
    n = len(line)
    while i < n:
        ch = line[i]
        # comment
        if ch == "#":
            t.append(line[i:], style=_COM_COLOR)
            break
        # string
        if ch in "\"'":
            q = ch
            j = i + 1
            if line[i:i+2] in ("f\"", "f'", "F\"", "F'"):
                j = i + 2
                q = line[i+1]
            while j < n and line[j] != q:
                j += 1
            t.append(line[i:j+1], style=_STR_COLOR)
            i = j + 1
            continue
        # number
        if ch.isdigit():
            j = i
            while j < n and (line[j].isdigit() or line[j] == "."):
                j += 1
            if any(i >= s and j <= e for (s, e) in emph_spans):
                t.append(line[i:j], style=emph_style)
            else:
                t.append(line[i:j], style=_NUM_COLOR)
            i = j
            continue
        # identifier / keyword
        if ch.isalpha() or ch == "_":
            j = i
            while j < n and (line[j].isalnum() or line[j] == "_"):
                j += 1
            word = line[i:j]
            if word in _PY_KW:
                t.append(word, style=_PY_KW_COLOR)
            elif j < n and line[j] == "(":
                t.append(word, style=_FUNC_COLOR)
            else:
                t.append(word)
            i = j
            continue
        t.append(ch)
        i += 1
    return t


def _code_text(line: str) -> Text:
    """Code with its syntax colors (keywords/strings/numbers) AND bold, so it
    reads BIGGER than the plain explanation text below — the code is the star,
    the explanation stays plain."""
    t = highlight_line(line)
    t.stylize("bold")
    return t


def _reveal_output_lines(text: str, upto: int) -> list[Text]:
    """Render console output as it 'prints': the first `upto` characters in
    green, a BLUE block cursor on the leading edge (the 'thing running' marker),
    and the unprinted tail blanked so every line keeps its final width — the box
    never breathes while the output streams in. Returns one Text per line."""
    upto = max(0, min(upto, len(text)))
    out: list[Text] = []
    pos = 0
    for line in text.split("\n"):
        n = len(line)
        start, end = pos, pos + n
        t = Text()
        if upto < start:
            t.append(" " * n)                       # line not reached yet
        elif upto < end:
            shown = upto - start                    # chars already printed on this line
            if shown:
                t.append(line[:shown], style="bold green")
            t.append(line[shown], style="black on #3b82f6 bold")   # blue cursor
            t.append(" " * (n - shown - 1))
        else:
            t.append(line, style="bold green")       # fully printed line
        out.append(t)
        pos = end + 1
    return out


def _box_lines(lines: list[Text], title: str = "", center: bool = False,
               min_width: int = 0) -> Text:
    """Wrap styled lines in a rounded single-line box. Returns a multiline Text.
    `center=True` centers each line inside the box (for prose); code stays
    left-aligned by default. `min_width` forces the box to at least this inner
    width (used to make the VIM editor fill the screen)."""
    if not lines:
        lines = [Text("")]
    inner = max([ln.cell_len for ln in lines] + ([len(title)] if title else []))
    inner = max(inner, min_width)
    t = Text()
    t.append("┌" + "─" * (inner + 2) + "┐", style="dim")
    t.append("\n")
    if title:
        pad = max(0, inner - len(title))
        left = pad // 2
        t.append("│ ", style="dim")
        t.append(" " * left)
        t.append(title, style="bold yellow")
        t.append(" " * (pad - left))
        t.append(" │", style="dim")
        t.append("\n")
    for ln in lines:
        pad = inner - ln.cell_len
        left = pad // 2 if center else 0
        right = pad - left
        t.append("│ ", style="dim")
        t.append(" " * left)
        t.append_text(ln)
        t.append(" " * right)
        t.append(" │", style="dim")
        t.append("\n")
    t.append("└" + "─" * (inner + 2) + "┘", style="dim")
    return t


def _center_screen(content: Text, width: int, height: int) -> Text:
    """Center a (usually boxed) multiline Text both ways within a WxH region."""
    lines = content.split("\n")
    inner_w = max((ln.cell_len for ln in lines), default=0)
    left = max(0, (width - inner_w) // 2)
    top = max(0, (height - len(lines)) // 2)
    t = Text()
    if top:
        t.append("\n" * top)
    for i, ln in enumerate(lines):
        if left:
            t.append(" " * left)
        t.append_text(ln)
        if i < len(lines) - 1:
            t.append("\n")
    return t


def _lines_of(t: Text) -> list[Text]:
    """Split a multiline Text into one styled Text per line (so `_box_lines` can
    pad/border each line correctly — a multiline Text passed whole breaks the
    right border on every line but the first)."""
    try:
        return list(t.split("\n"))
    except Exception:
        return [t]


def _wrap_words(text: str, width: int) -> list[str]:
    """Word-wrap plain text to `width` columns (for the 'why'/explanation lines)."""
    width = max(1, width)
    out = []
    for para in text.split("\n"):
        words = para.split()
        if not words:
            out.append("")
            continue
        cur = words[0]
        for w in words[1:]:
            if len(cur) + 1 + len(w) > width:
                out.append(cur)
                cur = w
            else:
                cur += " " + w
        out.append(cur)
    return out


def _char_wrap(text: str, width: int) -> list[str]:
    """Char-wrap a string to `width` cols, breaking at spaces when possible
    (for code lines that are longer than the sidebar box)."""
    width = max(1, width)
    if len(text) <= width:
        return [text]
    chunks = []
    while len(text) > width:
        cut = text.rfind(" ", 0, width)
        if cut < 1:
            cut = width
        chunks.append(text[:cut])
        text = text[cut:].lstrip()
    if text:
        chunks.append(text)
    return chunks


def _wrap_console(text: str, width: int) -> str:
    """Wrap every line of `text` to `width` columns (hard char-wrap, like a real
    terminal) so multi-value output stays inside the console instead of spilling
    out the side of the box."""
    width = max(1, width)
    out: list[str] = []
    for line in text.split("\n"):
        if len(line) <= width:
            out.append(line)
        else:
            while len(line) > width:
                out.append(line[:width])
                line = line[width:]
            out.append(line)
    return "\n".join(out)


def _cap_lines(text: str, max_lines: int) -> str:
    """Truncate a multi-line printout to `max_lines` lines, appending a
    '… and N more lines' marker — so a huge loop that prints 1000 numbers can
    never push the console off the bottom of the screen."""
    lines = text.split("\n")
    if len(lines) <= max_lines:
        return text
    hidden = len(lines) - max_lines
    return "\n".join(lines[:max_lines]) + f"\n… and {hidden} more line{'s' if hidden != 1 else ''}"


# Console output is capped to the room the ghost overlay actually has, minus the
# head/code/why/foot regions (~20 rows). Small outputs — like range(2,12) → 2..11
# — show EVERY number; only a genuinely huge printout (a loop printing 1000
# values) gets truncated with the '… and N more lines' marker. 8 is the floor so
# a very short terminal never clips the console to zero lines.
GHOST_MIN_OUTPUT_LINES = 8
GHOST_OUTPUT_HEADROOM = 20


def _flatten_out(text: str, max_items: int = 6) -> str:
    """Flatten a multi-line output into one short spoken line ('1, 2, 3, …')."""
    vals = [v for v in (text or "").split("\n") if v != ""]
    if not vals:
        return "nothing"
    if len(vals) <= max_items:
        return ", ".join(vals)
    return ", ".join(vals[:max_items]) + ", …"


def _indexed_list(s: str) -> list[str] | None:
    """If `s` is a Python list/tuple literal, return its items as '0→item',
    '1→item', … so the zero-indexing rule ('0 is the FIRST item') is spelled
    out instead of hidden in the repr. Else None."""
    try:
        v = ast.literal_eval(s)
    except Exception:
        return None
    if isinstance(v, (list, tuple)):
        return [f"{i}→{x}" for i, x in enumerate(v)]
    return None


def _range_boundary_spans(line: str) -> set[tuple[int, int]]:
    """(start, end) spans of the FIRST and LAST numeric argument inside every
    `range(...)` on the line — i.e. the 'start' and 'stop-before' numbers, the
    confusing part of range that's worth spotlighting."""
    spans: set[tuple[int, int]] = set()
    for m in re.finditer(r"range\s*\((.*?)\)", line):
        inner = m.group(1)
        base = m.start(1)
        nums = list(re.finditer(r"-?\d+", inner))
        if not nums:
            continue
        keep = [nums[0], nums[-1]] if len(nums) >= 2 else nums
        for mm in keep:
            spans.add((base + mm.start(), base + mm.end()))
    return spans


_OP_SYMBOL = {
    ast.Add: "+", ast.Sub: "-", ast.Mult: "*", ast.Div: "/",
    ast.FloorDiv: "//", ast.Mod: "%", ast.Pow: "**",
    ast.Eq: "==", ast.NotEq: "!=", ast.Lt: "<", ast.LtE: "<=",
    ast.Gt: ">", ast.GtE: ">=", ast.Is: "is", ast.In: "in",
    ast.NotIn: "not in",
}


def _find_recursion(tree):
    """If `tree` defines a function that calls ITSELF, return
    (name, self_call, arg, base_cond, style) — else None.

    * self_call = the rendered self-call, e.g. "count(n - 1)"
    * arg       = just the argument it passes, e.g. "n - 1"
    * base_cond = the `if` condition that guards the stop, e.g. "n == 0"
    * style     = "return" (the self-call feeds a return, so the answer stacks
                  back up) or "print" (it prints on the way down).

    This is what lets the 'why' panel and the spoken tip actually explain HOW
    recursion works (call itself with a smaller number, stop at the base case)
    instead of just glossing the individual tokens."""
    for fn in ast.walk(tree):
        if not isinstance(fn, ast.FunctionDef):
            continue
        name = fn.name
        self_arg = None
        for node in ast.walk(fn):
            if (isinstance(node, ast.Call) and isinstance(node.func, ast.Name)
                    and node.func.id == name):
                arg = ""
                if node.args:
                    try:
                        arg = " ".join(ast.unparse(node.args[0]).split())
                    except Exception:
                        arg = ""
                self_arg = arg
                break
        if self_arg is None:
            continue
        base = None
        for node in ast.walk(fn):
            if isinstance(node, ast.If) and any(
                    isinstance(s, ast.Return) for s in node.body):
                try:
                    base = " ".join(ast.unparse(node.test).split())
                except Exception:
                    base = ""
                break
        # return-style: a `return` whose value contains a self-call (the answer
        # stacks back up); print-style: it prints on the way down.
        style = "print"
        for node in ast.walk(fn):
            if isinstance(node, ast.Return) and node.value is not None:
                if any(isinstance(n, ast.Call) and isinstance(n.func, ast.Name)
                       and n.func.id == name for n in ast.walk(node.value)):
                    style = "return"
                    break
        return (name, f"{name}({self_arg})", self_arg, base, style)
    return None


def _speak_val(node) -> str:
    """Spoken form of a value/expression node — natural words, NOT raw code.

    TTS must never read out punctuation as literal speech: 'Bean' became
    'quote Bean quote' and ['apple', 'banana'] became 'open bracket quote apple
    comma …'. This renders values the way a person would say them: Bean, apple,
    banana, alice is 30, bob is 25."""
    if node is None:
        return "?"
    if isinstance(node, ast.Constant):
        v = node.value
        if isinstance(v, bool):
            return "true" if v else "false"
        if isinstance(v, str):
            return v                       # the bare word — no quotes
        return repr(v)                     # numbers, None, etc.
    if isinstance(node, (ast.List, ast.Tuple, ast.Set)):
        return ", ".join(_speak_val(e) for e in node.elts)
    if isinstance(node, ast.Dict):
        pairs = []
        for k, v in zip(node.keys, node.values):
            if k is None:
                continue
            pairs.append(f"{_speak_val(k)} is {_speak_val(v)}")
        return ", ".join(pairs) or "an empty dictionary"
    try:
        return " ".join(ast.unparse(node).split())
    except Exception:
        return "?"


def _ordinal(n: int) -> str:
    """'first', 'second', ... for a zero-based index, so 'fruits[1]' can be
    explained as 'position 1 is the second item' instead of the muddled
    'position zero is the first item'."""
    words = ["first", "second", "third", "fourth", "fifth",
             "sixth", "seventh", "eighth", "ninth", "tenth"]
    if 0 <= n < len(words):
        return words[n]
    return f"number {n + 1}"


def _explain_code(code: str) -> list[tuple[str, str]]:
    """Personalized, AST-driven explanation of THIS snippet. Each item is a
    (token, meaning) pair where `token` is the exact variable / number / string
    in play — never a generic one-size-fits-all line. Most confusing idea first,
    so both the spoken tip and the on-screen 'why' panel read like someone
    pointing at the specific symbol that matters."""
    c = (code or "").strip()
    if not c:
        return []
    tree = None
    for src in (c, c + "\n    pass"):   # the second form lets a bare 'for …:' line parse
        try:
            tree = ast.parse(src)
            break
        except SyntaxError:
            continue
    if tree is None:
        return []   # genuinely non-compilable snippet — nothing reliable to say

    def val(node) -> str:
        """Short, readable rendering of a value node (for the spoken meaning)."""
        if node is None:
            return "?"
        try:
            s = " ".join(ast.unparse(node).split())
        except Exception:
            return "?"
        return s if len(s) <= 28 else s[:28] + "…"

    def lit(node) -> str:
        """A literal's spoken form — bare words, no quotes/brackets (so TTS
        says 'Bean', not 'quote Bean quote')."""
        return _speak_val(node)

    out: list[tuple[str, str]] = []

    # -- recursion: a function that calls itself. This is the MOST confusing idea
    #    in any snippet that has it, so explain it FIRST — the self-call, then the
    #    base case that stops it — before the generic per-token bits below.
    recur = _find_recursion(tree)
    if recur:
        name, self_call, arg, base, style = recur
        out.append((self_call,
                    f"{name} calls ITSELF with {arg} — a smaller number. "
                    f"that's the recursion: it repeats, shrinking the problem each time"))
        if base:
            out.append((base,
                        f"the stop sign (base case) — when {base} is true it returns "
                        f"instead of calling itself again, so it ends instead of looping forever"))

    # -- assignments + reassignment (the #1 confusion, explained first) --
    writes: dict[str, list[str]] = {}
    for node in ast.walk(tree):
        if isinstance(node, ast.Assign):
            for tgt in node.targets:
                if isinstance(tgt, ast.Name):
                    writes.setdefault(tgt.id, []).append(lit(node.value))
        elif isinstance(node, ast.AugAssign) and isinstance(node.target, ast.Name):
            op = _OP_SYMBOL.get(type(node.op), "=")
            writes.setdefault(node.target.id, []).append(
                f"{node.target.id} {op} {lit(node.value)}")
    for name, w in writes.items():
        if len(w) > 1:
            out.append((name,
                        f"{name} is written {len(w)} times — first {w[0]}, then {w[-1]}. "
                        f"the last write wins, so {name} ends up {w[-1]}"))
        else:
            out.append((name, f"a box that now holds {w[0]}"))

    # -- range(...): spotlight the actual numbers --
    for node in ast.walk(tree):
        if (isinstance(node, ast.Call) and isinstance(node.func, ast.Name)
                and node.func.id == "range" and not node.keywords):
            args = [lit(a) for a in node.args]
            if len(args) == 1:
                out.append((args[0], f"counts 0 up to {args[0]} — stops one short"))
            elif len(args) == 2:
                out.append((args[0], "start counting here"))
                out.append((args[1], f"stop one short of this — {args[1]} itself never shows up"))
            elif len(args) >= 3:
                out.append((args[0], "start counting here"))
                out.append((args[1], f"stop one short of this — {args[1]} itself never shows up"))
                out.append((args[2], f"jump by {args[2]} each time"))
            break

    # -- for loop: name the loop variable --
    for node in ast.walk(tree):
        if isinstance(node, ast.For) and isinstance(node.target, ast.Name):
            v = node.target.id
            out.append((v, f"each pass, {v} grabs the next number, so the block "
                           f"runs again with a fresh {v} — that's the repeat"))
            break

    # -- comparison: the true/false question --
    #    (skipped for recursion — the base-case explanation above already covers
    #    the `if` in a clearer "stop sign" way)
    if not recur:
        for node in ast.walk(tree):
            if isinstance(node, ast.Compare):
                left = val(node.left)
                opstr = " ".join(_OP_SYMBOL.get(type(o), "?") for o in node.ops)
                right = " ".join(val(c) for c in node.comparators)
                out.append((left, f"checks: is {left} {opstr} {right}? true or false"))
                break

    # -- f-string {name}: value-first — "name is between curly braces", not
    #    "the braces hold name". Name the thing, then say where it sits.
    for node in ast.walk(tree):
        if isinstance(node, ast.FormattedValue):
            expr = " ".join(ast.unparse(node.value).split())
            out.append((f"{{{expr}}}",
                        f"{expr} is between curly braces, so Python fills in its value"))

    # -- print(...): spotlight what actually gets shown --
    loop_vars = {n.target.id for n in ast.walk(tree)
                 if isinstance(n, ast.For) and isinstance(n.target, ast.Name)}
    for node in ast.walk(tree):
        if (isinstance(node, ast.Call) and isinstance(node.func, ast.Name)
                and node.func.id == "print"):
            if node.args:
                arg = node.args[0]
                if isinstance(arg, ast.Constant):
                    if isinstance(arg.value, str):
                        out.append((val(arg),
                                    f"{arg.value} is between quotes — the quotes make it a word — "
                                    f"and it gets shown on the screen"))
                    elif isinstance(arg.value, (int, float)) and not isinstance(arg.value, bool):
                        out.append((val(arg), "this number gets shown on the screen"))
                elif (isinstance(arg, ast.Name) and arg.id not in writes
                      and arg.id not in loop_vars):
                    out.append((val(arg), f"print shows {arg.id} on the screen"))
            break

    # -- subscript s[0] vs slice s[::-1]: an index pulls ONE item; a slice
    #    (step/range) pulls a chunk — say which, so a slice never gets the
    #    "one item out" gloss that's flat wrong for s[::2] or s[::-1] --
    for node in ast.walk(tree):
        if isinstance(node, ast.Subscript):
            base = val(node.value)
            sl = node.slice
            if isinstance(sl, ast.Constant) and isinstance(sl.value, int):
                i = sl.value
                out.append((f"{base}[{i}]", f"reaches into {base} and pulls out item {i}"))
                out.append((str(i),
                            f"position {i} is the {_ordinal(i)} item — "
                            f"computers count from zero"))
            elif isinstance(sl, ast.Slice):
                step = sl.step
                if (isinstance(step, ast.UnaryOp)
                        or (isinstance(step, ast.Constant)
                            and isinstance(step.value, int) and step.value < 0)):
                    out.append((f"{base}[::-1]", f"walks {base} backwards, one item at a time"))
                elif isinstance(step, ast.Constant) and isinstance(step.value, int) and step.value > 1:
                    out.append((f"{base}[::{step.value}]",
                                f"pulls every {_ordinal(step.value - 1)} item of {base}, skipping in between"))
                else:
                    out.append((f"{base}[...]", f"cuts a slice out of {base}"))
            else:
                idx = val(sl)
                out.append((f"{base}[{idx}]", f"reaches into {base} and pulls one item out"))
            break

    # -- def: the name you can call later --
    for node in ast.walk(tree):
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            out.append((node.name, f"gives this block the name {node.name}, so you can call it later"))
            break

    # drop exact repeats, cap length so the panel never overflows
    seen: set[tuple[str, str]] = set()
    final: list[tuple[str, str]] = []
    for pair in out:
        if pair in seen or len(final) >= 8:
            continue
        seen.add(pair)
        final.append(pair)
    return final


def _ghost_tip(code: str) -> str:
    """Spoken pointer about THIS example — the confusing bits explained in
    plain words, personalized to the actual variables/numbers in play (so two
    different examples never get the same generic line)."""
    bits = _explain_code(code)
    if not bits:
        return "watch how it runs top to bottom, one line at a time."
    parts: list[str] = []
    for _, m in bits[:3]:
        m = m.strip().rstrip(".")
        if m and m not in parts:
            parts.append(m)
    if not parts:
        return "watch how it runs top to bottom, one line at a time."
    return ". ".join(parts) + "."


def _ghost_result_tip(code: str, result: str) -> str:
    """One personalized spoken line explaining WHY the output looks the way it
    does — ties the printed result back to the exact rule in play (the actual
    numbers, names, and jump), never a canned 'and that's what print…' line."""
    vals = [v for v in (result or "").split("\n") if v != ""]
    c = (code or "").strip()
    if not c:
        return ""
    tree = None
    for src in (c, c + "\n    pass"):
        try:
            tree = ast.parse(src)
            break
        except SyntaxError:
            continue
    if tree is None:
        return f"and it printed {vals[-1]}" if vals else ""

    def lit(node) -> str:
        # spoken form: bare words, no quotes/brackets (shared helper)
        return _speak_val(node)

    # recursion: a function that calls itself — explain the printed output as
    # the count-down/stack, not a flat "it printed the last value".
    recur = _find_recursion(tree)
    if recur and vals:
        name, self_call, arg, base, style = recur
        shown = ", ".join(vals[:6])
        if len(vals) > 6:
            shown += ", …"
        stop = f"then {base} became true and the base case stopped it" if base \
            else "then the base case stopped it"
        if style == "return":
            return (f"{name} kept calling itself with smaller numbers and "
                    f"stacked the answers back up — the final answer is {vals[-1]}. {stop}.")
        if len(vals) > 1:
            return (f"{name} kept calling itself with a smaller number, printing "
                    f"each one on the way down: {shown}. {stop}.")
        return (f"{name} called itself once with {arg}, printed {shown}, "
                f"and {stop}.")

    # reassignment: the last write wins
    writes: dict[str, list[str]] = {}
    for node in ast.walk(tree):
        if isinstance(node, ast.Assign):
            for tgt in node.targets:
                if isinstance(tgt, ast.Name):
                    writes.setdefault(tgt.id, []).append(lit(node.value))
    for name, w in writes.items():
        if len(w) > 1 and vals:
            return (f"look — {name} was written {len(w)} times, {w[0]} then {w[-1]}. "
                    f"the last write wins, so print showed {vals[-1]}.")

    # single assignment printed out: 'print showed what was in the box'
    if len(writes) == 1 and vals:
        name, w = next(iter(writes.items()))
        for node in ast.walk(tree):
            if (isinstance(node, ast.Call) and isinstance(node.func, ast.Name)
                    and node.func.id == "print" and node.args
                    and isinstance(node.args[0], ast.Name)
                    and node.args[0].id == name):
                return f"print showed what was in the box {name}: {w[0]}."

    # range(...): the printed values follow the start/stop/step rule
    for node in ast.walk(tree):
        if (isinstance(node, ast.Call) and isinstance(node.func, ast.Name)
                and node.func.id == "range" and not node.keywords):
            args = [lit(a) for a in node.args]
            shown = ", ".join(vals[:4])
            if len(vals) > 4:
                shown += ", …"
            n_shown = len(vals)
            plural = "s" if n_shown != 1 else ""
            if len(args) == 1:
                return (f"range({args[0]}) makes {args[0]} numbers, starting at 0. "
                        f"the loop runs once for each number and prints it, "
                        f"so you got {n_shown} line{plural}: {shown}.")
            if len(args) >= 3:
                return (f"the loop starts at {args[0]} and jumps by {args[2]} each pass, "
                        f"printing every number it lands on — one line per pass, "
                        f"so you got {n_shown} line{plural}: {shown}.")
            return (f"the loop starts at {args[0]} and stops before {args[1]}, "
                    f"printing each number in between — one line per pass, "
                    f"so you got {n_shown} line{plural}: {shown}.")

    # subscript s[0]: zero-index reach
    for node in ast.walk(tree):
        if isinstance(node, ast.Subscript) and vals:
            base = lit(node.value)
            if (isinstance(node.slice, ast.Constant)
                    and isinstance(node.slice.value, int)):
                i = node.slice.value
                return f"{base} at position {i} — the {_ordinal(i)} item — printed {vals[-1]}."
            idx = lit(node.slice)
            return f"{base} at position {idx} printed {vals[-1]}."

    # print of a literal
    for node in ast.walk(tree):
        if (isinstance(node, ast.Call) and isinstance(node.func, ast.Name)
                and node.func.id == "print" and node.args
                and isinstance(node.args[0], ast.Constant)
                and not isinstance(node.args[0].value, bool)):
            if vals:
                if isinstance(node.args[0].value, str):
                    return f"print showed the word {vals[-1]}."
                return f"print showed the number {vals[-1]}."
            break

    # a loop over something that isn't range (a list, a string, ...)
    for node in ast.walk(tree):
        if isinstance(node, ast.For):
            it = lit(node.iter)
            if len(vals) > 1:
                return (f"the loop runs once for each item in {it}, "
                        f"printing one per pass — that's why you got {len(vals)} lines.")
            break

    if vals:
        return f"and it printed {vals[-1]}."
    return ""


def _spotlight_token(frag: str) -> Text:
    """The exact token to notice, bold and colored. Bare identifiers (x, i, name)
    get an amber tint so a variable name pops as 'the thing to watch'; numbers
    keep their green, strings their orange."""
    if frag.strip().isidentifier():
        return Text(frag, style="bold #fbbf24")
    ft = highlight_line(frag)
    ft.stylize("bold")
    return ft


def _result_spot_tokens(code: str) -> list[str]:
    """The exact code tokens to 'grab' while the result TTS explains — the
    specific numbers / names the voice is talking about (range boundaries, the
    reassigned variable, the index), most important first. Fed to
    `_spotlight_line` to flash them bold while the coach speaks."""
    toks: list[str] = []
    seen: set[str] = set()
    for tok, _ in _explain_code(code):
        if not tok or tok in seen:
            continue
        if any(c.isalnum() for c in tok) and len(tok) <= 24:
            toks.append(tok)
            seen.add(tok)
    return toks[:4]


def _spotlight_line(line: str, tokens: list[str], style: str | None) -> Text:
    """Syntax-highlight `line`, but paint every occurrence of `tokens` with
    `style` (None = leave at its normal color). Longer tokens match first so
    '11' wins over '1' inside 'range(1, 11)'. Used to flash the explained bit
    bold-then-plain while the result TTS runs."""
    toks = sorted({t for t in tokens if t}, key=len, reverse=True)
    spans: list[tuple[int, int]] = []
    for tok in toks:
        if tok.isidentifier() and not tok.isdigit():
            # whole-word only, so a lone 'i' never lights up inside 'in'/'print'
            for m in re.finditer(rf"(?<!\w){re.escape(tok)}(?!\w)", line):
                spans.append(m.span())
        else:
            start = 0
            while True:
                i = line.find(tok, start)
                if i < 0:
                    break
                spans.append((i, i + len(tok)))
                start = i + len(tok)
    if not spans:
        return highlight_line(line)
    # sort by start, longest-first, then drop any span that overlaps a kept one
    spans.sort(key=lambda s: (s[0], -(s[1] - s[0])))
    kept: list[tuple[int, int]] = []
    last_end = -1
    for s, e in spans:
        if s >= last_end:
            kept.append((s, e))
            last_end = e
    t = Text()
    prev = 0
    for s, e in kept:
        if s > prev:
            t.append_text(highlight_line(line[prev:s]))
        if style:
            t.append(line[s:e], style=style)
        else:
            t.append_text(highlight_line(line[s:e]))
        prev = e
    if prev < len(line):
        t.append_text(highlight_line(line[prev:]))
    return t


def _ghost_why_text(code: str) -> Text:
    """The 'why' panel under the ghost code: each confusing bit of THIS snippet,
    with the exact token spotlighted (not the whole row) and explained in plain
    words. Airy spacing so it reads bigger and clearer."""
    t = Text()
    t.append("WHY", style="bold cyan")
    t.append("  —  ", style="dim")
    t.append("what each bit means", style="dim")
    t.append("\n\n")
    bits = _explain_code(code)
    if not bits:
        first = code.splitlines()[0] if code.splitlines() else code
        bits = [(first, "runs top to bottom, one line at a time")]
    for frag, meaning in bits:
        t.append("   ")
        t.append_text(_spotlight_token(frag))
        t.append("\n")
        t.append("      ", style="dim")
        t.append(meaning, style="#e8e8ef")
        t.append("\n\n")
    return t


def _code_wrap(line: str, width: int) -> list[str]:
    """Wrap a code line at clean break points (space, comma, paren, operator) so
    it never splits mid-token and expressions like `range(1, 11)` stay intact
    whenever they fit. Continuation pieces keep the caller's indent prefix."""
    width = max(1, width)
    line = line.rstrip()
    if len(line) <= width:
        return [line]
    out: list[str] = []
    rest = line
    while len(rest) > width:
        cut = -1
        for ch in " ,()=+-*/:>":
            p = rest.rfind(ch, 0, width)
            if p > cut:
                cut = p
        if cut < max(1, width // 2):
            cut = width              # nothing clean — hard cut
        else:
            cut += 1                 # keep the break char on the current line
        out.append(rest[:cut].rstrip())
        rest = rest[cut:].lstrip()
    if rest:
        out.append(rest)
    return out


# ---- code walkthrough tour (token highlights synced to TTS) --------------- #

_TOUR_COLORS = ["#22c55e", "#c084fc", "#38bdf8", "#facc15", "#fb7185", "#34d399"]


def _find_span(code: str, sub: str) -> tuple[int, int] | None:
    """(start, end) of the first occurrence of `sub` in `code`, or None."""
    i = code.find(sub)
    if i < 0:
        return None
    return (i, i + len(sub))


def _code_with_spans(code: str, spans: list[tuple[int, int, str]]) -> Text:
    """Syntax-highlight `code`, then paint `spans` (global char ranges -> style)
    on top. Later spans win where they overlap, so an active (blinking) span
    overrides a settled one."""
    lines = code.split("\n")
    offsets = [0]
    for ln in lines:
        offsets.append(offsets[-1] + len(ln) + 1)
    t = Text()
    for li, line in enumerate(lines):
        if li:
            t.append("\n")
        base = offsets[li]
        local = []
        for (s, e, style) in spans:
            ls, le = s - base, e - base
            if le > 0 and ls < len(line):
                local.append((max(0, ls), min(len(line), le), style))
        if not local:
            t.append_text(highlight_line(line))
            continue
        edges = sorted({0, len(line)} | {x for s, e, _ in local for x in (s, e)})
        for a, b in zip(edges, edges[1:]):
            style = None
            for (s, e, st) in local:
                if s <= a and b <= e:
                    style = st          # last matching span wins (active on top)
            if style is not None:
                t.append(line[a:b], style=style)
            else:
                t.append_text(highlight_line(line[a:b]))
    return t


# Authored token-level tours for the key examples — the rest fall back to a
# line-by-line auto tour (see _tour_parts_for).
CODE_TOURS = {
    's = "hello"\nprint(s[0])': [
        {"hl": 's = "hello"', "say": "make a variable called s, and put the word hello inside it.",
         "color": "#22c55e"},
        {"hl": "print", "say": "print shows the result on the screen.", "color": "#38bdf8"},
        {"hl": "s[0]", "say": "s[0] reaches into hello and grabs the letter at position zero.",
         "color": "#c084fc"},
        {"hl": "0", "say": "zero means the FIRST letter — computers count from zero, not one.",
         "color": "#facc15"},
    ],
    "for i in range(1, 11):\n    print(i)": [
        {"hl": "for", "say": "for means do this once for each number.", "color": "#22c55e"},
        {"hl": "range(1, 11)", "say": "range counts from one, and stops BEFORE eleven.",
         "color": "#c084fc"},
        {"hl": "print(i)", "say": "each time around, it prints the current number.",
         "color": "#38bdf8"},
    ],
    'name = "Bean"\nprint(name)': [
        {"hl": 'name = "Bean"', "say": "make a variable called name, and store Bean inside it.",
         "color": "#22c55e"},
        {"hl": "print(name)", "say": "print shows whatever is inside the box named name.",
         "color": "#c084fc"},
    ],
    'print("hello world")': [
        {"hl": "print", "say": "print sends the words to the screen.", "color": "#22c55e"},
        {"hl": '"hello world"', "say": "the quotes make it a word, not a variable name.",
         "color": "#c084fc"},
    ],
    # recursion — walk the build-up in order: define → base case (stop sign)
    # → do work → the self-call → kick it off. This is the "start slow, then
    # show the twist" narrative the recursion lesson teaches.
    "def greet(name):\n    print(\"hi\", name)\n\ngreet(\"Bean\")": [
        {"hl": "def greet(name):", "say": "a normal function — a recipe named greet that takes a name.", "color": "#22c55e"},
        {"hl": 'print("hi", name)', "say": "prints hi and the name together, one line.", "color": "#38bdf8"},
        {"hl": 'greet("Bean")', "say": "call the recipe with Bean — this line is what actually runs it.", "color": "#c084fc"},
    ],
    "def count(n):\n    if n == 0:\n        return\n    print(n)\n    count(n - 1)\n\ncount(3)": [
        {"hl": "def count(n):", "say": "a function named count that takes one number, n.", "color": "#22c55e"},
        {"hl": "if n == 0:", "say": "the base case — the stop sign. when n reaches zero, the function returns and the whole chain ends.", "color": "#c084fc"},
        {"hl": "print(n)", "say": "print the current number, before making the next call.", "color": "#38bdf8"},
        {"hl": "count(n - 1)", "say": "here is the recursion — count calls ITSELF with n minus one, a smaller number.", "color": "#facc15"},
        {"hl": "count(3)", "say": "kick it all off by calling count with three.", "color": "#34d399"},
    ],
    "def add_up(n):\n    if n == 1:\n        return 1\n    return n + add_up(n - 1)\n\nprint(add_up(4))": [
        {"hl": "def add_up(n):", "say": "a function add_up that takes a number n.", "color": "#22c55e"},
        {"hl": "if n == 1:", "say": "the base case — when n reaches one, stop.", "color": "#c084fc"},
        {"hl": "return 1", "say": "hand back one, the smallest possible sum.", "color": "#34d399"},
        {"hl": "return n + add_up(n - 1)", "say": "here is the recursion — n plus add_up of a smaller n, calling down until it hits the base case.", "color": "#facc15"},
        {"hl": "print(add_up(4))", "say": "start it with four — the answers stack back up to ten.", "color": "#38bdf8"},
    ],
    "def fact(n):\n    if n == 0:\n        return 1\n    return n * fact(n - 1)\n\nprint(fact(5))": [
        {"hl": "def fact(n):", "say": "a function fact that takes a number n.", "color": "#22c55e"},
        {"hl": "if n == 0:", "say": "the base case — factorial of zero is one, so stop here.", "color": "#c084fc"},
        {"hl": "return 1", "say": "hand back one, the stopping value.", "color": "#34d399"},
        {"hl": "return n * fact(n - 1)", "say": "here is the recursion — n times fact of a smaller n, stacking up until it hits the base case.", "color": "#facc15"},
        {"hl": "print(fact(5))", "say": "start it with five — the multiplications stack back up to one hundred twenty.", "color": "#38bdf8"},
    ],
}


def _line_explain(line: str) -> str:
    """A short plain-English gloss for one code line (used by the auto tour)."""
    bits = _explain_code(line)
    if bits:
        return ". ".join(m for _, m in bits[:2]).rstrip(".") + "."
    return "this line runs top to bottom"


def _tour_parts_for(code: str) -> list[dict]:
    """Tour parts for `code`: authored token-level tours when available, else a
    line-by-line auto tour so EVERY example gets a visual walkthrough."""
    authored = CODE_TOURS.get(code)
    if authored is not None:
        return [dict(p) for p in authored]
    parts = []
    for ln in code.split("\n"):
        s = ln.strip()
        if not s:
            continue
        parts.append({"hl": s, "say": _line_explain(s), "color": "#22c55e"})
    for i, p in enumerate(parts):
        p["color"] = _TOUR_COLORS[i % len(_TOUR_COLORS)]
    return parts


# ---- progress ------------------------------------------------------------- #

PROGRESS_FILE = Path.home() / ".learning" / "progress.json"


def load_progress() -> dict:
    if PROGRESS_FILE.exists():
        try:
            p = json.loads(PROGRESS_FILE.read_text())
            p.setdefault("stats", {})
            p.setdefault("last", "")
            p.setdefault("ghosted", [])
            p.setdefault("structure_taught", False)
            p.setdefault("topics_taught", [])
            return p
        except Exception:
            pass
    return {"xp": 0, "done": 0, "streak": 0, "best_streak": 0,
            "topics": [], "stats": {}, "last": "", "ghosted": [],
            "structure_taught": False, "topics_taught": []}


def challenge_stat(p: dict, title: str) -> dict:
    """Per-challenge right/wrong counters, keyed by title."""
    return p["stats"].setdefault(title, {"right": 0, "wrong": 0})


def save_progress(p: dict) -> None:
    PROGRESS_FILE.parent.mkdir(parents=True, exist_ok=True)
    PROGRESS_FILE.write_text(json.dumps(p))


def level_for(xp: int) -> int:
    return 1 + xp // 100


# ---- VimEditor ------------------------------------------------------------ #

class ModeChanged(Message):
    def __init__(self, mode: str) -> None:
        super().__init__()
        self.mode = mode


class VimEditor(Static):
    can_focus = True
    GUTTER = 6   # left padding (2) + line-number gutter (" N  " = 4)

    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self.buffer: list[str] = [""]
        self.cursor_row = 0
        self.cursor_col = 0
        self.mode = "normal"
        self.yank = ""
        self._yank_linewise = True
        self.undo_stack: list[list[str]] = []
        self._pending: str | None = None
        self._insert_snapshot: list[str] | None = None
        self.hint_lines: set[int] = set()

    def set_text(self, text: str) -> None:
        # strip a trailing newline so the buffer has no phantom empty last line
        # (a dangling blank row breaks vim navigation like G → last line, since
        # G would land on the blank instead of the real code).
        self.buffer = text.rstrip("\n").split("\n") if text else [""]
        self.cursor_row = 0
        self.cursor_col = 0
        self.mode = "normal"
        self.undo_stack = []
        self._pending = None
        self.hint_lines = set()
        self._redraw()

    def get_text(self) -> str:
        return "\n".join(self.buffer)

    def word_under_cursor(self) -> str:
        """The identifier/keyword under the cursor, or '' if none (for `K` lookup)."""
        line = self.buffer[self.cursor_row]
        if not line:
            return ""
        col = min(self.cursor_col, len(line) - 1)
        if col < 0:
            return ""
        start = col
        while start > 0 and (line[start - 1].isalnum() or line[start - 1] == "_"):
            start -= 1
        end = col
        while end < len(line) and (line[end].isalnum() or line[end] == "_"):
            end += 1
        return line[start:end]

    def render(self) -> Text:
        t = Text()
        for i, line in enumerate(self.buffer):
            if i > 0:
                t.append("\n")
            # relative line numbers like LazyVim (current line = its number, others = distance)
            if i == self.cursor_row:
                num = str(i + 1)
            else:
                num = str(abs(i - self.cursor_row))
            t.append(f"{num:>3} ", style="dim")
            if i == self.cursor_row:
                col = min(self.cursor_col, len(line))
                before = highlight_line(line[:col])
                after = highlight_line(line[col + 1:])
                # the character under the cursor — or a blank cell if we're past EOL,
                # so the cursor is ALWAYS visible even on an empty line
                ch = line[col] if col < len(line) else " "
                # cursorline: subtle bg on the whole current line (red-tinted if flagged)
                hl = "on #3a1a1a" if (i + 1) in self.hint_lines else "on #2b2b2b"
                before.stylize(hl)
                after.stylize(hl)
                if self.mode == "insert":
                    # nvim insert mode = a thin bar cursor; underline draws the `_`
                    cur_style = f"underline bold {hl}"
                else:
                    # nvim normal mode = a solid block, always visible even on a blank cell
                    cur_style = "black on #e6e6e6 bold"
                t.append_text(before)
                t.append(ch, style=cur_style)
                t.append_text(after)
            elif (i + 1) in self.hint_lines:
                # flagged line (the hint) — red arrow + underline so the fix spot pops
                t.append("▸ ", style="bold red")
                tt = highlight_line(line)
                tt.stylize("underline #ff6b6b")
                t.append_text(tt)
            else:
                t.append_text(highlight_line(line))
        return t

    def _redraw(self) -> None:
        self.refresh()

    def on_key(self, event: events.Key) -> None:
        if event.key == "ctrl+enter":
            event.stop(); event.prevent_default()
            self.app.action_run()
            return
        if event.key.startswith("ctrl+"):
            # tutor shortcuts (ctrl+n / ctrl+p) live at the app level — don't
            # swallow them as normal-mode typing
            return
        if self.mode == "insert":
            event.stop(); event.prevent_default()
            self._insert(event)
        else:
            if self._normal(event):
                event.stop(); event.prevent_default()
        # post-ghost vim warm-up: after any edit, let the app check if it's done
        if getattr(self.app, "_warmup_on", False):
            self.app._warmup_check()

    def on_click(self, event: events.Click) -> None:
        """Click to place the cursor and start typing there — a mouse-friendly
        alternative to vim's `i`, so people who don't use neovim can still edit.
        Clicking drops you into insert mode at that spot; Esc still exits."""
        row = max(0, min(event.y, len(self.buffer) - 1))
        col = max(0, event.x - self.GUTTER)
        self.cursor_row = row
        self.cursor_col = min(col, len(self.buffer[row]))
        if self.mode != "insert":
            self._enter_insert(after=False)
        else:
            self._redraw()
        event.stop()

    def _normal(self, event: events.Key) -> bool:
        ch = event.character
        if self._pending:
            p = self._pending
            self._pending = None
            if p == "r":
                self._replace_char(ch)
                return True
            if p == "g":
                if ch == "g":
                    self._goto_top()
                return True
            return self._do_operator(p, ch)
        if ch == "h": self._move(0, -1); return True
        if ch == "j": self._move(1, 0); return True
        if ch == "k": self._move(-1, 0); return True
        if ch == "l": self._move(0, 1); return True
        if ch == "w": self._goto_pos(*self._word_fwd_pos(self.cursor_row, self.cursor_col, False)); return True
        if ch == "W": self._goto_pos(*self._word_fwd_pos(self.cursor_row, self.cursor_col, True)); return True
        if ch == "b": self._goto_pos(*self._word_back_pos(self.cursor_row, self.cursor_col, False)); return True
        if ch == "B": self._goto_pos(*self._word_back_pos(self.cursor_row, self.cursor_col, True)); return True
        if ch == "e": self._goto_pos(*self._word_end_pos(self.cursor_row, self.cursor_col, False)); return True
        if ch == "E": self._goto_pos(*self._word_end_pos(self.cursor_row, self.cursor_col, True)); return True
        if ch == "0": self.cursor_col = 0; self._redraw(); return True
        if ch == "$": self.cursor_col = max(0, len(self.buffer[self.cursor_row]) - 1); self._redraw(); return True
        if ch == "G": self._goto_bottom(); return True
        if ch == "i": self._enter_insert(after=False); return True
        if ch == "a": self._enter_insert(after=True); return True
        if ch == "A": self.cursor_col = len(self.buffer[self.cursor_row]); self._enter_insert(after=False); return True
        if ch == "I": self.cursor_col = 0; self._enter_insert(after=False); return True
        if ch == "o": self._newline_below(); return True
        if ch == "O": self._newline_above(); return True
        if ch == "x": self._delete_char(); return True
        if ch == "X": self._delete_char_before(); return True
        if ch == "D": self._delete_to_eol(); return True
        if ch == "C": self._change_to_eol(); return True
        if ch == "S": self._substitute_line(); return True
        if ch == "d": self._pending = "d"; return True
        if ch == "c": self._pending = "c"; return True
        if ch == "y": self._pending = "y"; return True
        if ch == "g": self._pending = "g"; return True
        if ch == "r": self._pending = "r"; return True
        if ch == "p": self._paste(); return True
        if ch == "P": self._paste_before(); return True
        if ch == "u": self._undo(); return True
        if ch == "J": self._join_lines(); return True
        if ch == "~": self._toggle_case(); return True
        return False

    # ---- motions + operators (vim-style) --------------------------------- #

    def _goto_pos(self, r, c):
        self.cursor_row = max(0, min(len(self.buffer) - 1, r))
        self.cursor_col = max(0, min(len(self.buffer[self.cursor_row]), c))
        self._redraw()

    def _goto_bottom(self):
        self.cursor_row = len(self.buffer) - 1
        self.cursor_col = 0
        self._redraw()

    def _flat_text(self):
        return "\n".join(self.buffer)

    def _flat_pos(self, r, c):
        return sum(len(self.buffer[i]) + 1 for i in range(r)) + c

    def _from_flat(self, pos):
        pos = max(0, pos)
        for r, line in enumerate(self.buffer):
            llen = len(line)
            if pos <= llen:
                return r, pos
            pos -= llen + 1
        r = len(self.buffer) - 1
        return r, len(self.buffer[r])

    def _wcls(self, ch, big):
        if ch.isspace():
            return "s"
        if big:
            return "w"
        return "w" if (ch.isalnum() or ch == "_") else "p"

    def _word_fwd_pos(self, r, c, big):
        flat = self._flat_text(); n = len(flat)
        i = self._flat_pos(r, c)
        if i >= n:
            return r, c
        if not flat[i].isspace():
            cls = self._wcls(flat[i], big)
            while i < n and flat[i] != "\n" and self._wcls(flat[i], big) == cls:
                i += 1
        while i < n and flat[i] != "\n" and flat[i].isspace():
            i += 1
        return self._from_flat(i)

    def _word_back_pos(self, r, c, big):
        flat = self._flat_text()
        i = self._flat_pos(r, c) - 1
        while i >= 0 and flat[i] != "\n" and flat[i].isspace():
            i -= 1
        if i < 0:
            return 0, 0
        cls = self._wcls(flat[i], big)
        while i >= 0 and flat[i] != "\n" and self._wcls(flat[i], big) == cls:
            i -= 1
        return self._from_flat(i + 1)

    def _word_end_pos(self, r, c, big):
        flat = self._flat_text(); n = len(flat)
        i = self._flat_pos(r, c)
        while i < n and flat[i] != "\n" and flat[i].isspace():
            i += 1
        if i >= n or flat[i] == "\n":
            return self._from_flat(i)
        cls = self._wcls(flat[i], big)
        while i + 1 < n and flat[i + 1] != "\n" and self._wcls(flat[i + 1], big) == cls:
            i += 1
        return self._from_flat(i)

    def _motion_pos(self, ch):
        r, c = self.cursor_row, self.cursor_col
        line = self.buffer[r]
        if ch == "h": return self._flat_pos(r, max(0, c - 1))
        if ch == "l": return self._flat_pos(r, min(len(line), c + 1))
        if ch == "j": return self._flat_pos(min(len(self.buffer) - 1, r + 1), min(c, len(self.buffer[min(len(self.buffer) - 1, r + 1)])))
        if ch == "k": return self._flat_pos(max(0, r - 1), min(c, len(self.buffer[max(0, r - 1)])))
        if ch == "0": return self._flat_pos(r, 0)
        if ch == "$": return self._flat_pos(r, len(line))
        if ch == "w": return self._flat_pos(*self._word_fwd_pos(r, c, False))
        if ch == "W": return self._flat_pos(*self._word_fwd_pos(r, c, True))
        if ch == "b": return self._flat_pos(*self._word_back_pos(r, c, False))
        if ch == "B": return self._flat_pos(*self._word_back_pos(r, c, True))
        if ch == "e":
            r2, c2 = self._word_end_pos(r, c, False)
            return self._flat_pos(r2, c2 + 1)
        if ch == "E":
            r2, c2 = self._word_end_pos(r, c, True)
            return self._flat_pos(r2, c2 + 1)
        if ch == "G": return self._flat_pos(len(self.buffer) - 1, len(self.buffer[-1]))
        return None

    def _do_operator(self, op, ch):
        if ch == op:  # dd / cc / yy (linewise)
            if op == "d": self._delete_line(); return True
            if op == "c": self._change_line(); return True
            if op == "y": self._yank_line(); return True
        start = self._flat_pos(self.cursor_row, self.cursor_col)
        end = self._motion_pos(ch)
        if end is None:
            return True
        if end < start:
            start, end = end, start
        text = self._flat_text()[start:end]
        if op == "y":
            self.yank = text
            self._yank_linewise = False
            self._redraw()
            return True
        self._save_undo()
        flat = self._flat_text()
        flat = flat[:start] + flat[end:]
        self.buffer = flat.split("\n")
        self.cursor_row, self.cursor_col = self._from_flat(start)
        if op == "c":
            self._enter_insert(after=False)
        else:
            self._redraw()
        return True

    def _change_line(self):
        self._save_undo()
        self.buffer[self.cursor_row] = ""
        self.cursor_col = 0
        self._enter_insert(after=False)

    def _substitute_line(self):
        self._change_line()

    def _delete_to_eol(self):
        self._save_undo()
        line = self.buffer[self.cursor_row]
        self.buffer[self.cursor_row] = line[:self.cursor_col]
        self._redraw()

    def _change_to_eol(self):
        self._save_undo()
        line = self.buffer[self.cursor_row]
        self.buffer[self.cursor_row] = line[:self.cursor_col]
        self._enter_insert(after=False)

    def _delete_char_before(self):
        if self.cursor_col > 0:
            self._save_undo()
            line = self.buffer[self.cursor_row]
            self.buffer[self.cursor_row] = line[:self.cursor_col - 1] + line[self.cursor_col:]
            self.cursor_col -= 1
            self._redraw()

    def _replace_char(self, ch):
        if ch and ch != "\n":
            self._save_undo()
            line = self.buffer[self.cursor_row]
            if self.cursor_col < len(line):
                self.buffer[self.cursor_row] = line[:self.cursor_col] + ch + line[self.cursor_col + 1:]
                self._redraw()

    def _toggle_case(self):
        line = self.buffer[self.cursor_row]
        if self.cursor_col < len(line):
            self._save_undo()
            c = line[self.cursor_col]
            self.buffer[self.cursor_row] = line[:self.cursor_col] + c.swapcase() + line[self.cursor_col + 1:]
            self._redraw()

    def _join_lines(self):
        if self.cursor_row + 1 < len(self.buffer):
            self._save_undo()
            cur = self.buffer[self.cursor_row]
            nxt = self.buffer[self.cursor_row + 1]
            self.buffer[self.cursor_row] = cur + " " + nxt.lstrip()
            del self.buffer[self.cursor_row + 1]
            self.cursor_col = len(cur)
            self._redraw()

    def _insert(self, event: events.Key) -> None:
        k = event.key
        if k == "escape":
            self._leave_insert(); return
        play_key()
        if k == "enter":
            self._save_undo()
            line = self.buffer[self.cursor_row]
            before, after = line[:self.cursor_col], line[self.cursor_col:]
            self.buffer[self.cursor_row] = before
            self.buffer.insert(self.cursor_row + 1, after)
            self.cursor_row += 1; self.cursor_col = 0
        elif k == "backspace":
            if self.cursor_col > 0:
                self._save_undo()
                line = self.buffer[self.cursor_row]
                self.buffer[self.cursor_row] = line[:self.cursor_col - 1] + line[self.cursor_col:]
                self.cursor_col -= 1
            elif self.cursor_row > 0:
                # at start of a line: join it onto the end of the previous line
                # (real vim backspace). This is how you pull a stray ")" back up.
                self._save_undo()
                prev = self.buffer[self.cursor_row - 1]
                cur = self.buffer[self.cursor_row]
                self.buffer[self.cursor_row - 1] = prev + cur
                del self.buffer[self.cursor_row]
                self.cursor_row -= 1
                self.cursor_col = len(prev)
        elif k == "delete":
            line = self.buffer[self.cursor_row]
            if self.cursor_col < len(line):
                self._save_undo()
                self.buffer[self.cursor_row] = line[:self.cursor_col] + line[self.cursor_col + 1:]
        elif k == "tab":
            self._save_undo()
            line = self.buffer[self.cursor_row]
            self.buffer[self.cursor_row] = line[:self.cursor_col] + "    " + line[self.cursor_col:]
            self.cursor_col += 4
        elif k == "left":
            self.cursor_col = max(0, self.cursor_col - 1)
        elif k == "right":
            self.cursor_col = min(len(self.buffer[self.cursor_row]), self.cursor_col + 1)
        elif k == "up":
            if self.cursor_row > 0:
                self.cursor_row -= 1
                self.cursor_col = min(self.cursor_col, len(self.buffer[self.cursor_row]))
        elif k == "down":
            if self.cursor_row < len(self.buffer) - 1:
                self.cursor_row += 1
                self.cursor_col = min(self.cursor_col, len(self.buffer[self.cursor_row]))
        elif k == "home":
            self.cursor_col = 0
        elif k == "end":
            self.cursor_col = len(self.buffer[self.cursor_row])
        elif event.character:
            self._save_undo()
            line = self.buffer[self.cursor_row]
            ch = event.character
            # auto-close brackets/quotes like a normal editor
            pairs = {"(": ")", "[": "]", "{": "}", '"': '"', "'": "'"}
            if ch in pairs:
                self.buffer[self.cursor_row] = line[:self.cursor_col] + ch + pairs[ch] + line[self.cursor_col:]
                self.cursor_col += 1  # cursor sits inside the pair
            else:
                self.buffer[self.cursor_row] = line[:self.cursor_col] + ch + line[self.cursor_col:]
                self.cursor_col += 1
        self._redraw()

    def _move(self, dr, dc):
        self.cursor_row = max(0, min(len(self.buffer) - 1, self.cursor_row + dr))
        self.cursor_col = max(0, min(len(self.buffer[self.cursor_row]), self.cursor_col + dc))
        self._redraw()

    def _enter_insert(self, after=False):
        self._insert_snapshot = list(self.buffer)
        self.mode = "insert"
        if after and self.cursor_col < len(self.buffer[self.cursor_row]):
            self.cursor_col += 1
        self.post_message(ModeChanged("insert"))
        self._redraw()

    def _leave_insert(self):
        if self._insert_snapshot is not None and self._insert_snapshot != self.buffer:
            self.undo_stack.append(self._insert_snapshot)
        self._insert_snapshot = None
        self.mode = "normal"
        if self.cursor_col > 0:
            self.cursor_col -= 1
        self.post_message(ModeChanged("normal"))
        self._redraw()

    def _newline_below(self):
        self._save_undo()
        self.buffer.insert(self.cursor_row + 1, "")
        self.cursor_row += 1; self.cursor_col = 0
        self._enter_insert(after=False)

    def _newline_above(self):
        self._save_undo()
        self.buffer.insert(self.cursor_row, "")
        self.cursor_col = 0
        self._enter_insert(after=False)

    def _delete_char(self):
        self._save_undo()
        line = self.buffer[self.cursor_row]
        if self.cursor_col < len(line):
            self.buffer[self.cursor_row] = line[:self.cursor_col] + line[self.cursor_col + 1:]
        self._redraw()

    def _delete_line(self):
        self._save_undo()
        if len(self.buffer) > 1:
            del self.buffer[self.cursor_row]
            self.cursor_row = min(self.cursor_row, len(self.buffer) - 1)
        else:
            self.buffer[self.cursor_row] = ""
        self.cursor_col = 0
        self._redraw()

    def _yank_line(self):
        self.yank = self.buffer[self.cursor_row]
        self._yank_linewise = True
        self._redraw()

    def _paste(self):
        if self.yank:
            self._save_undo()
            if self._yank_linewise:
                self.buffer.insert(self.cursor_row + 1, self.yank)
                self.cursor_row += 1
                self.cursor_col = 0
            else:
                line = self.buffer[self.cursor_row]
                self.buffer[self.cursor_row] = (line[:self.cursor_col + 1] + self.yank
                                                + line[self.cursor_col + 1:])
                self.cursor_col += len(self.yank)
            self._redraw()

    def _paste_before(self):
        if self.yank:
            self._save_undo()
            if self._yank_linewise:
                self.buffer.insert(self.cursor_row, self.yank)
                self.cursor_row += 1
                self.cursor_col = 0
            else:
                line = self.buffer[self.cursor_row]
                self.buffer[self.cursor_row] = (line[:self.cursor_col] + self.yank
                                                + line[self.cursor_col:])
                self.cursor_col += len(self.yank)
            self._redraw()

    def _goto_top(self):
        self.cursor_row = 0; self.cursor_col = 0
        self._redraw()

    def _save_undo(self):
        self.undo_stack.append(list(self.buffer))

    def _undo(self):
        if self.undo_stack:
            self.buffer = self.undo_stack.pop()
            self.cursor_row = min(self.cursor_row, len(self.buffer) - 1)
            self._redraw()


class Confetti(Static):
    """Transparent full-screen celebration: falling confetti, then a centered
    'press Enter to continue' button."""

    CHARS = "✦✧★*#+@$%&"
    COLORS = ["red", "yellow", "green", "cyan", "magenta", "white",
              "#ff8c00", "#00ff99", "#ff00ff", "#ffff00", "#00d7ff"]

    def __init__(self, **kwargs):
        super().__init__("", **kwargs)
        self.particles: list = []
        self._timer = None
        self._phase = "idle"   # idle | confetti | prompt

    def start(self, seconds: float = 2.6):
        self.styles.display = "block"
        self._phase = "confetti"
        self.call_after_refresh(self._spawn)
        self._timer = self.set_interval(0.09, self._tick)
        self.set_timer(seconds, self._show_prompt)

    def dismiss(self):
        self._clear_timer()
        self._phase = "idle"
        self.particles = []
        self.styles.display = "none"

    def _clear_timer(self):
        if self._timer is not None:
            self._timer.stop()
            self._timer = None

    def _spawn(self):
        w = max(1, self.size.width)
        h = max(1, self.size.height)
        self.particles = []
        for _ in range(max(40, (w * h) // 12)):  # sparse → see-through
            self.particles.append([
                random.randint(0, w - 1), random.randint(0, h - 1),
                random.choice(self.CHARS), random.choice(self.COLORS),
                random.choice((0.5, 1.0, 1.5)),
            ])

    def _tick(self):
        if self._phase != "confetti":
            return
        w = max(1, self.size.width)
        h = max(1, self.size.height)
        for p in self.particles:
            p[1] += p[4]
            if p[1] >= h:
                p[1] = 0
                p[0] = random.randint(0, w - 1)
                p[2] = random.choice(self.CHARS)
                p[3] = random.choice(self.COLORS)
            elif random.random() < 0.25:
                p[0] = max(0, min(w - 1, p[0] + random.choice((-1, 0, 1))))
        self.refresh()

    def _show_prompt(self):
        self._clear_timer()
        self.particles = []
        self._phase = "prompt"
        self.refresh()

    def render(self) -> Text:
        if self._phase == "prompt":
            return self._render_prompt()
        return self._render_confetti()

    def _render_confetti(self) -> Text:
        w = max(1, self.size.width)
        h = max(1, self.size.height)
        grid: dict[int, dict[int, tuple[str, str]]] = {}
        for x, y, ch, color, _ in self.particles:
            xi, yi = int(x), int(y)
            if 0 <= xi < w and 0 <= yi < h:
                grid.setdefault(yi, {})[xi] = (ch, color)
        t = Text()
        for yi in range(h):
            row = grid.get(yi, {})
            line = Text()
            prev = 0
            for xi in sorted(row):
                if xi > prev:
                    line.append(" " * (xi - prev))
                ch, color = row[xi]
                line.append(ch, style=color)
                prev = xi + 1
            t.append_text(line)
            if yi < h - 1:
                t.append("\n")
        return t

    def _render_prompt(self) -> Text:
        w = max(1, self.size.width)
        h = max(1, self.size.height)
        msg = "▶ press Enter to continue"
        t = Text()
        cy = h // 2
        cx = max(0, (w - len(msg)) // 2)
        for yi in range(h):
            if yi == cy:
                line = Text(" " * cx)
                line.append(msg, style="bold black on yellow")
                t.append_text(line)
            if yi < h - 1:
                t.append("\n")
        return t


# ---- app ------------------------------------------------------------------ #

# Completion candidates for the `:` command line, in priority order (the
# wildmenu shows matches filtered by prefix as you type, nvim-style).
COMMANDS = ["!python3 %", "submit", "run", "w", "write", "wq", "q", "quit"]


class CommandInput(Input):
    """The `:` command bar with nvim-style wildmenu completion.

    Tab / Ctrl+n cycle forward through the matches; Shift+Tab / Ctrl+p cycle
    backward; Escape cancels back to the editor. Enter submits as usual.
    """

    class Complete(Message):
        """Cycle the wildmenu selection (delta = +1 forward, -1 backward)."""

        def __init__(self, delta: int) -> None:
            self.delta = delta
            super().__init__()

    class Cancel(Message):
        """Escape pressed — close the command line."""

    BINDINGS = [
        Binding("tab", "complete_next", "Next", show=False),
        Binding("ctrl+n", "complete_next", "Next", show=False),
        Binding("shift+tab", "complete_prev", "Prev", show=False),
        Binding("ctrl+p", "complete_prev", "Prev", show=False),
        Binding("escape", "cancel", "Cancel", show=False),
    ]

    def action_complete_next(self) -> None:
        self.post_message(self.Complete(1))

    def action_complete_prev(self) -> None:
        self.post_message(self.Complete(-1))

    def action_cancel(self) -> None:
        self.post_message(self.Cancel())


class TabLabel(Static):
    """A clickable panel header: clicking runs a named app action (e.g. toggle
    the examples panel). Shows its hotkey so the user can click OR use the key."""

    can_focus = True

    def __init__(self, action: str = "", *args, **kwargs):
        self._action = action
        super().__init__(*args, **kwargs)

    async def on_click(self, event: events.Click) -> None:
        event.stop()
        if self._action:
            await self.app.run_action(self._action)


class GhostWriter(Vertical):
    """Full-screen 'follow the ghost' typing trainer. The App owns the state
    machine; this container just needs keyboard focus so printable keys land
    here instead of the editor. Every key is forwarded to the App, which stops
    the events it consumes (so they don't leak into editor/app bindings). Its
    children (#ghost-head / #ghost-code / #ghost-console / #ghost-foot) are
    rendered separately so the CODE can shake on its own without moving the
    header, console, or footer."""

    can_focus = True

    def on_key(self, event: events.Key) -> None:
        self.app._ghost_on_key(event)


# ============================================================================ #
# VIM / NEOVIM TRAINER COURSE — keyboard-on-screen movement + editing dojo
# ============================================================================ #

VIM_KB_ROWS = [
    ["Esc", "`", "1", "2", "3", "4", "5", "6", "7", "8", "9", "0", "-", "=", "Bksp"],
    ["Tab", "q", "w", "e", "r", "t", "y", "u", "i", "o", "p", "[", "]", "\\"],
    ["Ctrl", "a", "s", "d", "f", "g", "h", "j", "k", "l", ";", "'", "Enter"],
    ["Shift", "z", "x", "c", "v", "b", "n", "m", ",", ".", "/", "Shift"],
    ["Ctrl", "Super", "Alt", "Space", "Alt", "Super", "Ctrl"],
]

# bare modifier presses that must NEVER count as a wrong key in the trainer
_VIM_MODIFIERS = {"shift", "ctrl", "control", "alt", "super", "meta", "hyper",
                  "left_shift", "right_shift", "left_ctrl", "right_ctrl",
                  "left_alt", "right_alt", "caps_lock", "num_lock", "scroll_lock"}

VIM_STAGES = ["Normal Core", "Word & Line Motion", "Jump & Navigate",
              "Select (Visual)", "Delete & Change", "Yank & Put",
              "Insert Mastery", "Power Editing", "LazyVim (Space)", "Shell / Fish"]

# (stage, title, desc, keys, note)  — keys: single keys sequential, chords as "Ctrl+d"
VIM_LESSONS = [
    (0, "h — move left", "one character at a time", ["h"], ""),
    (0, "j — move down", "one line down", ["j"], ""),
    (0, "k — move up", "one line up", ["k"], ""),
    (0, "l — move right", "one character right", ["l"], ""),
    (0, "Esc — normal mode", "always return here first", ["Esc"], ""),
    (0, "i — insert", "enter insert mode before the cursor", ["i"], ""),
    (0, ":w — save", "write the buffer to disk", [":", "w", "Enter"], ""),
    (0, ":q — quit", "close the buffer", [":", "q", "Enter"], ""),

    (1, "w — next word", "jump to the start of the next word", ["w"], ""),
    (1, "b — back a word", "jump to the start of the previous word", ["b"], ""),
    (1, "e — end of word", "jump to the end of the word", ["e"], ""),
    (1, "0 — line start", "go to column zero", ["0"], ""),
    (1, "$ — line end", "go to the end of the line", ["$"], ""),
    (1, "^ — first non-blank", "start of the real text (skips indent)", ["^"], ""),
    (1, "f + char — find", "jump to the next char on the line", ["f"], "then press the character to jump to"),

    (2, "gg — top of file", "jump to line one", ["g", "g"], ""),
    (2, "G — bottom of file", "jump to the last line", ["G"], ""),
    (2, "5j — down 5 lines", "read the number, type it, move", ["5", "j"], "swap 5 for any count — the #1 speed trick"),
    (2, "Ctrl+d — half page down", "scroll down half a screen", ["Ctrl+d"], ""),
    (2, "Ctrl+u — half page up", "scroll up half a screen", ["Ctrl+u"], ""),
    (2, "% — matching bracket", "jump between ( ) [ ] { }", ["%"], ""),
    (2, "/ — search", "search forward", ["/"], "type the pattern, Enter, then n / N to hop"),
    (2, "n — next match", "go to the next search hit", ["n"], ""),
    (2, "* — search word", "search the word under the cursor", ["*"], ""),
    (2, "Ctrl+o — jump back", "go back in your jump history", ["Ctrl+o"], "THE #1 code-reading key — pair with Ctrl+i"),

    (3, "v — visual mode", "select character by character", ["v"], ""),
    (3, "V — line visual", "select whole lines", ["V"], ""),
    (3, "Ctrl+v — block visual", "select a rectangle", ["Ctrl+v"], ""),
    (3, "viw — select word", "select inside the word", ["v", "i", "w"], ""),
    (3, "vi( — select parens", "select inside the parentheses", ["v", "i", "("], "swap ( for { [ < \" '"),
    (3, "v$ — select to end", "select to end of line", ["v", "$"], ""),

    (4, "x — delete char", "delete the character under the cursor", ["x"], ""),
    (4, "dd — delete line", "delete the whole line", ["d", "d"], ""),
    (4, "dw — delete word", "delete to the start of the next word", ["d", "w"], ""),
    (4, "d$ — delete to end", "delete from cursor to end of line", ["d", "$"], ""),
    (4, "diw — delete inside word", "delete the word you're on", ["d", "i", "w"], ""),
    (4, "D — delete to end", "same as d$, shorter", ["D"], ""),
    (4, "cw — change word", "delete word and drop into insert", ["c", "w"], ""),
    (4, "cc — change line", "blank the line and insert", ["c", "c"], ""),

    (5, "yy — yank line", "copy the whole line", ["y", "y"], ""),
    (5, "yw — yank word", "copy to the next word", ["y", "w"], ""),
    (5, "y$ — yank to end", "copy to end of line", ["y", "$"], ""),
    (5, "p — paste below", "put after the cursor", ["p"], ""),
    (5, "P — paste above", "put before the cursor", ["P"], ""),
    (5, "yyp — duplicate line", "copy + paste = duplicate", ["y", "y", "p"], ""),

    (6, "i — insert before", "insert mode before the cursor", ["i"], ""),
    (6, "a — append", "insert mode after the cursor", ["a"], ""),
    (6, "o — new line below", "open a line below and insert", ["o"], ""),
    (6, "O — new line above", "open a line above and insert", ["O"], ""),
    (6, "I — insert at start", "insert at the first non-blank char", ["I"], ""),
    (6, "A — append at end", "insert at the end of the line", ["A"], ""),
    (6, "Ctrl+w — delete word", "(in insert) delete the previous word", ["Ctrl+w"], ""),

    (7, "u — undo", "undo the last change", ["u"], ""),
    (7, "Ctrl+r — redo", "redo the last undo", ["Ctrl+r"], ""),
    (7, "Ctrl+a — increment", "+1 to the number under the cursor", ["Ctrl+a"], ""),
    (7, "= — indent", "auto-indent the selection", ["="], ""),
    (7, "gg=G — format file", "auto-format the whole file", ["g", "g", "=", "G"], ""),

    (8, "Space f f — find files", "fuzzy-find any file", ["Space", "f", "f"], ""),
    (8, "Space e — file tree", "toggle the file explorer", ["Space", "e"], ""),
    (8, ":vsplit — split", "vertical split, side by side", [":", "v", "s", "p", "l", "i", "t", "Enter"], ""),

    (9, "Ctrl+r — history", "search shell history backwards", ["Ctrl+r"], ""),
    (9, "Ctrl+l — clear", "clear the screen", ["Ctrl+l"], ""),
    (9, "Ctrl+c — cancel", "abort the current command", ["Ctrl+c"], ""),
    (9, "Tab — autocomplete", "complete the path or command", ["Tab"], ""),
]

VIM_DEMO = ["def greet(name):",
            "    print(f\"hello {name}\")",
            "",
            "for i in range(3):",
            "    print(i)",
            "def main():",
            "    greet(\"bean\")",
            "    total = 0",
            "    for i in range(5):",
            "        total += i",
            "    print(total)"]

# Practice challenges fired after the lessons: a mix of movement (cursor to a
# target cell) and editing (buffer must reach a verified state). Ordered light →
# heavy: single motions first, then word motion, then jumps, then deletes, then
# yank/paste combinations.
VIM_CHALLENGES = [
    # ---- movement, light → heavy ----
    {"title": "move down one line",
     "desc": "press j to step down one line",
     "kind": "move", "start": VIM_DEMO,
     "keys": "j k", "target": (1, 0)},
    {"title": "move to 'for'",
     "desc": "move down to line 4 with j",
     "kind": "move", "start": VIM_DEMO,
     "keys": "j k", "target": (3, 0)},
    {"title": "move onto 'greet'",
     "desc": "press w to jump to the next word",
     "kind": "move", "start": VIM_DEMO,
     "keys": "w b", "target": (0, 4)},
    {"title": "move onto 'print'",
     "desc": "jump down with j, then to the next word with w",
     "kind": "move", "start": VIM_DEMO,
     "keys": "j w", "target": (1, 4)},
    {"title": "jump to 'def main'",
     "desc": "jump to the top with gg, then step down to line 6",
     "kind": "move", "start": VIM_DEMO,
     "keys": "gg j k G", "target": (5, 0)},
    {"title": "jump to the last line",
     "desc": "press G to jump to the bottom of the buffer",
     "kind": "move", "start": VIM_DEMO,
     "keys": "G gg", "target": (10, 0)},
    {"title": "jump to end of line 1",
     "desc": "press $ to jump to the end of the line",
     "kind": "move", "start": VIM_DEMO,
     "keys": "$ 0 gg", "target": (0, 15)},

    # ---- editing, light → heavy ----
    {"title": "delete the empty line",
     "desc": "move to line 3 and delete it with dd",
     "kind": "edit", "start": VIM_DEMO,
     "keys": "j dd",
     "verify": lambda b: "for i in range(3):" in b.lines and "" not in b.lines},
    {"title": "delete one character",
     "desc": "delete the 'd' under the cursor with x",
     "kind": "edit", "start": VIM_DEMO,
     "keys": "x u",
     "verify": lambda b: "ef greet(name):" in b.lines},
    {"title": "delete the word 'for'",
     "desc": "move to line 4 and delete the word 'for' with dw",
     "kind": "edit", "start": VIM_DEMO,
     "keys": "j dw",
     "verify": lambda b: b.lines[3] == "i in range(3):"},
    {"title": "delete to end of line",
     "desc": "move onto 'print' (line 5) and delete to the end with d$",
     "kind": "edit", "start": VIM_DEMO,
     "keys": "j w d $",
     "verify": lambda b: b.lines[4] == "    "},
    {"title": "duplicate line 1",
     "desc": "copy line 1 with yy, then paste with p",
     "kind": "edit", "start": VIM_DEMO,
     "keys": "yy p",
     "verify": lambda b: b.lines.count("def greet(name):") >= 2},
    {"title": "yank and paste a word",
     "desc": "move to line 8, yank 'total' with yw, then paste with p",
     "kind": "edit", "start": VIM_DEMO,
     "keys": "j w yw p",
     "verify": lambda b: any(l.strip() == "total" for l in b.lines)},
    {"title": "duplicate the line twice",
     "desc": "yank line 1 with yy, then paste twice with p p",
     "kind": "edit", "start": VIM_DEMO,
     "keys": "yy p",
     "verify": lambda b: b.lines.count("def greet(name):") >= 3},
]

# Post-ghost vim edit warm-up: a short run of real edits the user must perform in
# the ACTUAL editor (not the demo buffer) so the motions they just learned get
# exercised right before the Python challenge. Each task starts from the same
# base buffer and is done when its verify() sees the edit.
def _build_warmup_tasks(starter: str) -> list[dict]:
    """Build a short, ramping vim-edit warm-up FROM the challenge's own starter
    code, so the practice is directly relevant (you edit the exact lines you're
    about to write) instead of an unrelated scratch buffer. Lightest edit first,
    heavier after — so the warm-up itself ramps like the rest of the course.
    Returns a list of {title, instruction, verify}; empty if there's nothing
    to edit (an empty-starter challenge skips the warm-up cleanly)."""
    lines = [l for l in (starter or "").rstrip("\n").split("\n") if l.strip() != ""]
    if not lines:
        return []
    if len(lines) >= 2:
        first, last = lines[0], lines[-1]
        return [
            # 1 — LIGHT: the cursor is already on the first line; one dd, done.
            {"title": "delete the first line",
             "instruction": "the cursor is on the first line — press dd to delete it",
             "verify": lambda b, first=first: first not in b},
            # 2 — MEDIUM: navigate to the last line, then duplicate it.
            {"title": "duplicate the last line",
             "instruction": "jump to the last line with G, then press yy and p",
             "verify": lambda b, last=last: sum(1 for l in b if l == last) >= 2},
            # 3 — HEAVY: open a fresh line and type a comment.
            {"title": "add a comment",
             "instruction": "press o, type # done, then press Esc",
             "verify": lambda b: any(l.strip().startswith("#") for l in b)},
        ]
    line = lines[0]
    return [
        # single-line starter: duplicate it, then annotate it.
        {"title": "duplicate the line",
         "instruction": "copy this line down — press yy then p",
         "verify": lambda b, line=line: sum(1 for l in b if l == line) >= 2},
        {"title": "add a comment",
         "instruction": "press o, type # done, then press Esc",
         "verify": lambda b: any(l.strip().startswith("#") for l in b)},
    ]

_VIM_DIR = {"h": "←", "l": "→", "j": "↓", "k": "↑", "w": "→", "b": "←",
            "e": "→", "0": "←", "$": "→", "^": "←", "g": "↑", "G": "↓"}


def _vim_arrow(keys):
    """The direction arrow for a lesson's FIRST motion key (blinking cue)."""
    for k in keys:
        if k in _VIM_DIR:
            return _VIM_DIR[k]
        if k == "gg":
            return "↑"
    return ""


class VimDemoBuffer:
    """A tiny text buffer that actually MOVES and EDITS as the ghost dictates,
    so the trainer shows the real effect of each key instead of a static flashcard."""

    def __init__(self, lines):
        self.lines = list(lines)
        self.row = 0
        self.col = 0
        self.yank = ""
        self.undo = []

    def _clamp(self):
        self.row = max(0, min(len(self.lines) - 1, self.row))
        self.col = max(0, min(len(self.lines[self.row]), self.col))

    def _save(self):
        self.undo.append((list(self.lines), self.row, self.col))

    def _flat_pos(self, r, c):
        return sum(len(self.lines[i]) + 1 for i in range(r)) + c

    def _from_flat(self, pos):
        pos = max(0, pos)
        for r, line in enumerate(self.lines):
            if pos <= len(line):
                return r, pos
            pos -= len(line) + 1
        r = len(self.lines) - 1
        return r, len(self.lines[r])

    def _word_fwd(self):
        flat = "\n".join(self.lines)
        i = self._flat_pos(self.row, self.col)
        n = len(flat)
        if i >= n:
            return
        # skip current word, then spaces, land on next non-space
        while i < n and flat[i] != "\n" and not flat[i].isspace():
            i += 1
        while i < n and flat[i] != "\n" and flat[i].isspace():
            i += 1
        self.row, self.col = self._from_flat(i)
        self._clamp()

    def _word_back(self):
        flat = "\n".join(self.lines)
        i = self._flat_pos(self.row, self.col) - 1
        while i >= 0 and flat[i] != "\n" and flat[i].isspace():
            i -= 1
        while i >= 0 and flat[i] != "\n" and not flat[i].isspace():
            i -= 1
        self.row, self.col = self._from_flat(i + 1)
        self._clamp()

    def _word_end(self):
        flat = "\n".join(self.lines)
        i = self._flat_pos(self.row, self.col)
        n = len(flat)
        while i < n and flat[i] != "\n" and flat[i].isspace():
            i += 1
        while i + 1 < n and flat[i + 1] != "\n" and not flat[i + 1].isspace():
            i += 1
        self.row, self.col = self._from_flat(i)
        self._clamp()

    def apply(self, seq):
        """Apply a completed key sequence. Returns a short message or None."""
        s = tuple(seq)
        if s == ("h",):
            self._save(); self.col -= 1; self._clamp(); return None
        if s == ("l",):
            self._save(); self.col += 1; self._clamp(); return None
        if s == ("j",):
            self._save(); self.row += 1; self._clamp(); return None
        if s == ("k",):
            self._save(); self.row -= 1; self._clamp(); return None
        if s == ("w",):
            self._save(); self._word_fwd(); return None
        if s == ("b",):
            self._save(); self._word_back(); return None
        if s == ("e",):
            self._save(); self._word_end(); return None
        if s == ("0",):
            self._save(); self.col = 0; return None
        if s == ("$",):
            self._save(); self.col = max(0, len(self.lines[self.row]) - 1); return None
        if s == ("^",):
            self._save(); self.col = len(self.lines[self.row]) - len(self.lines[self.row].lstrip()); return None
        if s == ("g", "g"):
            self._save(); self.row = 0; self.col = 0; return None
        if s == ("G",):
            self._save(); self.row = len(self.lines) - 1; self.col = 0; return None
        if s == ("5", "j"):
            self._save(); self.row += 5; self._clamp(); return None
        if s == ("x",):
            self._save()
            line = self.lines[self.row]
            if self.col < len(line):
                self.lines[self.row] = line[:self.col] + line[self.col + 1:]
                self._clamp()
            return None
        if s == ("d", "d"):
            self._save()
            if len(self.lines) > 1:
                del self.lines[self.row]
            else:
                self.lines[self.row] = ""
            self._clamp()
            return None
        if s == ("d", "w"):
            self._save()
            start = self._flat_pos(self.row, self.col)
            self._word_fwd()
            end = self._flat_pos(self.row, self.col)
            flat = "\n".join(self.lines)
            flat = flat[:start] + flat[end:]
            self.lines = flat.split("\n")
            self.row, self.col = self._from_flat(start)
            self._clamp()
            return None
        if s in (("d", "$"), ("D",)):
            self._save()
            self.lines[self.row] = self.lines[self.row][:self.col]
            self._clamp()
            return None
        if s == ("y", "y"):
            self.yank = self.lines[self.row]
            return "yanked the line"
        if s == ("y", "w"):
            start = self._flat_pos(self.row, self.col)
            self._word_fwd()
            end = self._flat_pos(self.row, self.col)
            self.yank = "\n".join(self.lines)[start:end]
            self.row, self.col = self._from_flat(start)
            return "yanked the word"
        if s == ("y", "$"):
            self.yank = self.lines[self.row][self.col:]
            return "yanked to end of line"
        if s in (("p",), ("P",)):
            if not self.yank:
                return "nothing to paste — yank first"
            self._save()
            target = self.row + 1 if s == ("p",) else self.row
            self.lines.insert(target, self.yank)
            self.row = target; self.col = 0
            return "pasted"
        if s == ("y", "y", "p"):
            if not self.yank:
                self.yank = self.lines[self.row]
            self._save()
            self.lines.insert(self.row + 1, self.yank)
            self.row += 1; self.col = 0
            return "duplicated the line"
        if s == ("u",):
            if self.undo:
                self.lines, self.row, self.col = self.undo.pop()
                self._clamp()
                return "undid"
            return "nothing to undo"
        return None  # flashcard lessons — no buffer effect

    def clone(self):
        b = VimDemoBuffer(list(self.lines))
        b.row, b.col = self.row, self.col
        b.yank = self.yank
        b.undo = list(self.undo)
        return b

    def predict(self, seq):
        """(row, col) the cursor would land on after `seq`, without mutating —
        used to show a 'you'll jump here' ghost before the key is pressed."""
        b = self.clone()
        b.apply(list(seq))
        return (b.row, b.col)


class VimTrainer(Vertical):
    """Full-screen VIM course overlay: a text buffer, an on-screen keyboard, the
    target key combo, and a blinking direction arrow. The app owns the state;
    this widget just holds keyboard focus so keys land here."""

    can_focus = True

    def on_key(self, event: events.Key) -> None:
        self.app._vim_on_key(event)


class TutorApp(App):
    CSS = """
    Screen { background: #000000; }
    #topbar { height: 3; padding: 1 2; background: $boost; }
    #body { height: 1fr; }
    #challenge-box { width: 30%; border: tall $accent; }
    #challenge { height: auto; min-height: 4; max-height: 12; padding: 1 2; overflow: auto; }
    #goal { height: auto; max-height: 9; padding: 0 1; background: #0d1117; border-bottom: solid $success; overflow: auto; }
    #demo-label { height: 1; padding: 0 2; background: $boost; }
    #demo-editor { height: 7; padding: 1 2; background: #0d1117; border: solid $primary; }
    #demo-console { height: 5; padding: 1 2; background: #000000; border: solid $success; }
    #editor-box { width: 1fr; border: tall $primary; }
    #editor-label { height: 1; padding: 0 2; color: $text; }
    #editor-label.normal { background: #1f4e79; }
    #editor-label.insert { background: #1e6b3f; }
    #example-ref { height: auto; padding: 1 2; background: #0d1117; border-bottom: solid $warning; }
    #editor { height: 1fr; padding: 1 2; }
    #output { height: 7; border-top: solid $primary; background: $surface-darken-1; }
    #guide { height: 3; padding: 1 2; background: $boost; border-top: solid $primary; }
    #task { height: 3; padding: 1 2; background: $accent; color: $text; }
    #cmd { dock: bottom; display: none; }
    #cmd.visible { display: block; }
    #cmd.flash { border: tall yellow; background: #4d4000; }
    #wildmenu { height: 1; display: none; padding: 0 2; background: $boost; border-top: solid $primary; }
    #wildmenu.visible { display: block; }
    #lesson { layer: overlay; width: 100%; height: 100%; padding: 2 4; background: #000000; display: none; overflow: auto; }
    #lesson.visible { display: block; }
    #gate { layer: overlay; width: 100%; height: 100%; padding: 2 4; background: #000000; display: none; overflow: auto; }
    #gate.visible { display: block; }
    #ghost { layer: overlay; width: 100%; height: 100%; padding: 2 4; background: #000000; display: none; align-horizontal: center; align-vertical: middle; }
    #ghost.visible { display: block; }
    #ghost-head { width: 100%; text-align: center; }
    #ghost-code { width: 100%; text-align: center; margin: 1 0; }
    #ghost-console { width: 100%; text-align: center; }
    #ghost-why { width: 100%; text-align: center; margin: 1 0; }
    #ghost-foot { width: 100%; text-align: center; }
    #vim { layer: overlay; width: 100%; height: 100%; padding: 1 2; background: #000000; display: none; }
    #vim.visible { display: block; }
    #vim-head { width: 100%; text-align: center; }
    #vim-body { width: 100%; height: 1fr; }
    #vim-buffer { width: 100%; height: 1fr; }
    #vim-cmd { width: 100%; text-align: center; margin: 1 0; }
    #vim-kb { width: 100%; margin: 1 0; text-align: center; }
    #vim-foot { width: 100%; text-align: center; }
    #cheat { width: 34%; border: tall $warning; padding: 1 2; display: none; }
    #cheat.visible { display: block; }
    #side-examples { width: 42%; border: tall $warning; padding: 0; }
    #side-examples.hidden { display: none; }
    #side-examples-title { height: 1; padding: 0 2; background: $boost; color: $text; }
    #side-scroll { height: 1fr; }
    #side-inner { height: auto; padding: 1 2; }
    #visual { layer: overlay; width: 100%; height: 100%; background: #000000; display: none; }
    #visual.visible { display: block; }
    #cat { layer: overlay; width: 100%; height: 100%; background: #000000; display: none; }
    #cat.visible { display: block; }
    #quick { layer: overlay; width: 100%; height: 100%; background: #000000 88%; display: none; }
    #quick.visible { display: block; }
    #quit { layer: overlay; width: 100%; height: 100%; background: #000000 88%; display: none; }
    #quit.visible { display: block; }
    .hidden { display: none; }
    Confetti { layer: overlay; width: 100%; height: 100%; display: none; }
    #menu-banner { height: auto; padding: 0 2; }
    #menu-progress { height: 1; padding: 0 2; background: $boost; text-style: bold; }
    #menu-body { height: 1fr; }
    #menu-list { width: 1fr; padding: 1 2; }
    #menu-list-inner { width: 1fr; height: auto; }
    #menu-preview { width: 42%; border-left: solid $primary; background: $boost; padding: 0; }
    #menu-preview-title { height: 1; padding: 0 2; background: $boost; color: $text; text-style: bold; }
    #menu-preview-scroll { height: 1fr; }
    #menu-preview-inner { height: auto; padding: 1 2; }
    #menu-keys { width: 34; padding: 1 2; border-left: solid $primary; background: $boost; }
    #menu-keys-inner { width: 1fr; height: auto; }
    #menu-settings-title { height: 1; padding: 1 1 0 1; text-style: bold; color: $text; }
    #menu-keys Checkbox { margin: 0 1; height: 1; }
    #menu-help { height: 3; padding: 1 2; background: $boost; border-top: solid $primary; }
    """

    BINDINGS = [
        Binding("q", "quit", "Quit"),
        Binding("ctrl+c", "quit", "Quit"),
        Binding("enter", "start", "Begin", show=False),
        Binding("i", "start", "Begin", show=False),
        Binding("j", "menu_down", "Down", show=False),
        Binding("down", "menu_down", "Down", show=False),
        Binding("k", "menu_up", "Up", show=False),
        Binding("up", "menu_up", "Up", show=False),
        Binding("escape", "menu", "Menu", show=False),
        Binding("colon", "command", "Command", show=False),
        Binding("ctrl+n", "next_challenge", "Next", show=False),
        Binding("ctrl+b", "prev_challenge", "Prev", show=False),
        Binding("f1", "help", "Keys", show=False),
        Binding("f2", "toggle_cheat", "Cheat", show=False),
        Binding("f3", "demo", "Demo", show=False),
        Binding("ctrl+g", "ghost", "Ghost", show=False),
        Binding("f6", "toggle_voice", "Voice", show=False),
        Binding("f7", "review", "Review", show=False),
        Binding("f12", "quick_check", "Check", show=False),
        Binding("m", "toggle_music", "Music", show=False),
        Binding("y", "quit_save", "SaveQuit", show=False),
        Binding("e", "lesson", "Lesson", show=False),
        Binding("w", "gate_watch", "Watch", show=False),
        Binding("l", "gate_listen", "Listen", show=False),
        Binding("f8", "examples", "Examples", show=False),
        Binding("f9", "toggle_hints", "Hints", show=False),
        Binding("f10", "editor_wider", "Wider", show=False),
        Binding("f11", "editor_narrower", "Narrower", show=False),
    ]

    def __init__(self):
        super().__init__()
        self.mode = "menu"           # "menu" | "challenge"
        self.group_idx = 0
        self.ch_idx = 0
        self.menu_sel = 0
        self.menu_level = "series"      # "series" (pick a tier) | "challenges"
        self.series_sel = -1            # -1 = VIM/NEOVIM course, 0.. = GROUPS
        self.started = False
        self.last: str | None = None
        self.seen_topics = set()
        self.p = load_progress()
        # persist the prelude + full-topic-lecture flags so they don't replay on
        # every app restart (in-memory-only meant "how python works" each session)
        self._structure_taught = bool(self.p.get("structure_taught", False))
        self._topics_taught = set(self.p.get("topics_taught", []))
        self._warmup_on = False        # post-ghost vim edit warm-up active
        self._warmup_idx = 0
        self.attempts: dict[int, int] = {}
        self.voice_on = True
        self.music_on = True          # "music" = the win/fail celebration mp3s (m toggles)
        self.hints_on = True          # F9 toggles: show/underline the mistake on a fail
        self._settings_guard = False  # suppresses checkbox echoes during programmatic sync
        self._ex_whys: list[str] = []  # ELI15 lines for the open examples panel (TTS)
        self._challenge_w = 30         # challenge-box width % (smaller = bigger editor)
        self._vis_spec = None          # visual replay state (boxes fill as code "runs")
        self._vis_kind = "counter"
        self._vis_n = 0
        self._vis_step = 0
        self._vis_timer = None
        self._tts = _tts_engine()
        self._demo_timer = None
        self._demo_next_timer = None
        self._demo_gen = 0
        self._demo_phase = "idle"
        self._demo_code = ""
        self._demo_i = 0
        self._ghost_on = False
        self._ghost_required = False    # True = mandatory drill, Esc is locked
        self._ghost_on_done = None      # completion callback (mandatory mode)
        self._ghost_gen = 0
        self._ghost_examples: list[dict] = []
        self._ghost_idx = 0
        self._ghost_target = ""
        self._ghost_stdin = ""
        self._ghost_pos = 0
        self._ghost_errors: dict[int, str] = {}   # target index -> wrong char typed
        self._ghost_done = False
        self._ghost_phase = "type"      # type | run | reveal | ran
        self._ghost_out_text = ""
        self._ghost_out_i = 0
        self._ghost_out_timer = None
        self._ghost_blink_on = False
        self._ghost_blink_timer = None
        self._ghost_nudge = False
        self._ghost_nudge_timer = None
        self._ghost_shake_i = 0
        self._ghost_shake_timer = None
        self._ghost_last_tip = None
        self._ghost_mode = "write"          # ramp level: watch | finish | write
        self._ghost_last_mode = None        # last announced mode (for the TTS cue)
        self._ghost_result_tip_text = ""   # spoken once the output reveal finishes
        self._ex_anim_timer = None    # worked-examples output spit-out animation
        self._ex_cards: list[dict] = []
        self._ex_w = 34
        self._ex_reveal = 0
        self._ex_total = 0
        self._ex_blink = False
        self._vim_on = False
        self._vim_idx = 0
        self._vim_step = 0
        self._vim_buf = VimDemoBuffer(VIM_DEMO)
        self._vim_blink = False
        self._vim_blink_timer = None
        self._vim_msg = ""
        self._vim_challenge = False
        self._vim_target = (0, 0)
        self._vim_challenge_idx = 0
        self._vim_pending = None       # first key of a 2-key command in a challenge
        self._vim_preview = None       # (row, col) ghost showing where the key lands
        self._vim_done = False         # all challenges cleared
        self._vim_advance_timer = None # short hold showing the move before the next lesson
        self._menu_anim_timer = None
        self._menu_frame = 0
        self._cmd_demo_shown = False
        self._cmd_demoing = False
        self._cmd_demo_timer = None
        self._flash_timer = None
        self._cel_pool = CEL_SOUNDS[:]
        random.shuffle(self._cel_pool)
        self._fail_pool = FAIL_SOUNDS[:]
        random.shuffle(self._fail_pool)
        self._sound_map: dict[int, tuple] = {}
        self._wm_index = 0
        self._wm_matches_list: list[str] = []
        self._wm_ignore_changed = False
        self.lesson_gate = False
        self._lesson_on = False
        self._lesson_gen = 0
        self._lesson_steps: list[dict] = []
        self._lesson_i = 0
        self._lesson_typed = 0
        self._lesson_code = ""
        self._lesson_caption = ""
        self._lesson_result = ""
        self._lesson_phase = ""
        self._lesson_timer = None
        self._lesson_blocks: list = []
        self._lesson_out_text = ""   # full output of the current example (for the reveal)
        self._lesson_out_i = 0       # how many chars have been revealed so far
        self._caption_title = ""
        self._caption_words: list = []
        self._caption_i = 0
        self._caption_wi = 0
        self._caption_word_durs: list = []
        self._tour_code = ""          # code walkthrough tour state
        self._tour_parts: list = []
        self._tour_i = 0
        self._tour_blink_on = False
        self._tour_blink_timer = None
        self._tour_output = ""
        self._tour_caption = ""
        self._tour_stdin = ""
        self._tour_why = ""
        self._celebrate_timer = None
        self._pending_win = None
        self._out_reveal_text = ""      # main #output reveal (blue cursor + sound)
        self._out_reveal_i = 0
        self._out_reveal_timer = None
        self._out_reveal_final = None
        self._cat_timer = None
        self._cat_on_done = None
        self._cat_playing = False
        self._cat_proc = None           # the ffplay/mpv process (killed on cancel)

    def compose(self) -> ComposeResult:
        yield Header(show_clock=True)
        yield Static("", id="topbar")
        # menu view (shown on launch)
        yield Static("", id="menu-banner")
        yield Static("", id="menu-progress")
        with Horizontal(id="menu-body"):
            with VerticalScroll(id="menu-list"):
                yield Static("", id="menu-list-inner")
            with Vertical(id="menu-preview"):
                yield Static("PREVIEW", id="menu-preview-title")
                with VerticalScroll(id="menu-preview-scroll"):
                    yield Static("", id="menu-preview-inner")
            with VerticalScroll(id="menu-keys"):
                yield Static("SETTINGS", id="menu-settings-title")
                yield Checkbox("Voice  (reads aloud)", id="set-voice", value=True)
                yield Checkbox("Music  (win/fail sounds)", id="set-music", value=True)
                yield Checkbox("Key sounds  (typing + blips)", id="set-keys", value=True)
                yield Checkbox("Hints  (underline mistakes)", id="set-hints", value=True)
                yield Static("", id="menu-keys-inner")
        yield Static("", id="menu-help")
        # challenge view (hidden until a challenge is selected)
        with Horizontal(id="body", classes="hidden"):
            with VerticalScroll(id="challenge-box"):
                yield Static("[bold]CHALLENGE[/]", id="challenge-label")
                yield Static("", id="task")
                yield Markdown("", id="challenge")
                yield Static("", id="goal")
                yield Static("", id="demo-label")
                yield Static("", id="demo-editor")
                yield Static("", id="demo-console")
            with Vertical(id="editor-box"):
                yield Static("", id="editor-label")
                yield Static("", id="example-ref")
                yield VimEditor(id="editor")
                yield Static("", id="output")
                yield Static("", id="wildmenu")
                yield CommandInput(placeholder=":  (w = save, !python3 % / submit = run+submit, q = quit · Tab = autocomplete)", id="cmd")
            with Vertical(id="side-examples"):
                yield TabLabel("examples", id="side-examples-title")
                with VerticalScroll(id="side-scroll"):
                    yield Static("", id="side-inner")
            yield Markdown("", id="cheat")
        yield Static("", id="guide", classes="hidden")
        yield Static("", id="status", classes="hidden")
        yield Static("", id="lesson")
        yield Static("", id="gate")
        with GhostWriter(id="ghost"):
            yield Static("", id="ghost-head")
            yield Static("", id="ghost-code")
            yield Static("", id="ghost-console")
            yield Static("", id="ghost-why")
            yield Static("", id="ghost-foot")
        with VimTrainer(id="vim"):
            yield Static("", id="vim-head")
            with Vertical(id="vim-body"):
                yield Static("", id="vim-buffer")
                yield Static("", id="vim-cmd")
            yield Static("", id="vim-kb")
            yield Static("", id="vim-foot")
        yield Static("", id="visual")
        yield Static("", id="cat")
        yield Static("", id="quick")
        yield Static("", id="quit")
        yield Confetti(id="confetti")

    def on_mount(self):
        self.title = "tutor"
        self.sub_title = "learn Python like it's nvim"
        self.query_one("#topbar", Static).update(
            f"[bold]tutor[/]  ·  LVL {level_for(self.p['xp'])} [yellow]{self.p['xp']} XP[/]"
        )
        self._set_resume_sel()
        self._show_menu()
        if self.voice_on:
            # pre-warm the piper voice in the background while the menu is up,
            # so the first utterance has no model-load delay
            threading.Thread(target=_warmup_server, daemon=True).start()

    # ---- menu -------------------------------------------------------------- #

    def _menu_items(self):
        """Flat list of (group_idx, challenge_idx) in display order."""
        items = []
        for gi, g in enumerate(GROUPS):
            for ci in range(len(g["challenges"])):
                items.append((gi, ci))
        return items

    def _set_resume_sel(self):
        items = self._menu_items()
        idx = None
        if self.p.get("last"):
            for i, (gi, ci) in enumerate(items):
                if GROUPS[gi]["challenges"][ci]["title"] == self.p["last"]:
                    idx = i
                    break
        if idx is None:
            for i, (gi, ci) in enumerate(items):
                st = challenge_stat(self.p, GROUPS[gi]["challenges"][ci]["title"])
                if st["right"] == 0 and st["wrong"] == 0:
                    idx = i
                    break
        if idx is None:
            idx = 0
        gi, ci = items[idx]
        self.series_sel = gi
        self.menu_sel = ci

    def _show_menu(self):
        self.mode = "menu"
        self.menu_level = "series"
        self._stop_demo_timers()
        self._stop_ex_anim()
        self._cancel_celebrate()
        self._cancel_cat()
        self.query_one("#confetti", Confetti).dismiss()
        self.query_one("#gate", Static).remove_class("visible")
        for w in ("#menu-banner", "#menu-body", "#menu-help"):
            self.query_one(w).remove_class("hidden")
        for w in ("#body", "#guide", "#status"):
            self.query_one(w).add_class("hidden")
        self._render_menu()
        self._sync_settings_checkboxes()

    def _show_challenge(self):
        self.mode = "challenge"
        self._stop_menu_anim()
        for w in ("#menu-banner", "#menu-body", "#menu-help"):
            self.query_one(w).add_class("hidden")
        for w in ("#body", "#guide", "#status"):
            self.query_one(w).remove_class("hidden")

    def _render_menu(self):
        self.query_one("#menu-banner", Static).update(self._banner_text())
        self._start_menu_anim()
        self._render_progress()
        if self.menu_level == "series":
            self._render_series_list()
        else:
            self._render_challenge_list()
        self._render_menu_preview()
        self._render_menu_help()
        self._render_menu_keys()

    # ---- progress --------------------------------------------------------- #

    def _overall_progress(self):
        total = sum(len(g["challenges"]) for g in GROUPS)
        done = sum(1 for g in GROUPS for c in g["challenges"]
                   if challenge_stat(self.p, c["title"])["right"] > 0)
        return done, total

    def _group_progress(self, gi):
        g = GROUPS[gi]
        total = len(g["challenges"])
        done = sum(1 for c in g["challenges"]
                   if challenge_stat(self.p, c["title"])["right"] > 0)
        return done, total

    def _bar_text(self, done, total, width=18):
        t = Text()
        fill = round(done / total * width) if total else 0
        t.append("▰" * fill, style="green")
        t.append("▱" * (width - fill), style="#333333")
        return t

    def _render_progress(self):
        done, total = self._overall_progress()
        pct = round(done / total * 100) if total else 0
        fill = round(done / total * 40) if total else 0
        t = Text()
        t.append("PROGRESS  ", style="dim")
        t.append("▰" * fill, style="green")
        t.append("▱" * (40 - fill), style="#333333")
        t.append(f"   {done}/{total}  {pct}%", style="bold")
        self.query_one("#menu-progress", Static).update(t)

    # ---- the two menu levels --------------------------------------------- #

    def _render_series_list(self):
        t = Text()
        t.append("CHOOSE A SERIES", style="bold magenta")
        t.append("\n\n")
        # VIM/NEOVIM course first (series_sel == -1)
        sel = self.series_sel == -1
        t.append("▶ " if sel else "  ")
        t.append("VIM / NEOVIM COURSE", style="bold #d8b4fe" if sel else "#c9a7eb")
        t.append("   keyboard dojo", style="dim")
        t.append("\n")
        t.append("   ")
        t.append("learn h j k l, editing, then a live challenge", style="dim")
        t.append("\n\n")
        for gi, g in enumerate(GROUPS):
            done, total = self._group_progress(gi)
            sel = gi == self.series_sel
            t.append("▶ " if sel else "  ")
            t.append(g["name"], style="bold white" if sel else "#d5d5d5")
            t.append(f"   {done}/{total}", style="dim")
            t.append("\n")
            t.append("   ")
            t.append_text(self._bar_text(done, total))
            t.append("\n\n")
        t.append("Enter — open a series   ·   j/k — move   ·   q — quit", style="dim")
        self.query_one("#menu-list-inner", Static).update(t)

    def _render_challenge_list(self):
        g = GROUPS[self.series_sel]
        t = Text()
        t.append(f"── {g['name']} ", style="bold cyan")
        t.append(f"({len(g['challenges'])} challenges)", style="dim")
        t.append("\n\n")
        sel_line = 0
        line_no = 0
        for ci, c in enumerate(g["challenges"]):
            st = challenge_stat(self.p, c["title"])
            right, wrong = st["right"], st["wrong"]
            sel = ci == self.menu_sel
            line = Text()
            line.append("▶ " if sel else "  ")
            if right > 0:
                line.append("✓ ", style="green")
            elif wrong > 0:
                line.append("✗ ", style="red")
            else:
                line.append("· ", style="dim")
            line.append(c["title"], style="bold" if sel else "")
            if sel:
                line.stylize("reverse")
                sel_line = line_no
            t.append_text(line)
            t.append("\n")
            line_no += 1
        t.append("\nEnter — start   ·   Esc — back to series   ·   j/k — move", style="dim")
        self.query_one("#menu-list-inner", Static).update(t)
        scroll = self.query_one("#menu-list", VerticalScroll)
        self.call_after_refresh(scroll.scroll_to, y=sel_line, animate=False)

    def _preview_challenge(self):
        if self.series_sel == -1:
            return None   # VIM course — handled separately in _render_menu_preview
        if self.menu_level == "series":
            g = GROUPS[self.series_sel]
            return g["challenges"][0] if g["challenges"] else None
        g = GROUPS[self.series_sel]
        return g["challenges"][self.menu_sel] if 0 <= self.menu_sel < len(g["challenges"]) else None

    def _render_menu_preview(self):
        if self.series_sel == -1:
            self.query_one("#menu-preview-title", Static).update("PREVIEW — VIM / NEOVIM COURSE")
            t = Text()
            t.append("A keyboard dojo that makes you fast at vim movement + editing.\n\n", style="#f0f0f5")
            for line in ("on-screen keyboard — the key to press glows",
                         "ghost movement — the cursor really moves",
                         "blinking arrows show the direction",
                         "then a live movement challenge"):
                t.append("• ", style="dim")
                t.append(line, style="#d5d5d5")
                t.append("\n")
            self.query_one("#menu-preview-inner", Static).update(t)
            return
        c = self._preview_challenge()
        if c is None:
            self.query_one("#menu-preview-title", Static).update("PREVIEW")
            self.query_one("#menu-preview-inner", Static).update("")
            return
        self.query_one("#menu-preview-title", Static).update(f"PREVIEW — {c['title']}")
        try:
            panel_w = self.query_one("#menu-preview", Vertical).size.width
        except Exception:
            panel_w = 42
        w = max(20, panel_w - 10)
        t = Text()
        t.append("WHAT TO DO", style="bold yellow")
        t.append("\n")
        t.append(re.sub(r"[`*_#>~]", "", c.get("prompt", "")), style="#f0f0f5")
        t.append("\n\n")
        cards = self._examples_cards(c)
        for i, card in enumerate(cards):
            if i:
                t.append("\n")
            t.append_text(self._render_ex_box(card, w))
        self.query_one("#menu-preview-inner", Static).update(t)

    def _banner_text(self):
        art = CAT_FRAMES[self._menu_frame % len(CAT_FRAMES)]
        w = max(len(ln) for ln in art)
        pad = max(0, (self.size.width - w) // 2)
        t = Text()
        for ln in art:
            if pad:
                t.append(" " * pad)
            t.append(ln, style=CAT_STYLE)
            t.append("\n")
        return t

    def _start_menu_anim(self):
        if self._menu_anim_timer is None:
            self._menu_anim_timer = self.set_interval(0.4, self._menu_anim_tick)

    def _stop_menu_anim(self):
        t = self._menu_anim_timer
        if t is not None:
            t.stop()
            self._menu_anim_timer = None

    def _menu_anim_tick(self):
        self._menu_frame = (self._menu_frame + 1) % len(CAT_FRAMES)
        self.query_one("#menu-banner", Static).update(self._banner_text())

    def _render_menu_help(self):
        music = "[green]music ON[/]" if self.music_on else "[red]music MUTED[/]"
        voice = "[green]voice ON[/]" if (self.voice_on and self._tts) else "[red]voice OFF[/]"
        nav = ("[dim]j/k move · Enter open series · q quit[/]" if self.menu_level == "series"
               else "[dim]j/k move · Enter start · Esc back to series[/]")
        self.query_one("#menu-help", Static).update(
            f"{nav}  {music} · {voice}  ·  "
            f"[dim]·[/] [green]{self.p['done']} done[/] [dim]·[/] streak [yellow]{self.p['streak']}[/]"
        )

    def _render_menu_keys(self):
        kc = lambda k: f"[on #3a3a3a]{k}[/]"
        self.query_one("#menu-keys-inner", Static).update(
            Text.from_markup(
                f"{kc('Enter')}  open / start\n"
                f"{kc('Esc')}  back\n"
                f"{kc('j')}{kc('k')}   move\n"
                f"{kc('q')}   quit\n\n"
                f"[dim]{kc('F1')} full keymap[/]"
            )
        )

    # ---- settings checkboxes (menu) ------------------------------------- #

    def _sync_settings_checkboxes(self):
        """Mirror the live flags onto the checkbox widgets (no-op echoes)."""
        self._settings_guard = True
        try:
            self.query_one("#set-voice", Checkbox).value = self.voice_on and bool(self._tts)
            self.query_one("#set-music", Checkbox).value = self.music_on
            self.query_one("#set-keys", Checkbox).value = key_sounds()
            self.query_one("#set-hints", Checkbox).value = self.hints_on
        finally:
            self._settings_guard = False

    def on_checkbox_changed(self, event: Checkbox.Changed) -> None:
        if self._settings_guard:
            return
        cid = event.checkbox.id
        if cid == "set-voice":
            self.voice_on = event.value
        elif cid == "set-music":
            self.music_on = event.value
        elif cid == "set-keys":
            set_key_sounds(event.value)
        elif cid == "set-hints":
            self.hints_on = event.value
        self._render_menu_help()
        if self.mode == "challenge":
            self._update_status()

    def action_menu_down(self):
        if self.mode != "menu":
            return
        if self.menu_level == "series":
            self.series_sel += 1
            if self.series_sel >= len(GROUPS):
                self.series_sel = -1
        else:
            n = len(GROUPS[self.series_sel]["challenges"])
            self.menu_sel = (self.menu_sel + 1) % n
        play_menu_blip(0)
        self._render_menu()

    def action_menu_up(self):
        if self.mode != "menu":
            return
        if self.menu_level == "series":
            self.series_sel -= 1
            if self.series_sel < -1:
                self.series_sel = len(GROUPS) - 1
        else:
            n = len(GROUPS[self.series_sel]["challenges"])
            self.menu_sel = (self.menu_sel - 1) % n
        play_menu_blip(0)
        self._render_menu()

    def action_quit(self):
        """q — vim-style: first press asks save/quit, second press quits."""
        if self.query_one("#quit", Static).has_class("visible"):
            self.exit()
            return
        self.query_one("#editor", VimEditor).blur()
        self._render_quit()
        self.query_one("#quit", Static).add_class("visible")

    def action_quit_save(self):
        """y — save progress & quit (:wq)."""
        if self.query_one("#quit", Static).has_class("visible"):
            save_progress(self.p)
            self.exit()

    def _render_quit(self):
        out = [Text("QUIT tutor?", style="bold white"), Text("")]
        out.append(Text("y   save progress & quit    (:wq)", style="#f0f0f5"))
        out.append(Text("q   quit without saving    (:q)", style="#f0f0f5"))
        out.append(Text("Esc   cancel", style="dim"))
        body = _box_lines(out)
        self.query_one("#quit", Static).update(
            _center_screen(body, self.size.width, self.size.height - 1))

    def action_menu(self):
        if self._ghost_on:
            return   # ghost overlay owns the keyboard; Esc there dismisses it
        if self._vim_on:
            return   # VIM course overlay owns the keyboard; Esc there exits it
        if self._lesson_on:
            self._finish_lesson()
            return
        if self.query_one("#visual", Static).has_class("visible"):
            self._close_visual()
            return
        if self.query_one("#quick", Static).has_class("visible"):
            self.query_one("#quick", Static).remove_class("visible")
            return
        if self.query_one("#quit", Static).has_class("visible"):
            self.query_one("#quit", Static).remove_class("visible")
            self.query_one("#editor", VimEditor).focus()
            return
        if self.mode == "menu":
            if self.menu_level == "challenges":
                self.menu_level = "series"
                self._render_menu()
            return
        self._stop_demo_timers()
        self.started = False
        self._show_menu()

    def _select_challenge(self):
        self.group_idx = self.series_sel
        self.ch_idx = self.menu_sel
        self.p["last"] = self._current()["title"]
        save_progress(self.p)
        self.started = True
        play_menu_blip(3)
        self._show_challenge()
        self._render_challenge()
        # editor focus happens once the user passes the lesson gate (Enter/e)

    def _current(self):
        return GROUPS[self.group_idx]["challenges"][self.ch_idx]

    def _flat_index(self):
        n = 0
        for gi in range(self.group_idx):
            n += len(GROUPS[gi]["challenges"])
        return n + self.ch_idx

    def action_start(self):
        if self._ghost_on:
            return   # ghost overlay owns the keyboard until dismissed
        if self._vim_on:
            return   # VIM course overlay owns the keyboard
        if self._cat_playing:
            return   # cat-microwave loading screen in progress — input is ignored
        if self._lesson_on:
            self._lesson_next()
            return
        if self.mode == "menu":
            if self.menu_level == "series":
                if self.series_sel == -1:
                    self._vim_begin()
                    return
                self.menu_level = "challenges"
                g = GROUPS[self.series_sel]
                self.menu_sel = 0
                for ci, c in enumerate(g["challenges"]):
                    if challenge_stat(self.p, c["title"])["right"] == 0:
                        self.menu_sel = ci
                        break
                self._render_menu()
            else:
                self._select_challenge()
            return
        if self.lesson_gate:
            self._enter_editor()
            return
        if not self.started:
            self.started = True
            self._render_challenge()
            return
        if self.last == "pass":
            self._advance_after_pass()

    def _render_challenge(self):
        c = self._current()
        xp, lvl = self.p["xp"], level_for(self.p["xp"])
        self.query_one("#topbar", Static).update(
            f"[bold]tutor[/]  ·  LVL {lvl} [yellow]{xp} XP[/]  ·  "
            f"[green]{self.p['done']} done[/]  ·  streak [yellow]{self.p['streak']}[/]"
        )
        if c.get("predict"):
            self.query_one("#challenge", Markdown).update(
                f"## {c['title']}\n\n"
                f"### READ THIS CODE\n```python\n{c['code']}\n```\n\n"
                f"### WHAT TO DO\n{c['prompt']}"
            )
        else:
            self.query_one("#challenge", Markdown).update(
                f"## {c['title']}\n\n"
                f"### WHAT TO DO\n{c['prompt']}"
            )
        self.query_one("#goal", Static).update(self._goal_panel(c))
        self.query_one("#example-ref", Static).update(
            "[dim]worked examples are on the right →  ([reverse]F8[/] hide/show · scroll for more)[/]")
        self.query_one("#editor", VimEditor).set_text(c["starter"])
        self.query_one("#output", Static).update("")
        self.last = None
        self._cancel_celebrate()
        self._cancel_output_reveal()
        self.query_one("#confetti", Confetti).dismiss()
        self._update_status()
        self._update_guide()
        self._set_task_arrow(c["title"])
        self._render_side_examples()
        self._start_demo()
        self.sub_title = c["title"]
        topic = c.get("topic", "custom")
        self.seen_topics.add(topic)
        # open the challenge gate popup: Enter = dive in, w = watch lesson, l = listen
        self.lesson_gate = True
        # hard-clear any stale ghost overlay so it can't swallow 'w' at the gate
        # (a leftover _ghost_on=True makes GhostWriter's on_key eat 'w' as typing)
        if self._ghost_on:
            self._ghost_dismiss()
        # blur the editor so w/l/e/Enter reach the app (gate) bindings instead of
        # being swallowed as normal-mode vim keys — otherwise after advancing from
        # a challenge the editor still has focus and `w` just moves a word.
        self.query_one("#editor", VimEditor).blur()
        self._render_gate()
        self._update_guide()
        if self.voice_on:
            speak(f"Task {self._flat_index() + 1}: {c['title']}. Press enter to dive in, w to watch the lesson, or l to listen.")

    def _goal_values(self, c) -> list[str]:
        """The target output as a short list of values, for the GOAL diagram."""
        spec = c.get("visual")
        if spec:
            n = int(spec.get("n", 0) or 0)
            kind = spec.get("kind", "counter")
            if kind == "counter":
                return [str(i) for i in range(1, n + 1)]
            expect = [str(v) for v in c.get("expect", [])]
            if len(expect) == n:
                return expect
            if len(set(expect)) == 1 and expect:
                return expect * n
            return [str(i) for i in range(1, n + 1)]
        expect = [str(v) for v in c.get("expect", [])]
        if expect:
            return expect[:8]
        code = example_code(c.get("example", ""))[1] or self._textbook_code(c)
        out = self._example_output(code, c.get("stdin", ""))
        return [v for v in out.split("\n") if v][:8]

    def _goal_panel(self, c) -> Text:
        """A compact 'at a glance' panel under the challenge text: the target
        output as colored cells + the syntax you'll need, highlighted."""
        try:
            bw = self.query_one("#challenge-box", VerticalScroll).size.width
        except Exception:
            bw = 34
        w = max(20, bw - 8)
        t = Text()
        t.append("GOAL", style="bold yellow")
        t.append("\n")
        prompt = re.sub(r"[`*_#>~]", "", c.get("prompt", "")).strip()
        for ln in _wrap_words(prompt, w):
            t.append(ln, style="#f0f0f5")
            t.append("\n")
        values = self._goal_values(c)
        cells = []
        for i, v in enumerate(values):
            cells.append((f" {v} ", "bold black on #22c55e"))
            if i < len(values) - 1:
                cells.append(("→", "dim"))
        line = Text()
        for txt, style in cells:
            if line.cell_len and line.cell_len + len(txt) > w:
                t.append_text(line)
                t.append("\n")
                line = Text()
            line.append(txt, style=style)
        if line.cell_len:
            t.append_text(line)
        t.append("\n")
        need = c.get("need", [])
        if need:
            t.append("NEED", style="bold cyan")
            t.append("  ", style="dim")
            for i, tok in enumerate(need):
                ft = highlight_line(tok)
                ft.stylize("bold")
                t.append_text(ft)
                if i < len(need) - 1:
                    t.append("   ", style="dim")
        return _box_lines(_lines_of(t))

    def _set_task_arrow(self, title):
        """Steady arrow pointing at the current task.

        Was a blinking arrow via set_interval — but the timer was never
        cancelled, so every challenge added another 0.5s timer and the task
        title flickered rapidly between challenge titles. Now it's static,
        and any leftover timer is stopped first."""
        t = getattr(self, "_arrow_timer", None)
        if t is not None:
            t.stop()
            self._arrow_timer = None
        self.query_one("#task", Static).update(f"[bold]▶ {title}[/]  ·  read, type, test")

    # ---- textbook example (static, above your editor) ---------------------- #

    def _textbook_code(self, c) -> str:
        # Prefer the challenge's inline "similar but different" example (so the
        # reference never shows the exact answer), else the first authored one.
        code = example_code(c.get("example", ""))[1]
        if code:
            return code
        exs = EXAMPLES.get(c["title"])
        if exs:
            return exs[0]["code"]
        return EXAMPLES["custom"][0]["code"]

    def _render_example_ref(self, code: str) -> Text:
        t = Text()
        t.append("TEXTBOOK EXAMPLE — similar, not your answer", style="bold yellow")
        t.append("\n")
        for i, line in enumerate(code.split("\n")):
            t.append(f"{i+1:>2} │ ", style="dim")
            t.append_text(_code_text(line))
            t.append("\n")
        return t

    # ---- demo (type examples, run them, loop with a pause) ----------------- #

    DEMO_TYPE_MS = 0.12       # slow, readable typing
    DEMO_CONSOLE_MS = 0.03    # console replay — a blue cursor + tick per char
    DEMO_PAUSE_S = 10.0       # hold the result before the next example

    def _start_demo(self):
        c = self._current()
        self._demo_examples = EXAMPLES.get(c["title"]) or self._fallback_examples(c)
        self._demo_idx = 0
        self._demo_gen += 1
        self._begin_demo_example()

    def _fallback_examples(self, c):
        # AI/custom challenges have no authored examples — use the inline
        # example if present, else the generic set.
        code = example_code(c.get("example", ""))[1]
        if code:
            return [{"code": code, "stdin": c.get("stdin", "")}]
        return EXAMPLES["custom"]

    def _stop_demo_timers(self):
        for attr in ("_demo_timer", "_demo_next_timer"):
            t = getattr(self, attr, None)
            if t is not None:
                t.stop()
                setattr(self, attr, None)
        self._demo_phase = "idle"

    def _begin_demo_example(self):
        self._stop_demo_timers()
        self._demo_phase = "typing"
        ex = self._demo_examples[self._demo_idx]
        n = len(self._demo_examples)
        self._demo_code = ex["code"]
        self._demo_stdin = ex.get("stdin", "")
        self._demo_i = 0
        self._demo_console_i = 0
        self.query_one("#demo-label", Static).update(
            f"[bold]EXAMPLE {self._demo_idx + 1}/{n}[/] — watch it get typed, then run")
        self.query_one("#demo-editor", Static).update(self._render_demo_editor(""))
        self.query_one("#demo-console", Static).update(Text(""))
        self._demo_timer = self.set_interval(self.DEMO_TYPE_MS, self._demo_type_tick)

    def _demo_type_tick(self):
        if self._demo_phase != "typing":
            return
        code = self._demo_code
        if self._demo_i < len(code):
            self._demo_i += 1
            self.query_one("#demo-editor", Static).update(
                self._render_demo_editor(code[:self._demo_i]))
            return
        # typing finished → run it in a thread (PTY capture can block briefly)
        self._demo_phase = "running"
        self._demo_timer.stop()
        self._demo_timer = None
        self.query_one("#demo-editor", Static).update(self._render_demo_editor(code))
        self.query_one("#demo-console", Static).update(
            Text("running…", style="dim"))
        gen = self._demo_gen
        threading.Thread(
            target=self._capture_demo,
            args=(code, self._demo_stdin, gen),
            daemon=True,
        ).start()

    def _capture_demo(self, code, stdin, gen):
        transcript = run_demo_session(code, stdin)
        self.call_from_thread(self._on_demo_captured, transcript, gen)

    def _on_demo_captured(self, transcript, gen):
        if gen != self._demo_gen:
            return
        try:
            w = max(12, self.query_one("#demo-console", Static).size.width - 4)
        except Exception:
            w = 40
        self._demo_transcript = _wrap_console(transcript, w)
        self._demo_console_i = 0
        self._demo_phase = "console"
        self._demo_timer = self.set_interval(self.DEMO_CONSOLE_MS, self._demo_console_tick)

    def _demo_console_tick(self):
        if self._demo_phase != "console":
            return
        t = self._demo_transcript
        if self._demo_console_i < len(t):
            self._demo_console_i += 1
            # skip newlines instantly so the blue cursor always sits on a printed char
            while self._demo_console_i < len(t) and t[self._demo_console_i] == "\n":
                self._demo_console_i += 1
            # NOTE: no print sound here — the left "EXAMPLE" console is muted
            # (it auto-plays during every challenge and the ticking was annoying).
            self.query_one("#demo-console", Static).update(
                self._render_demo_console(t, self._demo_console_i))
            return
        self._demo_phase = "paused"
        self._demo_timer.stop()
        self._demo_timer = None
        self.query_one("#demo-console", Static).update(self._render_demo_console(t))
        # hold the result, then advance to the next example (loop forever)
        self._demo_next_timer = self.set_timer(self.DEMO_PAUSE_S, self._demo_advance)

    def _demo_advance(self):
        self._demo_next_timer = None
        self._demo_idx = (self._demo_idx + 1) % len(self._demo_examples)
        self._begin_demo_example()

    def _render_demo_editor(self, typed: str) -> Text:
        lines = typed.split("\n") if typed else [""]
        t = Text()
        for i, line in enumerate(lines):
            t.append(f"{i+1:>2} │ ", style="dim")
            t.append_text(_code_text(line))
            if i == len(lines) - 1:
                t.append(" ", style="reverse")
            t.append("\n")
        return t

    def _render_demo_console(self, text: str, upto: int | None = None) -> Text:
        if upto is None:
            t = Text()
            for line in text.split("\n"):
                t.append(line, style="green")
                t.append("\n")
            return t
        t = Text()
        for i, rl in enumerate(_reveal_output_lines(text, upto)):
            if i:
                t.append("\n")
            t.append_text(rl)
        return t

    # ---- ghost write (follow-the-ghost typing trainer) ------------------- #

    def action_ghost(self):
        """Ctrl+G / :ghost — optional re-drill: type the examples out char-by-char,
        following the ghost. Builds muscle + visual memory of the syntax WITHOUT
        being handed the answer (the ghost is a DIFFERENT variation)."""
        if self.mode != "challenge":
            return
        if self._ghost_on:
            if self._ghost_required:
                return   # can't opt out of a mandatory drill
            self._ghost_dismiss()
            self.query_one("#editor", VimEditor).focus()
            return
        self._ghost_examples = self._ghost_pool(self._current())
        self._ghost_idx = 0
        self._ghost_gen += 1
        self._ghost_on = True
        self._ghost_required = False
        self._ghost_on_done = None
        self.query_one("#ghost", GhostWriter).add_class("visible")
        self.query_one("#ghost", GhostWriter).focus()
        self._ghost_begin_example(0)

    def _ghost_pool(self, c):
        """Every distinct worked example for this challenge/topic (EXAMPLES +
        inline + lesson examples), padded with value-swapped variants up to
        GHOST_TARGET — so the drill lands ~8 different styles of the syntax."""
        codes = []
        seen = set()

        def add(code, stdin=""):
            code = (code or "").strip()
            if code and code not in seen:
                seen.add(code)
                codes.append({"code": code, "stdin": stdin or ""})

        for ex in EXAMPLES.get(c["title"], []):
            add(ex["code"], ex.get("stdin", ""))
        add(example_code(c.get("example", ""))[1], c.get("stdin", ""))
        topic = c.get("topic", "custom")
        for ex in LESSONS.get(topic, LESSONS.get("custom")).get("examples", []):
            add(ex.get("code", ""), ex.get("stdin", ""))
        # pad with value-swapped variants (same structure, different values)
        base = list(codes)
        while len(codes) < GHOST_TARGET and base:
            added = False
            for ex in base:
                if len(codes) >= GHOST_TARGET:
                    break
                var = _ghost_variant(ex["code"])
                if var and var not in seen:
                    add(var, ex.get("stdin", ""))
                    base.append({"code": var, "stdin": ex.get("stdin", "")})
                    added = True
            if not added:
                break
        # append 1-2 "change it" reps: the same code with ONE meaningful edit, so
        # the user learns that editing THIS number changes THAT output. These go
        # last — the most thought-provoking step of the ramp.
        for ex in codes[:3]:
            if len(codes) >= GHOST_TARGET + 2:
                break
            res = _change_variant(ex["code"], ex.get("stdin", ""))
            if res:
                nc, ch = res
                if nc and nc not in seen:
                    seen.add(nc)
                    codes.append({"code": nc, "stdin": ex.get("stdin", ""), "change": ch})
        return codes

    def _start_ghost_required(self):
        """Mandatory drill: lock the user into ghost-writing the syntax before
        they may type their own answer. Esc is ignored until it's all written."""
        c = self._current()
        pool = self._ghost_pool(c)
        if not pool:
            self._focus_editor()
            return
        self._ghost_examples = pool
        self._ghost_idx = 0
        self._ghost_gen += 1
        self._ghost_on = True
        self._ghost_required = True
        self._ghost_on_done = self._finish_required_ghost
        self.query_one("#ghost", GhostWriter).add_class("visible")
        self.query_one("#ghost", GhostWriter).focus()
        self._ghost_begin_example(0)

    def _finish_required_ghost(self):
        """Ghost drill complete — run the vim edit warm-up, then unlock the editor."""
        self._start_editor_warmup()

    def _start_editor_warmup(self):
        """After the ghost drill, a short vim-edit warm-up on YOUR OWN challenge
        code (duplicate a line, delete a line, add a comment) so the vim motions
        get exercised on the exact code you're about to write. Skipped when the
        starter has nothing to edit."""
        c = self._current()
        self._warmup_tasks = _build_warmup_tasks(c.get("starter", ""))
        if not self._warmup_tasks:
            self._finish_warmup()
            return
        self._warmup_on = True
        self._warmup_idx = 0
        self.query_one("#editor", VimEditor).set_text(c.get("starter", ""))
        self._warmup_render()
        self.query_one("#editor", VimEditor).focus()
        if self.voice_on:
            speak("Vim warm-up on your code. " + self._warmup_tasks[0]["instruction"] + ".")

    def _warmup_render(self):
        n = len(self._warmup_tasks)
        task = self._warmup_tasks[self._warmup_idx]
        self.query_one("#guide", Static).update(
            f"[bold magenta]VIM WARM-UP {self._warmup_idx + 1}/{n} — practice on your code[/]  "
            f"[bold]{task['title']}[/]  —  {task['instruction']}")
        self.query_one("#task", Static).update(
            f"[bold magenta]▶ {task['title']}[/]  ·  {task['instruction']}")

    def _warmup_check(self):
        """Called after every editor key during a warm-up — advance the task the
        moment the current edit's verify() passes."""
        if not self._warmup_on:
            return
        task = self._warmup_tasks[self._warmup_idx]
        ed = self.query_one("#editor", VimEditor)
        if not task["verify"](list(ed.buffer)):
            return
        play_menu_blip(3)
        self._warmup_idx += 1
        if self._warmup_idx >= len(self._warmup_tasks):
            self._finish_warmup()
            return
        c = self._current()
        self.query_one("#editor", VimEditor).set_text(c.get("starter", ""))
        self._warmup_render()
        if self.voice_on:
            speak(self._warmup_tasks[self._warmup_idx]["instruction"])

    def _finish_warmup(self):
        self._warmup_on = False
        c = self._current()
        self.query_one("#editor", VimEditor).set_text(c["starter"])
        self._focus_editor()

    def _ghost_finish(self):
        """Ghost sequence finished (all reps written) — run the completion hook."""
        cb = self._ghost_on_done
        self._ghost_on_done = None
        self._ghost_dismiss()
        if cb:
            cb()
        else:
            self.query_one("#editor", VimEditor).focus()

    def _ghost_start_pos(self, idx, n):
        """Ramp the drill from 'watch & run' to 'write it all'. Returns
        (start_pos, mode): the first reps are already written (just press enter),
        the middle reps are started for you (finish them), and the last reps you
        type from scratch. start_pos is always a clean token boundary."""
        L = len(self._ghost_target)
        # "change it" reps: type the whole (edited) code — the twist is the
        # instruction + before/after output, not the typing difficulty
        if self._ghost_examples[idx].get("change"):
            return 0, "change"
        if n <= 1:
            return 0, "write"
        watch = max(1, n // 3)            # first third: watch & run
        if idx < watch:
            return L, "watch"
        write_from = n - max(1, n // 3)   # last third: write it all
        if idx >= write_from:
            return 0, "write"
        # middle: finish it — a pre-filled fraction that ramps down
        span = write_from - watch
        frac = 1.0 - (idx - watch + 1) / (span + 1)
        pos = int(L * frac)
        # back up to the start of the current token so we never split a word
        while pos > 0 and (self._ghost_target[pos - 1].isalnum()
                           or self._ghost_target[pos - 1] == "_"):
            pos -= 1
        # and don't start on a structural char (newline / leading indent)
        while pos < L and self._ghost_structural(pos):
            pos += 1
        return pos, "finish"

    def _ghost_begin_example(self, idx):
        self._ghost_stop_timers()
        ex = self._ghost_examples[idx]
        self._ghost_target = ex["code"]
        self._ghost_stdin = ex.get("stdin", "")
        self._ghost_errors = {}
        self._ghost_phase = "type"
        self._ghost_out_text = ""
        self._ghost_out_i = 0
        self._ghost_spot_tokens = []   # result tokens to flash bold during "ran"
        self._ghost_change = ex.get("change")   # "change it" metadata, or None
        # ---- learning ramp: watch -> finish -> write -> change (see, do, change) ----
        self._ghost_pos, self._ghost_mode = self._ghost_start_pos(idx, len(self._ghost_examples))
        self._ghost_done = self._ghost_pos >= len(self._ghost_target)
        # say one short useful thing about THIS example; announce the ramp level
        # the first time it changes, so the progression is explained as you go
        if self.voice_on:
            if self._ghost_change:
                ch = self._ghost_change
                tip = (f"Change it. I turned {ch['meaning']} from {ch['old']} into {ch['new']}. "
                       f"Type it out and watch how the output changes.")
            else:
                tip = _ghost_tip(self._ghost_target)
                if self._ghost_mode != self._ghost_last_mode:
                    self._ghost_last_mode = self._ghost_mode
                    cue = _GHOST_MODE_CUE.get(self._ghost_mode, "")
                    tip = (cue + " " + tip).strip() if tip else cue
            if tip and tip != self._ghost_last_tip:
                speak(tip)
            self._ghost_last_tip = tip
        self._ghost_start_blink()   # blink the ENTER/TAB prompt when one shows
        # the 'why' panel is static per example — set it once, not per keystroke
        self.query_one("#ghost-why", Static).update(_ghost_why_text(self._ghost_target))
        self._ghost_render()

    def _ghost_structural(self, i):
        """True when target[i] is structure the user doesn't TYPE — they press
        Enter for a newline, Tab for a leading-indent space. So: a newline, or a
        leading-indent space (all spaces back to the last newline)."""
        c = self._ghost_target[i]
        if c == "\n":
            return True
        if c == " ":
            j = i - 1
            while j >= 0 and self._ghost_target[j] == " ":
                j -= 1
            return j < 0 or self._ghost_target[j] == "\n"
        return False

    def _ghost_at_newline(self) -> bool:
        return (self._ghost_pos < len(self._ghost_target)
                and self._ghost_target[self._ghost_pos] == "\n")

    def _ghost_at_indent(self) -> bool:
        return (self._ghost_pos < len(self._ghost_target)
                and self._ghost_target[self._ghost_pos] == " "
                and self._ghost_structural(self._ghost_pos))

    def _ghost_consume_newline(self):
        if self._ghost_at_newline():
            self._ghost_pos += 1
            play_key()
            self._ghost_render()

    def _ghost_consume_indent(self):
        if self._ghost_at_indent():
            while (self._ghost_pos < len(self._ghost_target)
                   and self._ghost_target[self._ghost_pos] == " "):
                self._ghost_pos += 1
            play_key()
            self._ghost_render()

    def _ghost_has_prompt(self) -> bool:
        """True when a blinkable prompt is showing: the run button, or an
        Enter/Tab structural prompt."""
        if self._ghost_done:
            return True
        return self._ghost_at_newline() or self._ghost_at_indent()

    def _ghost_on_key(self, event):
        if not self._ghost_on:
            return
        key = event.key
        ch = event.character
        if key == "escape":
            event.stop(); event.prevent_default()
            if self._ghost_required:
                self._ghost_nudge_show()   # locked in — must finish
            else:
                self._ghost_dismiss()
                self.query_one("#editor", VimEditor).focus()
            return
        if key == "enter":
            event.stop(); event.prevent_default()
            if self._ghost_phase == "ran":
                self._ghost_next()
            elif self._ghost_done:
                self._ghost_run()
            elif self._ghost_at_newline():
                self._ghost_consume_newline()   # explicit Enter to drop a line
            else:
                self._ghost_nudge_show()
            return
        if key == "tab":
            event.stop(); event.prevent_default()
            if self._ghost_at_indent():
                self._ghost_consume_indent()    # explicit Tab to indent
            else:
                self._ghost_nudge_show()
            return
        if key == "backspace":
            event.stop(); event.prevent_default()
            self._ghost_backspace()
            return
        if ch and not key.startswith("ctrl+"):
            event.stop(); event.prevent_default()
            self._ghost_type(ch)

    def _ghost_type(self, ch):
        if self._ghost_phase != "type" or self._ghost_done:
            return
        if self._ghost_pos >= len(self._ghost_target):
            # fully typed but red letters remain — nothing left to type, go fix
            self._ghost_nudge_show()
            return
        if self._ghost_structural(self._ghost_pos):
            # at a newline or indent — press Enter/Tab, not a letter
            self._ghost_nudge_show()
            return
        p = self._ghost_pos
        if ch == self._ghost_target[p]:
            self._ghost_pos += 1
            play_key()
        else:
            # wrong char is COMMITTED (keep typing), flagged red to fix later
            self._ghost_errors[p] = ch
            self._ghost_pos += 1
            play_ghost_error()   # comedic 'womp' so the miss is HEARD
            self._ghost_shake()   # and FELT — the text jolts once
        self._ghost_done = (self._ghost_pos >= len(self._ghost_target)
                            and not self._ghost_errors)
        if self._ghost_done:
            play_menu_blip(3)          # completion cue — you're at the end
            self._ghost_start_blink()
        self._ghost_render()

    def _ghost_backspace(self):
        if self._ghost_phase != "type" or self._ghost_pos <= 0:
            return
        self._ghost_pos -= 1
        while self._ghost_pos >= 0 and self._ghost_structural(self._ghost_pos):
            self._ghost_pos -= 1
        # un-typed the char at _ghost_pos — drop any red error there so it's retyped
        self._ghost_errors.pop(self._ghost_pos, None)
        self._ghost_done = False
        # keep the blink timer running — if a newline/indent prompt is now in
        # view it should keep blinking (stopping it would freeze the prompt)
        self._ghost_render()

    def _ghost_nudge_show(self):
        self._ghost_nudge = True
        self._ghost_render()
        if self._ghost_nudge_timer is not None:
            self._ghost_nudge_timer.stop()
        self._ghost_nudge_timer = self.set_timer(1.2, self._ghost_nudge_clear)

    def _ghost_nudge_clear(self):
        self._ghost_nudge_timer = None
        self._ghost_nudge = False
        if self._ghost_on:
            self._ghost_render()

    def _ghost_shake(self):
        """Subtly jolt just the CODE text on a wrong key — ±1 column, a couple
        of quick frames. Only #ghost-code moves; the header, console, and footer
        stay still so it reads as the text trembling, not the screen shaking."""
        if self._ghost_shake_timer is not None:
            self._ghost_shake_timer.stop()
            self._ghost_shake_timer = None
        self._ghost_shake_i = 0
        offsets = [(-1, 0), (0, 0)]

        def _frame():
            code = self.query_one("#ghost-code", Static)
            i = self._ghost_shake_i
            if i < len(offsets):
                code.styles.offset = offsets[i]
                self._ghost_shake_i += 1
            else:
                code.styles.offset = (0, 0)
                if self._ghost_shake_timer is not None:
                    self._ghost_shake_timer.stop()
                    self._ghost_shake_timer = None

        self._ghost_shake_timer = self.set_interval(0.06, _frame)

    def _ghost_start_blink(self):
        self._ghost_blink_on = True
        if self._ghost_blink_timer is None:
            self._ghost_blink_timer = self.set_interval(0.5, self._ghost_blink_tick)

    def _ghost_blink_tick(self):
        self._ghost_blink_on = not self._ghost_blink_on
        if self._ghost_on and (
                (self._ghost_phase == "type" and self._ghost_has_prompt())
                or self._ghost_phase == "ran"):
            self._ghost_render()

    def _ghost_stop_blink(self):
        if self._ghost_blink_timer is not None:
            self._ghost_blink_timer.stop()
            self._ghost_blink_timer = None
        self._ghost_blink_on = False

    def _ghost_run(self):
        self._ghost_stop_blink()
        self._ghost_phase = "run"
        self._ghost_render()
        gen = self._ghost_gen
        threading.Thread(target=self._ghost_capture,
                         args=(self._ghost_target, self._ghost_stdin, gen),
                         daemon=True).start()

    def _ghost_capture(self, code, stdin, gen):
        self._ghost_final_vars = None
        if stdin:
            out = run_demo_session(code, stdin)
            err = ""
        else:
            out, err = run_lesson_code(code, stdin)
            if not out.strip() and not err.strip():
                # printed nothing (pure math / assignment) — surface the final
                # variable values so the answer is still visible, never a blank
                final = final_vars_of(code, stdin)
                if final:
                    self._ghost_final_vars = final
                    out = "\n".join(f"{k} = {v}" for k, v in final.items())
                else:
                    out = "✓ ran — no output"
        if gen != self._ghost_gen:
            return
        self.call_from_thread(self._ghost_on_result, (out or err or "").rstrip("\n"), gen)

    def _ghost_on_result(self, result, gen):
        if gen != self._ghost_gen:
            return
        # wrap the output so multi-value results stay inside the console, and cap
        # the height to the room actually on screen — a 10-line result shows every
        # number, while a 1000-line loop still truncates before it spills off-screen
        self._ghost_out_text = _wrap_console(result or "", max(20, self.size.width - 12))
        cap = max(GHOST_MIN_OUTPUT_LINES, self.size.height - GHOST_OUTPUT_HEADROOM)
        self._ghost_out_text = _cap_lines(self._ghost_out_text, cap)
        self._ghost_out_i = 0
        # reveal in bigger steps for longer output, so it always finishes in
        # ~2s and never "keeps going forever" on a wall of numbers
        self._ghost_out_step = max(1, len(self._ghost_out_text) // 66)
        self._ghost_phase = "reveal"
        final = getattr(self, "_ghost_final_vars", None)
        chg = getattr(self, "_ghost_change", None)
        if chg:
            # "change it" rep — tie the edit to the output change directly
            before = _flatten_out(chg.get("before", ""))
            after = _flatten_out(chg.get("after", ""))
            self._ghost_result_tip_text = (
                f"You changed {chg['meaning']} from {chg['old']} to {chg['new']}. "
                f"Before it was {before}; now it's {after}. That one edit did that.")
        elif final:
            bits = ", ".join(f"{k} is {v}" for k, v in final.items())
            self._ghost_result_tip_text = f"no print here, so it shows the final state: {bits}."
        else:
            self._ghost_result_tip_text = _ghost_result_tip(self._ghost_target, result or "")
        self._ghost_render()
        self._ghost_out_timer = self.set_interval(0.03, self._ghost_out_tick)

    def _ghost_out_tick(self):
        if self._ghost_phase != "reveal":
            return
        text = self._ghost_out_text
        if self._ghost_out_i < len(text):
            self._ghost_out_i += getattr(self, "_ghost_out_step", 1)
            while self._ghost_out_i < len(text) and text[self._ghost_out_i] == "\n":
                self._ghost_out_i += 1
            play_output_tick()
            self._ghost_render()
            return
        if self._ghost_out_timer is not None:
            self._ghost_out_timer.stop()
            self._ghost_out_timer = None
        self._ghost_phase = "ran"
        # flash the exact tokens the coach is about to explain, bold ↔ plain
        chg = getattr(self, "_ghost_change", None)
        if chg:
            self._ghost_spot_tokens = [chg["new"]]   # the one edited value
        else:
            self._ghost_spot_tokens = _result_spot_tokens(self._ghost_target)
        self._ghost_start_blink()
        self._ghost_render()
        # once the output is on screen, briefly explain WHY it looks like this
        if self.voice_on and self._ghost_result_tip_text:
            speak(self._ghost_result_tip_text)
            self._ghost_result_tip_text = ""

    def _ghost_next(self):
        self._ghost_idx += 1
        if self._ghost_idx >= len(self._ghost_examples):
            self._ghost_finish()
        else:
            self._ghost_begin_example(self._ghost_idx)

    def _ghost_dismiss(self):
        self._ghost_on = False
        self._ghost_required = False
        self._ghost_gen += 1
        self._ghost_stop_timers()
        self.query_one("#ghost", GhostWriter).remove_class("visible")
        self._update_guide()

    def _ghost_stop_timers(self):
        for attr in ("_ghost_out_timer", "_ghost_blink_timer", "_ghost_nudge_timer",
                     "_ghost_shake_timer"):
            t = getattr(self, attr, None)
            if t is not None:
                t.stop()
                setattr(self, attr, None)
        self._ghost_blink_on = False
        self._ghost_nudge = False
        self._ghost_shake_i = 0
        try:
            self.query_one("#ghost-code", Static).styles.offset = (0, 0)
        except Exception:
            pass

    def _ghost_render(self):
        n = len(self._ghost_examples)
        mode_label = {
            "watch": "WATCH & RUN  —  it's written, press ⏎ to run",
            "finish": "FINISH IT  —  I started, you finish the rest",
            "write": "WRITE IT ALL  —  you're locked in, type it out",
            "change": "CHANGE IT  —  I edited one thing, type it and see the output change",
        }.get(self._ghost_mode, "GHOST WRITE")
        if self._ghost_required:
            head = Text(f"SYNTAX DRILL  {self._ghost_idx + 1}/{n}  —  {mode_label}",
                        style="bold magenta")
        else:
            head = Text(f"GHOST WRITE  {self._ghost_idx + 1}/{n}  —  {mode_label}",
                        style="bold yellow")
        code = self._ghost_render_code()
        console = self._ghost_render_console()
        foot = {
            "watch": "just read it · ⏎ to run",
            "finish": "finish the dim part · ⏎ new line · ⇥ indent · ⏎ runs at the end",
            "write": "type the ghost · ⏎ new line · ⇥ indent · ⏎ runs at the end",
            "change": "type the changed code · ⏎ new line · ⇥ indent · ⏎ runs at the end",
        }.get(self._ghost_mode, "type the ghost · ⏎ new line · ⇥ indent · ⏎ runs at the end")
        if not self._ghost_required:
            foot = "Esc quit · " + foot
        # render each region into its OWN widget, so the code box can shake on
        # its own without moving the header, console, or footer.
        self.query_one("#ghost-head", Static).update(head)
        self.query_one("#ghost-code", Static).update(_box_lines(_lines_of(code)))
        self.query_one("#ghost-console", Static).update(
            _box_lines(_lines_of(console)) if console.cell_len else Text(""))
        self.query_one("#ghost-foot", Static).update(Text(foot, style="dim"))

    def _ghost_render_code(self):
        t = Text()
        pos = self._ghost_pos
        idx = 0
        prompt_style = ("bold #d8b4fe" if self._ghost_blink_on else "bold #9333ea")
        # "ran" phase: the code is fully written — flash the tokens the coach is
        # explaining (bold yellow ↔ normal) so the eye lands on the exact bit
        spot = getattr(self, "_ghost_spot_tokens", None)
        if self._ghost_phase == "ran" and spot:
            style = "bold #facc15" if self._ghost_blink_on else None
            for i, line in enumerate(self._ghost_target.split("\n")):
                if i:
                    t.append("\n")
                t.append(f"{i+1:>2} │ ", style="dim")
                t.append_text(_spotlight_line(line, spot, style))
            return t
        for i, line in enumerate(self._ghost_target.split("\n")):
            start = idx
            end = idx + len(line)
            typed_n = max(0, min(pos, end) - start)
            if i:
                t.append("\n")
            t.append(f"{i+1:>2} │ ", style="dim")
            # typed portion: correct runs syntax-colored + BOLD (bigger focus),
            # error chars red
            j = 0
            while j < typed_n:
                if (start + j) in self._ghost_errors:
                    # the wrong letter is drawn in bright red + underlined, on the
                    # NORMAL background — no solid block to hide it. (A bg fill
                    # renders opaque in the terminal and swallows the glyph.)
                    t.append(self._ghost_errors[start + j],
                             style="bold underline #ff5555")
                    j += 1
                else:
                    run_start = j
                    while j < typed_n and (start + j) not in self._ghost_errors:
                        j += 1
                    ct = _code_text(line[run_start:j])
                    ct.stylize("bold")
                    t.append_text(ct)
            # structural prompts: an explicit Enter/Tab the user performs next
            need_enter = (pos == end and end < len(self._ghost_target)
                          and self._ghost_target[end] == "\n")
            need_tab = (start <= pos < end and self._ghost_target[pos] == " "
                        and self._ghost_structural(pos))
            if need_tab:
                # at the indent — prompt for Tab, then show the ghost of the rest
                k = 0
                while k < len(line) and line[k] == " ":
                    k += 1
                t.append("⇥ TAB", style=prompt_style)
                if k < len(line):
                    t.append(line[k:], style="#5a5a5a")
            elif need_enter:
                # whole line typed — blink an Enter prompt on the right of this line
                t.append("   ⏎ ENTER", style=prompt_style)
            elif typed_n < len(line) and start <= pos < end:
                t.append(line[typed_n], style="reverse bold")   # next char to type
                t.append(line[typed_n + 1:], style="#5a5a5a")   # ghost (dim)
            elif typed_n < len(line):
                t.append(line[typed_n:], style="#5a5a5a")
            idx = end + 1
        return t

    def _ghost_enter_button(self):
        """A real, boxed 'press ENTER to RUN' button that blinks when the ghost
        is fully typed — so the next action is a thing you SEE, not a hint."""
        label = "▶  press ENTER to RUN"
        if self._ghost_blink_on:
            return _box_lines([Text(label, style="bold black on #22c55e")])
        return _box_lines([Text(label, style="bold #22c55e")])

    def _ghost_render_console(self):
        if self._ghost_phase == "type":
            if self._ghost_done:
                return self._ghost_enter_button()
            if self._ghost_errors:
                if self._ghost_pos >= len(self._ghost_target):
                    return Text(f"✗ {len(self._ghost_errors)} red letter(s) to fix — backspace and retype", style="bold red")
                return Text(f"keep going — {len(self._ghost_errors)} red letter(s) to fix at the end", style="bold yellow")
            if self._ghost_nudge:
                return Text("locked in — finish the ghost, then Enter", style="bold yellow")
            if self._ghost_required:
                return Text("type the ghost · wrong letters stick red · you're locked in", style="dim")
            return Text("type the ghost · wrong letters stick red · Esc quits", style="dim")
        if self._ghost_phase == "run":
            return Text("running…", style="dim")
        if self._ghost_phase == "reveal":
            out = Text()
            for i, rl in enumerate(_reveal_output_lines(self._ghost_out_text, self._ghost_out_i)):
                if i:
                    out.append("\n")
                out.append_text(rl)
            return out
        out = Text()
        for i, line in enumerate(self._ghost_out_text.split("\n")):
            if i:
                out.append("\n")
            out.append(line, style="bold green")
        return out

    # ---- VIM / NEOVIM trainer course ------------------------------------- #

    def _vim_begin(self):
        """Open the VIM course overlay and start the first lesson."""
        self._vim_on = True
        self._vim_idx = 0
        self._vim_step = 0
        self._vim_challenge = False
        self._vim_done = False
        self._vim_msg = ""
        self._vim_buf = VimDemoBuffer(VIM_DEMO)
        self._vim_home()
        self.query_one("#vim", VimTrainer).add_class("visible")
        self.query_one("#vim", VimTrainer).focus()
        if self._vim_blink_timer is None:
            self._vim_blink_timer = self.set_interval(0.5, self._vim_blink_tick)
        self._vim_lesson_speak()
        self._vim_render()

    def _vim_home(self):
        """Park the cursor in the middle of the buffer so every motion key has
        room to move (h/l/j/k all visibly do something from the start)."""
        b = self._vim_buf
        if len(b.lines) > 1:
            b.row = 1
        b.col = min(12, len(b.lines[b.row]))
        b._clamp()

    def _vim_lesson(self):
        return VIM_LESSONS[self._vim_idx]

    def _vim_lesson_speak(self):
        if not self.voice_on:
            return
        if self._vim_challenge:
            speak("Vim challenge. Move the cursor to the highlighted target using your movement keys.")
            return
        s, title, desc, keys, note = self._vim_lesson()
        speak(f"{title}. {desc}.")

    def _vim_cur_key(self):
        if self._vim_challenge:
            return None
        _, _, _, keys, _ = self._vim_lesson()
        if self._vim_step < len(keys):
            return keys[self._vim_step]
        return None

    def _vim_key_matches(self, expected, event):
        e = expected.lower()
        k = (event.key or "").lower()
        ch = event.character
        if "+" in e:
            if k == e:
                return True
            # a terminal without kitty-keyboard-protocol delivers a ctrl chord as
            # the raw control char (ctrl+d -> '\x04') with key set to the bare
            # letter — accept that too, so Ctrl lessons never false-error.
            if e.startswith("ctrl+") and len(e) == 6 and e[-1].isalpha():
                if ch == chr(ord(e[-1]) - ord("a") + 1):
                    return True
            return False
        if e == "esc":
            return k == "escape"
        if e == "enter":
            return k == "enter"
        if e == "space":
            return k == "space" or ch == " "
        if e == "tab":
            return k == "tab"
        if e == "bksp":
            return k == "backspace"
        if len(e) == 1:
            return ch == e or k == e
        return k == e

    def _vim_on_key(self, event):
        if not self._vim_on:
            return
        key = event.key
        if key == "escape":
            event.stop(); event.prevent_default()
            # The "Esc" lesson needs Esc to register as the key to press, NOT to
            # quit the course — otherwise that lesson is unplayable. Only back
            # out when Esc isn't the thing being taught right now.
            expected = self._vim_cur_key() if not self._vim_challenge else None
            if expected and expected.lower() == "esc":
                self._vim_advance()
            else:
                self._vim_dismiss()
            return
        # bare modifier presses (Shift/Ctrl/Alt/Super held alone) are not keys —
        # swallow them silently instead of flashing a 'wrong key' error.
        if key in _VIM_MODIFIERS:
            event.stop(); event.prevent_default()
            return
        # course complete — only Esc does anything (backs out to the menu)
        if self._vim_done:
            event.stop(); event.prevent_default()
            return
        if self._vim_challenge:
            event.stop(); event.prevent_default()
            self._vim_challenge_key(event)
            return
        expected = self._vim_cur_key()
        if expected is None:
            return
        if self._vim_key_matches(expected, event):
            event.stop(); event.prevent_default()
            self._vim_advance()
        else:
            event.stop(); event.prevent_default()
            play_ghost_error()
            self._vim_shake()
            self._vim_msg = f"not yet — press {self._vim_label(expected)}"
            self._vim_render()

    def _vim_advance(self):
        """Register a correct key press and move to the next step (or lesson)."""
        play_key()
        self._vim_step += 1
        _, _, _, keys, _ = self._vim_lesson()
        if self._vim_step >= len(keys):
            msg = self._vim_buf.apply(keys)
            self._vim_msg = msg or ""
            play_menu_blip(3)
            # show the move for a beat before hopping to the next lesson
            self._vim_render()
            self._vim_advance_timer = self.set_timer(0.45, self._vim_next)
        else:
            self._vim_render()

    def _vim_challenge_key(self, event):
        ch = event.character
        b = self._vim_buf
        # resolve a pending two-key command (gg / dd / dw / d$ / yy / yw / y$)
        if self._vim_pending:
            first = self._vim_pending
            self._vim_pending = None
            if (first, ch) in (("g", "g"), ("d", "d"), ("d", "w"), ("d", "$"),
                               ("y", "y"), ("y", "w"), ("y", "$")):
                msg = b.apply([first, ch])
                self._vim_msg = msg or ""
                play_key()
                self._vim_after_move()
                return
            # invalid second key — drop the pending press and flag it
            play_ghost_error(); self._vim_shake()
            self._vim_msg = f"{first} needs a second key — try {first}{first}"
            self._vim_render()
            return
        # first key of a two-key command
        if ch in ("g", "d", "y"):
            self._vim_pending = ch
            play_key()
            self._vim_msg = f"{ch} …"
            self._vim_render()
            return
        # single-key movement / edit
        if ch in "hjklwbe0$^Gxpu":
            if ch == "g":
                b.apply(["g", "g"])
            else:
                b.apply([ch])
            play_key()
            self._vim_after_move()
            return
        # anything else is a miss
        play_ghost_error(); self._vim_shake()
        self._vim_render()

    def _vim_after_move(self):
        """After a move/edit in a challenge, check whether the goal is reached."""
        if self._vim_challenge_done():
            play_console_result(True)
            self._vim_msg = "DONE — nice!"
            if self.voice_on:
                speak("Nailed it.")
            self._vim_advance_challenge()
        else:
            self._vim_render()

    def _vim_challenge_done(self):
        ch = VIM_CHALLENGES[self._vim_challenge_idx]
        if ch["kind"] == "move":
            return (self._vim_buf.row, self._vim_buf.col) == ch["target"]
        return ch["verify"](self._vim_buf)

    def _vim_advance_challenge(self):
        self._vim_challenge_idx += 1
        self._vim_pending = None
        if self._vim_challenge_idx >= len(VIM_CHALLENGES):
            self._vim_done = True
            self._vim_msg = "ALL CHALLENGES CLEARED — you can move AND edit. Esc to leave."
            if self.voice_on:
                speak("All challenges cleared. You can move and edit like a pro.")
            self._vim_render()
            return
        self._vim_start_one_challenge()

    def _vim_next(self):
        self._vim_step = 0
        self._vim_msg = ""
        self._vim_idx += 1
        if self._vim_idx >= len(VIM_LESSONS):
            self._vim_start_challenge()
        else:
            self._vim_home()      # park the cursor so this motion is visible
            self._vim_lesson_speak()
            self._vim_render()

    def _vim_start_challenge(self):
        self._vim_challenge = True
        self._vim_challenge_idx = 0
        self._vim_pending = None
        self._vim_start_one_challenge()

    def _vim_start_one_challenge(self):
        ch = VIM_CHALLENGES[self._vim_challenge_idx]
        self._vim_buf = VimDemoBuffer(list(ch["start"]))
        self._vim_target = ch.get("target")   # None for edit challenges (no target cell)
        self._vim_pending = None
        self._vim_msg = ""
        if self.voice_on:
            speak(f"Challenge {self._vim_challenge_idx + 1}: {ch['title']}. {ch['desc']}.")
        self._vim_render()

    def _vim_label(self, key):
        return {"Bksp": "⌫", "Enter": "⏎", "Space": "␣"}.get(key, key)

    def _vim_dismiss(self):
        self._vim_on = False
        if self._vim_blink_timer is not None:
            self._vim_blink_timer.stop(); self._vim_blink_timer = None
        t = getattr(self, "_vim_advance_timer", None)
        if t is not None:
            t.stop(); self._vim_advance_timer = None
        self.query_one("#vim", VimTrainer).remove_class("visible")
        self._show_menu()

    def _vim_shake(self):
        """Subtle single-nudge jolt of the buffer on a wrong key."""
        if getattr(self, "_vim_shake_timer", None) is not None:
            self._vim_shake_timer.stop()
            self._vim_shake_timer = None
        offsets = [(-1, 0), (0, 0)]
        i = 0
        buf = self.query_one("#vim-buffer", Static)

        def _frame():
            nonlocal i
            if i < len(offsets):
                buf.styles.offset = offsets[i]; i += 1
            else:
                buf.styles.offset = (0, 0)
                if getattr(self, "_vim_shake_timer", None) is not None:
                    self._vim_shake_timer.stop()
                    self._vim_shake_timer = None

        self._vim_shake_timer = self.set_interval(0.06, _frame)

    def _vim_blink_tick(self):
        self._vim_blink = not self._vim_blink
        if self._vim_on:
            self._vim_render()

    def _vim_render(self):
        self.query_one("#vim-head", Static).update(self._vim_render_head())
        self.query_one("#vim-buffer", Static).update(self._vim_render_buffer())
        self.query_one("#vim-cmd", Static).update(self._vim_render_cmd())
        self.query_one("#vim-kb", Static).update(self._vim_render_kb())
        self.query_one("#vim-foot", Static).update(self._vim_render_foot())

    def _vim_mode(self):
        """NORMAL vs INSERT — so the trainer looks like a real editor whose
        mode visibly changes when you learn i/a/o/O/I/A."""
        if self._vim_challenge:
            return "normal"
        _, _, _, keys, _ = self._vim_lesson()
        if keys and keys[0] in ("i", "a", "o", "O", "I", "A"):
            return "insert"
        return "normal"

    def _vim_render_head(self):
        t = Text()
        if self._vim_challenge:
            if self._vim_done:
                t.append("COURSE COMPLETE", style="bold green")
                t.append("\n\n")
                t.append("you cleared every challenge — you can move AND edit", style="#d5d5d5")
                t.append("\n\n")
                t.append("Esc — back to the menu", style="dim")
                return t
            ch = VIM_CHALLENGES[self._vim_challenge_idx]
            t.append("VIM CHALLENGE", style="bold magenta")
            t.append(f"  {self._vim_challenge_idx + 1}/{len(VIM_CHALLENGES)}", style="dim")
            t.append("\n")
            t.append(ch["title"], style="bold yellow")
            t.append("\n")
            t.append(ch["desc"], style="#d5d5d5")
            t.append("\n\n")
            t.append("keys: ", style="dim")
            t.append(ch["keys"], style="bold #fbbf24")
            return t
        s, title, desc, keys, note = self._vim_lesson()
        # mode badge (like a real editor's status line)
        mode = self._vim_mode()
        mode_style = ("bold black on #1e6b3f" if mode == "insert" else "bold black on #1f4e79")
        t.append(f" {mode.upper()} ", style=mode_style)
        t.append("   ", style="dim")
        t.append(VIM_STAGES[s].upper(), style="bold cyan")
        t.append(f"   {self._vim_idx + 1}/{len(VIM_LESSONS)}", style="dim")
        # big blinking direction arrow, OUTSIDE the buffer box (so it never
        # re-flows the box width and makes it "tweak out")
        arrow = _vim_arrow(keys)
        if arrow:
            t.append("\n")
            t.append("   " + arrow * 5, style=("bold #d8b4fe" if self._vim_blink else "#4a4a55"))
        t.append("\n")
        t.append(title, style="bold yellow")
        t.append("\n")
        t.append(desc, style="#d5d5d5")
        if note:
            t.append("\n")
            t.append(note, style="#f0c674")
        t.append("\n\n")
        for i, k in enumerate(keys):
            if i:
                t.append("  ", style="dim")
            if i < self._vim_step:
                t.append(f"[ {self._vim_label(k)} ]", style="bold green")
            elif i == self._vim_step:
                t.append(f"[ {self._vim_label(k)} ]", style="bold black on #fbbf24")
            else:
                t.append(f"[ {self._vim_label(k)} ]", style="dim")
        return t

    def _vim_render_buffer(self):
        b = self._vim_buf
        if not self._vim_challenge:
            _, _, _, keys, _ = self._vim_lesson()
            self._vim_preview = b.predict(keys) if keys else None
            if self._vim_preview == (b.row, b.col):
                self._vim_preview = None
        else:
            self._vim_preview = None
        t = Text()
        for i, line in enumerate(b.lines):
            if i:
                t.append("\n")
            t.append(f"{i+1:>2} │ ", style="dim")
            t.append_text(self._vim_line(line, i))
        # full-width editor: the box spans the screen so the trainer feels big,
        # with the code left-aligned like a real vim buffer.
        min_w = max(0, self.size.width - 14)
        return _box_lines(_lines_of(t), min_width=min_w)

    def _vim_render_cmd(self):
        """A realistic vim command line for the `:w` / `:q` / `:vsplit` lessons —
        a boxed ':' prompt that fills in as you type the command."""
        if self._vim_challenge or self._vim_done:
            return Text("")
        _, _, _, keys, _ = self._vim_lesson()
        if not keys or keys[0] != ":":
            return Text("")
        typed = "".join(k for k in keys[:self._vim_step] if k not in (":", "Enter"))
        inner = Text()
        inner.append(":", style="bold cyan")
        inner.append(typed, style="#f0f0f5")
        inner.append(" ", style="reverse")
        return _box_lines([inner])

    def _vim_line(self, line, row):
        """One buffer line with marker cells overlaid: the ghost preview (dim),
        the challenge target (green), and the real cursor (white, on top). The
        code is bold so the buffer reads as big as the ghost panel."""
        b = self._vim_buf
        marks = []  # (col, style); later entries win on overlap
        if self._vim_preview is not None and self._vim_preview[0] == row:
            marks.append((self._vim_preview[1], "black on #4b5563 bold"))   # ghost
        if self._vim_challenge and not self._vim_done and self._vim_target is not None and self._vim_target[0] == row:
            marks.append((self._vim_target[1], "black on #22c55e bold"))    # target
        if b.row == row:
            marks.append((b.col, "black on #e6e6e6 bold"))                  # cursor
        if not marks:
            return _code_text(line)
        style_at = {}
        for c, s in marks:
            style_at[c] = s
        t = Text()
        prev = 0
        for c in sorted(style_at):
            c = min(c, len(line))
            if c > prev:
                t.append_text(_code_text(line[prev:c]))
            if c < len(line):
                t.append(line[c], style=style_at[c])
                prev = c + 1
            else:
                t.append(" ", style=style_at[c])   # end-of-line cursor
                prev = c
        if prev < len(line):
            t.append_text(_code_text(line[prev:]))
        return t

    def _vim_render_kb(self):
        # highlight the WHOLE key combo on the keyboard: the key you press right
        # now is amber, the rest of the combo is a dimmer green, everything else
        # is a visible grey keycap (bigger than before).
        current = set()
        combo = set()
        if not self._vim_challenge:
            _, _, _, keys, _ = self._vim_lesson()
            for k in keys:
                for part in k.split("+"):
                    combo.add(part)
            cur = self._vim_cur_key()
            if cur:
                for part in cur.split("+"):
                    current.add(part)
        t = Text()
        for row in VIM_KB_ROWS:
            for key in row:
                label = self._vim_label(key)
                if key in current:
                    t.append(f"   {label}   ", style="bold black on #fbbf24")
                elif key in combo:
                    t.append(f"   {label}   ", style="bold #a3e635 on #3a3a3a")
                else:
                    t.append(f"   {label}   ", style="#b0b0b8 on #26262b")
            t.append("\n")
        return t

    def _vim_render_foot(self):
        t = Text()
        if self._vim_challenge:
            if self._vim_done:
                if self._vim_msg:
                    t.append(self._vim_msg, style="bold green")
                t.append(" · Esc exits", style="dim")
                return t
            if self._vim_msg:
                t.append(self._vim_msg, style="bold yellow")
                t.append("\n")
            ch = VIM_CHALLENGES[self._vim_challenge_idx]
            t.append(ch["keys"] + " · Esc exits", style="dim")
            return t
        if self._vim_msg:
            style = "bold red" if self._vim_msg.startswith("not yet") else "bold green"
            t.append(self._vim_msg, style=style)
            t.append("\n")
        cur = self._vim_cur_key()
        if cur and cur.lower() == "esc":
            t.append("press [Esc] — it's the key this time, not a quit", style="bold yellow")
        else:
            t.append("type the glowing key · the ghost shows where it lands · Esc exits", style="dim")
        return t

    def action_demo(self):
        """Replay the current challenge's example demo (press F3)."""
        if self.started:
            self._start_demo()

    def _update_guide(self):
        """The hold-your-hand bar — always says exactly what to do next."""
        editor = self.query_one("#editor", VimEditor)
        predict = (self.mode == "challenge" and self.started
                   and self._current().get("predict"))
        if self.lesson_gate:
            self.query_one("#guide", Static).update(
                "[bold]→ [reverse] Enter [/reverse] = dive in   ·   [reverse] w [/reverse] = watch lesson   ·   [reverse] l [/reverse] = listen[/]")
            return
        if not self.started:
            guide = "[bold]→ Press [reverse] i [/reverse] or [reverse] Enter [/reverse] to begin your first challenge.[/]"
        elif editor.mode == "insert":
            what = "your prediction" if predict else "your answer"
            guide = f"[yellow][bold]→ TYPING[/bold] — write {what}, then press [reverse] Esc [/reverse] when done.[/]"
        elif self.last == "pass":
            guide = ("[green][bold]→ PASSED![/bold]  [reverse] Enter [/reverse] = next   ·   "
                     "[reverse] w [/reverse] = re-watch the lesson   ·   [reverse] l [/reverse] = listen[/]")
        elif self.last == "fail" and predict:
            guide = "[red][bold]→ NOT QUITE.[/bold] Re-read the code, type a new prediction, then [reverse] :!python3 % [/reverse] to run.[/]"
        elif self.last == "fail":
            guide = "[red][bold]→ NOT APPROVED.[/bold] Fix your code, then press [reverse] :!python3 % [/reverse] to run + submit again.[/]"
        elif predict:
            guide = ("[bold]→ Step 1:[/bold] READ the code and predict what it prints  ·  "
                     "[bold]Step 2:[/bold] [reverse] i [/reverse] to type your guess (or [reverse]click[/] to place the cursor)  ·  "
                     "[bold]Step 3:[/bold] [reverse] Esc [/reverse] then [reverse] :!python3 % [/reverse] to check")
        else:
            if self._flat_index() == 0:
                # very first challenge — teach the two vim essentials up front
                guide = ("[bold]→ new to vim? [/bold] "
                         "[reverse] i [/reverse] = start typing   ·   "
                         "[reverse] Esc [/reverse] = stop typing   ·   "
                         "[reverse]click[/] anywhere also places the cursor   ·   then [reverse]:!python3 %[/reverse] to run")
            else:
                guide = ("[bold]→ Step 1:[/bold] read the challenge  ·  "
                         "[bold]Step 2:[/bold] [reverse] i [/reverse] to type (or [reverse]click[/] where you type)  ·  "
                         "[bold]Step 3:[/bold] [reverse] Esc [/reverse] then [reverse] :!python3 % [/reverse] to run + submit")
        self.query_one("#guide", Static).update(guide)

    def _update_status(self):
        editor = self.query_one("#editor", VimEditor)
        fname = f"challenge{self._flat_index()+1}.py"
        voice = "[on]" if self.voice_on and self._tts else "[off]"
        label = self.query_one("#editor-label", Static)
        if editor.mode == "insert":
            label.update(f"[b]INSERT[/b]  [dim]{fname}[/]")
            label.remove_class("normal"); label.add_class("insert")
        else:
            label.update(f"[b]NORMAL[/b]  [dim]{fname}[/]")
            label.remove_class("insert"); label.add_class("normal")
        kc = lambda k: f"[on #3a3a3a]{k}[/]"
        self.query_one("#status", Static).update(
            f"{kc('h')}{kc('j')}{kc('k')}{kc('l')} move · {kc('i')} type · "
            f"{kc(':!python3 %')} run+submit · {kc('Ctrl+n')}/{kc('Ctrl+b')} next/prev · "
            f"{kc('F1')} keys · {kc('q')} quit"
        )

    def on_mode_changed(self, msg: ModeChanged) -> None:
        self._update_status()
        self._update_guide()

    # ---- cheat ------------------------------------------------------------ #

    def _show_cheat(self, topic, force_visible=False):
        sheet = TOPIC_CHEATS.get(topic, TOPIC_CHEATS["custom"])
        c = self._current()
        lines = [f"## {c.get('title', sheet['title'])}", ""]
        # This challenge's OWN worked example comes first — it differs per
        # challenge, so F2 never shows the identical sheet for two challenges
        # in the same topic.
        example = c.get("example", "")
        if example.strip():
            caption, code = example_code(example)
            if caption:
                lines.append(caption)
                lines.append("")
            if code:
                lines.append(f"```python\n{code}\n```")
                lines.append("")
        # Shared topic crib below, under its own heading so it doesn't blur
        # with the challenge-specific example above.
        lines.append(f"### {sheet['title']} crib")
        for label, code in sheet["examples"]:
            lines.append(f"**{label}**\n```python\n{code}\n```")
        lines += ["", f"> {sheet['tip']}"]
        self.query_one("#cheat", Markdown).update("\n".join(lines))
        if force_visible:
            self.query_one("#cheat", Markdown).add_class("visible")
            # the right rail holds ONE reference panel at a time — hide the examples
            self.query_one("#side-examples", Vertical).add_class("hidden")

    def action_toggle_cheat(self):
        cheat = self.query_one("#cheat", Markdown)
        cheat.toggle_class("visible")
        self._show_cheat(self._current().get("topic", "custom"))
        # cheat and side-examples share the right rail — show one at a time
        if cheat.has_class("visible"):
            self.query_one("#side-examples", Vertical).add_class("hidden")
        else:
            self.query_one("#side-examples", Vertical).remove_class("hidden")

    def action_toggle_voice(self):
        self.voice_on = not self.voice_on
        self._update_status()
        if self.voice_on and self._tts:
            speak("voice on, let's go")

    def action_toggle_music(self):
        """Mute/unmute the win/fail celebration mp3s (the 'music')."""
        self.music_on = not self.music_on
        if self.mode == "menu":
            self._render_menu_help()
        else:
            self.query_one("#guide", Static).update(
                f"[bold]→ music {'[green]ON[/]' if self.music_on else '[red]MUTED[/]'}[/] — win/fail sounds")
        if self.voice_on:
            speak("music on" if self.music_on else "music muted")

    # ---- run / check / review -------------------------------------------- #

    def action_run(self):
        if getattr(self, "_warmup_on", False):
            return   # vim warm-up owns the editor — no running yet
        if self.mode != "challenge":
            return
        self._run_and_submit()

    def _run_and_submit(self):
        """Run the buffer and, if it runs clean, submit it for a pass/fail verdict."""
        if not self.started:
            self.action_start()
            return
        c = self._current()
        if c.get("predict"):
            self._run_predict(c)
            return
        code = self.query_one("#editor", VimEditor).get_text()
        topic = c["topic"]
        stdin = c.get("stdin", "")
        if stdin:
            # interactive input: run in a PTY so the prompt + typed value show up
            transcript = run_code_echo(code, stdin)
            if "Traceback" in transcript or "Error" in transcript:
                self._mark_fail(topic, "", transcript)
                return
            passed, hint = verify(c, code, transcript)
            if passed:
                self._mark_pass(transcript)
            else:
                self._mark_fail(topic, transcript, hint)
            return
        out, err = run_code(code, stdin)
        if err:
            self._mark_fail(topic, "", err)
            return
        passed, hint = verify(c, code, out)
        if passed:
            self._mark_pass(out)
        else:
            self._mark_fail(topic, out, hint)

    # ---- predict-the-output (READ the code) ------------------------------- #
    # The code is already written — the student predicts what it prints, types
    # their guess into the editor, and we run the real code to compare. Teaches
    # tracing, the #1 "can write it but can't read it" gap.

    def _run_predict(self, c):
        code = c["code"]
        stdin = c.get("stdin", "")
        if stdin:
            actual = run_code_echo(code, stdin)
        else:
            out, err = run_code(code, stdin)
            actual = (out if not err else err).rstrip("\n")
        guess = self.query_one("#editor", VimEditor).get_text()
        if _match_output(guess, actual):
            self._mark_pass_predict(actual)
        else:
            self._mark_fail_predict(actual, guess)

    def _mark_pass_predict(self, actual):
        self.attempts[self._flat_index()] = 0
        challenge_stat(self.p, self._current()["title"])["right"] += 1
        self.p["done"] += 1
        self.p["streak"] += 1
        self.p["best_streak"] = max(self.p["best_streak"], self.p["streak"])
        self.p["xp"] += 50
        save_progress(self.p)
        self.last = "pass"
        self.query_one("#editor", VimEditor).blur()
        self.query_one("#editor", VimEditor).hint_lines = set()
        if actual.strip():
            self._start_output_reveal(actual, lambda: self._finalize_pass_predict(actual))
        else:
            self._finalize_pass_predict(actual)

    def _finalize_pass_predict(self, actual):
        play_console_result(True)
        actual = _wrap_console(actual, self._output_w()) if actual else ""
        t = Text()
        t.append("it prints:\n", style="dim")
        t.append(actual, style="green")
        t.append("\n")
        t.append("✓ you read it right", style="bold green")
        t.append(f"  ·  streak {self.p['streak']}", style="dim")
        t.append("\n")
        t.append("NEXT ▶", style="bold yellow")
        t.append("  press Enter", style="dim")
        self.query_one("#output", Static).update(t)
        self._update_guide()
        win, _ = self._sounds_for(self._flat_index())
        self._cancel_celebrate()
        self._pending_win = win
        self._celebrate_timer = self.set_timer(1.8, self._celebrate_pass)

    def _mark_fail_predict(self, actual, guess):
        self.p["streak"] = 0
        key = self._flat_index()
        self.attempts[key] = self.attempts.get(key, 0) + 1
        challenge_stat(self.p, self._current()["title"])["wrong"] += 1
        save_progress(self.p)
        self.last = "fail"
        _, fail = self._sounds_for(key)
        if fail and self.music_on:
            play_file(fail, volume=self._fx_volume())
        if actual.strip():
            self._start_output_reveal(actual, lambda: self._finalize_fail_predict(actual, guess))
        else:
            self._finalize_fail_predict(actual, guess)

    def _finalize_fail_predict(self, actual, guess):
        play_console_result(False)
        hint = self._current().get("read_hint", "") or \
            "Trace it line by line: each line runs top to bottom, and print() shows what the variable holds AT THAT MOMENT."
        actual = _wrap_console(actual, self._output_w()) if actual else ""
        t = Text()
        t.append("✗ not quite", style="bold red")
        t.append("\n\n")
        t.append("it actually prints:", style="dim")
        t.append("\n")
        t.append(actual, style="green")
        t.append("\n\n")
        t.append("you predicted:", style="dim")
        t.append("\n")
        t.append(guess.rstrip("\n") or "(empty)", style="yellow")
        t.append("\n\n")
        t.append("TRACE IT:", style="bold yellow")
        t.append("\n")
        t.append(hint, style="#f0f0f5")
        self.query_one("#output", Static).update(t)
        self._update_guide()
        if self.voice_on:
            speak("not quite. " + hint)

    def _take_sound(self, pool, all_sounds):
        if not pool and all_sounds:
            pool[:] = all_sounds[:]
            random.shuffle(pool)
        return pool.pop() if pool else None

    def _sounds_for(self, key):
        """The (win, fail) sound pair for a challenge — stable, no repeats in a session."""
        if key not in self._sound_map:
            self._sound_map[key] = (
                self._take_sound(self._cel_pool, CEL_SOUNDS),
                self._take_sound(self._fail_pool, FAIL_SOUNDS),
            )
        return self._sound_map[key]

    def _fx_volume(self) -> float:
        """The win/fail sting volume. Quieted a further 20% across the board
        (they were too loud), and HALVED again while the coach voice is on so
        the TTS always stays on top."""
        return 0.28 if self.voice_on else 0.56

    def _celebrate(self):
        self.query_one("#confetti", Confetti).start()

    # ---- output reveal (blue cursor + sound on the console) --------------- #

    def _render_reveal_text(self, text: str, upto: int) -> Text:
        t = Text()
        for i, rl in enumerate(_reveal_output_lines(text, upto)):
            if i:
                t.append("\n")
            t.append_text(rl)
        return t

    def _output_w(self) -> int:
        """Inner width (cols) of the #output console, so results wrap to fit."""
        try:
            return max(12, self.query_one("#output", Static).size.width - 4)
        except Exception:
            return 60

    def _start_output_reveal(self, text: str, final_cb):
        """Stream `text` into the #output box (blue cursor + a sound per char),
        then run `final_cb()` once it's fully printed."""
        self._cancel_output_reveal()
        self._out_reveal_text = _wrap_console(text, self._output_w())
        self._out_reveal_i = 0
        self._out_reveal_final = final_cb
        self._out_reveal_timer = self.set_interval(self.OUT_REVEAL_MS, self._out_reveal_tick)

    def _out_reveal_tick(self):
        text = self._out_reveal_text
        if self._out_reveal_i < len(text):
            self._out_reveal_i += 1
            # skip newlines instantly so the blue cursor always sits on a printed char
            while self._out_reveal_i < len(text) and text[self._out_reveal_i] == "\n":
                self._out_reveal_i += 1
            play_output_tick()
            self.query_one("#output", Static).update(self._render_reveal_text(text, self._out_reveal_i))
            return
        t = self._out_reveal_timer
        if t is not None:
            t.stop()
        self._out_reveal_timer = None
        cb = self._out_reveal_final
        self._out_reveal_final = None
        if cb:
            cb()

    def _cancel_output_reveal(self):
        t = self._out_reveal_timer
        if t is not None:
            t.stop()
            self._out_reveal_timer = None
        self._out_reveal_final = None

    def _mark_pass(self, out=""):
        self.attempts[self._flat_index()] = 0
        challenge_stat(self.p, self._current()["title"])["right"] += 1
        self.p["done"] += 1
        self.p["streak"] += 1
        self.p["best_streak"] = max(self.p["best_streak"], self.p["streak"])
        self.p["xp"] += 50
        save_progress(self.p)
        self.last = "pass"
        # blur the editor so w (watch) / l (listen) / e (lesson) reach the app
        # bindings now that the user is done typing — not vim's word motions
        self.query_one("#editor", VimEditor).blur()
        self.query_one("#editor", VimEditor).hint_lines = set()
        if self._current().get("visual"):
            self._start_visual(out)
            return
        if out.strip():
            self._start_output_reveal(out.rstrip("\n"), lambda: self._finalize_pass(out))
        else:
            self._finalize_pass(out)

    def _finalize_pass(self, out):
        play_console_result(True)
        out = _wrap_console(out.rstrip("\n"), self._output_w()) if out else ""
        t = Text()
        if out.strip():
            t.append(out, style="green")
            t.append("\n")
        else:
            t.append("(no output)", style="dim")
            t.append("\n")
        t.append("✓ passed", style="bold green")
        t.append(f"  ·  streak {self.p['streak']}", style="dim")
        t.append("\n")
        t.append("NEXT ▶", style="bold yellow")
        t.append("  press Enter", style="dim")
        self.query_one("#output", Static).update(t)
        self._update_guide()
        # let the result sit on screen so it's clearly visible, THEN celebrate
        win, _ = self._sounds_for(self._flat_index())
        self._cancel_celebrate()   # clear any prior pending celebration first
        self._pending_win = win
        self._celebrate_timer = self.set_timer(1.8, self._celebrate_pass)

    def _celebrate_pass(self):
        self._celebrate_timer = None
        if self.music_on and self._pending_win:
            play_file(self._pending_win, volume=self._fx_volume())
        self._pending_win = None
        self._celebrate()
        if self.voice_on:
            speak("nailed it")

    def _cancel_celebrate(self):
        t = self._celebrate_timer
        if t is not None:
            t.stop()
            self._celebrate_timer = None
        self._pending_win = None

    def _advance_after_pass(self):
        if self.last != "pass":
            return
        self._close_visual()
        group = GROUPS[self.group_idx]
        streak = self.p["streak"]
        # finishing a whole tier is a BIG moment — cat-microwave loading screen
        big = (
            self.group_idx + 1 < len(GROUPS) and
            (streak >= 3 or self.ch_idx + 1 >= len(group["challenges"]))
        )
        if big and not self._cat_playing:
            self._play_cat(self._step_advance)
            return
        self._step_advance()

    def _step_advance(self):
        group = GROUPS[self.group_idx]
        streak = self.p["streak"]
        # difficulty ramp: string 3+ wins in a row and you jump up a level
        if streak >= 3 and self.group_idx + 1 < len(GROUPS):
            self.group_idx += 1
            self.ch_idx = 0
        elif self.ch_idx + 1 < len(group["challenges"]):
            self.ch_idx += 1
        elif self.group_idx + 1 < len(GROUPS):
            self.group_idx += 1
            self.ch_idx = 0
        else:
            # finished every challenge → back to the menu
            self._show_menu()
            return
        self.attempts[self._flat_index()] = 0
        self._render_challenge()

    def _mark_fail(self, topic, out, hint):
        self.p["streak"] = 0
        key = self._flat_index()
        self.attempts[key] = self.attempts.get(key, 0) + 1
        challenge_stat(self.p, self._current()["title"])["wrong"] += 1
        save_progress(self.p)
        self.last = "fail"
        _, fail = self._sounds_for(key)
        if fail and self.music_on:
            play_file(fail, volume=self._fx_volume())
        a = self.attempts[key]
        if out.strip() and not _looks_like_traceback(hint):
            # stream the (non-crashing) output first, then stamp the verdict
            self._start_output_reveal(out.rstrip("\n"),
                                      lambda: self._finalize_fail(topic, out, hint, a))
        else:
            self._finalize_fail(topic, out, hint, a)

    def _finalize_fail(self, topic, out, hint, a):
        play_console_result(False)
        crash = _looks_like_traceback(hint)
        why = translate_error(hint) if crash else ""
        out = _wrap_console(out.rstrip("\n"), self._output_w()) if out else ""
        t = Text()
        if out.strip():
            t.append(out, style="green")
            t.append("\n")
        t.append("✗ your code crashed" if crash else "✗ not approved", style="bold red")
        if hint:
            t.append("\n")
            if crash:
                t.append(_traceback_last_line(hint), style="red")
                if why:
                    t.append("\n\n")
                    t.append("WHAT THIS MEANS", style="bold yellow")
                    t.append("\n")
                    t.append(why, style="#f0f0f5")
            else:
                t.append(hint, style="red")
        if self.hints_on and not crash:
            # underline the exact broken lines in the editor + say what's off
            ed = self.query_one("#editor", VimEditor)
            issues, bad_lines = self._analyze_code(self._current(), ed.get_text())
            ed.hint_lines = set(bad_lines)
            ed.refresh()
            real = [x for x in issues if "looks solid" not in x]
            if real:
                t.append("\n\n")
                t.append("WHAT'S OFF:", style="bold yellow")
                for issue in real[:3]:
                    t.append("\n• ")
                    t.append(issue, style="#f0f0f5")
                if self.voice_on:
                    speak("what's off. " + " ".join(real[:2]))
        if a >= 2:
            tip = TOPIC_CHEATS.get(topic, {}).get("tip", "hit F2 for the cheat sheet")
            t.append("\n")
            t.append("HINT: ", style="bold")
            t.append(tip)
            if self.voice_on and not crash:
                speak(f"not approved. hint: {tip}")
        else:
            if not crash:
                t.append("  ·  fix it and run again (:!python3 %)", style="dim")
            if self.voice_on and not crash:
                speak("not approved. fix it and run again.")
        if crash and self.voice_on and why:
            speak("what this means. " + why)
        self.query_one("#output", Static).update(t)
        self._update_guide()

    def action_review(self):
        if self.mode != "challenge":
            return
        self._start_review()

    def action_quick_check(self):
        """F12 — fast, local live fix: show the ONE thing to fix as big text on a
        box overlay AND say it out loud (punctuation read as words). No AI."""
        if self.mode != "challenge" or not self.started:
            return
        c = self._current()
        code = self.query_one("#editor", VimEditor).get_text()
        title, lines, spoken, flag = self._quick_issue(code, c)
        ed = self.query_one("#editor", VimEditor)
        ed.hint_lines = set(flag)
        ed.refresh()
        self._render_quick(title, lines)
        self.query_one("#quick", Static).add_class("visible")
        if self.voice_on:
            speak(spoken, rate=1.15)

    def _quick_issue(self, code, c):
        """Return (title, display_lines, spoken, flag_lines) for the single most
        important, dumbed-down fix — used by the quick-check overlay + TTS."""
        if not code.strip():
            return ("NOTHING YET",
                    ["you haven't typed anything.", "press i and write your answer first."],
                    "You haven't typed anything yet. Press i and write your answer first.",
                    {1})
        for i, ln in enumerate(code.split("\n"), 1):
            s = ln.strip()
            if s == "pass" or s.startswith("# your code here") or s.startswith("# TODO"):
                return ("STILL A PLACEHOLDER",
                        ["line " + str(i) + " is still a placeholder.", "replace 'pass' with real code."],
                        "Line " + str(i) + " is still a placeholder. Replace pass with real code.",
                        {i})
        try:
            compile(code, "<tutor>", "exec")
        except SyntaxError as e:
            return self._syntax_quick(e)
        for n in c.get("need", []):
            if n not in code:
                return ("MISSING A PIECE",
                        ["the task wants you to use '" + n + "'.", "add it, then run again."],
                        "The task wants you to use " + n + ". Add it, then run again.",
                        set())
        out, err = run_code(code, c.get("stdin", ""))
        if err:
            first = [x for x in err.strip().splitlines() if x.strip()]
            msg = first[-1] if first else err.strip()
            return ("IT CRASHED",
                    ["when Python ran it: " + msg, "check that line and try again."],
                    "When Python ran it, it hit an error. " + msg + ". Check that line and try again.",
                    set())
        for e in c.get("expect", []):
            if e.lower() not in out.lower():
                return ("WRONG OUTPUT",
                        ["your output is missing '" + e + "'.", "make it print exactly that."],
                        "Your output is missing " + e + ". Make it print exactly that.",
                        set())
        return ("LOOKS GOOD",
                ["this looks right — run it!", "press :!python3 % to submit."],
                "This looks right. Run it to submit.",
                set())

    def _syntax_quick(self, e):
        msg = (e.msg or "").lower()
        ln = e.lineno or 0
        if "unterminated string" in msg or "eol while scanning" in msg:
            return ("MISSING A QUOTE",
                    ["you're missing a closing \" at the end of line " + str(ln) + ".",
                     "try that."],
                    "You're missing a closing quote at the end of line " + str(ln) + ". Try that.",
                    {ln})
        if "expected ':'" in msg:
            return ("MISSING A COLON",
                    ["line " + str(ln) + " needs a : at the end.",
                     "the colon is what starts the block."],
                    "Line " + str(ln) + " needs a colon at the end. The colon is what starts the block.",
                    {ln})
        if "expected an indented block" in msg or "expected indented block" in msg:
            return ("NEEDS INDENT",
                    ["the line under a : must be indented 4 spaces.",
                     "push it in so Python knows it's inside the block."],
                    "The line under a colon must be indented four spaces. Push it in so Python knows it's inside the block.",
                    {ln})
        if "unexpected indent" in msg:
            return ("INDENT TOO FAR",
                    ["line " + str(ln) + " is indented but shouldn't be.",
                     "pull it back to the left edge."],
                    "Line " + str(ln) + " is indented but it should not be. Pull it back to the left edge.",
                    {ln})
        if "unmatched" in msg:
            return ("UNMATCHED BRACKET",
                    ["you have an extra ) or ] or } near line " + str(ln) + ".",
                     "count and match up your brackets."],
                    "You have an extra closing bracket near line " + str(ln) + ". Count and match up your brackets.",
                    {ln})
        if "cannot assign" in msg:
            return ("CAN'T STORE THAT",
                    ["line " + str(ln) + ": the left side of = must be a name.",
                     "not a value."],
                    "On line " + str(ln) + ", the left side of equals must be a name, not a value.",
                    {ln})
        return ("SYNTAX OFF",
                ["something is off on line " + str(ln) + ": " + (e.msg or ""),
                 "check for a missing : , quote, or ( )."],
                "Something is off on line " + str(ln) + ". Check for a missing colon, comma, quote, or parenthesis.",
                {ln})

    def _render_quick(self, title, lines):
        out = [Text(title, style="bold white"), Text("")]
        for ln in lines:
            out.append(Text(ln, style="#f0f0f5"))
        out.append(Text(""))
        out.append(Text("[Esc] close  ·  keep fixing in the editor", style="dim"))
        body = _box_lines(out)
        self.query_one("#quick", Static).update(
            _center_screen(body, self.size.width, self.size.height - 1))

    def _analyze_code(self, c, code):
        """Deterministic read of the student's code — no AI. Returns the list of
        issues and the 1-based line numbers to flag in red."""
        issues = []
        bad_lines = set()
        if not code.strip():
            issues.append("The editor is empty — type something first!")
            return issues, {1}
        lines = code.split("\n")
        for i, ln in enumerate(lines, 1):
            s = ln.strip()
            if s == "pass" or s.startswith("# your code here") or s.startswith("# TODO"):
                bad_lines.add(i)
        try:
            compile(code, "<tutor>", "exec")
        except SyntaxError as e:
            issues.append(f"Syntax error on line {e.lineno}: {e.msg}")
            bad_lines.add(e.lineno)
        for n in c.get("need", []):
            if n not in code:
                issues.append(f"You're missing '{n}' — the task needs it.")
        if not any("Syntax error" in x for x in issues):
            out, err = run_code(code, c.get("stdin", ""))
            if err:
                first = [x for x in err.strip().splitlines() if x.strip()]
                msg = first[-1] if first else err.strip()
                issues.append(f"It errored: {msg}")
            else:
                for e in c.get("expect", []):
                    if e.lower() not in out.lower():
                        issues.append(f"The output is missing {e!r}.")
        if not issues:
            issues.append("Honestly, this looks solid — run it and see if it passes!")
        return issues, sorted(bad_lines)

    def _start_review(self):
        c = self._current()
        code = self.query_one("#editor", VimEditor).get_text()
        issues, bad_lines = self._analyze_code(c, code)
        topic = c.get("topic", "custom")
        cheat = TOPIC_CHEATS.get(topic, TOPIC_CHEATS["custom"])
        similar = example_code(c.get("example", ""))[1] or cheat["examples"][0][1]
        rules = LESSON_RULES.get(topic)
        pit = PITFALLS.get(topic)
        bad_code = pit["bad"] if pit else (code or "# (nothing written)")
        good_code = pit["good"] if pit else similar
        why = pit["why"] if pit else (cheat["tip"] or "Run it and watch what breaks.")
        # Straight to the point: your code first (flagged), then the rules you
        # bent, then a bad-vs-good comparison, then a runnable fix.
        steps = [{"t": "review", "code": code, "bad": bad_lines, "issues": issues}]
        if rules:
            steps.append({"t": "rules", "rules": rules})
        steps.append({"t": "compare", "bad": bad_code, "good": good_code, "why": why})
        steps.append({"t": "code", "caption": "try this instead",
                      "code": similar, "stdin": c.get("stdin", "")})
        self._play_steps(steps)

    def action_next_challenge(self):
        if self.mode != "challenge":
            return
        if not self.started:
            self.action_start()
            return
        group = GROUPS[self.group_idx]
        self.ch_idx = (self.ch_idx + 1) % len(group["challenges"])
        self.attempts[self._flat_index()] = 0
        self._render_challenge()

    def action_prev_challenge(self):
        if self.mode != "challenge":
            return
        group = GROUPS[self.group_idx]
        self.ch_idx = (self.ch_idx - 1) % len(group["challenges"])
        self.attempts[self._flat_index()] = 0
        self._render_challenge()

    # ---- lesson (class-intro explainer) ----------------------------------- #

    LESSON_TYPE_MS = 0.16    # code typewriter — slow and readable
    OUT_REVEAL_MS = 0.04     # output 'printing' — a tick per char, sound on each
    AUDIO_LEAD = 0.18        # aplay/ALSA startup latency before sound actually begins

    def _lesson_focus(self, c):
        """Name the SPECIFIC new technique this challenge teaches (from its `need`
        list), so the W lesson calls out exactly what's being learned."""
        parts = []
        for n in c.get("need", []):
            hint = FOCUS_HINTS.get(n)
            if hint and hint not in parts:
                parts.append(hint)
        if not parts:
            tip = TOPIC_CHEATS.get(c.get("topic", "custom"), {}).get("tip", "")
            if tip:
                parts.append(tip)
        if not parts:
            return ""
        return "This challenge is teaching something new: " + " ".join(parts) + \
               "  Lock that in before you start typing."

    def _build_lesson_steps(self, c):
        lesson = LESSONS.get(c.get("topic", "custom"), LESSONS["custom"])
        topic = c.get("topic", "custom")
        steps = []
        if not self._structure_taught:
            self._structure_taught = True
            self.p["structure_taught"] = True
            save_progress(self.p)
            steps.append({"t": "text", "title": "How Python reads your code",
                          "body": STRUCTURE_PRELUDE})
        steps.append({"t": "text", "title": lesson["title"],
                      "body": f"Your mission: {c['prompt']}"})
        focus = self._lesson_focus(c)
        if focus:
            steps.append({"t": "text", "title": "What's new here", "body": focus})
        # First time this TOPIC is taught -> full lesson (intro, points, rules,
        # pitfall). Already taught -> skip the repeated lecture so the W
        # walkthrough stays challenge-specific instead of re-reading the same
        # "rules" every time you hit another challenge in the same topic.
        already_taught = topic in self._topics_taught
        self._topics_taught.add(topic)
        if not already_taught:
            self.p["topics_taught"] = sorted(self._topics_taught)
            save_progress(self.p)
            steps.append({"t": "text", "title": "", "body": lesson["intro"]})
            for i, (pt_title, pt_body) in enumerate(lesson["points"], 1):
                steps.append({"t": "text", "title": f"{i}. {pt_title}", "body": pt_body})
            rules = LESSON_RULES.get(topic)
            if rules:
                steps.append({"t": "rules", "rules": rules})
            pit = PITFALLS.get(topic)
            if pit:
                steps.append({"t": "compare", "bad": pit["bad"], "good": pit["good"],
                              "why": pit["why"]})
        # challenge-specific example FIRST — the "same idea, different X" trick
        # THIS challenge teaches, with its own challenge-specific why. Then the
        # topic's generic examples follow. So every watch leads with the exact
        # thing this challenge is about, never just the shared topic lesson.
        spec_caption, spec_code = example_code(c.get("example", ""))
        seen_codes: set = set()
        if spec_code:
            head = spec_caption.split("\n")[0].strip().rstrip(":").strip()
            if not head:
                head = "this challenge's idea"
            steps.append({"t": "tour", "caption": head,
                          "code": spec_code, "stdin": c.get("stdin", ""),
                          "why": example_why(c.get("example", ""))})
            seen_codes.add(spec_code.strip())
        whys = WHYS.get(topic, WHYS["custom"])
        for i, ex in enumerate(lesson["examples"]):
            # never show the exact same code twice in one watch
            if ex["code"].strip() in seen_codes:
                continue
            seen_codes.add(ex["code"].strip())
            steps.append({"t": "tour", "caption": ex["caption"],
                          "code": ex["code"], "stdin": ex.get("stdin", ""),
                          "why": whys[i % len(whys)] if whys else ""})
        if not already_taught:
            steps.append({"t": "text", "title": "Bottom line", "body": lesson["outro"]})
        # end with the ghost-write explainer — the drill fires right after
        steps.append({"t": "text", "title": "Now we're going to write it",
                      "body": GHOST_INTRO_TEXT})
        return steps

    def action_lesson(self):
        if self.mode != "challenge":
            return
        if self._ghost_on or self._vim_on or self._cat_playing or self._lesson_on:
            return
        self._start_lesson()

    def action_gate_watch(self):
        if self.mode != "challenge":
            return
        if self._ghost_on or self._vim_on or self._cat_playing or self._lesson_on:
            return
        self._start_lesson()

    def action_gate_listen(self):
        if self.mode != "challenge":
            return
        if self._ghost_on or self._vim_on or self._cat_playing or self._lesson_on:
            return
        c = self._current()
        topic = c.get("topic", "custom")
        tip = TOPIC_CHEATS.get(topic, TOPIC_CHEATS["custom"])["tip"]
        prompt = re.sub(r"[`*_#>~]", "", c["prompt"])
        prompt = " ".join(prompt.split())
        speak(f"{c['title']}. {prompt}. Quick tip: {tip}")
        self.query_one("#guide", Static).update(
            "[bold cyan]→ listening… (l again to repeat · Enter to dive in · w to watch)[/]")

    def _render_gate(self):
        c = self._current()
        w = max(24, self.size.width - 8)
        prompt = re.sub(r"[`*_#>~]", "", c["prompt"])
        prompt = " ".join(prompt.split())
        words = prompt.split()
        lines = []
        cur = ""
        for word in words:
            if cur and len(cur) + 1 + len(word) > w:
                lines.append(cur)
                cur = word
            else:
                cur = (cur + " " + word) if cur else word
        if cur:
            lines.append(cur)

        def center(s, style=""):
            return " " * max(0, (w - len(s)) // 2) + s

        t = Text()
        t.append("\n" * max(0, self.size.height // 6))
        t.append(center("◤  NEW CHALLENGE  ◥", "bold magenta"))
        t.append("\n\n")
        t.append(center(c["title"], "bold yellow"))
        t.append("\n\n")
        for line in lines:
            t.append(center(line, "#d5d5d5"))
            t.append("\n")
        t.append("\n\n")
        t.append(center("[ Enter ]  dive in — I got this", "bold green"))
        t.append("\n")
        t.append(center("[  w    ]  watch the full lesson", "bold yellow"))
        t.append("\n")
        t.append(center("[  l    ]  listen to the intro", "bold cyan"))
        t.append("\n\n")
        if self._flat_index() == 0:
            # very first challenge: teach the editor's vim modes up front
            t.append(center("how the editor works:  [i] type  ·  [Esc] stop typing  ·  [:] command bar  ·  type :!python3 % to run  ·  (click anywhere to place the cursor)", "dim"))
            t.append("\n")
        t.append(center("◢                    ◣", "dim"))
        self.query_one("#gate", Static).update(t)
        self.query_one("#gate", Static).add_class("visible")

    def _start_lesson(self):
        self._play_steps(self._build_lesson_steps(self._current()))

    def _play_steps(self, steps):
        self._stop_lesson()
        _kill_piper()
        self.lesson_gate = False
        self.query_one("#gate", Static).remove_class("visible")
        self._lesson_on = True
        self._lesson_gen += 1
        self._lesson_blocks = []
        self._lesson_steps = steps
        self._lesson_i = 0
        self.query_one("#lesson", Static).add_class("visible")
        self._lesson_play_step()

    def _stop_lesson(self):
        t = getattr(self, "_lesson_timer", None)
        if t is not None:
            t.stop()
            self._lesson_timer = None
        self._tour_stop_blink()
        self._lesson_phase = ""
        _kill_piper()  # stop any caption audio still playing

    def _finish_lesson(self):
        self._lesson_gen += 1  # discard any in-flight synth/capture
        self._stop_lesson()
        _kill_piper()
        self._lesson_on = False
        self.query_one("#lesson", Static).remove_class("visible")
        self._enter_editor()

    def _enter_editor(self):
        self.lesson_gate = False
        self.query_one("#gate", Static).remove_class("visible")
        # mandatory ghost-writing drill before the editor unlocks — EVERY time
        # you open a challenge (done or not), no skipping. Muscle memory first.
        self._start_ghost_required()

    def _focus_editor(self):
        self.query_one("#editor", VimEditor).focus()
        self._update_guide()

    def _lesson_play_step(self):
        self._stop_lesson()
        steps = self._lesson_steps
        if self._lesson_i >= len(steps):
            self._finish_lesson()
            return
        step = steps[self._lesson_i]
        kind = step["t"]
        if kind == "text":
            self._caption_start(step.get("title", ""), step.get("body", ""))
        elif kind == "rules":
            self._lesson_render_rules(step["rules"])
            self._speak_then_advance("The rules. " + ". ".join(step["rules"]))
        elif kind == "practice":
            self._lesson_render_practice(step["items"])
            # no auto-advance: let the user actually try these, then press Enter
            self._speak_only("Your turn. Try these after you solve the challenge. " + ". ".join(step["items"]))
        elif kind == "review":
            self._lesson_render_review(step)
            self._speak_then_advance("Here's your code. " + ". ".join(step["issues"]))
        elif kind == "compare":
            self._lesson_render_compare(step)
            self._speak_then_advance(
                "Here's a classic mistake. " + step.get("why", "") +
                "  Now look at the good version — that's the clean way to write it.")
        elif kind == "tour":
            self._tour_start(step)
        else:  # code example — speak the caption + why FIRST, then type it slowly
            self._lesson_typed = 0
            self._lesson_code = step["code"]
            self._lesson_caption = step.get("caption", "")
            self._lesson_stdin = step.get("stdin", "")
            self._lesson_why = step.get("why", "")
            self._lesson_phase = "pre"
            self._lesson_render_blocks("", cursor=True)
            if self.voice_on and (self._lesson_caption or self._lesson_why):
                self._lesson_speak_intro()
            else:
                self._lesson_begin_typing()

    def _lesson_next(self):
        # stop the pending auto-advance timer BEFORE nulling it, so a manual
        # Enter-skip can't race it — otherwise the old timer fires later and
        # skips a SECOND step (the "double skip" glitch mid-TTS).
        t = getattr(self, "_lesson_timer", None)
        if t is not None:
            t.stop()
            self._lesson_timer = None
        self._lesson_gen += 1  # invalidate any in-flight synth/capture from the old step
        self._lesson_i += 1
        self._lesson_play_step()

    def _speak_then_advance(self, text, extra=0.4):
        """Speak `text` and advance to the next step only once the audio has
        finished (measured from the audio bytes), so the voice is never cut off.
        Falls back to a text-length estimate when there's no voice."""
        if not self.voice_on:
            self._lesson_timer = self.set_timer(self._estimate_dur(text) + extra, self._lesson_next)
            return
        gen = self._lesson_gen

        def _synth():
            raw = synthesize(text, TEACH_RATE)
            self.call_from_thread(self._on_speak_ready, text, raw, gen, extra)

        threading.Thread(target=_synth, daemon=True).start()

    def _on_speak_ready(self, text, raw, gen, extra):
        if gen != self._lesson_gen:
            return
        if raw:
            dur = max(0.1, len(raw) / 2 / 22050.0)
            play_raw(raw)
            lead = self.AUDIO_LEAD   # sound actually starts ~0.18s after play_raw
        else:
            dur = self._estimate_dur(text)
            lead = 0.0
        self._lesson_timer = self.set_timer(lead + dur + extra, self._lesson_next)

    def _speak_only(self, text):
        """Speak `text` WITHOUT auto-advancing — the user presses Enter to move on.
        Used by the practice step so it doesn't cut out before they can try it."""
        if not self.voice_on:
            return
        gen = self._lesson_gen

        def _synth():
            raw = synthesize(text, TEACH_RATE)
            if gen != self._lesson_gen:
                return
            self.call_from_thread(self._on_speak_only, raw, gen)

        threading.Thread(target=_synth, daemon=True).start()

    def _on_speak_only(self, raw, gen):
        if gen != self._lesson_gen:
            return
        if raw:
            play_raw(raw)

    def _lesson_speak_intro(self):
        text = " ".join(x for x in (self._lesson_caption, self._lesson_why) if x)
        gen = self._lesson_gen

        def _synth():
            raw = synthesize(text, TEACH_RATE)
            self.call_from_thread(self._on_intro_ready, raw, gen)

        threading.Thread(target=_synth, daemon=True).start()

    def _on_intro_ready(self, raw, gen):
        if gen != self._lesson_gen:
            return
        if raw:
            dur = max(0.1, len(raw) / 2 / 22050.0)
            play_raw(raw)
            self._lesson_timer = self.set_timer(self.AUDIO_LEAD + dur + 0.25, self._lesson_begin_typing)
        else:
            self._lesson_begin_typing()

    def _lesson_begin_typing(self):
        self._lesson_phase = "typing"
        self._lesson_render_blocks("", cursor=True)
        self._lesson_timer = self.set_interval(self.LESSON_TYPE_MS, self._lesson_type_tick)

    def _lesson_type_tick(self):
        if self._lesson_phase != "typing":
            return
        code = self._lesson_code
        if self._lesson_typed < len(code):
            self._lesson_typed += 1
            play_key()  # mechanical typewriter thock per character
            self._lesson_render_blocks(code[:self._lesson_typed], cursor=True)
            return
        # typed out → HOLD so the learner can read it, THEN run
        self._stop_lesson()  # stop the typewriter timer first
        self._lesson_phase = "hold"
        self._lesson_render_blocks(code, cursor=False)
        self._lesson_timer = self.set_timer(1.4, self._lesson_run_code)

    def _lesson_run_code(self):
        self._lesson_phase = "running"
        self._lesson_render_blocks(self._lesson_code, cursor=False)
        gen = self._lesson_gen
        threading.Thread(target=self._lesson_capture,
                         args=(self._lesson_code, self._lesson_stdin, gen), daemon=True).start()

    def _lesson_capture(self, code, stdin, gen):
        if stdin:
            # interactive input(): echo the prompt + typed value + result in a PTY
            out = run_demo_session(code, stdin)
            err = ""
        else:
            out, err = run_lesson_code(code, stdin)
        if gen != self._lesson_gen:
            return
        self.call_from_thread(self._lesson_on_result, (out or err or "").rstrip("\n"), gen)

    def _lesson_on_result(self, result, gen):
        if gen != self._lesson_gen:
            return
        # Stream the output into the console (blue cursor + sound per char),
        # THEN keep this example on screen and stack the next one below it.
        self._lesson_out_text = result
        self._lesson_out_i = 0
        self._lesson_phase = "reveal"
        self._lesson_render_blocks(self._lesson_code, cursor=False)
        self._lesson_timer = self.set_interval(self.OUT_REVEAL_MS, self._lesson_out_tick)

    def _lesson_out_tick(self):
        if self._lesson_phase != "reveal":
            return
        text = self._lesson_out_text
        if self._lesson_out_i < len(text):
            self._lesson_out_i += 1
            # skip newlines instantly so the blue cursor always sits on a printed char
            while self._lesson_out_i < len(text) and text[self._lesson_out_i] == "\n":
                self._lesson_out_i += 1
            play_output_tick()
            self._lesson_render_blocks(self._lesson_code, cursor=False)
            return
        # reveal complete — stop the reveal timer, settle the block, then advance
        self._stop_lesson()
        self._lesson_blocks.append({"caption": self._lesson_caption,
                                    "code": self._lesson_code,
                                    "output": text})
        self._lesson_out_text = ""
        self._lesson_out_i = 0
        self._lesson_phase = "paused"
        self._lesson_render_blocks("", cursor=False)
        self._lesson_timer = self.set_timer(2.0, self._lesson_next)

    # ---- code walkthrough tour (token highlights synced to TTS) ---------- #

    def _tour_start(self, step):
        self._stop_lesson()
        self._tour_code = step["code"]
        self._tour_caption = step.get("caption", "")
        self._tour_stdin = step.get("stdin", "")
        self._tour_why = step.get("why", "")
        self._tour_parts = _tour_parts_for(step["code"])
        self._tour_i = 0
        self._tour_output = ""
        self._tour_blink_on = False
        self._tour_typed = 0
        # line-by-line execution trace (the "watch it run, top to bottom" pass)
        self._trace_steps: list = []
        self._trace_i = 0
        self._trace_cur_line = 0
        self._trace_cur_boxes: dict = {}
        self._trace_cur_out_before = ""
        self._trace_cur_out_after = ""
        # write the code out character by character first (the "watch it get
        # typed" effect), THEN walk its tokens with highlights + TTS
        self._lesson_phase = "tour_typing"
        self._tour_render_typing()
        self._lesson_timer = self.set_interval(self.LESSON_TYPE_MS, self._tour_type_tick)

    def _tour_type_tick(self):
        if self._lesson_phase != "tour_typing":
            return
        if self._tour_typed < len(self._tour_code):
            self._tour_typed += 1
            play_key()
            self._tour_render_typing()
            return
        # written out → start the token walkthrough
        self._stop_lesson()   # stop the typewriter interval
        self._lesson_phase = "tour"
        self._tour_render()
        if self._tour_parts:
            self._tour_play_part(0)
        else:
            self._tour_run_code()

    def _tour_render_typing(self):
        typed = self._tour_code[:self._tour_typed]
        out = [Text("EXAMPLE — ", style="bold yellow"),
               Text(self._tour_caption, style="yellow"), Text(""), Text("")]
        lines = (typed if typed else " ").split("\n")
        for i, ln in enumerate(lines, 1):
            row = Text(f"{i:>2} │ ", style="dim")
            row.append_text(_code_text(ln))
            if self._tour_typed < len(self._tour_code) and i == len(lines):
                row.append(" ", style="reverse")   # cursor where the next char lands
            out.append(row)
        self.query_one("#lesson", Static).update(self._lesson_screen(out))

    def _tour_render(self):
        # settled parts (already explained) keep a steady color; the active part
        # blinks bold<->non-bold; future parts stay plain.
        spans: list[tuple[int, int, str]] = []
        for i, p in enumerate(self._tour_parts):
            if i >= self._tour_i:
                break
            sp = _find_span(self._tour_code, p["hl"])
            if sp:
                spans.append((sp[0], sp[1], p.get("color", "#22c55e")))
        if self._tour_i < len(self._tour_parts):
            p = self._tour_parts[self._tour_i]
            sp = _find_span(self._tour_code, p["hl"])
            if sp:
                color = p.get("color", "#22c55e")
                style = ("bold " + color) if self._tour_blink_on else color
                spans.append((sp[0], sp[1], style))
        code_t = _code_with_spans(self._tour_code, spans)
        out = [Text("EXAMPLE — ", style="bold yellow"),
               Text(self._tour_caption, style="yellow"), Text(""), Text("")]
        for i, ln in enumerate(_lines_of(code_t), 1):
            row = Text(f"{i:>2} │ ", style="dim")
            row.append_text(ln)
            out.append(row)
        if self._tour_output:
            out.append(Text(""))
            # one Text per output line — a multiline Text passed whole to
            # _box_lines only draws the border on its first line, so the rest of
            # the numbers spill out the side of the box.
            for k, line in enumerate(self._tour_output.split("\n")):
                ol = Text("→ output: " if k == 0 else "          ", style="bold #d5d5d5")
                ol.append(line, style="bold green")
                out.append(ol)
        if self._tour_i >= len(self._tour_parts) and self._tour_why:
            out.append(Text(""))
            # wrap the why so a long sentence doesn't widen the box past the screen
            why_w = max(36, self.size.width - 24)
            for j, wl in enumerate(_wrap_words(self._tour_why, why_w)):
                wt = Text("why: " if j == 0 else "     ", style="cyan")
                wt.append(wl, style="#9a9aa5")
                out.append(wt)
        self.query_one("#lesson", Static).update(self._lesson_screen(out))

    def _tour_play_part(self, i):
        self._tour_i = i
        self._tour_blink_on = True
        self._tour_render()
        if self._tour_blink_timer is None:
            self._tour_blink_timer = self.set_interval(0.4, self._tour_blink_tick)
        text = self._tour_parts[i]["say"]
        if not self.voice_on:
            self._lesson_timer = self.set_timer(self._estimate_dur(text) + 0.4, self._tour_next)
            return
        gen = self._lesson_gen

        def _synth():
            raw = synthesize(text, TEACH_RATE)
            self.call_from_thread(self._tour_on_say_ready, raw, gen, i)

        threading.Thread(target=_synth, daemon=True).start()

    def _tour_on_say_ready(self, raw, gen, i):
        if gen != self._lesson_gen:
            return
        if raw:
            dur = max(0.1, len(raw) / 2 / 22050.0)
            play_raw(raw)
            lead = self.AUDIO_LEAD
        else:
            dur = self._estimate_dur(self._tour_parts[i]["say"])
            lead = 0.0
        self._lesson_timer = self.set_timer(lead + dur + 0.35, self._tour_next)

    def _tour_blink_tick(self):
        if self._lesson_phase != "tour":
            return
        self._tour_blink_on = not self._tour_blink_on
        if self._tour_blink_on:
            play_menu_blip(4)          # the ping rides the BOLD phase
        self._tour_render()

    def _tour_next(self):
        self._tour_i += 1
        if self._tour_i < len(self._tour_parts):
            self._tour_play_part(self._tour_i)
        else:
            self._tour_stop_blink()
            self._tour_run_code()

    def _tour_stop_blink(self):
        t = getattr(self, "_tour_blink_timer", None)
        if t is not None:
            t.stop()
            self._tour_blink_timer = None
        self._tour_blink_on = False

    def _tour_run_code(self):
        self._tour_stop_blink()
        self._lesson_phase = "trace"
        gen = self._lesson_gen
        threading.Thread(target=self._tour_trace_capture,
                         args=(self._tour_code, self._tour_stdin, gen), daemon=True).start()

    def _tour_capture(self, code, stdin, gen):
        if stdin:
            out = run_demo_session(code, stdin)
            err = ""
        else:
            out, err = run_lesson_code(code, stdin)
        if gen != self._lesson_gen:
            return
        self.call_from_thread(self._tour_on_result, (out or err or "").rstrip("\n"), gen)

    def _tour_on_result(self, result, gen):
        if gen != self._lesson_gen:
            return
        self._tour_output = result
        self._lesson_phase = "done"
        self._tour_render()
        if self.voice_on and self._tour_why:
            self._speak_then_advance(self._tour_why)
        else:
            self._lesson_timer = self.set_timer(2.2, self._lesson_next)

    # ---- execution trace: watch it run top to bottom --------------------- #

    def _tour_trace_capture(self, code, stdin, gen):
        out, err, events = trace_code(code, stdin)
        if gen != self._lesson_gen:
            return
        self.call_from_thread(self._tour_trace_on_ready, out, err, events, gen)

    def _tour_trace_on_ready(self, out, err, events, gen):
        if gen != self._lesson_gen:
            return
        result = (out or err or "").rstrip("\n")
        if not events:
            # tracing produced no line events — fall back to a plain reveal
            self._tour_on_result(result, gen)
            return
        # build steps: the state shown for a line is the state AFTER it runs,
        # which is the NEXT event's snapshot (the last line keeps its own). Each
        # step also carries the output printed before/after so the console can
        # show the real prints accumulating line by line.
        self._tour_output = result
        steps = []
        for i, ev in enumerate(events):
            ln = ev[0]
            locs = ev[1]
            out_before = (ev[2] if len(ev) > 2 else "").rstrip("\n")
            after = events[i + 1][1] if i + 1 < len(events) else locs
            if i + 1 < len(events):
                nxt = events[i + 1]
                out_after = (nxt[2] if len(nxt) > 2 else "").rstrip("\n")
            else:
                out_after = result
            steps.append((ln, locs, after, out_before, out_after))
        self._trace_steps = steps
        self._trace_i = 0
        self._lesson_phase = "trace"
        self._tour_trace_step(0)

    def _tour_trace_step(self, i):
        self._trace_i = i
        ln, before, after, out_before, out_after = self._trace_steps[i]
        self._trace_cur_line = ln
        self._trace_cur_boxes = after
        self._trace_cur_out_before = out_before
        self._trace_cur_out_after = out_after
        self._tour_trace_render()
        play_menu_blip(min(4 + i, 12))
        text = self._trace_narrate(ln, before, after)
        if not self.voice_on or not text:
            self._lesson_timer = self.set_timer(0.9, self._tour_trace_next)
            return
        gen = self._lesson_gen

        def _synth():
            raw = synthesize(text, TEACH_RATE)
            self.call_from_thread(self._tour_trace_say_ready, raw, gen)

        threading.Thread(target=_synth, daemon=True).start()

    def _tour_trace_say_ready(self, raw, gen):
        if gen != self._lesson_gen:
            return
        if raw:
            dur = max(0.1, len(raw) / 2 / 22050.0)
            play_raw(raw)
            lead = self.AUDIO_LEAD
        else:
            ln, before, after, _ob, _oa = self._trace_steps[self._trace_i]
            dur = self._estimate_dur(self._trace_narrate(ln, before, after))
            lead = 0.0
        self._lesson_timer = self.set_timer(lead + dur + 0.2, self._tour_trace_next)

    def _trace_narrate(self, lineno, before, after):
        """What changed on this line, spoken value-first — 'x becomes 2' — so the
        voice narrates the STATE as the user watches the boxes update."""
        changes = []
        for k, v in after.items():
            if k not in before:
                changes.append(f"{k} is now {v}")
            elif before[k] != v:
                changes.append(f"{k} becomes {v}")
        gone = [k for k in before if k not in after]
        if gone:
            changes.append(" and ".join(gone) + " is gone")
        if changes:
            return f"line {lineno}: " + ", ".join(changes) + "."
        lines = self._tour_code.split("\n")
        line_text = lines[lineno - 1].strip() if 0 < lineno <= len(lines) else ""
        # a `return` inside a recursive function is the KEY idea: the stop sign
        # (base case) vs the recursive step — say which one, don't just gloss it.
        if line_text.startswith("return"):
            recur = None
            try:
                recur = _find_recursion(ast.parse(self._tour_code))
            except Exception:
                recur = None
            if recur is not None:
                name = recur[0]
                if name in line_text and "(" in line_text:
                    return (f"line {lineno}: the recursive call — {name} calls itself "
                            f"with a smaller number and stacks the answer.")
                return (f"line {lineno}: the stop sign — this return ends the "
                        f"recursion, so it stops calling itself.")
            return f"line {lineno}: this return hands back and ends the function."
        return f"line {lineno}: " + _line_explain(line_text)

    def _tour_trace_next(self):
        if self._trace_i + 1 < len(self._trace_steps):
            self._tour_trace_step(self._trace_i + 1)
        else:
            self._tour_on_result(self._tour_output, self._lesson_gen)

    def _tour_trace_render(self):
        code_lines = self._tour_code.split("\n")
        cur = self._trace_cur_line
        out = [Text("RUN — ", style="bold magenta"),
               Text("watch it go top to bottom, one line at a time", style="dim"),
               Text(""), Text("")]
        for i, ln in enumerate(code_lines, 1):
            row = Text(f"{i:>2} ", style="dim")
            if i == cur:
                row.append("▶ ", style="bold yellow")
                row.append_text(Text(ln, style="reverse bold"))
            else:
                row.append("  ")
                row.append_text(_code_text(ln))
            out.append(row)
        out.append(Text(""))
        boxes = self._trace_cur_boxes
        if boxes:
            out.append(Text("  boxes right now:", style="bold cyan"))
            for k, v in boxes.items():
                out.append(Text(f"    {k}  →  {v}", style="#e8e8ef"))
        else:
            out.append(Text("  (no boxes yet — nothing stored)", style="dim"))
        # the REAL prints, accumulating below — keep every old line and highlight
        # what THIS line just printed (yellow), so the eye ties print() → output
        after = self._trace_cur_out_after or ""
        if after:
            before = self._trace_cur_out_before or ""
            new = after[len(before):] if before and after.startswith(before) else after
            new_count = len([l for l in new.split("\n") if l != ""])
            out.append(Text(""))
            out.append(Text("  printed so far:", style="bold green"))
            after_lines = after.split("\n")
            max_out = 10
            if len(after_lines) > max_out:
                out.append(Text(f"    … {len(after_lines) - max_out} earlier line(s)", style="dim"))
                after_lines = after_lines[-max_out:]
            n = len(after_lines)
            for j, line in enumerate(after_lines):
                is_new = line != "" and (n - j) <= new_count
                style = "bold #facc15" if is_new else "bold green"
                ol = Text("    ", style="dim")
                ol.append(line if line != "" else " ", style=style)
                out.append(ol)
        self.query_one("#lesson", Static).update(self._lesson_screen(out))

    # ---- caption (karaoke word highlight) -------------------------------- #

    def _caption_start(self, title, body):
        self._caption_title = title
        self._caption_words = re.findall(r"\S+", body)
        self._caption_i = -1  # nothing highlighted until audio is ready
        self._lesson_phase = "caption"
        self._caption_redraw()
        gen = self._lesson_gen
        if not self.voice_on:
            self._cap_body_ready(body, None, gen)
            return
        threading.Thread(target=self._cap_synth_body, args=(body, gen), daemon=True).start()

    def _cap_synth_body(self, body, gen):
        raw = synthesize(body, TEACH_RATE)
        self.call_from_thread(self._cap_body_ready, body, raw, gen)

    def _cap_body_ready(self, body, raw, gen):
        if gen != self._lesson_gen:
            return
        if raw:
            # real audio duration — the highlight rides exactly on the voice
            dur = max(0.1, len(raw) / 2 / 22050.0)
            play_raw(raw)
            lead = self.AUDIO_LEAD  # sound doesn't start until aplay/ALSA wakes up
        else:
            dur = self._estimate_dur(body)
            lead = 0.0
        self._caption_word_durs = self._distribute_words(dur, self._caption_words)
        self._caption_wi = 0
        self._caption_i = -1  # nothing highlighted until the sound actually starts
        self._caption_redraw()
        if lead > 0:
            self._lesson_timer = self.set_timer(lead, self._cap_begin_words)
        else:
            self._cap_begin_words()

    def _cap_begin_words(self):
        self._caption_i = 0
        self._caption_redraw()
        self._cap_schedule_word()

    def _cap_schedule_word(self):
        if self._caption_wi >= len(self._caption_word_durs):
            self._lesson_timer = self.set_timer(0.6, self._lesson_next)
            return
        self._lesson_timer = self.set_timer(self._caption_word_durs[self._caption_wi], self._cap_word_tick)

    def _cap_word_tick(self):
        self._caption_wi += 1
        self._caption_i += 1
        self._caption_redraw()
        self._cap_schedule_word()

    def _distribute_words(self, dur, words):
        weights = []
        for w in words:
            wgt = len(w) + 1.0
            if w and w[-1] in ",;:":
                wgt += 0.6
            elif w and w[-1] in ".!?":
                wgt += 1.4
            weights.append(wgt)
        tot = sum(weights) or 1.0
        return [dur * (wgt / tot) for wgt in weights]

    def _estimate_dur(self, body):
        return max(0.3, len(body) * 0.062)

    def _caption_redraw(self):
        # Fixed-width column so the caption card sits centered (horiz + vert)
        # with wrapped prose instead of stretching edge-to-edge across the screen.
        w = min(max(24, self.size.width - 16), 68)
        lines: list[list[int]] = []
        cur: list[int] = []
        cur_len = 0
        for wi, word in enumerate(self._caption_words):
            add = len(word) + (1 if cur else 0)
            if cur and cur_len + add > w:
                lines.append(cur)
                cur = []
                cur_len = 0
            cur.append(wi)
            cur_len += len(word) + (1 if len(cur) > 1 else 0)
        if cur:
            lines.append(cur)
        out: list[Text] = []
        for word_idxs in lines:
            ln = Text()
            for j, wi in enumerate(word_idxs):
                word = self._caption_words[wi]
                if wi == self._caption_i:
                    style = "bold yellow"      # being said right now
                elif wi < self._caption_i:
                    style = "yellow"           # already said — turned yellow
                else:
                    style = "#d5d5d5"          # not yet — white
                ln.append(word, style=style)
                if j < len(word_idxs) - 1:
                    ln.append(" ")
            out.append(ln)
        body = _box_lines(out, title=self._caption_title or "", center=True)
        self.query_one("#lesson", Static).update(
            _center_screen(body, self.size.width, self.size.height - 1))

    # ---- lesson render helpers ------------------------------------------- #

    def _lesson_screen(self, out: list[Text]) -> Text:
        """Box a list of styled lines, add the Enter/Esc footer, and center it."""
        out = out + [Text("")]
        out.append(Text("Enter ⏎ next   ·   Esc back to editor", style="dim"))
        body = _box_lines(out)
        return _center_screen(body, self.size.width, self.size.height - 1)

    def _lesson_render_rules(self, rules):
        out = [Text("THE RULES", style="bold yellow"), Text("")]
        for i, r in enumerate(rules, 1):
            ln = Text(f"{i}.  ", style="dim")
            ln.append(r, style="#f0f0f5")
            out.append(ln)
        self.query_one("#lesson", Static).update(self._lesson_screen(out))

    def _lesson_render_practice(self, items):
        out = [Text("YOUR TURN", style="bold green"), Text("")]
        out.append(Text("After you solve this challenge, try these twists:", style="#f0f0f5"))
        out.append(Text(""))
        for i, p in enumerate(items, 1):
            ln = Text(f"{i}.  ", style="dim")
            ln.append(p, style="#f0f0f5")
            out.append(ln)
        self.query_one("#lesson", Static).update(self._lesson_screen(out))

    def _lesson_render_review(self, step):
        out = [Text("YOUR CODE", style="bold magenta"), Text("")]
        lines = step["code"].split("\n") if step["code"] else [""]
        for i, line in enumerate(lines, 1):
            ln = Text(f"{i:>2} ", style="dim")
            if i in step["bad"]:
                ln.append("▸ ", style="bold red")
                ln.append(line, style="bold red")
            else:
                ln.append("  ")
                ln.append_text(_code_text(line))
            out.append(ln)
        out.append(Text(""))
        out.append(Text("WHAT TO FIX", style="bold yellow"))
        for issue in step["issues"]:
            ln = Text("• ", style="dim")
            ln.append(issue, style="#f0f0f5")
            out.append(ln)
        self.query_one("#lesson", Static).update(self._lesson_screen(out))

    def _lesson_render_compare(self, step):
        out = [Text("GOOD vs BAD", style="bold yellow"), Text("")]
        out.append(Text("BAD — this breaks:", style="bold red"))
        for i, line in enumerate(step.get("bad", "").split("\n"), 1):
            ln = Text(f"{i:>2} ", style="dim")
            ln.append("▸ ", style="bold red")
            ln.append(line, style="#ff9a9a")
            out.append(ln)
        out.append(Text(""))
        out.append(Text("GOOD — the fix:", style="bold green"))
        for i, line in enumerate(step.get("good", "").split("\n"), 1):
            ln = Text(f"{i:>2} ", style="dim")
            ln.append_text(_code_text(line))
            out.append(ln)
        out.append(Text(""))
        why = Text("why this matters: ", style="bold cyan")
        why.append(step.get("why", ""), style="#f0f0f5")
        out.append(why)
        self.query_one("#lesson", Static).update(self._lesson_screen(out))

    def _lesson_render_blocks(self, typed, cursor):
        out: list[Text] = []
        fulls = [blk["code"] for blk in self._lesson_blocks] + [self._lesson_code]
        target = max((len(ln) for code in fulls for ln in code.split("\n")), default=0)
        for blk in self._lesson_blocks:
            self._lesson_append_block(out, blk["caption"], blk["code"], blk["output"], target, cursor=False)
            out.append(Text(""))
        if self._lesson_phase in ("pre", "typing", "hold", "running", "reveal"):
            if self._lesson_phase == "reveal":
                out_text, out_i = self._lesson_out_text, self._lesson_out_i
            else:
                out_text, out_i = "", None
            self._lesson_append_block(out, self._lesson_caption, typed, out_text, target,
                                      cursor=cursor, reveal_i=out_i)
        self.query_one("#lesson", Static).update(self._lesson_screen(out))

    def _lesson_append_block(self, out, caption, code, output, target, cursor, reveal_i=None):
        head = Text("EXAMPLE — ", style="bold yellow")
        head.append(caption, style="yellow")
        out.append(head)
        lines = code.split("\n") if code else [""]
        for i, line in enumerate(lines):
            ln = Text(f"{i+1:>2} │ ", style="dim")
            ln.append_text(_code_text(line))
            ln.append(" " * max(0, target - len(line)))   # pad to a stable box width
            if cursor and i == len(lines) - 1:
                ln.append(" ", style="reverse")
            out.append(ln)
        if output:
            out.append(Text("→ output:", style="bold #d5d5d5"))
            if reveal_i is not None:
                for rl in _reveal_output_lines(output, reveal_i):
                    ol = Text("  ", style="dim")
                    ol.append_text(rl)
                    out.append(ol)
            else:
                for line in output.split("\n"):
                    ol = Text("  ", style="dim")
                    ol.append(line, style="bold green")
                    out.append(ol)

    # ---- real nvim command line (`:`) ----------------------------------- #

    def action_command(self):
        if self.mode != "challenge":
            return
        cmd = self.query_one("#cmd", CommandInput)
        cmd.add_class("visible")
        cmd.value = ""
        cmd.focus()
        # the `:` keypress itself is seen + heard
        play_key()
        self._flash_cmd()
        # pop the wildmenu right away (all commands), like nvim `:`
        self._wm_index = 0
        self._update_wildmenu()
        if not self._cmd_demo_shown:
            # one-time lesson: type the run command key-by-key so it's seen & heard
            self._cmd_demo_shown = True
            self._wm_hide()  # keep the wildmenu quiet while the demo types it out
            self._type_command("!python3 %")
        else:
            # after the demo, point at the recommended commands + Tab completion
            self.query_one("#guide", Static).update(
                "[yellow]→ press Tab to cycle the recommended run commands, then Enter.[/]")

    def on_input_changed(self, event: Input.Changed) -> None:
        if event.input.id != "cmd":
            return
        # swallow the async echo of a programmatic fill (Tab completion)
        if getattr(self, "_wm_ignore_changed", False):
            self._wm_ignore_changed = False
            return
        # once the command bar is dismissed, ignore the lingering clear echo
        if not self.query_one("#cmd", CommandInput).has_class("visible"):
            return
        if getattr(self, "_cmd_demoing", False):
            return
        if event.value:
            play_key()
            self._flash_cmd()
        # re-filter the wildmenu on every keystroke (first match highlighted)
        self._wm_index = 0
        self._update_wildmenu()

    def _flash_cmd(self):
        cmd = self.query_one("#cmd", Input)
        cmd.add_class("flash")
        t = getattr(self, "_flash_timer", None)
        if t is not None:
            t.stop()
        self._flash_timer = self.set_timer(0.5, self._unflash_cmd)

    def _unflash_cmd(self):
        self.query_one("#cmd", Input).remove_class("flash")

    def _type_command(self, text: str):
        """Type `text` into the `:` bar one key at a time (0.25s each), with a
        key click + yellow flash per key, so the keys are seen and heard. The
        bar is LOCKED while it types so the user can't overwrite the demo."""
        self._stop_command_demo()
        cmd = self.query_one("#cmd", Input)
        cmd.add_class("visible")
        cmd.value = ""
        cmd.disabled = True          # lock it — you can't mess up the demo text
        self._cmd_demo_text = text
        self._cmd_demo_pos = 0
        self._cmd_demoing = True
        self._cmd_demo_timer = self.set_interval(0.25, self._cmd_demo_tick)

    def _cmd_demo_tick(self):
        if not getattr(self, "_cmd_demoing", False):
            return
        cmd = self.query_one("#cmd", Input)
        if self._cmd_demo_pos < len(self._cmd_demo_text):
            self._cmd_demo_pos += 1
            cmd.value = self._cmd_demo_text[:self._cmd_demo_pos]
            play_key()
            self._flash_cmd()
        else:
            self._stop_command_demo()
            cmd = self.query_one("#cmd", Input)
            cmd.disabled = False   # unlock now that the demo text is written
            cmd.focus()
            self._wm_index = 0
            self._update_wildmenu()
            self.query_one("#guide", Static).update(
                "[yellow]→ that's the run command — press Enter to submit. (press Tab to see other commands)[/]")

    def _stop_command_demo(self):
        t = getattr(self, "_cmd_demo_timer", None)
        if t is not None:
            t.stop()
            self._cmd_demo_timer = None
        self._cmd_demoing = False
        try:
            self.query_one("#cmd", Input).disabled = False
        except Exception:
            pass

    def on_input_submitted(self, event: Input.Submitted):
        if event.input.id != "cmd":
            return
        raw = event.value.strip()
        event.input.value = ""
        self.query_one("#cmd", Input).remove_class("visible")
        self.query_one("#cmd", Input).remove_class("flash")
        self._wm_hide()
        self.query_one("#editor", VimEditor).focus()
        self._run_command(raw)

    def _run_command(self, raw: str):
        # `%` = the current buffer (like nvim). We run it against a temp file.
        code = self.query_one("#editor", VimEditor).get_text()
        if raw in ("q", "quit"):
            self.exit()
        elif raw in ("wq", "x"):
            save_progress(self.p)
            self.exit()
        elif raw in ("w", "write"):
            self.query_one("#output", Static).update("[bold]\"challenge.py\" written[/]")
        elif raw in ("submit", "run"):
            # lazy alias — same as :!python3 %
            self._run_and_submit()
        elif raw == "ghost":
            self.action_ghost()
        elif raw.startswith("!python3"):
            # the real nvim way to test: :!python3 %  — runs AND submits for a verdict
            self._run_and_submit()
        else:
            self.query_one("#output", Static).update(f"[dim]Unknown command: :{raw}[/]")

    # ---- nvim wildmenu (command-line autocomplete) ------------------------ #

    def on_command_input_complete(self, event: CommandInput.Complete) -> None:
        self._wm_cycle(event.delta)

    def on_command_input_cancel(self, event: CommandInput.Cancel) -> None:
        self._hide_command()

    def _hide_command(self) -> None:
        self._stop_command_demo()
        cmd = self.query_one("#cmd", CommandInput)
        cmd.value = ""
        cmd.remove_class("visible")
        cmd.remove_class("flash")
        self._wm_hide()
        self.query_one("#editor", VimEditor).focus()

    def _wm_matches(self, value: str) -> list[str]:
        v = value.strip().casefold()
        if not v:
            return list(COMMANDS)
        return [c for c in COMMANDS if c.casefold().startswith(v)]

    def _update_wildmenu(self) -> None:
        matches = self._wm_matches(self.query_one("#cmd", CommandInput).value)
        self._wm_matches_list = matches
        if not matches:
            self._wm_hide()
            return
        self._wm_index = min(self._wm_index, len(matches) - 1)
        self._wm_show(matches)

    def _wm_show(self, matches: list[str]) -> None:
        idx = self._wm_index
        t = Text()
        for i, m in enumerate(matches):
            if i:
                t.append("   ")
            if i == idx:
                t.append(m, style="reverse bold")
            else:
                t.append(m)
        self.query_one("#wildmenu", Static).update(t)
        self.query_one("#wildmenu", Static).add_class("visible")

    def _wm_hide(self) -> None:
        wm = self.query_one("#wildmenu", Static)
        wm.remove_class("visible")
        wm.update("")
        self._wm_matches_list = []

    def _wm_cycle(self, delta: int) -> None:
        cmd = self.query_one("#cmd", CommandInput)
        # cycle over the match set last computed from what the user typed, so
        # Tab keeps stepping through the same list instead of re-filtering on
        # the value we just filled in.
        matches = self._wm_matches_list or self._wm_matches(cmd.value)
        if not matches:
            return
        self._wm_matches_list = matches
        self._wm_index = (self._wm_index + delta) % len(matches)
        target = matches[self._wm_index]
        # fill the selected completion into the command line, cursor at the end
        if cmd.value != target:
            self._wm_ignore_changed = True
            cmd.value = target
        cmd.cursor_position = len(target)
        play_key()
        self._flash_cmd()
        self._wm_show(matches)

    # ---- keycaps help screen (`?`) -------------------------------------- #

    def action_help(self):
        cheat = self.query_one("#cheat", Markdown)
        cheat.update(self._keys_help())
        cheat.toggle_class("visible")
        if cheat.has_class("visible"):
            self.query_one("#side-examples", Vertical).add_class("hidden")
        else:
            self.query_one("#side-examples", Vertical).remove_class("hidden")

    def _keys_help(self):
        # keycap-style reference grouped into knowledge packs
        kc = lambda k: f"[on #3a3a3a]{k}[/]"
        return "\n\n".join([
            "## KEYS — knowledge packs\n",
            "### movement\n" + "  ".join(kc(x) for x in ["h", "j", "k", "l"]) +
            "  ·  " + " ".join(f"{kc(x)}={y}" for x, y in [("w","word"),("b","back"),("0","start"),("$","end"),("gg","top"),("G","bottom")]),
            "### editing\n" + "  ".join(kc(x) for x in ["i", "a", "o", "O"]) +
            "  ·  " + " ".join(f"{kc(x)}={y}" for x, y in [("dd","delete line"),("yy","yank"),("p","paste"),("x","del char"),("u","undo")]),
            "### run / test (real nvim)\n" + "  ".join(kc(x) for x in [":w", ":!python3 %", ":submit", ":q"]) +
            "  ·  " + f"{kc('Ctrl+Enter')}=run+submit",
            "### tutor\n" + " ".join(f"{kc(x)}={y}" for x, y in [("Ctrl+n","next"),("Ctrl+b","prev"),("Enter","dive in"),("w","watch"),("l","listen"),("e","lesson"),("F12","quick check"),("F1","keys"),("F2","cheat"),("F3","demo"),("Ctrl+G","ghost write"),("F6","voice"),("F7","review"),("F8","examples"),("F9","hints"),("F10","wider editor"),("F11","narrower editor"),("m","music"),("Esc","menu"),("q","quit")]),
        ])

    # ---- examples panel (F8): static wall of worked examples ------------ #

    def _render_side_examples(self):
        c = self._current()
        cards = self._examples_cards(c)
        try:
            panel_w = self.query_one("#side-examples", Vertical).size.width or 0
        except Exception:
            panel_w = 0
        # content budget: border + padding + line-number gutter + scrollbar. Fall
        # back to a comfortable width before the layout settles, so code lines
        # never over-wrap into a dangling fragment.
        w = panel_w - 10 if panel_w > 28 else 34
        self._ex_cards = cards
        self._ex_w = w
        # total output values across cards drives the silent spit-out animation
        total = 0
        for card in cards:
            out = self._example_output(card["code"], card["stdin"])
            total += len([v for v in out.split("\n") if v != ""])
        self._ex_total = total
        self._ex_reveal = 0
        self._ex_blink = True
        self._ex_render()
        self._stop_ex_anim()
        if total:
            # reveal one value every 0.5s (NO sound), blinking the range bounds
            self._ex_anim_timer = self.set_interval(0.5, self._ex_anim_tick)
        self.query_one("#side-examples-title", TabLabel).update(
            f"[bold]{len(cards)} EXAMPLES[/] — {c['title']}  ·  [reverse]F8[/] open/close · click to hide")

    def _ex_render(self):
        """Rebuild the examples wall with the current reveal/blink state."""
        t = Text()
        used = 0
        for i, card in enumerate(self._ex_cards):
            if i:
                t.append("\n")
            out = self._example_output(card["code"], card["stdin"])
            nvals = len([v for v in out.split("\n") if v != ""])
            local = max(0, self._ex_reveal - used)
            used += nvals
            reveal = local if local < nvals else nvals
            blink = self._ex_blink and self._ex_reveal < self._ex_total
            t.append_text(self._render_ex_box(card, self._ex_w, reveal=reveal, blink=blink))
        self.query_one("#side-inner", Static).update(t)

    def _ex_anim_tick(self):
        self._ex_reveal += 1
        self._ex_blink = not self._ex_blink
        if self._ex_reveal >= self._ex_total:
            self._stop_ex_anim()
            self._ex_blink = False
        self._ex_render()

    def _stop_ex_anim(self):
        t = getattr(self, "_ex_anim_timer", None)
        if t is not None:
            t.stop()
            self._ex_anim_timer = None
        self._ex_blink = False

    def _examples_cards(self, c):
        """All worked examples for a challenge: the lesson's captioned examples,
        the title-keyed variations, and the inline 'similar' example — each with
        a plain-English why. Deduped by code."""
        topic = c.get("topic", "custom")
        lesson = LESSONS.get(topic, LESSONS["custom"])
        whys = WHYS.get(topic, WHYS["custom"])
        cards = []
        seen = set()
        for i, ex in enumerate(lesson["examples"]):
            code = ex["code"]
            if code in seen:
                continue
            seen.add(code)
            cards.append({"caption": ex.get("caption", "example"), "code": code,
                          "stdin": ex.get("stdin", ""),
                          "why": whys[i % len(whys)] if whys else ""})
        for ex in EXAMPLES.get(c["title"], []):
            if ex["code"] in seen:
                continue
            seen.add(ex["code"])
            cards.append({"caption": "another way", "code": ex["code"],
                          "stdin": ex.get("stdin", ""),
                          "why": "Same idea, different values — the pattern is identical, just the names change."})
        cap, code = example_code(c.get("example", ""))
        if code and code not in seen:
            # caption = first text line, the "> note" becomes the why
            title, note = "", ""
            for ln in cap.splitlines():
                s = ln.strip()
                if not s:
                    continue
                if s.startswith(">"):
                    note = s.lstrip("> ").strip()
                elif not title:
                    title = s
            cards.append({"caption": title or "similar", "code": code,
                          "stdin": c.get("stdin", ""),
                          "why": note or (whys[len(cards) % len(whys)] if whys else "")})
        return cards

    def _example_output(self, code, stdin):
        key = (code, stdin)
        if key in _OUT_CACHE:
            return _OUT_CACHE[key]
        out, err = run_lesson_code(code, stdin)
        res = (out or err or "").rstrip("\n")
        _OUT_CACHE[key] = res
        return res

    def _render_ex_box(self, card, w: int = 34, reveal: int | None = None,
                       blink: bool = False) -> Text:
        """One worked-example card, boxed to a uniform width with line numbers,
        a divider, and a word-wrapped 'why'. `reveal` animates the output one
        value at a time (grey then green); `blink` flashes the range boundaries."""
        code = card["code"]
        out = self._example_output(code, card["stdin"])
        inner = max(14, w)   # target max content width (fits the sidebar)
        lines: list[Text] = []
        for j, cl in enumerate(_wrap_words(card["caption"], inner - 2)):
            c = Text("▸ " if j == 0 else "  ", style="bold green")
            c.append(cl, style="bold yellow")
            lines.append(c)
        for i, raw in enumerate(code.split("\n")):
            pieces = _code_wrap(raw, inner - 3)
            for pi, piece in enumerate(pieces):
                tl = Text(f"{i+1:>2}│" if pi == 0 else "   ", style="dim")
                spans = _range_boundary_spans(raw) if len(pieces) == 1 else set()
                if spans:
                    style = "bold #facc15 on #3a3a3a" if blink else "bold #facc15"
                    tl.append_text(highlight_line(piece, emph_spans=spans, emph_style=style))
                else:
                    tl.append_text(_code_text(piece))
                lines.append(tl)
        if out:
            self._append_output(lines, out, inner - 10, reveal)   # prefix "→ output: " is 10 cols
        lines.append(Text("─" * (inner - 2), style="dim"))
        why_lines = _wrap_words(card["why"], inner - 5)
        for j, wl in enumerate(why_lines):
            wt = Text("why: " if j == 0 else "     ", style="cyan")
            wt.append(wl, style="#9a9aa5")
            lines.append(wt)
        return _box_lines(lines)

    def _append_output(self, lines, out, width, reveal):
        """Append the output line(s), wrapped so no value lands in a weird spot.
        When `reveal` is set, values 'spit out' one at a time: already-shown
        values are green, the incoming one is grey, the rest are hidden."""
        values = [v for v in out.split("\n") if v != ""]
        if not values:
            return
        # a single list/tuple literal → show items with their index, so '0 is the
        # first' is explicit instead of hidden in the raw repr
        if len(values) == 1:
            idx = _indexed_list(values[0])
            if idx:
                values = idx
        if reveal is None or reveal >= len(values):
            show, incoming = values, None
        else:
            show, incoming = values[:reveal], values[reveal]
        parts = [(v, "bold green") for v in show]
        if incoming is not None:
            parts.append((incoming, "bold #555555"))   # grey — about to fill green
        # flow the values, wrapping to `width` and keeping each value whole
        wrapped: list[Text] = []
        line = Text()
        for idx, (v, st) in enumerate(parts):
            seg = ("" if idx == 0 else " · ") + v
            if line.cell_len and line.cell_len + len(seg) > width:
                wrapped.append(line)
                line = Text()
                seg = v
            line.append(seg, style=st)
        if line.cell_len:
            wrapped.append(line)
        for k, ln in enumerate(wrapped):
            ol = Text("→ output: " if k == 0 else "          ", style="bold #d5d5d5")
            ol.append_text(ln)
            lines.append(ol)

    def action_examples(self):
        """F8 — toggle the right-side worked-examples panel (static, scrollable)."""
        if self.mode != "challenge":
            return
        panel = self.query_one("#side-examples", Vertical)
        panel.toggle_class("hidden")
        if not panel.has_class("hidden"):
            self.query_one("#cheat", Markdown).remove_class("visible")

    # ---- toggles + editor size ------------------------------------------- #

    def action_toggle_hints(self):
        self.hints_on = not self.hints_on
        self.query_one("#guide", Static).update(
            f"[bold]→ hints {'ON' if self.hints_on else 'OFF'}[/]  ·  "
            f"{'a fail now underlines the broken line' if self.hints_on else 'no auto-hints on fail'}")
        if self.voice_on:
            speak("hints on" if self.hints_on else "hints off")

    def _set_challenge_width(self, w):
        self._challenge_w = max(20, min(70, w))
        self.query_one("#challenge-box", VerticalScroll).styles.width = f"{self._challenge_w}%"

    def action_editor_wider(self):
        # bigger editor = smaller challenge pane
        if self.mode == "challenge":
            self._set_challenge_width(self._challenge_w - 5)

    def action_editor_narrower(self):
        if self.mode == "challenge":
            self._set_challenge_width(self._challenge_w + 5)

    # ---- live visual replay (boxes fill as the code "runs") -------------- #

    def _start_visual(self, out):
        spec = self._current().get("visual")
        self._vis_spec = spec
        self._vis_kind = spec.get("kind", "counter")
        self._vis_n = int(spec.get("n", 6))
        self._vis_step = 0
        # keep the raw result visible in the output box under the overlay
        self.query_one("#output", Static).update(
            Text((out or "(no output)").rstrip("\n") + "\n✓ passed", style="green"))
        self.query_one("#visual", Static).add_class("visible")
        self._visual_render()
        t = getattr(self, "_vis_timer", None)
        if t is not None:
            t.stop()
        self._vis_timer = self.set_interval(0.4, self._visual_tick)

    def _visual_tick(self):
        if self._vis_step < self._vis_n:
            self._vis_step += 1
            play_menu_blip(min(self._vis_step, 12))  # rising note as it counts up
            self._visual_render()
            return
        t = self._vis_timer
        if t is not None:
            t.stop()
        self._vis_timer = None
        self._visual_finish()

    def _visual_render(self):
        kind = self._vis_kind
        n = self._vis_n
        step = self._vis_step
        t = Text()
        t.append("\n" * max(0, self.size.height // 5))
        t.append(f"  {self._current()['title']}", style="bold yellow")
        t.append("\n\n\n")
        t.append("  ")
        if kind == "progress":
            t.append("|", style="bold")
            for i in range(n):
                t.append("█" if i < step else "░",
                         style="bold #ffffff" if i < step else "bold #3a3a3a")
            t.append("|", style="bold")
            t.append(f"  {step}/{n}", style="dim")
        else:  # counter — grey boxes fill white in order
            for i in range(1, n + 1):
                if i <= step:
                    t.append(f" {i} ", style="bold black on #ffffff")
                else:
                    t.append(f" {i} ", style="bold #555555")
                if i < n:
                    t.append(" → ", style="dim")
        t.append("\n\n")
        if step >= n:
            t.append("  ✓ all lit up — Enter for the next one", style="bold green")
        else:
            t.append("  running…", style="dim")
        self.query_one("#visual", Static).update(t)

    def _visual_finish(self):
        self._update_guide()
        win, _ = self._sounds_for(self._flat_index())
        self._cancel_celebrate()
        self._pending_win = win
        self._celebrate_pass()

    def _close_visual(self):
        t = getattr(self, "_vis_timer", None)
        if t is not None:
            t.stop()
            self._vis_timer = None
        self.query_one("#visual", Static).remove_class("visible")

    # ---- cat-microwave loading screen (big challenge completed) ----------- #

    def _play_cat(self, on_done):
        """Tier-complete loading screen: play the cat-microwave mp4 FULLSCREEN
        (centered over the terminal), silent, with NOTHING overlapping it — no
        TTS, no win mp3, no confetti. It's its own self-contained moment."""
        _kill_piper()                # never let TTS overlap
        self._cancel_celebrate()     # cancel any pending win mp3 / confetti
        self.query_one("#confetti", Confetti).dismiss()
        self._cat_on_done = on_done
        self._cat_playing = True
        self._cat_proc = play_video(CAT_VIDEO, mute=False)   # full audio loading screen
        self.query_one("#cat", Static).add_class("visible")
        self.query_one("#cat", Static).update(self._cat_banner())
        t = getattr(self, "_cat_timer", None)
        if t is not None:
            t.stop()
        self._cat_timer = self.set_timer(CAT_VIDEO_S, self._cat_done)

    def _cat_banner(self) -> Text:
        """Fallback note if the fullscreen video can't open — one plain centered
        line, not ASCII art (the mp4 is the star)."""
        return _center_screen(Text("▶ tier complete", style="bold magenta"),
                              self.size.width, self.size.height - 1)

    def _cat_done(self):
        self._cat_timer = None
        # Make sure the fullscreen mpv/ffplay overlay is REALLY gone before we
        # show the next gate — otherwise its --fs window can keep keyboard focus
        # on Wayland/Hyprland and swallow the very next key ('w' to watch).
        proc = getattr(self, "_cat_proc", None)
        if proc is not None:
            try:
                if proc.poll() is None:
                    proc.terminate()
            except Exception:
                pass
        self._cat_proc = None
        self.query_one("#cat", Static).remove_class("visible")
        self._cat_playing = False
        cb = self._cat_on_done
        self._cat_on_done = None
        if cb:
            cb()

    def _cancel_cat(self):
        t = getattr(self, "_cat_timer", None)
        if t is not None:
            t.stop()
            self._cat_timer = None
        proc = getattr(self, "_cat_proc", None)
        if proc is not None:
            try:
                proc.terminate()
            except Exception:
                pass
            self._cat_proc = None
        self.query_one("#cat", Static).remove_class("visible")
        self._cat_playing = False
        self._cat_on_done = None


def main():
    TutorApp().run()


if __name__ == "__main__":
    main()
