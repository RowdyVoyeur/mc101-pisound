# Set the compiler
CC ?= gcc

# Location of the source files
SOURCE_DIR = src/
EXTENSION = .c

# Find all source files and headers
SRC_FILES := $(shell find $(SOURCE_DIR) -type f -name "*$(EXTENSION)")
OBJ := $(SRC_FILES:.c=.o)
DEPS := $(shell find src -type f -name "*.h")

# Libraries: Using libusb-1.0 for Teensy/M8 and rtmidi for controllers
INCLUDES = $(shell pkg-config --libs sdl3 libusb-1.0 rtmidi)

# Compiler flags: Optimized for Pi 4
# -DUSE_LIBUSB activates the Teensy USB code
# -DUSE_RTMIDI activates the MIDI controller code
local_CFLAGS = $(CFLAGS) $(shell pkg-config --cflags sdl3 libusb-1.0 rtmidi) \
               -Wall -Wextra -O3 -pipe -I. \
               -march=armv8-a+crc -mtune=cortex-a72 \
               -fomit-frame-pointer -flto -DNDEBUG \
               -DUSE_LIBUSB -DUSE_RTMIDI

# Linker flags
LDFLAGS = -flto -Wl,-O1 -Wl,--as-needed -s

# Rule for object files
%.o: %$(EXTENSION) $(DEPS)
	$(CC) -c -o $@ $< $(local_CFLAGS)

# Rule for final binary
m8c: $(OBJ)
	$(CC) $(LDFLAGS) -o $@ $^ $(local_CFLAGS) $(INCLUDES)

# Cleanup
.PHONY: clean
clean:
	rm -f $(OBJ) *~ m8c

# Install
ifeq ($(PREFIX),)
    PREFIX := /usr/local
endif

install: m8c
	install -d $(DESTDIR)$(PREFIX)/bin/
	install -m 755 m8c $(DESTDIR)$(PREFIX)/bin/