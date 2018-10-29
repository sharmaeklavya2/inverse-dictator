#!/usr/bin/env python

"""
This is an inverse-dictation program.
It speaks out word-by-word whatever you type.

You can optionally specify how to make it speak using command-line arguments.
The command-line arguments will be executed and
the text that you type will be passed into its stdin.
"""

from __future__ import print_function, unicode_literals, division

import sys
import os
import subprocess
import argparse
import threading
import signal

DEBUG = False
PY3 = sys.version_info.major >= 3
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
PROG_NAME = os.path.basename(os.path.abspath(__file__))


printed_newline = False
printed_newline_lock = threading.Lock()

def print_debug(*args, **kwargs):
    debug_only = kwargs.get('debug_only', True)  # python 2 workaround for https://www.python.org/dev/peps/pep-3102/#specification
    if DEBUG or not debug_only:
        with printed_newline_lock:
            global printed_newline
            if not printed_newline:
                print()
                sys.stdout.flush()
                printed_newline = True
        l = []
        for arg in args:
            if isinstance(arg, BaseException):
                l.append(type(arg).__name__ + ': ' + str(arg))
            else:
                l.append(str(arg))
        print(': '.join(l), file=sys.stderr)


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
        print_debug('Console: resetting')
        if Console.isatty and Console.is_unix:
            import termios
            termios.tcsetattr(Console.fd, termios.TCSANOW, Console.oldattr)


class StopExternal(Exception): pass


def run_external(text, speak_args):
    try:
        popen = subprocess.Popen(speak_args, stdin=subprocess.PIPE, universal_newlines=True)
    except OSError as e:
        print_debug(e, debug_only=False)
        if not (PY3 and isinstance(e, FileNotFoundError)):
            print_debug(PROG_NAME, 'Looks like your command-line arguments are incorrect.', debug_only=False)
        raise StopExternal('run_external: OSError')

    popen.communicate(text)
    if popen.returncode == - signal.SIGINT:
        raise StopExternal('run_external: received SIGINT')
    elif popen.returncode != 0:
        raise subprocess.CalledProcessError(returncode=popen.returncode, cmd=speak_args)


class WordBuffer(object):

    class ClosedError(Exception): pass

    def __init__(self):
        self.wordlist = []
        self.lock = threading.Lock()
        self.available = threading.Event()
        self.closed = False  # closed: whether bufferis closed for writing

    def is_closed(self):
        with self.lock:
            return self.closed

    def close(self, clear):
        with self.lock:
            self.closed = True
            if clear:
                self.wordlist[:] = []
            self.available.set()

    def add(self, word):
        with self.lock:
            if self.closed:
                raise WordBuffer.ClosedError('add failed because WordBuffer was closed.')
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
    func_name = 'word_buffer_to_sound'
    try:
        while True:
            wordlist = word_buffer.extract_all()
            if wordlist is None:
                break
            elif wordlist:
                sentence = ' '.join(wordlist)
                run_external(sentence, speak_args)
    except (KeyboardInterrupt, StopExternal, subprocess.CalledProcessError)  as e:
        word_buffer.close(True)
        print_debug(func_name, e, debug_only=not isinstance(e, subprocess.CalledProcessError))
    print_debug(func_name, 'exited')


EOF_CHARCODE = '\x04'
BKSP_CHARCODE = '\x7f'


def keyboard_to_word_buffer(word_buffer):
    func_name = 'keyboard_to_word_buffer'
    chars = []
    keep_going = True
    try:
        while keep_going:
            ch = Console.getch()

            if ch in ('', EOF_CHARCODE):
                word_buffer.close(False)
                keep_going = False
            elif word_buffer.is_closed():
                keep_going = False
                print_debug(func_name, 'speaker thread ended but keyboard thread did not.', debug_only=False)
                continue
            elif ch.isalnum() or ch in '.,;!?\'\"':
                chars.append(ch)
            elif ch == BKSP_CHARCODE:
                if chars:
                    chars.pop()
                    print('\b \b', end='')
                    sys.stdout.flush()
            elif chars:
                word = ''.join(chars)
                chars[:] = []
                try:
                    word_buffer.add(word)
                except WordBuffer.ClosedError as e:
                    print_debug(func_name, e, debug_only=False)
                    continue

            if ch not in ('', EOF_CHARCODE, BKSP_CHARCODE):
                print(ch, end='')
                sys.stdout.flush()
    except KeyboardInterrupt as e:
        word_buffer.close(True)
        print_debug(func_name, e)
    print_debug(func_name, 'exited')


def inverse_dictation(speak_args):
    word_buffer = WordBuffer()
    consumer_thread = threading.Thread(target=word_buffer_to_sound, name='word_buffer_to_sound',
        args=(word_buffer, speak_args))
    consumer_thread.start()
    try:
        Console.init()
        keyboard_to_word_buffer(word_buffer)
    finally:
        if not printed_newline:
            print()
        Console.reset()


def get_default_args():
    return ['say', '-r', '100']


USAGE = '%(prog)s [--debug] [--help | args]'

def main():
    global DEBUG
    parser = argparse.ArgumentParser(add_help=False, usage=USAGE, description=__doc__)
    parser.add_argument('--help', action='help', help='show a help message and exit')
    parser.add_argument('--debug', action='store_true', default=False, help='print debugging info')
    prog_args, speak_args = parser.parse_known_args()

    if prog_args.debug:
        DEBUG = True
    if not speak_args:
        speak_args = get_default_args()

    inverse_dictation(speak_args)


if __name__ == '__main__':
    main()
