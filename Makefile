# Ubuntu 14.04 wants to have libclang in a special place.
# use -rpath to hardcode load path in libcache.so
#
#
# LFLAGS=-lclang -L/usr/lib/llvm-3.7/lib/ -Wl,-rpath,/usr/lib/llvm-3.7/lib
# CFLAGS=-O3 -D_NDEBUG -Wall -fPIC -shared -std=c++11 -I/usr/lib/llvm-3.7/include

CC=gcc
LFLAGS=-lclang -L$(HOME)/bin/clang-3.7.1/lib/ -Wl,-rpath,$(HOME)/bin/clang-3.7.1/lib/
CFLAGS=-O3 -D_NDEBUG -Wall -fPIC -shared -std=c++11 -I$(HOME)/bin/clang-3.7.1/include/

libcache.so:
	$(CC) $(CFLAGS) src/main.cpp -o libcache.so $(LFLAGS)

clean:
	rm libcache.so
