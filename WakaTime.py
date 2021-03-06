""" ==========================================================
File:        WakaTime.py
Description: Automatic time tracking for Sublime Text 2 and 3.
Maintainer:  WakaTi.me <support@wakatime.com>
Website:     https://www.wakati.me/
==========================================================="""

__version__ = '1.3.2'

import sublime
import sublime_plugin

import glob
import os
import platform
import sys
import time
import threading
import uuid
from os.path import expanduser, dirname, realpath, isfile, join, exists


# globals
ACTION_FREQUENCY = 5
ST_VERSION = int(sublime.version())
PLUGIN_DIR = dirname(realpath(__file__))
API_CLIENT = '%s/packages/wakatime/wakatime-cli.py' % PLUGIN_DIR
SETTINGS_FILE = 'WakaTime.sublime-settings'
SETTINGS = {}
LAST_ACTION = 0
LAST_FILE = None
HAS_SSL = False
LOCK = threading.RLock()

# check if we have SSL support
try:
    import ssl
    HAS_SSL = True

    # import wakatime package
    sys.path.insert(0, join(PLUGIN_DIR, 'packages', 'wakatime'))
    import wakatime

except ImportError:
    from subprocess import Popen


def setup_settings_file():
    """ Convert ~/.wakatime.conf to WakaTime.sublime-settings
    """
    global SETTINGS
    # To be backwards compatible, rename config file
    SETTINGS = sublime.load_settings(SETTINGS_FILE)
    api_key = SETTINGS.get('api_key', '')
    if not api_key:
        api_key = ''
        try:
            with open(join(expanduser('~'), '.wakatime.conf')) as old_file:
                for line in old_file:
                    line = line.split('=', 1)
                    if line[0] == 'api_key':
                        api_key = str(line[1].strip())
            try:
                os.remove(join(expanduser('~'), '.wakatime.conf'))
            except:
                pass
        except IOError:
            pass
    SETTINGS.set('api_key', api_key)
    sublime.save_settings(SETTINGS_FILE)


def prompt_api_key():
    global SETTINGS
    if not SETTINGS.get('api_key'):
        def got_key(text):
            if text:
                SETTINGS.set('api_key', str(text))
                sublime.save_settings(SETTINGS_FILE)
        window = sublime.active_window()
        if window:
            window.show_input_panel('Enter your WakaTime api key:', '', got_key, None, None)
            return True
        else:
            print('Error: Could not prompt for api key because no window found.')
    return False


def python_binary():
    python = 'python'
    if platform.system() == 'Windows':
        python = 'pythonw'
        try:
            Popen([python, '--version'])
        except:
            for path in glob.iglob('/python*'):
                if exists(realpath(join(path, 'pythonw.exe'))):
                    python = realpath(join(path, 'pythonw'))
                    break
    return python


def enough_time_passed(now):
    if now - LAST_ACTION > ACTION_FREQUENCY * 60:
        return True
    return False


def handle_write_action(view):
    global LOCK, LAST_FILE, LAST_ACTION
    with LOCK:
        targetFile = view.file_name()
        thread = SendActionThread(targetFile, isWrite=True)
        thread.start()
        LAST_FILE = targetFile
        LAST_ACTION = time.time()


def handle_normal_action(view):
    global LOCK, LAST_FILE, LAST_ACTION
    with LOCK:
        targetFile = view.file_name()
        thread = SendActionThread(targetFile)
        thread.start()
        LAST_FILE = targetFile
        LAST_ACTION = time.time()


class SendActionThread(threading.Thread):

    def __init__(self, targetFile, isWrite=False, force=False):
        threading.Thread.__init__(self)
        self.targetFile = targetFile
        self.isWrite = isWrite
        self.force = force
        self.debug = SETTINGS.get('debug')
        self.api_key = SETTINGS.get('api_key', '')
        self.last_file = LAST_FILE

    def run(self):
        if self.targetFile:
            self.timestamp = time.time()
            if self.force or self.isWrite or self.targetFile != self.last_file or enough_time_passed(self.timestamp):
                self.send()

    def send(self):
        if not self.api_key:
            print('missing api key')
            return
        cmd = [
            API_CLIENT,
            '--file', self.targetFile,
            '--time', str('%f' % self.timestamp),
            '--plugin', 'sublime-wakatime/%s' % __version__,
            '--key', str(bytes.decode(self.api_key.encode('utf8'))),
        ]
        if self.isWrite:
            cmd.append('--write')
        if self.debug:
            cmd.append('--verbose')
            print(cmd)
        if HAS_SSL:
            wakatime.main(cmd)
        else:
            cmd.insert(0, python_binary())
            if platform.system() == 'Windows':
                Popen(cmd, shell=False)
            else:
                with open(join(expanduser('~'), '.wakatime.log'), 'a') as stderr:
                    Popen(cmd, stderr=stderr)


def plugin_loaded():
    setup_settings_file()
    after_loaded()


def after_loaded():
    if not prompt_api_key():
        sublime.set_timeout(after_loaded, 500)


# need to call plugin_loaded because only ST3 will auto-call it
if ST_VERSION < 3000:
    plugin_loaded()


class WakatimeListener(sublime_plugin.EventListener):

    def on_post_save(self, view):
        handle_write_action(view)

    def on_activated(self, view):
        handle_normal_action(view)

    def on_modified(self, view):
        handle_normal_action(view)
