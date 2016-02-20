#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
Copyright (c) 2011-2012 Fredrik Ehnbom

This software is provided 'as-is', without any express or implied
warranty. In no event will the authors be held liable for any damages
arising from the use of this software.

Permission is granted to anyone to use this software for any purpose,
including commercial applications, and to alter it and redistribute it
freely, subject to the following restrictions:

   1. The origin of this software must not be misrepresented; you must not
   claim that you wrote the original software. If you use this software
   in a product, an acknowledgment in the product documentation would be
   appreciated but is not required.

   2. Altered source versions must be plainly marked as such, and must not be
   misrepresented as being the original software.

   3. This notice may not be removed or altered from any source
   distribution.
"""

"""
Copyright (c) 2016 Sami Väisänen, Ensisoft
http://www.ensisoft.com
"""


import threading
import time
import Queue
import os
import re
import sys
import glob
import json

if sys.version[0] == '2':
    def sencode(s):
        return s.encode("utf-8")

    def sdecode(s):
        return s

    def bencode(s):
        return s
    def bdecode(s):
        return s
else:
    def sencode(s):
        return s

    def sdecode(s):
        return s

    def bencode(s):
        return s.encode("utf-8")

    def bdecode(s):
        return s.decode("utf-8")

loaded = False
loaded_callbacks = []
def plugin_loaded():
    global loaded
    global loaded_callbacks
    loaded = True
    for c in loaded_callbacks:
        c()
    loaded_callbacks = []

try:
    import sublime
    def are_we_there_yet(x):
        global loaded_callbacks
        if loaded:
            x()
        else:
            loaded_callbacks.append(x)

    def run_in_main_thread(func):
        sublime.set_timeout(func, 0)


    def error_message(msg):
        # Work around for http://www.sublimetext.com/forum/viewtopic.php?f=3&t=9825
        if sublime.active_window() == None:
            sublime.set_timeout(lambda: error_message(msg), 500)
        else:
            sublime.error_message(msg)


    def is_supported_language(view):
        if view.is_scratch() or not get_setting("enabled", True, view) or view.file_name() == None:
            return False
        language = get_language(view)
        if language == None or (language != "c++" and
                                language != "c" and
                                language != "objc" and
                                language != "objc++"):
            return False
        return True

    def status_message(msg):
        sublime.status_message(sdecode(msg))

    def get_settings():
        return sublime.load_settings("SublimeClang.sublime-settings")


    def get_setting(key, default=None, view=None):
        try:
            if view == None:
                view = sublime.active_window().active_view()
            s = view.settings()
            if s.has("sublimeclang_%s" % key):
                return s.get("sublimeclang_%s" % key)
        except:
            pass
        return get_settings().get(key, default)

    def expand_path(value, window):
        if window == None:
            # Views can apparently be window less, in most instances getting
            # the active_window will be the right choice (for example when
            # previewing a file), but the one instance this is incorrect
            # is during Sublime Text 2 session restore. Apparently it's
            # possible for views to be windowless then too and since it's
            # possible that multiple windows are to be restored, the
            # "wrong" one for this view might be the active one and thus
            # ${project_path} will not be expanded correctly.
            #
            # This will have to remain a known documented issue unless
            # someone can think of something that should be done plugin
            # side to fix this.
            window = sublime.active_window()

        get_existing_files = \
            lambda m: [ path \
                for f in window.folders() \
                for path in [os.path.join(f, m.group('file'))] \
                if os.path.exists(path) \
            ]
        view = window.active_view()
        project_path = None
        if hasattr(window, "project_file_name") and window.project_file_name() is not None:
            project_path = os.path.split(window.project_file_name())[0]
        else:
            for f in window.folders():
                projects = glob.glob(os.path.join(f, '*.sublime-project'))
                if len(projects):
                    project_path = f
                    break

        if project_path:
            project_path = project_path.replace("\\", "\\\\") # Path will be used within a regex, thus escape every backslash
            value = re.sub(r'\${project_path}', project_path, value)
        value = re.sub(r'\${project_path:(?P<file>[^}]+)}', lambda m: len(get_existing_files(m)) > 0 and get_existing_files(m)[0] or m.group('file'), value)
        value = re.sub(r'\${env:(?P<variable>[^}]+)}', lambda m: os.getenv(m.group('variable')) if os.getenv(m.group('variable')) else "%s_NOT_SET" % m.group('variable'), value)
        value = re.sub(r'\${home}', re.escape(os.getenv('HOME')) if os.getenv('HOME') else "HOME_NOT_SET", value)
        value = re.sub(r'\${folder:(?P<file>[^}]+)}', lambda m: os.path.dirname(m.group('file')), value)
        value = value.replace('${this_file_path}', os.path.dirname(view.file_name()) if view and view.file_name() else "FILE_NOT_ON_DISK")
        value = value.replace('\\', '/')

        return value

    def display_user_selection(options, callback):
        sublime.active_window().show_quick_panel(options, callback)

    def look_for_file(filename, current_dir, levels_up):
        """Look for file up to #levels_up dir levels, starting from #current_dir."""
        while current_dir != os.path.dirname(current_dir):
            if os.path.exists(os.path.join(current_dir, filename)):
                return os.path.join(current_dir, filename)
            if levels_up <= 0:
                break
            levels_up -= 1
            current_dir = os.path.dirname(current_dir)
        return None


    # Find the project file for project/user specific settings.
    # The search is performed based on the C++ source file location.
    # and ascends from that folder towards the root.
    # Returns filename with complete path to the file or None if not found.
    def find_project_file(source_file):
        p = re.compile("\\.sublime-project$")
        dir = os.path.dirname(source_file)
        while len(dir) != 0:
            #print("Trying: " + dir)
            entities = os.listdir(dir)
            for e in entities:
                m = p.search(e)
                if m == None:
                    continue
                return os.path.normpath(dir + "/" + e)
                if (dir == "/"):
                    break
            # move up one folder
            (head, tail) = os.path.split(dir)
            dir = head

    # Read the project specific settings from the project file.
    def read_project_settings(project_file):
        file = open(project_file, mode="r")
        try:
            data = json.load(file)
        except ValueError:
            return None
        settings = data["settings"]
        if settings != None:
            return settings["sublimeclang_options"]

        return None


    # expand special variable such as ${home} in user settings.
    def expand_setting_variable(input):
        if "${home}" in input:
            home = os.path.expanduser("~")
            input = input.replace("${home}", home)

        return input

except:
    # Just used for unittesting
    def are_we_there_yet(f):
        f()

    def error_message(msg):
        raise Exception(msg)

    def get_setting(key, default=None, view=None):
        return default

    def run_in_main_thread(func):
        func()

    def status_message(msg):
        print(msg)

    def expand_path(value, window):
        return value

    def display_user_selection(options, callback):
        callback(0)

    def look_for_file(filename, current_dir, levels_up):
        return None


class LockedVariable:
    def __init__(self, var):
        self.var = var
        self.l = threading.Lock()

    def try_lock(self):
        return self.l.acquire(False)

    def lock(self):
        self.l.acquire()
        return self.var

    def unlock(self):
        self.l.release()


class Worker(object):
    def __init__(self, threadcount=-1):
        if threadcount < 1:
            threadcount = get_cpu_count()
        self.tasks = Queue.Queue()
        for i in range(threadcount):
            t = threading.Thread(target=self.worker)
            t.daemon = True
            t.start()

    def display_status(self):
        status_message(self.status)

    def set_status(self, msg):
        self.status = msg
        run_in_main_thread(self.display_status)

    def worker(self):
        try:
            # Just so we give time for the editor itself to start
            # up before we start doing work
            if sys.version[0] != '3':
                time.sleep(5)
        except:
            pass
        while True:
            task, data = self.tasks.get()
            try:
                task(data)
            except:
                import traceback
                traceback.print_exc()
            finally:
                self.tasks.task_done()


def complete_path(value):
    path_init, path_last = os.path.split(value)
    if path_init[:2] == "-I" and (path_last == "**" or path_last == "*"):
        starting_path = path_init[2:]
        include_paths = []
        if os.path.exists(starting_path):
            if path_last == "*":
                for dirname in os.listdir(starting_path):
                    if not dirname.startswith("."):  # skip directories that begin with .
                        include_paths.append("-I" + os.path.join(starting_path, dirname))
            elif path_last == "**":
                for dirpath, dirs, files in os.walk(starting_path):
                    for dirname in list(dirs):
                        if dirname.startswith("."):  # skip directories that begin with .
                            dirs.remove(dirname)
                    if dirpath != starting_path:
                        include_paths.append("-I" + dirpath)
            else:
                include_paths.append("-I" + starting_path)
        else:
            pass  # perhaps put some error here?
        return include_paths
    else:
        return [value]


def get_path_setting(key, default=None, view=None):
    value = get_setting(key, default, view)
    opts = []
    if isinstance(value, list):
        for v in value:
            opts.append(expand_path(v, view.window()))
    else:
        opts.append(expand_path(value, view.window()))
    return opts

def get_project_settings(cpp_source_file):
    project_settings_file = find_project_file(cpp_source_file)
    if project_settings_file == None:
        return (None, None)
    project_settings = read_project_settings(project_settings_file)
    if project_settings == None:
        return (None, None)
    outs = []
    for setting in project_settings:
        outs.append(expand_setting_variable(setting))
    return (project_settings_file, outs)


def get_cpu_count():
    cpus = 1
    try:
        import multiprocessing
        cpus = multiprocessing.cpu_count()
    except:
        pass
    return cpus
