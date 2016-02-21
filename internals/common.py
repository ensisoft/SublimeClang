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

###---------------------------------------------------###
###              WARNING: Magic ahead.                ###
###---------------------------------------------------###
#
# If the stuff inside the try blocked is moved out of this
# file (for example into clang-complete.py) shit stops
# working. I.e. get_setting returns default values. I
# suspect this plugin_loaded() crap has something to do
# with this, however in this code fork it's not being even
# used. Anyhow, while stuff remains in this file stuff
# appears to work. Go figure.
#

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

    def display_user_selection(options, callback):
        sublime.active_window().show_quick_panel(options, callback)


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

    def display_user_selection(options, callback):
        callback(0)


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
            if e == ".":
                continue
            elif e == "..":
                continue
            name = os.path.join(dir, e)
            if os.path.isfile(name) == False:
                continue
            #print("Found file: " + e)
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

def get_project_settings(cpp_source_file):
    project_settings_file = find_project_file(cpp_source_file)
    if project_settings_file == None:
        return (None, None)
    project_settings = read_project_settings(project_settings_file)
    if project_settings == None:
        return (project_settings_file, None)
    outs = []
    for setting in project_settings:
        if "${home}" in setting:
            home = os.path.expanduser("~")
            outs.append(setting.replace("${home}", home))
        elif "${project}" in setting:
            pass

    return (project_settings_file, outs)

def find_file_location(directory, filename):
    entities = os.listdir(directory)
    for e in entities:
        if e == ".":
            continue
        elif e == "..":
            continue
        if filename == e:
            return directory

    # recursive into subdirs
    for e in entities:
        if e == ".":
            continue
        elif e == "..":
            continue
        path = os.path.join(directory, e)
        if os.path.isdir(path) == False:
            continue

        found = find_file(path, filename)
        if found:
            return found

    return ""


def get_cpu_count():
    cpus = 1
    try:
        import multiprocessing
        cpus = multiprocessing.cpu_count()
    except:
        pass
    return cpus
