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

from clang import cindex
from ctypes import cdll, Structure, POINTER, c_char_p, c_void_p, c_uint, c_bool
from common import *
from parsehelp import *
# brain damaged circular imports...
#from extensivesearch import ExtensiveSearch
import re

def get_cache_library(arch):
    import platform
    import sys
    filename = ''
    platform = platform.system()
    if platform == 'Windows':
        if arch == 'x64':
            filename = 'win64\\libcache.dll'
        elif arch == 'x32':
            filename = 'win32\\libcache.dll'
        else:
            raise Error("Unsupported architecture")
    elif platform == 'Linux':
        filename = 'libcache.so'
    else:
        raise Error("Unsupported Operating System")
    
    return filename


class CacheEntry(Structure):
    _fields_ = [("cursor", cindex.Cursor), ("raw_insert", c_char_p), ("raw_display", c_char_p), ("access", c_uint), ("static", c_bool), ("baseclass", c_bool)]
    @property
    def insert(self):
        return bdecode(self.raw_insert)

    @property
    def display(self):
        return bdecode(self.raw_display)

class _Cache(Structure):
    def __del__(self):
        _deleteCache(self)

class CacheCompletionResults(Structure):
    @property
    def length(self):
        return self.__len__()

    def __len__(self):
        return completionResults_length(self)

    def __getitem__(self, key):
        if key >= self.length:
            raise IndexError
        return completionResults_getEntry(self, key)[0]

    def __del__(self):
        completionResults_dispose(self)

cachelib                   = None
_createCache               = None
_deleteCache               = None
cache_completeNamespace    = None
cache_complete_startswith  = None
completionResults_length   = None
completionResults_getEntry = None
completionResults_dispose  = None
cache_findType             = None
cache_completeCursor       = None
cache_clangComplete        = None

def init_cache_lib(libname):
    global cachelib
    global _createCache
    global _deleteCache
    global cache_completeNamespace
    global cache_complete_startswith
    global completionResults_length
    global completionResults_getEntry
    global completionResults_dispose
    global cache_findType
    global cache_completeCursor
    global cache_clangComplete

    assert cachelib == None
    assert libname != None

    cachelib = cdll.LoadLibrary(libname)
    _createCache = cachelib.createCache
    _createCache.restype = POINTER(_Cache)
    _createCache.argtypes = [cindex.Cursor]
    _deleteCache = cachelib.deleteCache
    _deleteCache.argtypes = [POINTER(_Cache)]
    cache_completeNamespace = cachelib.cache_completeNamespace
    cache_completeNamespace.argtypes = [POINTER(_Cache), POINTER(c_char_p), c_uint]
    cache_completeNamespace.restype = POINTER(CacheCompletionResults)
    cache_complete_startswith = cachelib.cache_complete_startswith
    cache_complete_startswith.argtypes = [POINTER(_Cache), c_char_p]
    cache_complete_startswith.restype = POINTER(CacheCompletionResults)
    completionResults_length = cachelib.completionResults_length
    completionResults_length.argtypes = [POINTER(CacheCompletionResults)]
    completionResults_length.restype = c_uint
    completionResults_getEntry = cachelib.completionResults_getEntry
    completionResults_getEntry.argtypes = [POINTER(CacheCompletionResults)]
    completionResults_getEntry.restype = POINTER(CacheEntry)
    completionResults_dispose = cachelib.completionResults_dispose
    completionResults_dispose.argtypes = [POINTER(CacheCompletionResults)]
    cache_findType = cachelib.cache_findType
    cache_findType.argtypes = [POINTER(_Cache), POINTER(c_char_p), c_uint, c_char_p]
    cache_findType.restype = cindex.Cursor
    cache_completeCursor = cachelib.cache_completeCursor
    cache_completeCursor.argtypes = [POINTER(_Cache), cindex.Cursor]
    cache_completeCursor.restype = POINTER(CacheCompletionResults)
    cache_clangComplete = cachelib.cache_clangComplete
    cache_clangComplete.argtypes = [POINTER(_Cache), c_char_p, c_uint, c_uint, POINTER(cindex._CXUnsavedFile), c_uint, c_bool]
    cache_clangComplete.restype = POINTER(CacheCompletionResults)


def remove_duplicates(data):
    if data == None:
        return None
    seen = {}
    ret = []
    for d in data:
        if d in seen:
            continue
        seen[d] = 1
        ret.append(d)
    return ret

class Diagnostic(object):
    Ignored = 0
    Note    = 1
    Warning = 2
    Error   = 3
    Fatal   = 4

    def __init__(self, severity, line, column, spelling, filename):
        self.value_    = severity
        self.line_     = line
        self.column_   = column
        self.spelling_ = spelling
        self.filename_ = filename
        self.disable_flag_ = ""


    @property
    def name(self):
        if self.value == Diagnostic.Ignored:
            return "Ignored"
        elif self.value == Diagnostic.Note:
            return "Note"
        elif self.value == Diagnostic.Warning:
            return "Warning"
        elif self.value == Diagnostic.Error:
            return "Error"
        elif self.value == Diagnostic.Fatal:
            return "Fatal"
        assert False

    @property
    def line(self):
        return self.line_

    @property
    def column(self):
        return self.column_

    @property
    def spelling(self):
        return self.spelling_

    @property
    def filename(self):
        return self.filename_

    def disable_flag(self):
        return self.disable_flag_

    @property
    def value(self):
        return self.value_

    def has_suppression(self):
        return len(self.disable_flag_) > 0

    def can_ignore(self):
        return self.value_ <= Diagnostic.Warning

    def is_fatal(self):
        return self.value_ == Diagnostic.Fatal

    def is_warning(self):
        return self.value_ == Diagnostic.Warning

    def is_error(self):
        return self.value_ == Diagnostic.Error


# represents the result of a SourceFile compilation
class TranslationUnit(object):
    def __init__(self, tu, filename, opts):
        self.lock = threading.Lock()
        self.tu = tu
        self.cache = _createCache(tu.cursor)[0]
        self.filename = filename
        self.opts     = opts # compile options

    def __del__(self):
        self.tu = None
        self.cache = None

    def __format_cursor(self, cursor):
        assert cursor != None
        return "%s:%d:%d" % (cursor.location.file.name, cursor.location.line,
           cursor.location.column)

    def __get_cursor_spelling(self, cursor):
        cursor_spelling = None
        assert cursor != None
        cursor_spelling = cursor.spelling or cursor.displayname
        cursor_spelling = re.sub(r"^(enum\s+|(class|struct)\s+(\w+::)*)", "", cursor_spelling)
        return cursor_spelling

    def __get_native_namespace(self, namespace):
        nsarg = (c_char_p*len(namespace))()
        for i in range(len(namespace)):
            nsarg[i] = bencode(namespace[i])
        return nsarg

    def __complete_namespace(self, namespace):
        ret = None
        if len(namespace):
            nsarg = self.__get_native_namespace(namespace)
            comp = cache_completeNamespace(self.cache, nsarg, len(nsarg))
            if comp:
                ret = [(x.display, x.insert) for x in comp[0]]
        return ret

    def __get_namespace_from_cursor(self, cursor):
        namespace = []
        while cursor != None and cursor.kind == cindex.CursorKind.NAMESPACE:
            namespace.insert(0, cursor.displayname)
            cursor = cursor.lexical_parent
        return namespace

    def __find_type(self, data, typename):
        extra = None
        idx = typename.rfind("::")
        if idx != -1:
            extra = typename[:idx]
            typename = typename[idx+2:]
        if "<" in typename:
            typename = typename[:typename.find("<")]
        namespaces = parsehelp.extract_used_namespaces(data)
        namespaces.insert(0, None)
        namespaces.insert(1, parsehelp.extract_namespace(data))
        cursor = None
        for ns in namespaces:
            nsarg = None
            nslen = 0
            if extra:
                if ns:
                    ns = ns + "::" + extra
                else:
                    ns = extra
            if ns:
                nsarg = self.__get_native_namespace(ns.split("::"))
                nslen = len(nsarg)
            cursor = cache_findType(self.cache, nsarg, nslen, bencode(typename))
            if cursor != None:
                assert self.tu != None
                cursor._tu = self.tu

            if cursor != None and not cursor.kind.is_invalid():
                if cursor.kind.is_reference():
                    cursor = cursor.referenced
                break

        if (cursor != None and not cursor.kind.is_invalid()) or idx == -1:
            return cursor

        # Maybe it's a subtype?
        parent = self.__find_type(data, extra)
        if parent != None and not parent.kind.is_invalid():
            for child in parent.get_children():
                if child.kind.is_declaration() and child.spelling == typename:
                    return child
        return None

    def __solve_template_from_cursor(self, temp, member, template):
        found = False
        children = []
        for child in member.get_children():
            if not found:
                ref = child.referenced
                if ref != None and ref == temp:
                    found = True
                continue
            if child.kind == cindex.CursorKind.TEMPLATE_REF:
                # Don't support nested templates for now
                children = []
                break
            elif child.kind == cindex.CursorKind.TYPE_REF:
                children.append((child.get_resolved_cursor(), None))
        return temp, children

    def __solve_member(self, data, typecursor, member, template):
        temp = None
        pointer = 0
        if member != None and not member.kind.is_invalid():
            temp = member.get_returned_cursor()
            pointer = member.get_returned_pointer_level()

            if temp != None and not temp.kind.is_invalid():
                if temp.kind == cindex.CursorKind.TEMPLATE_TYPE_PARAMETER:
                    off = 0
                    for child in typecursor.get_children():
                        if child.kind == cindex.CursorKind.TEMPLATE_TYPE_PARAMETER:
                            if child == temp:
                                break
                            off += 1
                    if template[1] and off < len(template[1]):
                        template = template[1][off]
                        if isinstance(template[0], cindex.Cursor):
                            temp = template[0]
                        else:
                            temp = self.__find_type(data, template[0])
                elif temp.kind == cindex.CursorKind.CLASS_TEMPLATE:
                    template = self.solve_template_from_cursor(temp, member, template)

        return temp, template, pointer

    def __inherits(self, parent, child):
        if child == None or child.kind.is_invalid():
            return False
        if parent == child:
            return True
        for c in child.get_children():
            if c.kind == cindex.CursorKind.CXX_BASE_SPECIFIER:
                for c2 in c.get_children():
                    if c2.kind == cindex.CursorKind.TYPE_REF:
                        c2 = c2.referenced
                        return self.__inherits(parent, c2)
        return False

    def __filter(self, ret, constr=False):
        if ret == None:
            return None
        if constr:
            match = "\t(namespace|constructor|class|typedef|struct)$"
        else:
            match = "\t(?!constructor)[^\t]+$"
        regex = re.compile(match)
        ret2 = []
        constrs = []
        for display, insert in ret:
            if not regex.search(display):
                continue
            if constr and display.endswith("constructor"):
                constrs.append(display[:display.find("(")])
            ret2.append((display, insert))
        if constr:
            for name in constrs:
                regex = re.compile(r"%s\t(class|typedef|struct)$" % name)
                ret2 = list(filter(lambda a: not regex.search(a[0]), ret2))
        return ret2


    def __complete_code(self, data, prefix):
        line = parsehelp.extract_line_at_offset(data, len(data)-1)
        before = line
        if len(prefix) > 0:
            before = line[:-len(prefix)]

        ret = None
        if re.search(r"::$", before):
            constr = re.search(r"(\W|^)new\s+(\w+::)+$", before) != None

            ret = []
            match = re.search(r"([^\(\s,]+::)+$", before)
            if match == None:
                ret = None
                cached_results = cache_complete_startswith(self.cache, bencode(prefix))
                if cached_results:
                    ret = []
                    for x in cached_results[0]:
                        x.cursor._tu = self.tu
                        if x.cursor.kind != cindex.CursorKind.MACRO_DEFINITION and \
                                x.cursor.kind != cindex.CursorKind.CXX_METHOD:
                            ret.append((x.display, x.insert))
                return ret
            before = match.group(1)
            namespace = before.split("::")
            namespace.pop()  # the last item is going to be "prefix"
            ret = self.__complete_namespace(namespace)

            if len(ret) == 0:
                typename = "::".join(namespace)
                c = self.__find_type(data, typename)
                if c != None:
                    if c.kind == cindex.CursorKind.ENUM_DECL:
                        # It's not valid to complete enum::
                        c = None
                if c != None and not c.kind.is_invalid() and c.kind != cindex.CursorKind.NAMESPACE:
                    # It's going to be a declaration of some kind, so
                    # get the returned cursor
                    c = c.get_returned_cursor()
                    if c != None and c.kind == cindex.CursorKind.TYPEDEF_DECL:
                        # Too complex typedef to be able to complete, fall back to slow completions
                        c = None
                        ret = None
                if c != None and not c.kind.is_invalid():
                    if c.kind == cindex.CursorKind.NAMESPACE:
                        namespace = self.__get_namespace_from_cursor(c)
                        return self.__complete_namespace(namespace)
                    comp = cache_completeCursor(self.cache, c)

                    if comp:
                        inherits = False
                        clazz = parsehelp.extract_class_from_function(data)
                        if clazz == None:
                            clazz = parsehelp.extract_class(data)
                        if clazz != None:
                            c2 = self.__find_type(data, clazz)
                            inherits = self.__inherits(c, c2)

                        selfcompletion = clazz == c.spelling

                        for c in comp[0]:
                            assert self.tu != None
                            c.cursor._tu = self.tu
                            if (selfcompletion and not c.baseclass) or \
                                    (inherits and not c.access == cindex.CXXAccessSpecifier.PRIVATE) or \
                                    (c.access == cindex.CXXAccessSpecifier.PUBLIC and \
                                     (
                                        c.static or \
                                        c.cursor.kind == cindex.CursorKind.TYPEDEF_DECL or \
                                        c.cursor.kind == cindex.CursorKind.CLASS_DECL or \
                                        c.cursor.kind == cindex.CursorKind.STRUCT_DECL or \
                                        c.cursor.kind == cindex.CursorKind.ENUM_CONSTANT_DECL or \
                                        c.cursor.kind == cindex.CursorKind.ENUM_DECL)):
                                ret.append((c.display, c.insert))
            ret = self.__filter(ret, constr)
            return ret
        elif re.search(r"(\w+\]+\s+$|\[[\w\.\-\>]+\s+$|([^ \t]+)(\.|\->)$)", before):
            comp = data
            if len(prefix) > 0:
                comp = data[:-len(prefix)]
            typedef = parsehelp.get_type_definition(comp)
            if typedef == None:
                return None
            line, column, typename, var, tocomplete = typedef
            if typename == None:
                return None
            cursor = None
            template = parsehelp.solve_template(parsehelp.get_base_type(typename))
            pointer = parsehelp.get_pointer_level(typename)
            if var == "this":
                pointer = 1

            if var != None:
                if line > 0 and column > 0:
                    cursor = cindex.Cursor.get(self.tu, self.filename, line, column)
                if cursor == None or cursor.kind.is_invalid() or cursor.spelling != var:
                    cursor = self.__find_type(data, template[0])
                else:
                    pointer = 0  # get the pointer level from the cursor instead
                if cursor != None and not cursor.kind.is_invalid() and \
                        cursor.spelling == typename and \
                        cursor.kind == cindex.CursorKind.VAR_DECL:
                    # We're trying to use a variable as a type.. This isn't valid
                    cursor = None
                    ret = []
                if cursor != None and not cursor.kind.is_invalid():
                    # It's going to be a declaration of some kind, so
                    # get the returned cursor
                    pointer += cursor.get_returned_pointer_level()
                    cursor = cursor.get_returned_cursor()
                    if cursor == None:
                        ret = []
            else:
                # Probably a member of the current class
                clazz = parsehelp.extract_class_from_function(data)
                if clazz == None:
                    clazz = parsehelp.extract_class(data)
                if clazz != None:
                    cursor = self.__find_type(data, clazz)
                    if cursor != None and not cursor.kind.is_invalid():
                        func = False
                        if typename.endswith("()"):
                            func = True
                            typename = typename[:-2]
                        member = cursor.get_member(typename, func)
                        cursor, template, pointer = self.__solve_member(data, cursor, member, template)
                        if member != None and (cursor == None or cursor.kind.is_invalid()):
                            ret = []
                if cursor == None or cursor.kind.is_invalid():
                    # Is it by any chance a struct variable or an ObjC class?
                    cursor = self.__find_type(data, template[0])
                    if cursor == None or cursor.kind.is_invalid() or \
                            cursor.spelling != typename or \
                            (not tocomplete.startswith("::") and \
                                cursor.kind != cindex.CursorKind.VAR_DECL and \
                                cursor.kind != cindex.CursorKind.OBJC_INTERFACE_DECL) or \
                            (tocomplete.startswith("::") and \
                                not (cursor.kind == cindex.CursorKind.CLASS_DECL or \
                                     cursor.kind == cindex.CursorKind.STRUCT_DECL or \
                                     cursor.kind == cindex.CursorKind.OBJC_INTERFACE_DECL or \
                                     cursor.kind == cindex.CursorKind.CLASS_TEMPLATE)):
                        cursor = None
                    if cursor != None and not cursor.kind.is_invalid():
                        # It's going to be a declaration of some kind, so
                        # get the returned cursor
                        pointer = cursor.get_returned_pointer_level()
                        cursor = cursor.get_returned_cursor()
                        if cursor == None:
                            ret = []
                if cursor == None or cursor.kind.is_invalid():
                    # Is it a non-member function?
                    func = False
                    if typename.endswith("()"):
                        func = True
                        typename = typename[:-2]
                    cached_results = cache_complete_startswith(self.cache, bencode(typename))
                    if cached_results:
                        for x in cached_results[0]:
                            x.cursor._tu = self.tu
                            if x.cursor.spelling == typename:
                                if x.cursor.kind == cindex.CursorKind.VAR_DECL or \
                                        x.cursor.kind == cindex.CursorKind.FUNCTION_DECL:
                                    cursor = x.cursor
                                    pointer = cursor.get_returned_pointer_level()
                                    cursor = cursor.get_returned_cursor()
                                    if cursor == None:
                                        ret = []
                                    break

            if cursor != None and not cursor.kind.is_invalid():
                r = cursor
                m2 = None
                count = 0
                while len(tocomplete) and count < 10:
                    if r == None or \
                            not (r.kind == cindex.CursorKind.CLASS_DECL or \
                            r.kind == cindex.CursorKind.STRUCT_DECL or \
                            r.kind == cindex.CursorKind.UNION_DECL or \
                            r.kind == cindex.CursorKind.OBJC_INTERFACE_DECL or \
                            r.kind == cindex.CursorKind.CLASS_TEMPLATE):
                        if r != None and not (r.kind == cindex.CursorKind.TEMPLATE_TYPE_PARAMETER or \
                                             (r.kind == cindex.CursorKind.TYPEDEF_DECL and len(r.get_children()))):
                            ret = []
                        r = None
                        break
                    count += 1
                    match = re.search(r"^([^\.\-\(:\[\]]+)?(\[\]|\(|\.|->|::)(.*)", tocomplete)
                    if match == None:
                        # probably Objective C code
                        match = re.search(r"^(\S+)?(\s+)(.*)", tocomplete)
                        if match == None:
                            break

                    if r.kind == cindex.CursorKind.OBJC_INTERFACE_DECL:
                        pointer = 0
                    tocomplete = match.group(3)
                    count = 1
                    function = False
                    if match.group(2) == "(":
                        function = True
                        tocomplete = tocomplete[1:]

                    left = re.match(r"(\.|\->|::)?(.*)", tocomplete)
                    tocomplete = left.group(2)
                    if left.group(1) != None:
                        tocomplete = left.group(1) + tocomplete
                    nextm2 = match.group(2)

                    if match.group(1) == None and pointer == 0 and r.kind != cindex.CursorKind.OBJC_INTERFACE_DECL:
                        if match.group(2) == "->":
                            comp = r.get_member("operator->", True)
                            r, template, pointer = self.__solve_member(data, r, comp, template)
                            if pointer > 0:
                                pointer -= 1
                            if comp == None or comp.kind.is_invalid():
                                ret = []
                        elif match.group(2) == "[]":
                            # TODO: different index types?
                            comp = r.get_member("operator[]", True)
                            r, template, pointer = self.__solve_member(data, r, comp, template)
                            if comp == None or comp.kind.is_invalid():
                                ret = []
                    elif match.group(1) == None and pointer > 0:
                        if (nextm2 == "->" or nextm2 == "[]"):
                            pointer -= 1
                        elif nextm2 == ".":
                            # Trying to dot-complete a pointer, this is invalid
                            # so there can be no completions
                            ret = []
                            r = None
                            break

                    if match.group(1):
                        member = match.group(1)
                        if "[" in member:
                            member = parsehelp.get_base_type(member)
                        if "]" in member:
                            member = member[:member.find("]")]
                        if m2 == " ":
                            function = True
                        member = r.get_member(member, function)
                        r, template, pointer = self.__solve_member(data, r, member, template)
                        if r == None and member != None:
                            # This can't be completed as a cursor object isn't returned
                            # from this member
                            ret = []
                        if match.group(2) != "(":
                            tocomplete = match.group(2) + tocomplete
                    m2 = nextm2

                if r != None and not r.kind.is_invalid() and (pointer == 0 or r.kind == cindex.CursorKind.OBJC_INTERFACE_DECL):
                    clazz = parsehelp.extract_class_from_function(data)
                    if clazz == None:
                        clazz = parsehelp.extract_class(data)
                    selfcompletion = clazz == r.spelling
                    comp = cache_completeCursor(self.cache, r)
                    replaces = []
                    if template[1] != None:
                        tempnames = []
                        for child in r.get_children():
                            if child.kind == cindex.CursorKind.TEMPLATE_TYPE_PARAMETER:
                                tempnames.append(child.spelling)
                        count = min(len(template[1]), len(tempnames))
                        for i in range(count):
                            s = template[1][i][0]
                            if isinstance(s, cindex.Cursor):
                                s = s.spelling
                            replaces.append((r"(^|,|\(|\d:|\s+)(%s)($|,|\s+|\))" % tempnames[i], r"\1%s\3" % s))
                    if comp:
                        ret = []
                        if r.kind == cindex.CursorKind.OBJC_INTERFACE_DECL:
                            isStatic = var == None
                            if m2 == ".":
                                for c in comp[0]:
                                    assert self.tu != None
                                    c.cursor._tu = self.tu
                                    add = True
                                    if c.cursor.kind == cindex.CursorKind.OBJC_IVAR_DECL:
                                        continue
                                    for child in c.cursor.get_children():
                                        if child.kind == cindex.CursorKind.PARM_DECL:
                                            add = False
                                            break
                                    if add:
                                        ret.append((c.display, c.insert))
                            elif m2 == "->":
                                for c in comp[0]:
                                    if c.cursor.kind != cindex.CursorKind.OBJC_IVAR_DECL:
                                        continue
                                    ret.append((c.display, c.insert))
                            else:
                                for c in comp[0]:
                                    if c.static == isStatic and c.cursor.kind != cindex.CursorKind.OBJC_IVAR_DECL:
                                        ret.append((c.display, c.insert))
                        else:
                            for c in comp[0]:
                                if not c.static and c.cursor.kind != cindex.CursorKind.ENUM_CONSTANT_DECL and \
                                        c.cursor.kind != cindex.CursorKind.ENUM_DECL and \
                                        c.cursor.kind != cindex.CursorKind.TYPEDEF_DECL and \
                                        c.cursor.kind != cindex.CursorKind.CLASS_DECL and \
                                        c.cursor.kind != cindex.CursorKind.STRUCT_DECL and \
                                        c.cursor.kind != cindex.CursorKind.CLASS_TEMPLATE and \
                                        (c.access == cindex.CXXAccessSpecifier.PUBLIC or \
                                            (selfcompletion and not (c.baseclass and c.access == cindex.CXXAccessSpecifier.PRIVATE))):
                                    disp = c.display
                                    ins = c.insert
                                    for r in replaces:
                                        disp = re.sub(r[0], r[1], disp)
                                        ins = re.sub(r[0], r[1], ins)
                                    add = (disp, ins)
                                    ret.append(add)
            ret = self.__filter(ret)
            return remove_duplicates(ret)
        else:
            constr = re.search(r"(^|\W)new\s+$", before) != None
            cached_results = cache_complete_startswith(self.cache, bencode(prefix))
            if cached_results:
                ret = [(x.display, x.insert) for x in cached_results[0]]
            variables = parsehelp.extract_variables(data) if not constr else []
            var = [("%s\t%s" % (v[1], re.sub(r"(^|\b)\s*static\s+", "", v[0])), v[1]) for v in variables]
            if len(var) and ret == None:
                ret = []
            for v in var:
                if v[1].startswith(prefix):
                    ret.append(v)
            clazz = parsehelp.extract_class_from_function(data)
            if clazz == None:
                clazz = parsehelp.extract_class(data)
            if clazz != None:
                c = self.__find_type(data, clazz)
                if c != None and not c.kind.is_invalid():
                    comp = cache_completeCursor(self.cache, c)
                    if comp:
                        for c in comp[0]:
                            c.cursor._tu = self.tu
                            if not c.static and \
                                    not (c.baseclass and c.access == cindex.CXXAccessSpecifier.PRIVATE):
                                add = (c.display, c.insert)
                                ret.append(add)
            namespaces = parsehelp.extract_used_namespaces(data)
            ns = parsehelp.extract_namespace(data)
            if ns:
                namespaces.append(ns)
            for ns in namespaces:
                ns = ns.split("::")
                add = self.__complete_namespace(ns)
                if add:
                    ret.extend(add)
            ret = self.__filter(ret, constr)
        return remove_duplicates(ret)

    def complete(self, data, prefix):
        self.lock.acquire()
        ret = None
        try:
            ret = self.__complete_code(data, prefix)
        finally:
            self.lock.release()
        return ret


    def __clangcomplete_code(self, filename, row, col, unsaved_files, membercomp):
        ret = None
        unsaved = None
        if len(unsaved_files):
            unsaved = (cindex._CXUnsavedFile * len(unsaved_files))()
            for i, (name, value) in enumerate(unsaved_files):
                if not isinstance(value, str):
                    value = value.encode("ascii", "ignore")
                value = bencode(value)
                unsaved[i].name = bencode(name)
                unsaved[i].contents = value
                unsaved[i].length = len(value)
        comp = cache_clangComplete(self.cache, bencode(filename), row, col, unsaved, len(unsaved_files), membercomp)

        if comp:
            ret = [(c.display, c.insert) for c in comp[0]]
        return ret

    def clangcomplete(self, filename, row, col, unsaved_files, membercomp):
        self.lock.acquire()
        ret = None
        try:
            ret = self.__clangcomplete(self, filename, row, col, unsaved_files, membercomp)
        finally:
            self.lock.release()
        return ret


    def __get_impdef_prep(self, data, offset):
        row, col = parsehelp.get_line_and_column_from_offset(data, offset)
        cursor = cindex.Cursor.get(self.tu, self.filename, row, col)
        cursor_spelling = self.__get_cursor_spelling(cursor)
        word_under_cursor = parsehelp.extract_word_at_offset(data, offset)
        if word_under_cursor == "" and cursor != None:
            # Allow a parenthesis, brackets and some other non-name characters right after the name
            match = re.search(r"(\w+)[\(\[\&\+\-\*\/]*$", parsehelp.extract_line_until_offset(data, offset))
            if match:
                word_under_cursor = match.group(1)
        return cursor, cursor_spelling, word_under_cursor


    def find_definition(self, data, offset, found_callback, folders):
        import extensivesearch
        target = None
        try:
            self.lock.acquire()
            self.tu.reparse([(self.filename, data)])
            cursor, cursor_spelling, word_under_cursor = self.__get_impdef_prep(data, offset)
            if len(word_under_cursor) == 0:
                found_callback(None)
                return
            if cursor == None or cursor.kind.is_invalid() or cursor_spelling != word_under_cursor:
                if cursor == None or cursor.kind.is_invalid():
                    cursor = None
                ExtensiveSearch(cursor, word_under_cursor, found_callback, folders, self.opts)
                return
            d = cursor.get_definition()
            if d != None and cursor != d:
                target = self.__format_cursor(d)
            elif d != None and cursor == d and \
                    (cursor.kind == cindex.CursorKind.VAR_DECL or \
                    cursor.kind == cindex.CursorKind.PARM_DECL or \
                    cursor.kind == cindex.CursorKind.FIELD_DECL):
                for child in cursor.get_children():
                    if child.kind == cindex.CursorKind.TYPE_REF:
                        d = child.get_definition()
                        if d != None:
                            target = self.__format_cursor(d)
                        break
            elif cursor.kind == cindex.CursorKind.CLASS_DECL:
                for child in cursor.get_children():
                    if child.kind == cindex.CursorKind.CXX_BASE_SPECIFIER:
                        d = child.get_definition()
                        if d != None:
                            target = self.__format_cursor(d)
            elif d == None:
                if cursor.kind == cindex.CursorKind.DECL_REF_EXPR or \
                        cursor.kind == cindex.CursorKind.MEMBER_REF_EXPR or \
                        cursor.kind == cindex.CursorKind.CALL_EXPR:
                    cursor = cursor.referenced

                if cursor.kind == cindex.CursorKind.CXX_METHOD or \
                        cursor.kind == cindex.CursorKind.FUNCTION_DECL or \
                        cursor.kind == cindex.CursorKind.CONSTRUCTOR or \
                        cursor.kind == cindex.CursorKind.DESTRUCTOR:
                    f = cursor.location.file.name
                    if f.endswith(".h"):
                        endings = ["cpp", "c", "cc", "m", "mm"]
                        for ending in endings:
                            f = "%s.%s" % (f[:f.rfind(".")], ending)
                            if f != self.filename and os.access(f, os.R_OK):
                                tu2 = tuCache.get_translation_unit(f, self.opts)
                                if tu2 == None:
                                    continue
                                tu2.lock()
                                try:
                                    cursor2 = cindex.Cursor.get(
                                            tu2.var, cursor.location.file.name,
                                            cursor.location.line,
                                            cursor.location.column)
                                    if cursor2 != None:
                                        d = cursor2.get_definition()
                                        if d != None and cursor2 != d:
                                            target = self.__format_cursor(d)
                                            break
                                finally:
                                    tu2.unlock()
                    if not target:
                        ExtensiveSearch(cursor, word_under_cursor, found_callback, folders, self.opts)
                        return
            else:
                target = self.__format_cursor(d)
        finally:
            self.lock.release()
        found_callback(target)

    def find_declaration(self, data, offset, found_callback, folders):
        target = None
        try:
            self.lock.acquire()
            self.tu.reparse([(self.filename, data)])
            cursor, cursor_spelling, word_under_cursor = self.__get_impdef_prep(data, offset)
            if len(word_under_cursor) == 0:
                found_callback(None)
                return
            ref = cursor.referenced
            target = None

            if ref != None:
                target = self.__format_cursor(ref)
            elif cursor.kind == cindex.CursorKind.INCLUSION_DIRECTIVE:
                f = cursor.get_included_file()
                if not f is None:
                    target = f.name
        finally:
            self.lock.release()

        found_callback(target)

    def reparse(self, unsaved_files):
        try:
            self.lock.acquire()
            self.tu.reparse(unsaved_files)
            self.cache = _createCache(self.tu.cursor)[0]
        finally:
            self.lock.release()


    # todo: this needs to move out
    def get_diagnostics(self):
        ret = list()
        try:
            self.lock.acquire()
            for d in self.tu.diagnostics:
                location = d.location
                value    = d.severity
                spelling = d.spelling
                line     = location.line
                column   = location.column
                filename = self.filename
                if location.file != None:
                    filename = location.file.name
                info = Diagnostic(value, line, column, spelling, filename)
                if hasattr(d, 'disable_option'):
                    info.disable_flag = d.disable_option

                ret.append(info)
        finally:
            self.lock.release()
        return ret
