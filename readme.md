# Inverse Dictator

Inverse Dictator is a program which speaks what you type, word-by-word.

### How to use it

    python inv_dict.py

See `python inv_dict.py --help` for more info.

### Prerequisites

The following programs must be installed:

* `python` (version 2 or 3)
* `say`

### How it works

`say` speaks out its input line-by-line.
Inverse dictator splits the input into phrases and sends each phrase to a different invocation of `say`.
It also uses advanced terminal IO to detect key presses and react instantly
(instead of waiting for you to press the return/enter key).

The size of phrases is proportional to your typing speed.
If you type fast, the phrases will be larger and speech will sound continuous.
If you type very slow, each word will be in a separate phrase.
