# Ubuntu 14.04 wants to have libclang in a special place.
# use -rpath to hardcode load path in libcache.so
#
#
# LFLAGS=-lclang -L/usr/lib/llvm-3.7/lib/ -Wl,-rpath,/usr/lib/llvm-3.7/lib
# CFLAGS=-O3 -D_NDEBUG -Wall -fPIC -shared -std=c++11 -I/usr/lib/llvm-3.7/include

CC=gcc
LFLAGS=-lclang -L$(HOME)/bin/clang-3.7.1/lib/ -Wl,-rpath,$(HOME)/bin/clang-3.7.1/lib/
CFLAGS=-O3 -D_NDEBUG -Wall -fPIC -shared -std=c++11 -I$(HOME)/bin/clang-3.7.1/include/

libcache.so: src/libcache.cpp src/libcache.h
	$(CC) $(CFLAGS) src/libcache.cpp -o libcache.so $(LFLAGS)

clean:
	rm libcache.so

unit_test_debug: src/unit_test_libcache.cpp src/libcache.cpp src/libcache.h
	g++ -std=c++11 -g -O0 -Wall src/unit_test_libcache.cpp src/libcache.cpp -o unit_test $(LFLAGS)

unit_test_release: src/unit_test_libcache.cpp src/libcache.cpp src/libcache.h
	g++ -std=c++11 -O3 -Wall src/unit_test_libcache.cpp src/libcache.cpp -o unit_test $(LFLAGS)

clean:
	rm libcache.so
	rm unit_test