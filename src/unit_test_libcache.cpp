
#include <clang-c/Index.h>
#include <vector>
#include <string>
#include <cstring>
#include "libcache.h"
#include "test_minimal.h"

// gcc -xc++ -E -v -
// clang++ -### -c test.cpp


bool operator==(const CXCursor& lhs, const CXCursor& rhs)
{
    return !std::memcmp(&lhs, &rhs, sizeof(lhs));
}

bool operator!=(const CXCursor& lhs, const CXCursor& rhs)
{
    return !(lhs == rhs);
}

void test_success()
{
    std::vector<const char*> args;
    args.push_back("-std=c++11");
    args.push_back("-Wall");
    args.push_back("-isystem");
    args.push_back("/usr/lib/gcc/x86_64-unknown-linux-gnu/5.3.0/../../../../include/c++/5.3.0");
    args.push_back("-isystem");
    args.push_back("/usr/lib/gcc/x86_64-unknown-linux-gnu/5.3.0/../../../../include/c++/5.3.0/x86_64-unknown-linux-gnu");
    args.push_back("-isystem");
    args.push_back("/usr/lib/gcc/x86_64-unknown-linux-gnu/5.3.0/../../../../include/c++/5.3.0/backward");
    args.push_back("-isystem");
    args.push_back("/usr/lib/gcc/x86_64-unknown-linux-gnu/5.3.0/include");
    args.push_back("-isystem");
    args.push_back("/usr/local/include");
    args.push_back("-isystem");
    args.push_back("/usr/lib/gcc/x86_64-unknown-linux-gnu/5.3.0/include-fixed");
    args.push_back("-isystem");
    args.push_back("/usr/include");

    CXIndex index = clang_createIndex(1, 1);
    TEST_REQUIRE(index != nullptr);

    CXTranslationUnit tu = clang_createTranslationUnitFromSourceFile(
        index, "/home/enska/coding/SublimeClang/src/test-code.cpp",
        args.size(), &args[0],
        0, nullptr);
    TEST_REQUIRE(tu != nullptr);

    CXCursor cursor = clang_getTranslationUnitCursor(tu);
    TEST_REQUIRE(cursor != clang_getNullCursor());

    Cache* cache = createCache(cursor);

    {
        //CacheCompletionResults* results = cache_clangComplete(cache,
        //    "/home/enska/coding/SublimeClang/src/test-code.cpp",


    }



    deleteCache(cache);


    clang_disposeTranslationUnit(tu);
    clang_disposeIndex(index);
}


int test_main(int argc, char* argv[])
{
    test_success();

    return 0;
}