#!/usr/bin/env python

"""
This is an inverse-dictation program.
It speaks out word-by-word whatever you type.
"""

from __future__ import print_function, unicode_literals, division

import sys
import os
import subprocess
import argparse
import threading
import signal

DEBUG = False
BASE_DIR = os.path.dirname(os.path.abspath(__file__))


class Console(object):

    @staticmethod
    def init():
        Console.isatty = sys.stdin.isatty()
        if not Console.isatty:
            Console.getch = staticmethod(lambda: sys.stdin.read(1))
        else:
            try:
                import termios
                Console.is_unix = True
                Console.getch = staticmethod(lambda: sys.stdin.read(1))
                # Disable buffering
                Console.fd = sys.stdin.fileno()
                Console.oldattr = termios.tcgetattr(Console.fd)
                newattr = termios.tcgetattr(Console.fd)
                newattr[3] = newattr[3] & ~termios.ICANON & ~termios.ECHO
                termios.tcsetattr(Console.fd, termios.TCSANOW, newattr)
            except ImportError:
                Console.is_unix = False
                import msvcrt
                if sys.version_info.major == 2:
                    Console.getch = staticmethod(msvcrt.getch)
                else:
                    Console.getch = staticmethod(lambda: msvcrt.getch().decode('utf-8'))

    @staticmethod
    def reset():
        if DEBUG:
            print('Resetting console', file=sys.stderr)
        if Console.isatty and Console.is_unix:
            import termios
            termios.tcsetattr(Console.fd, termios.TCSANOW, Console.oldattr)


class SpeakArgs(object):
    DEFAULT_SPEED = 100
    def __init__(self, speed):
        self.speed = speed if speed is not None else SpeakArgs.DEFAULT_SPEED


def run_external(text, speak_args):
    cmd = ['say', '-r', str(speak_args.speed)]
    popen = subprocess.Popen(cmd, stdin=subprocess.PIPE, universal_newlines=True)
    popen.communicate(text)
    if popen.returncode not in (0, signal.SIGINT):
        raise subprocess.CalledProcessError(returncode=popen.returncode, cmd=cmd)


class WordBuffer(object):

    class ClosedError(Exception): pass

    def __init__(self):
        self.wordlist = []
        self.lock = threading.Lock()
        self.available = threading.Event()
        self.closed = False  # closed: whether bufferis closed for writing

    def close(self, clear):
        with self.lock:
            self.closed = True
            if clear:
                self.wordlist[:] = []
            self.available.set()

    def add(self, word):
        with self.lock:
            if self.closed:
                raise WordBuffer.ClosedError()
            else:
                self.wordlist.append(word)
                self.available.set()

    def extract_all(self):
        self.available.wait()
        with self.lock:
            if not self.closed:
                self.available.clear()
            if self.wordlist:
                wordlist = self.wordlist
                self.wordlist = []
                return wordlist
            elif self.closed:
                return None
            else:
                return []


def word_buffer_to_sound(word_buffer, speak_args):
    try:
        while True:
            wordlist = word_buffer.extract_all()
            if wordlist is None:
                break
            elif wordlist:
                sentence = ' '.join(wordlist)
                run_external(sentence, speak_args)
    except KeyboardInterrupt:
        word_buffer.close(True)
    except subprocess.CalledProcessError as e:
        word_buffer.close(True)
        if e.returncode != - signal.SIGINT:
            raise
    if DEBUG:
        print('word_buffer_to_sound: exited', file=sys.stderr)


EOF_CHARCODE = '\x04'
BKSP_CHARCODE = '\x7f'


def keyboard_to_word_buffer(word_buffer):
    chars = []
    keep_going = True
    try:
        while keep_going:
            ch = Console.getch()

            if ch.isalnum() or ch in '.,;!?\'\"':
                chars.append(ch)
            elif ch in ('', EOF_CHARCODE):
                word_buffer.close(False)
                keep_going = False
            elif ch == BKSP_CHARCODE:
                if chars:
                    chars.pop()
                    print('\b \b', end='')
                    sys.stdout.flush()
            elif chars:
                word = ''.join(chars)
                chars[:] = []
                word_buffer.add(word)

            if ch not in ('', EOF_CHARCODE, BKSP_CHARCODE):
                print(ch, end='')
                sys.stdout.flush()
    except KeyboardInterrupt:
        word_buffer.close(True)
        if DEBUG:
            print('keyboard_to_word_buffer: interrupted', file=sys.stderr)


def inverse_dictation(speak_args):
    word_buffer = WordBuffer()
    consumer_thread = threading.Thread(target=word_buffer_to_sound, name='word_buffer_to_sound',
        args=(word_buffer, speak_args))
    consumer_thread.start()
    try:
        Console.init()
        keyboard_to_word_buffer(word_buffer)
    finally:
        print()
        Console.reset()
    if DEBUG:
        print('inverse_dictation: exited', file=sys.stderr)


def main():
    global DEBUG
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('-s', '--speed', type=int, help='Speed in words per minute')
    parser.add_argument('-d', '--debug', action='store_true', default=False)
    args = parser.parse_args()

    speak_args = SpeakArgs(args.speed)
    if args.debug:
        DEBUG = True

    inverse_dictation(speak_args)


if __name__ == '__main__':
    main()
