# Software-in-the-loop build (host).  The flight sources are the ones the MCU
# will build; -Wdouble-promotion keeps them single precision for the rv32imc.
#
#   make            unit tests binary, scenario runner, Python bridge library
#   make test       unit tests + every closed-loop scenario
#   make run        3D viewer on http://127.0.0.1:8777
CC      ?= cc
CFLAGS  ?= -std=c99 -O2 -g -Wall -Wextra -Werror -Wdouble-promotion -Wshadow
LDLIBS  = -lm
B       = build

FLIGHT  = ../mcu/sensors/filters.c ../mcu/sensors/gyro_calib.c \
          ../mcu/estimator/attitude.c ../mcu/estimator/altitude.c \
          ../mcu/control/pid.c ../mcu/control/control.c ../mcu/mixer/mixer.c \
          ../mcu/failsafe/arming.c ../mcu/fc/fc.c ../mcu/fc/fc_params.c \
          ../shared/rc/crsf.c ../shared/rc/rc_map.c \
          ../shared/ipc/fc_ipc.c ../mcu/link/fc_link.c
SIM     = quad_model.c sim_sensors.c sim.c

UNAME   := $(shell uname)
ifeq ($(UNAME),Darwin)
  SHLIB = $(B)/libsim.dylib
  SHFLAGS = -dynamiclib
else
  SHLIB = $(B)/libsim.so
  SHFLAGS = -shared -fPIC
endif

all: $(B)/test_flight $(B)/sim_cli $(SHLIB)

$(B):
	mkdir -p $(B)

$(B)/test_flight: ../mcu/tests/test_flight.c $(FLIGHT) | $(B)
	$(CC) $(CFLAGS) -o $@ $^ $(LDLIBS)

$(B)/sim_cli: sim_cli.c $(SIM) $(FLIGHT) | $(B)
	$(CC) $(CFLAGS) -o $@ $^ $(LDLIBS)

$(SHLIB): $(SIM) $(FLIGHT) | $(B)
	$(CC) $(CFLAGS) -fPIC $(SHFLAGS) -o $@ $^ $(LDLIBS)

test: $(B)/test_flight $(B)/sim_cli
	./$(B)/test_flight
	./$(B)/sim_cli
	./$(B)/sim_cli --vib

# real key events through headless Chrome (needs Google Chrome and node >= 22)
e2e: $(SHLIB)
	node e2e_keyboard.mjs

run: $(SHLIB)
	python3 server.py

clean:
	rm -rf $(B)

.PHONY: all test e2e run clean
