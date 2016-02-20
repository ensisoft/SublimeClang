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

from clang import cindex
from common import *
from translationunit import TranslationUnit
import Queue
import time
import shlex
import subprocess
import sys

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

    def is_objective_family(self):
        if self.value == Language.ObjC:
            return True
        elif self.value == Language.ObjCPP:
            return True
        return False


class CompileOptions(object):
    def __init__(self, lang, sys_includes):
        assert lang is not None
        assert lang.is_supported()
        assert sys_includes is not None

        self.index_parse_type = 13
        self.system_includes  = sys_includes
        self.language_options = None # array
        self.project_options  = None # array
        self.project_file     = ""
        self.language         = lang


    def __str__(self):
        assert self.system_includes is not None

        s = ""
        for sys in self.system_includes:
            s = s + '-isystem ' + sys
            s = s + '\n'

        if self.language_options is not None:
            s = s + '\n'.join(self.language_options)
            s = s + "\n"

        if self.project_options is not None:
            s = s + '\n'.join(self.project_options)
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
            opts = opts + self.language_options
        if self.project_options is not None:
            opts = opts + self.project_options
        return opts


class TranslationUnitCache(Worker):
    STATUS_PARSING      = 1
    STATUS_REPARSING    = 2
    STATUS_READY        = 3
    STATUS_NOT_IN_CACHE = 4

    def __init__(self, num_threads):
        self.as_super = super(TranslationUnitCache, self)
        self.as_super.__init__(num_threads)
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

            # todo refactor this
            #searchcache.clear()
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

            tu = TranslationUnit(blob, filename, opts)
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
