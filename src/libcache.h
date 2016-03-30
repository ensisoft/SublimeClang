/*
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
*/

//
// Copyright (c) 2016 Sami Väisänen, Ensisoft
// http://www.ensisoft.com
//

#if _WIN32
#  if defined(LIBRARY_IMPLEMENTATION)
#    define DLLAPI __declspec(dllexport)
#  else
#    define DLLAPI __declspec(dllimport)
#  endif
#else
#  define DLLAPI
#endif

#include <clang-c/Index.h>
#include <string>
#include <cstring>
#include <vector>
#include <memory>
#include <map>
#include <cassert>

class CacheCompletionResults;
class Cache;
class CacheEntry;

// IMPORTANT: This class is used through ctypes from Python code.
// So this type here must be maintained binary compatible with
// the definition in internals/translationunit.py
// Hence also the use of "raw" C style strings.

class CacheEntry
{
public:
    CacheEntry(const CacheEntry&) = delete;


    CacheEntry(CXCursor c, const std::string &disp, const std::string &ins, CX_CXXAccessSpecifier a=CX_CXXPublic, bool base=false)
    : cursor(c), access(a), isStatic(false), isBaseClass(base)
    {
        display = new char[disp.length()+1];
        insert  = new char[ins.length()+1];
        std::strcpy(display, disp.c_str());
        std::strcpy(insert, ins.c_str());

        if (clang_Cursor_isNull(c))
            return;

        CXCursorKind ck = clang_getCursorKind(c);
        switch (ck)
        {
            case CXCursor_CXXMethod:           isStatic = clang_CXXMethod_isStatic(c); break;
            case CXCursor_VarDecl:             isStatic = true;                        break;
            case CXCursor_ObjCClassMethodDecl: isStatic = true;                        break;
            default:                           isStatic = false;                       break;
        }
    }
   ~CacheEntry()
    {
        delete [] display;
        delete [] insert;
    }
    bool operator==(const CacheEntry& other) const
    {
        return std::strcmp(display, other.display) == 0 && std::strcmp(insert, other.insert) == 0;
    }
    // see class comments.
    CXCursor              cursor;
    char *                insert;
    char *                display;
    CX_CXXAccessSpecifier access;
    bool                  isStatic;
    bool                  isBaseClass;

    CacheEntry& operator=(const CacheEntry&) = delete;
private:

};

typedef std::vector<CXCursor>                CursorList;
typedef std::vector<std::shared_ptr<CacheEntry> > EntryList;
typedef std::map<CXCursor, CursorList>       CategoryContainer;

class CacheCompletionResults
{
public:
    CacheCompletionResults(EntryList::iterator start, EntryList::iterator end)
    : mEntries(start, end)
    {}

    CacheCompletionResults(EntryList&& results) : mEntries(std::move(results))
    {}

    unsigned int length() const
    {
        return mEntries.size();
    }
    const CacheEntry* getEntry(unsigned int index) const
    {
        assert(index >= 0 && index < mEntries.size());
        return mEntries[index].get();
    }

    CacheEntry& operator[](std::size_t index)
    {
        assert(index < mEntries.size());
        return *mEntries[index];
    }
    const CacheEntry& operator[](std::size_t index) const
    {
        assert(index < mEntries.size());
        return *mEntries[index];
    }

private:
    EntryList mEntries;
};



extern "C"
{

DLLAPI CacheCompletionResults* cache_clangComplete(Cache* cache, const char *filename, unsigned int row, unsigned int col, CXUnsavedFile *unsaved, unsigned int usLength, bool memberCompletion);

DLLAPI CacheCompletionResults* cache_completeCursor(Cache* cache, CXCursor cur);

DLLAPI CXCursor cache_findType(Cache* cache, const char **namespaces, unsigned int nsLength, const char *type);

DLLAPI CacheCompletionResults* cache_completeNamespace(Cache* cache, const char **namespaces, unsigned int length);

DLLAPI CacheCompletionResults* cache_complete_startswith(Cache* cache, const char *prefix);

DLLAPI unsigned int completionResults_length(CacheCompletionResults *comp);

DLLAPI const CacheEntry* completionResults_getEntry(CacheCompletionResults *comp, unsigned int index);

DLLAPI void completionResults_dispose(CacheCompletionResults *comp);

DLLAPI Cache* createCache(CXCursor base);

DLLAPI void deleteCache(Cache *cache);

DLLAPI const char* getVersion();

} // extern C
