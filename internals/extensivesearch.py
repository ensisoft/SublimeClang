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

import common
import threading
import Queue
import re
import os
import translationunitcache
from clang import cindex

searchcache = {}

class ExtensiveSearch:
    def quickpanel_extensive_search(self, idx):
        if idx == 0:
            for cpu in range(common.get_cpu_count()):
                t = threading.Thread(target=self.worker)
                t.start()
            self.queue.put((0, "*/+"))
        elif len(self.options) > 2:
            self.found_callback(self.options[idx][1])

    def __format_cursor(self, cursor):
        return "%s:%d:%d" % (cursor.location.file.name, cursor.location.line,
           cursor.location.column)

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
            self.cursor = self.__format_cursor(cursor)
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
        common.display_user_selection(self.options, self.quickpanel_extensive_search)

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
            common.run_in_main_thread(lambda: common.status_message(self.status))
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
                    common.run_in_main_thread(lambda: common.status_message("Searching for %s..." % ("implementation" if self.impl else "definition")))
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
                    for i in range(common.get_cpu_count()-1):
                        self.queue.put((1001, "*/+++"))

                    self.queue.put((1010, "*/++"))
                    self.queue.task_done()
                    continue
                elif name == "*/++":
                    common.run_in_main_thread(self.done)
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
                                            common.run_in_main_thread(self.done)
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


