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



import sublime
import ctypes

import Queue as Queue
from internals.clang import cindex
from errormarkers import clear_error_marks, add_error_mark, show_error_marks, \
   update_statusbar, erase_error_marks, clang_error_panel
from internals.common import get_setting, get_settings, \
    get_cpu_count, run_in_main_thread, \
    status_message, sencode, are_we_there_yet, plugin_loaded, \
    get_project_settings
from internals import translationunitcache
from internals.translationunitcache import Language as Language
from internals.translationunitcache import CompileOptions as CompileOptions
from internals.translationunitcache import TranslationUnitCache as TUCache

from internals.parsehelp import parsehelp

import sublime_plugin
from sublime import Region
import sublime
import re
import threading
import time
import traceback
import os
import json
import sys

# todo: what's with the sencode??
def get_filename(view):
    return sencode(view.file_name())

# identify the language inside the file the view displays
def get_language(view):
    language_regex = re.compile("(?<=source\.)[\w+#]+")

    caret = view.sel()[0].a
    language = language_regex.search(view.scope_name(caret))
    if language == None:
        return Language(Language.Other)
    lang = language.group(0).lower()
    #print("LANG IS : " + lang)
    if lang in "c":
        return Language(Language.C)
    elif lang in "c++":
        return Language(Language.CPP)
    elif lang in "objc":
        return Language(Language.ObjC)
    elif lang in "objc++":
        return Language(Language.ObjCPP)

    return Language(Language.Other)


# collect all compilation options based on the view and the file
# the user is currently working on.
# creates a CompileOptions object.
def collect_all_options(view, filename, language):
    assert view is not None
    assert filename is not None
    assert language is not None
    assert language.is_supported()

    # todo: automate this.
    sys_includes = get_setting("system_include_paths", [])

    opt = translationunitcache.CompileOptions(language, sys_includes)

    # This is the bitmask sent to index.parse.
    # For example, to be able to go to the definition of
    # preprocessed macros, set it to 1, for using an implicit
    # precompiled header set it to 4 and for caching completion
    # results, set it to 8. Or all together 1+4+8=13.
    # See http://clang.llvm.org/doxygen/group__CINDEX__TRANSLATION__UNIT.html#gab1e4965c1ebe8e41d71e90203a723fe9
    # and http://clang.llvm.org/doxygen/Index_8h_source.html
    # for more details
    opt.index_parse_type = 13

    language_options = get_setting("language_options", {})
    if language_options.has_key(language.key()):
        opt.language_options = language_options[language.key()]

    project_file, project_options = get_project_settings(filename)
    if project_file != None:
        opt.project_file = project_file
        opt.project_options  = project_options
    return opt

# initialize cache if not done yet.
def get_cache():
    if translationunitcache.tuCache == None:
        number_threads = 4
        translationunitcache.tuCache = translationunitcache.TranslationUnitCache(number_threads)

    return translationunitcache.tuCache

def warm_up_cache(view, filename, language):
    cache = get_cache()
    state = cache.get_status(filename)

    if state == translationunitcache.TranslationUnitCache.STATUS_NOT_IN_CACHE:
        opts = collect_all_options(view, filename, language)
        cache.prepare(filename, opts)

    return state

# process, i.e. compile the given file identified by filename.
# gathers the arguments from project files for compiling.
# returns a translation unit object
def get_translation_unit(view, filename, language, blocking=False):
    cache = get_cache()

    if get_setting("warm_up_in_separate_thread", True) and not blocking:
        stat = warm_up_cache(view, filename, language)
        if stat == translationunitcache.TranslationUnitCache.STATUS_NOT_IN_CACHE:
            return None
        elif stat == translationunitcache.TranslationUnitCache.STATUS_PARSING:
            sublime.status_message("Hold your horses, cache still warming up")
            return None

    opts = collect_all_options(view, filename, language)
    debug = get_setting("debug", False)
    if debug == True:
        print("Compiling: '%s'" % (filename))
        print("Language: '%s'" % (language))
        print("Project File: '%s'" % (opts.project_file))
        print("Options:")
        print(opts)

    return cache.get_translation_unit(filename, opts)

navigation_stack = []
clang_complete_enabled = True


def format_current_file(view):
    row, col = view.rowcol(view.sel()[0].a)
    return "%s:%d:%d" % (sencode(view.file_name()), row + 1, col + 1)


def navi_stack_open(view, target):
    navigation_stack.append((format_current_file(view), target))
    view.window().open_file(target, sublime.ENCODED_POSITION)


class ClangTogglePanel(sublime_plugin.WindowCommand):
    def run(self, **args):
        show = args["show"] if "show" in args else None
        aview = sublime.active_window().active_view()
        error_marks = get_setting("error_marks_on_panel_only", False, aview)

        if show or (show == None and not clang_error_panel.is_visible(self.window)):
            clang_error_panel.open(self.window)
            if error_marks:
                show_error_marks(aview)
        else:
            clang_error_panel.close()
            if error_marks:
                erase_error_marks(aview)


class ClangToggleCompleteEnabled(sublime_plugin.TextCommand):
    def run(self, edit):
        global clang_complete_enabled
        clang_complete_enabled = not clang_complete_enabled
        sublime.status_message("Clang complete is %s" % ("On" if clang_complete_enabled else "Off"))


class ClangWarmupCache(sublime_plugin.TextCommand):
    def run(self, edit):
        view = self.view
        language = get_language(view)
        filename = get_filename(view)

        stat = warm_up_cache(view, filename, language)
        if stat == translationunitcache.TranslationUnitCache.STATUS_PARSING:
            sublime.status_message("Cache is already warming up")
        elif stat != translationunitcache.TranslationUnitCache.STATUS_NOT_IN_CACHE:
            sublime.status_message("Cache is already warmed up")


class ClangGoBackEventListener(sublime_plugin.EventListener):
    def on_close(self, view):
        if not get_setting("pop_on_close", True, view):
            return
        # If the view we just closed was last in the navigation_stack,
        # consider it "popped" from the stack
        fn = view.file_name()
        if fn == None:
            return
        fn = sencode(fn)
        while True:
            if len(navigation_stack) == 0 or \
                    not navigation_stack[
                        len(navigation_stack) - 1][1].startswith(fn):
                break
            navigation_stack.pop()


class ClangGoBack(sublime_plugin.TextCommand):
    def run(self, edit):
        assert len(navigation_stack) > 0

        self.view.window().open_file(
            navigation_stack.pop()[0], sublime.ENCODED_POSITION)

    def is_enabled(self):
        if len(navigation_stack) == 0:
            return False
        view = sublime.active_window().active_view()
        lang = get_language(view)
        if lang.is_supported() == False:
            return False

        return True

    def is_visible(self):
        return self.is_enabled()


class ClangGotoBase(sublime_plugin.TextCommand):
    def get_target(self, tu, data, offset, found_callback, folders):
        pass

    def found_callback(self, target):
        if target == None:
            sublime.status_message("Don't know where the %s is!" % self.goto_type)
        elif not isinstance(target, list):
            navi_stack_open(self.view, target)
        else:
            self.targets = target
            self.view.window().show_quick_panel(target, self.open_file)

    def open_file(self, idx):
        if idx >= 0:
            target = self.targets[idx]
            if isinstance(target, list):
                target = target[1]
            navi_stack_open(self.view, target)

    def run(self, edit):
        view = self.view
        filename = get_filename(view)
        language = get_language(view)
        tu = get_translation_unit(view, filename, language)
        if tu == None:
            return

        offset = view.sel()[0].a
        data = view.substr(sublime.Region(0, view.size()))
        self.get_target(tu, data, offset, self.found_callback, self.view.window().folders())


    def is_enabled(self):
        return True

    def is_visible(self):
        view = sublime.active_window().active_view()
        lang = get_language(view)
        return lang.is_supported()


class ClangGotoDefinition(ClangGotoBase):
    def get_target(self, tu, data, offset, found_callback, folders):
        self.goto_type = "definition"
        return tu.find_definition(data, offset, found_callback, folders)


class ClangGotoDeclaration(ClangGotoBase):
    def get_target(self, tu, data, offset, found_callback, folders):
        self.goto_type = "declaration"
        return tu.find_declaration(data, offset, found_callback, folders)


class ClangClearCache(sublime_plugin.TextCommand):
    def run(self, edit):
        if translationunitcache.tuCache is None:
            return
        translationunitcache.tuCache.clear()
        sublime.status_message("Cache cleared!")


def suppress_based_on_location(source_file):
    suppress_dirs = get_setting("diagnostic_suppress_dirs", [])
    for d in suppress_dirs:
        if source_file in d:
            return True
    return False

def suppress_based_on_match(message):
    suppress_strings = get_setting("diagnostic_suppress_match", [])
    for suppress in suppress_strings:
        if suppress in message:
            return True
    return False


def display_compilation_results(view):
    filename = get_filename(view)
    language = get_language(view)

    # todo: this can be None if warm_up_in_separate_thread is true.
    # fix this somehow?

    tu = get_translation_unit(view, filename, language)
    assert tu is not None

    clear_error_marks()  # clear visual error marks
    erase_error_marks(view)

    errString    = ""
    errorCount   = 0
    warningCount = 0
    diagnostics  = tu.get_diagnostics()

    for diagnostic in diagnostics:
        source   = diagnostic.filename
        name     = diagnostic.name
        line     = diagnostic.line
        col      = diagnostic.column
        spelling = diagnostic.spelling

        if diagnostic.is_fatal():
            if "not found" in spelling:
                message = "Did you configure the include path used by clang properly?\n" \
                "See http://github.com/ensisoft/SublimeClang for more details on how to configure SublimeClang."
                errString = "%s" % (message)
                message = "%s:%d,%d - %s - %s" % (source, line, col, name, spelling)
                errString = "%s\n%s" % (errString, message)
                break

        if suppress_based_on_location(source):
            continue
        elif suppress_based_on_match(spelling):
            continue

        message = "%s:%d,%d - %s - %s" % (source, line, col, name, spelling)
        if diagnostic.can_ignore():
            if diagnostic.has_suppression():
                disable_flag = diagnostic.disable_flag
                message = "%s [Disable with %s]" % (message, disable_flag)

        errString = "%s%s\n" % (errString, message)
        if diagnostic.is_warning():
            warningCount += 1
        elif diagnostic.is_error():
            errorCount += 1

        add_error_mark(name, source, line - 1, spelling)

    if errorCount > 0 or warningCount > 0:
        statusString = "Clang Status: "
        if errorCount > 0:
            statusString = "%s%d Error%s" % (statusString, errorCount, "s" if errorCount != 1 else "")
        if warningCount > 0:
            statusString = "%s%s%d Warning%s" % (statusString, ", " if errorCount > 0 else "",
                                                 warningCount, "s" if warningCount != 1 else "")
        view.set_status("SublimeClang", statusString)
    else:
        view.erase_status("SublimeClang")

    window = view.window()
    if not window is None:
        show_panel = errString
        window.run_command("clang_toggle_panel", {"show": show_panel})

    clang_error_panel.set_data(errString)
    update_statusbar(view)

    show_error_marks(view)


def is_member_completion(view, caret):
    regex = re.compile(r"(([a-zA-Z_]+[0-9_]*)|([\)\]])+)((\.)|(->))$")
    line = view.substr(Region(view.line(caret).a, caret))
    lang = get_language(view)
    if regex.search(line) != None:
        return True
    elif lang.is_objective_family():
        return re.search(r"\[[\.\->\s\w\]]+\s+$", line) != None
    return False


class ClangComplete(sublime_plugin.TextCommand):
    def run(self, edit, characters):
        regions = [a for a in self.view.sel()]
        self.view.sel().clear()
        for region in reversed(regions):
            pos = 0
            region.end() + len(characters)
            if region.size() > 0:
                self.view.replace(edit, region, characters)
                pos = region.begin() + len(characters)
            else:
                self.view.insert(edit, region.end(), characters)
                pos = region.end() + len(characters)

            self.view.sel().add(sublime.Region(pos, pos))
        caret = self.view.sel()[0].begin()
        line = self.view.substr(sublime.Region(self.view.word(caret-1).a, caret))
        if is_member_completion(self.view, caret) or line.endswith("::") or re.search("(^|\W)new\s+\w*$", line):
            self.view.run_command("hide_auto_complete")
            sublime.set_timeout(self.delayed_complete, 1)

    def delayed_complete(self):
        self.view.run_command("auto_complete")


class SublimeClangAutoComplete(sublime_plugin.EventListener):
    def __init__(self):
        plugin_settings = get_settings()
        plugin_settings.clear_on_change("options")
        plugin_settings.add_on_change("options", self.clear_cache)
        plugin_settings.add_on_change("options", self.load_settings)

        # wtf is this?
        are_we_there_yet(lambda: self.load_settings())
        self.compile_timer = None
        self.load_settings()
        self.not_code_regex = re.compile("(string.)|(comment.)")

    def clear_cache(self):
        if translationunitcache.tuCache is None:
            return
        translationunitcache.tuCache.clear()

    def load_settings(self):
        self.recompile_delay = get_setting("recompile_delay", 0)
        self.cache_on_load = get_setting("cache_on_load", True)
        self.not_code_regex = re.compile("(string.)|(comment.)")
        self.remove_on_close = get_setting("remove_on_close", True)
        self.recompile_delay = get_setting("recompile_delay", 1000)
        self.cache_on_load = get_setting("cache_on_load", True)
        self.remove_on_close = get_setting("remove_on_close", True)
        self.reparse_on_save  = get_setting("reparse_on_save", True)
        self.reparse_on_focus = get_setting("reparse_on_focus", True)
        self.reparse_on_edit = get_setting("reparse_on_edit", False)

        self.dont_complete_startswith = ['operator', '~']


    def is_enabled(self, view):
        if get_setting("enabled", view, True) == False:
            return False
        elif clang_complete_enabled == False:
            return False

        return True

    def is_member_kind(self, kind):
        return  kind == cindex.CursorKind.CXX_METHOD or \
                kind == cindex.CursorKind.FIELD_DECL or \
                kind == cindex.CursorKind.OBJC_PROPERTY_DECL or \
                kind == cindex.CursorKind.OBJC_CLASS_METHOD_DECL or \
                kind == cindex.CursorKind.OBJC_INSTANCE_METHOD_DECL or \
                kind == cindex.CursorKind.OBJC_IVAR_DECL or \
                kind == cindex.CursorKind.FUNCTION_TEMPLATE or \
                kind == cindex.CursorKind.NOT_IMPLEMENTED

    def return_completions(self, comp, view):
        if get_setting("inhibit_sublime_completions", True, view):
            return (comp, sublime.INHIBIT_WORD_COMPLETIONS | sublime.INHIBIT_EXPLICIT_COMPLETIONS)
        return comp

    def on_query_completions(self, view, prefix, locations):
        if self.is_enabled(view) == False:
            return self.return_completions([], view)
        if clang_complete_enabled == False:
            return self.return_completions([], view)
        language = get_language(view)
        if language.is_supported == False:
            return self.return_completions([], view)

        # what's this??
        if not view.match_selector(locations[0], '-string -comment -constant'):
            return self.return_completions([], view)

        line = view.substr(sublime.Region(view.line(locations[0]).begin(), locations[0]))
        match = re.search(r"[,\s]*(\w+)\s+\w+$", line)
        if match != None:
            valid = ["new", "delete", "return", "goto", "case", "const", "static", "class", "struct", "typedef", "union"]
            if match.group(1) not in valid:
                # Probably a variable or function declaration
                # There's no point in trying to complete
                # a name that hasn't been typed yet...
                return self.return_completions([], view)

        filename = get_filename(view)

        tu = get_translation_unit(view, filename, language)
        assert tu is not None

        data = view.substr(sublime.Region(0, locations[0]))

        results = None
        results = tu.complete(data, prefix)

        if results == None:
            row, col = view.rowcol(locations[0] - len(prefix))
            unsaved_files = []
            # todo fix this
            #if view.is_dirty():
            #    unsaved_files.append((sencode(view.file_name()),
            #      view.substr(Region(0, view.size()))))
            #    results = tu.cache.clangcomplete(sencode(view.file_name()), row+1, col+1, unsaved_files, is_member_completion(view, locations[0] - len(prefix)))

        if len(self.dont_complete_startswith) and results:
            i = 0
            while i < len(results):
                disp = results[i][0]
                pop = False
                for comp in self.dont_complete_startswith:
                    if disp.startswith(comp):
                        pop = True
                        break

                if pop:
                    results.pop(i)
                else:
                    i += 1

        if not results is None:
            return self.return_completions(results, view)
        return self.return_completions([], view)

    def reparse_done(self):
        display_compilation_results(self.view)

    def start_recompile_timer(self, timeout):
        if self.compile_timer != None:
            self.compile_timer.cancel()
            self.compile_timer = None

        # schedule recompile
        self.compile_timer = threading.Timer(timeout, sublime.set_timeout,
                                               [self.recompile, 0])
        self.compile_timer.start()


    def recompile(self):
        view = self.view
        unsaved_files = []
        # todo: fix this
        #if view.is_dirty() and get_setting("reparse_use_dirty_buffer", False, view):
        #    unsaved_files.append((sencode(view.file_name()),
        #                          view.substr(Region(0, view.size()))))

        filename = get_filename(view)
        language = get_language(view)

        cache = get_cache()
        opts  = collect_all_options(view, filename, language)

        if cache.reparse(filename, opts, unsaved_files, self.reparse_done) == False:
            self.start_recompile_timer(1) # Already parsing so retry in a bit

    def on_activated(self, view):
        if self.is_enabled(view) == False:
            return

        if self.reparse_on_focus == False:
            return
        lang = get_language(view)
        if lang.is_supported() == False:
            return

        self.view = view
        self.start_recompile_timer(0.1)

    def on_post_save(self, view):
        if self.is_enabled(view) == False:
            return

        if self.reparse_on_save == False:
            return
        lang = get_language(view)
        if lang.is_supported() == False:
            return

        #print("on_post_save")


        self.view = view
        self.start_recompile_timer(0.1)

    def on_modified(self, view):
        if self.is_enabled(view) == False:
            return

        if self.reparse_on_edit == False:
            return

        lang = get_language(view)
        if lang.is_supported() == False:
            return

        #print("on_modified")

        self.view = view
        self.start_recompile_timer(1.0)

    def on_load(self, view):
        if self.is_enabled(view) == False:
            return

        if self.cache_on_load == False:
            return
        lang = get_language(view)
        if lang.is_supported() == False:
            return

        source = get_filename(view)

        warm_up_cache(view, source, lang)

    def on_close(self, view):
        if self.remove_on_close == False:
            return
        lang = get_language(view)
        if lang.is_supported() == False:
            return

        filename = get_filename(view)
        translationunitcache.tuCache.remove(filename)

    def on_query_context(self, view, key, operator, operand, match_all):
        if key == "clang_supported_language":
            if view == None:
                view = sublime.active_window().active_view()
            lang = get_language(view)
            return lang.is_supported()
        elif key == "clang_is_code":
            return self.not_code_regex.search(view.scope_name(view.sel()[0].begin())) == None
        elif key == "clang_complete_enabled":
            return clang_complete_enabled
        elif key == "clang_automatic_completion_popup":
            return True
        elif key == "clang_panel_visible":
            return clang_error_panel.is_visible()
