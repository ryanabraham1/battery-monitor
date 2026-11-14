// Pin map and fixed constants for the IR node, hardware rev A.
// Must match tools/design.py (the schematic source).
#pragma once
#include <Arduino.h>

// ---- GPIO ----
#define PIN_CAN_TX     4
#define PIN_CAN_RX     5
#define PIN_LOAD_EN    6   // high = request pulse (one-shot caps it at ~220 ms in hardware)
#define PIN_LOAD_FB    7   // one-shot output readback, high while the gate driver is enabled
#define PIN_RELAY_EN   15  // high = relay energised = charger DISCONNECTED (NC contact opens)
#define PIN_LED_R      16  // three separate 0603 LEDs, active low
#define PIN_LED_G      17
#define PIN_LED_B      18
#define PIN_I2C0_SDA   8   // INA226
#define PIN_I2C0_SCL   9
#define PIN_INA_ALERT  10
#define PIN_NTC_FET    2   // ADC1_CH1, on-board NTC next to the MOSFET

// ---- measurement ----
#define INA_ADDR         0x40
#define SHUNT_OHMS       0.001f
#define PULSE_MS         100     // firmware pulse length
#define PULSE_SKIP_MS    40      // ignore samples before this (lead inductance, driver rise, averaging window)
#define BASELINE_SAMPLES 16
#define MIN_TEST_GAP_MS  10000   // load resistor duty limit
#define MIN_TEST_VOLTS   10.5f
#define MAX_FET_TEMP_C   80
#define DI_MIN_A         5.0f    // below this the load resistor / thermostat is open
#define DI_MAX_A         20.0f
#define BATT_PRESENT_V   9.0f

// ---- CAN (250 kbit/s, 11-bit IDs, little-endian payloads) ----
#define CAN_ID_CMD     0x080   // + node id, or exactly 0x080 for "all nodes"
#define CAN_ID_STATUS  0x100   // + node id, 1 Hz
#define CAN_ID_RESULT  0x200   // + node id, sent 3x after each test

enum Cmd : uint8_t { CMD_TEST = 1, CMD_CHARGER = 2, CMD_IDENTIFY = 3, CMD_CLEAR_FAULT = 4 };

enum State : uint8_t {
  ST_NO_BATT = 0,
  ST_IDLE = 1,       // battery present, not charging
  ST_CHARGING = 2,
  ST_SETTLE = 3,     // charger disconnected, waiting before the pulse
  ST_TEST = 4,
  ST_FAULT_STUCK = 0x80,  // load current did not stop after the pulse (latched)
};

enum Err : uint8_t {
  ERR_NONE = 0,
  ERR_LOW_VOLTAGE = 1,
  ERR_HOT = 2,
  ERR_NO_PULSE = 3,    // one-shot / driver never turned on
  ERR_LOAD_OPEN = 4,   // pulse current too low: resistor missing, thermostat open, bad lug
  ERR_OVERCURRENT = 5,
  ERR_INA = 6,         // no samples from the INA226
  ERR_STUCK = 7,
};

// status flags
#define FLAG_CHG_CONN   0x02
#define FLAG_INA_OK     0x08
#define FLAG_RESULT_OK  0x10
