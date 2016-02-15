CC=gcc
LFLAGS=-lclang
CFLAGS=-O3 -D_NDEBUG -Wall -fPIC -shared -std=c++11

libcache.so:
	$(CC) $(CFLAGS) $(LFLAGS) src/main.cpp -o libcache.so
