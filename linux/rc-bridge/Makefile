# Host build (macOS / Linux PC) for testing against simulator/server.py --ipc.
# The board build uses the SDK ARM toolchain: tools/build_linux_tools.sh.
CC      ?= cc
CFLAGS  ?= -std=gnu99 -O2 -Wall -Wextra -Werror
SRC     = rc_bridge.c uart.c ../../shared/ipc/fc_ipc.c ../../shared/rc/crsf.c
B       = build

$(B)/rc-bridge: $(SRC) | $(B)
	$(CC) $(CFLAGS) -o $@ $(SRC)

$(B):
	mkdir -p $(B)

clean:
	rm -rf $(B)

.PHONY: clean
