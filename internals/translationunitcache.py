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

import os
import sys

from clang import cindex
from common import *
from parsehelp import *
from translationunit import TranslationUnit
import threading
import Queue
import time
import shlex
import subprocess
import sys
from ctypes import cdll, Structure, POINTER, c_char_p, c_void_p, c_uint, c_bool

import re
import threading
import collections







def format_cursor(cursor):
    return "%s:%d:%d" % (cursor.location.file.name, cursor.location.line,
                         cursor.location.column)

def get_cursor_spelling(cursor):
    cursor_spelling = None
    if cursor != None:
        cursor_spelling = cursor.spelling or cursor.displayname
        cursor_spelling = re.sub(r"^(enum\s+|(class|struct)\s+(\w+::)*)", "", cursor_spelling)
    return cursor_spelling

searchcache = {}

class ExtensiveSearch:
    def quickpanel_extensive_search(self, idx):
        if idx == 0:
            for cpu in range(get_cpu_count()):
                t = threading.Thread(target=self.worker)
                t.start()
            self.queue.put((0, "*/+"))
        elif len(self.options) > 2:
            self.found_callback(self.options[idx][1])

    def __init__(self, cursor, spelling, found_callback, folders, opts, name="", impl=True, search_re=None, file_re=None):
        self.name = name
        if impl:
            self.re = re.compile(r"\w+[\*&\s]+(?:\w+::)?(%s\s*\([^;\{]*\))(?:\s*const)?(?=\s*\{)" % re.escape(spelling))
            self.impre = re.compile(r"(\.cpp|\.c|\.cc|\.m|\.mm)$")
        else:
            self.re = re.compile(r"\w+[\*&\s]+(?:\w+::)?(%s\s*\([^;\{]*\))(?:\s*const)?(?=\s*;)" % re.escape(spelling))
            self.impre = re.compile(r"(\.h|\.hpp)$")
        if search_re != None:
            self.re = search_re
        if file_re != None:
            self.impre = file_re
        self.spelling = spelling
        self.folders = folders
        self.opts = opts
        self.impl = impl
        self.target = ""
        self.cursor = None
        if cursor:
            self.cursor = format_cursor(cursor)
        self.queue = Queue.PriorityQueue()
        self.candidates = Queue.Queue()
        self.lock = threading.RLock()
        self.timer = None
        self.status_count = 0
        self.found_callback = found_callback
        self.options = [["Yes", "Do extensive search"], ["No", "Don't do extensive search"]]
        k = self.key()
        if k in searchcache:
            self.options = [["Redo search", "Redo extensive search"], ["Don't redo", "Don't redo extensive search"]]
            targets = searchcache[k]
            if isinstance(targets, str):
                # An exact match is known, we're done here
                found_callback(targets)
                return
            elif targets != None:
                self.options.extend(targets)
        display_user_selection(self.options, self.quickpanel_extensive_search)

    def key(self):
        return str((self.cursor, self.spelling, self.impre.pattern, self.re.pattern, self.impl, str(self.folders)))

    def done(self):
        cache = None
        if len(self.target) > 0:
            cache = self.target
        elif not self.candidates.empty():
            cache = []
            while not self.candidates.empty():
                name, function, line, column = self.candidates.get()
                pos = "%s:%d:%d" % (name, line, column)
                cache.append([function, pos])
                self.candidates.task_done()
        searchcache[self.key()] = cache
        self.found_callback(cache)

    def do_message(self):
        try:
            self.lock.acquire()
            run_in_main_thread(lambda: status_message(self.status))
            self.status_count = 0
            self.timer = None
        finally:
            self.lock.release()

    def set_status(self, message):
        try:
            self.lock.acquire()
            self.status = message
            if self.timer:
                self.timer.cancel()
                self.timer = None
            self.status_count += 1
            if self.status_count == 30:
                self.do_message()
            else:
                self.timer = threading.Timer(0.1, self.do_message)
        finally:
            self.lock.release()

    def worker(self):
        try:
            while len(self.target) == 0:
                prio, name = self.queue.get(timeout=60)
                if name == "*/+":
                    run_in_main_thread(lambda: status_message("Searching for %s..." % ("implementation" if self.impl else "definition")))
                    name = os.path.basename(self.name)
                    for folder in self.folders:
                        for dirpath, dirnames, filenames in os.walk(folder):
                            for filename in filenames:
                                full_path = os.path.join(dirpath, filename)
                                ok = not "./src/build" in full_path and not "\\src\\build" in full_path
                                if not ok:
                                    full_path = os.path.abspath(full_path)
                                    ok = not "SublimeClang" in full_path and not "Y:\\src\\build" in full_path
                                if ok and self.impre.search(filename) != None:
                                    score = 1000
                                    for i in range(min(len(filename), len(name))):
                                        if filename[i] == name[i]:
                                            score -= 1
                                        else:
                                            break
                                    self.queue.put((score, full_path))
                    for i in range(get_cpu_count()-1):
                        self.queue.put((1001, "*/+++"))

                    self.queue.put((1010, "*/++"))
                    self.queue.task_done()
                    continue
                elif name == "*/++":
                    run_in_main_thread(self.done)
                    break
                elif name == "*/+++":
                    self.queue.task_done()
                    break

                remove = tuCache.get_status(name) == TranslationUnitCache.STATUS_NOT_IN_CACHE
                fine_search = not remove

                self.set_status("Searching %s" % name)

                # try a regex search first
                f = open(name, "r")
                data = f.read()
                f.close()
                fine_cands = []
                for match in self.re.finditer(data):
                    fine_search = True
                    loc = match.start()
                    for i in range(len(match.groups())+1):
                        m = match.group(i)
                        if self.spelling in m:
                            loc = match.start(i)

                    line, column = get_line_and_column_from_offset(data, loc)
                    fine_cands.append((name, line, column))
                    self.candidates.put((name, match.group(0), line, column))

                if fine_search and self.cursor and self.impl:
                    tu2 = tuCache.get_translation_unit(name, self.opts)
                    if tu2 != None:
                        tu2.lock()
                        try:
                            for cand in fine_cands:
                                cursor2 = cindex.Cursor.get(
                                        tu2.var, cand[0],
                                        cand[1],
                                        cand[2])
                                if cursor2 != None:
                                    d = cursor2.canonical_cursor
                                    if d != None and cursor2 != d:
                                        if format_cursor(d) == self.cursor:
                                            self.target = format_cursor(cursor2)
                                            run_in_main_thread(self.done)
                                            break
                        finally:
                            tu2.unlock()
                        if remove:
                            tuCache.remove(name)
                self.queue.task_done()
        except Queue.Empty as e:
            pass
        except:
            import traceback
            traceback.print_exc()


# our supported languages
class Language:
    CPP    = 1    # C++ (Yay!)
    C      = 2    # Plain C (Yuck)
    ObjC   = 3    # Objective C (I don't even..)
    ObjCPP = 4    # Objective C++ (urf)
    Other  = 5    # whatever else (Ok, script kids)

    def __init__(self, val):
        self.value = val

    def is_supported(self):
        assert self.value is not None
        if self.value == Language.Other:
            return False
        return True

    def __str__(self):
        if self.value == Language.CPP:
            return "C++"
        elif self.value == Language.C:
            return "C"
        elif self.value == Language.ObjC:
            return "Objective C"
        elif self.value == Language.ObjCPP:
            return "Objective C++"
        return "Other"

    def key(self):
        if self.value == Language.CPP:
            return "c++"
        elif self.value == Language.C:
            return "c"
        elif self.value == Language.ObjC:
            return "objc"
        elif self.value == Language.ObjCPP:
            return "objc++"
        return "other"


class CompileOptions(object):
    def __init__(self, lang, sys_includes):
        assert lang is not None
        assert lang.is_supported()

        self.index_parse_type = 13
        self.system_includes  = sys_includes
        self.language_options = None # array
        self.project_options  = None # array
        self.language         = lang

    def __str__(self):
        s = ' -isystem '.join([""] + self.system_includes)
        s = s + '\n'
        if self.language_options is not None:
            s = s + ' '.join(self.language_options)
        if self.project_options is not None:
            s = s + ' '.join(self.project_options)
        return s

    __repr__ = __str__

    @property
    def index_type(self):
        return self.index_parse_type

    def is_valid(self):
        if system_includes == []:
            return False
        return True

    def prepare(self):
        assert self.system_includes is not None
        opts = []
        for inc in self.system_includes:
            opts = opts + ["-isystem", inc]

        if self.language_options is not None:
            opts = opts = self.language_options
        if self.project_options is not None:
            opts = opts + self.project_options
        return opts

# this is a source file to be parsed (compiled).
class SourceFile(object):
    def __init__(self, cpp_source_file):
        self.source_file = cpp_source_file

    @property
    def name(self):
        return self.source_file

    def __str__(self):
        return self.source_file




# this will replace TranslationUnitCache
class Compiler(object):
    def __init__(self):
        self.index  = cindex.Index.Create()
        self.lock   = threading.Lock()
        self.cache  = {} # filename -> TranslationUnit
        self.parse_options = 13

    # compile a sourcefile into a translation unit with the given options.
    def compile(self, sourcefile, options):
        unit = None
        self.lock.acquire()
        try:
            name = sourcefile.name()
            if self.cache.has_key(name):
                return self.cache[name]

            memory_buffer_files = None
            opts = options.prepare()
            tu = self.index.parse(None, opts, memory_buffer_files,
                self.parse_options)
            assert tu is not None

            unit = TranslationUnit(sourcefile, tu)
            self.cache[sourcefile] = unit

        finally:
            self.lock.release()
        return unit


# background compile queue
class CompileQueue(object):
    def __init__(self):
        self.queue  = Queue.Queue()
        self.thread = threading.Thread(target=self.thread_loop)
        self.thread.daemon = True
        self.thread.start()

    def thread_loop(self):
        pass



class TranslationUnitCache(Worker):
    STATUS_PARSING      = 1
    STATUS_REPARSING    = 2
    STATUS_READY        = 3
    STATUS_NOT_IN_CACHE = 4

    def __init__(self, num_threads):
        workerthreadcount = num_threads
        self.as_super = super(TranslationUnitCache, self)
        self.as_super.__init__(workerthreadcount)
        self.translationUnits = LockedVariable({})
        self.parsingList = LockedVariable([])
        self.busyList = LockedVariable([])
        self.index = None

    def get_status(self, filename):
        tu = self.translationUnits.lock()
        pl = self.parsingList.lock()
        a = filename in tu
        b = filename in pl
        self.translationUnits.unlock()
        self.parsingList.unlock()
        if a and b:
            return TranslationUnitCache.STATUS_REPARSING
        elif a:
            return TranslationUnitCache.STATUS_READY
        elif b:
            return TranslationUnitCache.STATUS_PARSING
        else:
            return TranslationUnitCache.STATUS_NOT_IN_CACHE

    # todo: refactor out of here
    def __display_status(self):
        if get_setting("parse_status_messages", True):
            self.as_super.__display_status()

    def __add_busy(self, filename, task, data):
        bl = self.busyList.lock()
        test = filename in bl

        if test:
            self.busyList.unlock()
            # Another thread is already doing something with
            # this file, so try again later
            if self.tasks.empty():
                try:
                    time.sleep(1)
                except:
                    pass
            self.tasks.put((task, data))
            return True
        else:
            bl.append(filename)
            self.busyList.unlock()
        return False

    def __remove_busy(self, filename):
        bl = self.busyList.lock()
        try:
            bl.remove(filename)
        finally:
            self.busyList.unlock()

    def __task_parse(self, data):
        filename, opts, on_done = data
        if self.__add_busy(filename, self.__task_parse, data):
            return
        try:
            self.set_status("Parsing %s" % filename)
            self.get_translation_unit(filename, opts)
            self.set_status("Parsing %s done" % filename)
        finally:
            l = self.parsingList.lock()
            try:
                l.remove(filename)
            finally:
                self.parsingList.unlock()
                self.__remove_busy(filename)
        if on_done != None:
            run_in_main_thread(on_done)

    def __task_reparse(self, data):
        filename, opts, unsaved_files, on_done = data
        if self.__add_busy(filename, self.__task_reparse, data):
            return
        try:
            self.set_status("Reparsing %s" % filename)
            tu = self.get_translation_unit(filename, opts, unsaved_files)
            if tu != None:
                tu.reparse(unsaved_files)
                self.set_status("Reparsing %s done" % filename)

        finally:
            l = self.parsingList.lock()
            try:
                l.remove(filename)
            finally:
                self.parsingList.unlock()
                self.__remove_busy(filename)
        if on_done != None:
            run_in_main_thread(on_done)

    def __task_clear(self, data):
        tus = self.translationUnits.lock()
        try:
            tus.clear()
            searchcache.clear()
        finally:
            self.translationUnits.unlock()

    def __task_remove(self, data):
        if self.__add_busy(data, self.__task_remove, data):
            return
        try:
            tus = self.translationUnits.lock()
            try:
                if data in tus:
                    del tus[data]
            finally:
                self.translationUnits.unlock()
        finally:
            self.__remove_busy(data)

    def reparse(self, filename, opts, unsaved_files=[], on_done=None):
        ret = False
        pl = self.parsingList.lock()
        try:
            if filename not in pl:
                ret = True
                pl.append(filename)
                self.tasks.put((
                    self.__task_reparse,
                    (filename, opts, unsaved_files, on_done)))
        finally:
            self.parsingList.unlock()
        return ret

    def add_ex(self, filename, opts, on_done=None):
        tu = self.translationUnits.lock()
        pl = self.parsingList.lock()
        try:
            if filename not in tu and filename not in pl:
                pl.append(filename)
                self.tasks.put((
                    self.__task_parse,
                    (filename, opts, on_done)))
        finally:
            self.translationUnits.unlock()
            self.parsingList.unlock()

    def prepare(self, filename, opts, on_done=None):
        ret = False
        tu = self.translationUnits.lock()
        pl = self.parsingList.lock()
        try:
            if filename not in tu and filename not in pl:
                ret = True
                pl.append(filename)
                self.tasks.put((
                    self.__task_parse,
                    (filename, opts, on_done)))
        finally:
            self.translationUnits.unlock()
            self.parsingList.unlock()
        return ret


    def get_translation_unit(self, filename, opts, unsaved_files=[]):
        if self.index == None:
            self.index = cindex.Index.create()
        tu = None
        tus = self.translationUnits.lock()
        args = opts.prepare()
        args.append(filename)

        if filename not in tus:
            self.translationUnits.unlock()

            blob = self.index.parse(None, args, unsaved_files, opts.index_type)
            assert blob is not None

            tu = TranslationUnit(blob, filename)
            tu.args = args
            tus = self.translationUnits.lock()
            tus[filename] = tu
            self.translationUnits.unlock()
        else:
            tu = tus[filename]
            recompile = tu.args != args

            if recompile:
                del tus[filename]
            self.translationUnits.unlock()

            if recompile:
                self.set_status("Options change detected. Will recompile %s" % filename)
                self.add_ex(filename, opts, None)
        return tu

    def remove(self, filename):
        self.tasks.put((self.__task_remove, filename))

    def clear(self):
        self.tasks.put((self.__task_clear, None))

tuCache =  None #TranslationUnitCache()
