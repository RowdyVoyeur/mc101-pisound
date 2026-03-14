#Set the compiler you are using
CC ?= gcc

#Set the filename extension of your C files
EXTENSION = .c

# Location of the source files
SOURCE_DIR = src/

# Find all source files in the src directory and subdirectories
SRC_FILES := $(shell find $(SOURCE_DIR) -type f -name "*$(EXTENSION)")

# Convert to object files
OBJ := $(SRC_FILES:.c=.o)

# Find all header files for dependencies
DEPS := $(shell find src -type f -name "*.h")

# Libraries for the project (Removed Windows-specific hacks)
INCLUDES = $(shell pkg-config --libs sdl3 libserialport)

# Compiler flags optimized for Raspberry Pi 4 (Cortex-A72, 64-bit)
local_CFLAGS = $(CFLAGS) $(shell pkg-config --cflags sdl3 libserialport) \
               -Wall -Wextra -O3 -pipe -I. \
               -march=armv8-a+crc -mtune=cortex-a72 \
               -fomit-frame-pointer -flto -DNDEBUG

# Linker flags for Link-Time Optimization and stripping binaries to reduce size
LDFLAGS = -flto -Wl,-O1 -Wl,--as-needed -s

#define a rule that applies to all files ending in the .o suffix. Compile each object file
%.o: %$(EXTENSION) $(DEPS)
	$(CC) -c -o $@ $< $(local_CFLAGS)

#Combine them into the output file
m8c: $(OBJ)
	$(CC) $(LDFLAGS) -o $@ $^ $(local_CFLAGS) $(INCLUDES)

# rtmidi target: Optimized for Pi 4 (Kept for MC-101 / PiSound MIDI integration)
rtmidi: INCLUDES = $(shell pkg-config --libs sdl3 rtmidi)
rtmidi: local_CFLAGS = $(CFLAGS) $(shell pkg-config --cflags sdl3 rtmidi) \
                       -Wall -Wextra -O3 -pipe -I. \
                       -march=armv8-a+crc -mtune=cortex-a72 \
                       -fomit-frame-pointer -flto -DUSE_RTMIDI -DNDEBUG
rtmidi: m8c

#Cleanup
.PHONY: clean

clean:
	rm -f src/*.o src/backends/*.o *~ m8c

# PREFIX is environment variable, but if it is not set, then set default value
ifeq ($(PREFIX),)
    PREFIX := /usr/local
endif

install: m8c
	install -d $(DESTDIR)$(PREFIX)/bin/
	install -m 755 m8c $(DESTDIR)$(PREFIX)/bin/