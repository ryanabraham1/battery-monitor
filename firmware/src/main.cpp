// FRC battery IR monitor node firmware (hardware rev A).
//
// What it does:
//   - reads battery voltage/current from the INA226 across the 1 mOhm shunt
//   - measures internal resistance: disconnect charger -> settle -> 100 ms ~12 A pulse ->
//     IR = (V_open - V_loaded) / (I_loaded - I_open) - lead resistance
//   - reports over CAN to the pit hub (results are per station; there is no battery ID reader) and takes commands from it
//   - USB serial console for setup (type "help")
//
// Radios are never started.

#include <Arduino.h>
#include <Wire.h>
#include <Preferences.h>
#include "driver/twai.h"
#include "config.h"

// ---------------------------------------------------------------- settings (NVS)
static Preferences prefs;
static uint8_t  nodeId      = 1;      // 1..31
static float    leadMilliohm = 0.0f;  // subtracted from every result (cable + connector between lugs and battery)
static uint16_t autoMinutes = 30;     // periodic retest while a battery is connected, 0 = off
static uint16_t settleSec   = 5;      // rest time after the charger is disconnected
static float    goodBelow   = 15.0f;  // mOhm: green below this
static float    warnBelow   = 20.0f;  // mOhm: yellow below this, red at or above

static void loadSettings() {
  prefs.begin("irnode", false);
  nodeId       = prefs.getUChar("id", 1);
  leadMilliohm = prefs.getFloat("lead", 0.0f);
  autoMinutes  = prefs.getUShort("auto", 30);
  settleSec    = prefs.getUShort("settle", 5);
  goodBelow    = prefs.getFloat("good", 15.0f);
  warnBelow    = prefs.getFloat("warn", 20.0f);
  if (nodeId < 1 || nodeId > 31) nodeId = 1;
}

// ---------------------------------------------------------------- live state
static State    state = ST_NO_BATT;
static bool     inaOk = false, canOk = false;
static float    busV = 0, amps = 0;          // filtered; amps > 0 = battery discharging
static int8_t   tFet = -128;                 // MOSFET temperature, degC, -128 = sensor fault

static bool     resultValid = false;
static Err      lastErr = ERR_NONE;
static float    irMilliohm = 0, vOpen = 0, vLoad = 0, iPulse = 0;
static uint8_t  resultSeq = 0;
static uint8_t  resultResend = 0;

static bool     holdChargerOff = false;      // hub asked to keep the charger disconnected
static bool     testRequested = false;
static uint32_t settleStart = 0, lastTestMs = 0, battSince = 0, identifyUntil = 0;
static bool     battPresent = false, firstTestDone = false;


// ---------------------------------------------------------------- LED (active low)
static void led(bool r, bool g, bool b) {
  digitalWrite(PIN_LED_R, !r);
  digitalWrite(PIN_LED_G, !g);
  digitalWrite(PIN_LED_B, !b);
}

static void updateLed() {
  uint32_t t = millis();
  bool fast = (t / 125) & 1, slow = (t % 2000) < 1800;
  if (t < identifyUntil)            { led(fast, fast, fast); return; }
  if (state == ST_FAULT_STUCK)      { led(fast, 0, 0); return; }
  if (state == ST_TEST)             { led(1, 1, 1); return; }
  if (state == ST_SETTLE)           { led(0, 0, fast); return; }
  if (state == ST_NO_BATT)          { led(0, 0, (t % 2000) < 100); return; }   // short blue heartbeat
  bool on = (state == ST_CHARGING) ? slow : true;                              // blink off briefly while charging
  if (!on)                          { led(0, 0, 0); return; }
  if (resultValid) {
    if (irMilliohm < goodBelow)      led(0, 1, 0);
    else if (irMilliohm < warnBelow) led(1, 1, 0);
    else                             led(1, 0, 0);
  } else if (lastErr != ERR_NONE)    led(1, 0, 1);   // magenta: last test failed, see console / hub
  else                               led(0, 1, 1);   // cyan: battery seen, not tested yet
}

// ---------------------------------------------------------------- INA226
#define INA_REG_CONFIG 0x00
#define INA_REG_SHUNT  0x01
#define INA_REG_BUS    0x02
#define INA_REG_MASK   0x06
#define INA_REG_MFG    0xFE
// 4 averages, 1.1 ms bus + 1.1 ms shunt conversion, continuous: one fresh pair every 8.8 ms
#define INA_CONFIG     0x4327

static bool inaWr(uint8_t reg, uint16_t v) {
  Wire.beginTransmission(INA_ADDR);
  Wire.write(reg); Wire.write(v >> 8); Wire.write(v & 0xFF);
  return Wire.endTransmission() == 0;
}

static bool inaRd(uint8_t reg, uint16_t &v) {
  Wire.beginTransmission(INA_ADDR);
  Wire.write(reg);
  if (Wire.endTransmission(false) != 0) return false;
  if (Wire.requestFrom((int)INA_ADDR, 2) != 2) return false;
  v = ((uint16_t)Wire.read() << 8) | Wire.read();
  return true;
}

static bool inaInit() {
  uint16_t id;
  if (!inaRd(INA_REG_MFG, id) || id != 0x5449) return false;   // "TI"
  return inaWr(INA_REG_CONFIG, INA_CONFIG);
}

static bool inaReadVI(float &v, float &i) {
  uint16_t rb, rs;
  if (!inaRd(INA_REG_BUS, rb) || !inaRd(INA_REG_SHUNT, rs)) return false;
  v = rb * 1.25e-3f;
  i = (int16_t)rs * 2.5e-6f / SHUNT_OHMS;   // IN+ is the battery side, so discharge is positive
  return true;
}

// true when a new conversion is ready (reading the register clears the flag)
static bool inaReady() {
  uint16_t m;
  return inaRd(INA_REG_MASK, m) && (m & 0x0008);
}

static bool inaWaitSample(float &v, float &i, uint32_t timeoutMs) {
  uint32_t t = millis();
  while (millis() - t < timeoutMs) {
    if (inaReady()) return inaReadVI(v, i);
    delayMicroseconds(300);
  }
  return false;
}

// ---------------------------------------------------------------- temperatures
static int8_t readNtc(int pin) {
  uint32_t mv = 0;
  for (int k = 0; k < 8; k++) mv += analogReadMilliVolts(pin);
  mv /= 8;
  if (mv > 3150 || mv < 50) return -128;                  // open or shorted
  float r = 10000.0f * mv / (3300.0f - mv);
  float tk = 1.0f / (1.0f / 298.15f + logf(r / 10000.0f) / 3950.0f);
  float c = tk - 273.15f;
  if (c < -40) c = -40;
  if (c > 125) c = 125;
  return (int8_t)lroundf(c);
}

// ---------------------------------------------------------------- CAN
static bool canInit() {
  twai_general_config_t g = TWAI_GENERAL_CONFIG_DEFAULT((gpio_num_t)PIN_CAN_TX, (gpio_num_t)PIN_CAN_RX, TWAI_MODE_NORMAL);
  g.tx_queue_len = 16;
  g.rx_queue_len = 16;
  twai_timing_config_t t = TWAI_TIMING_CONFIG_250KBITS();
  twai_filter_config_t f = TWAI_FILTER_CONFIG_ACCEPT_ALL();
  if (twai_driver_install(&g, &t, &f) != ESP_OK) return false;
  return twai_start() == ESP_OK;
}

static void canSend(uint32_t id, const uint8_t *d) {
  if (!canOk) return;
  twai_message_t m = {};
  m.identifier = id;
  m.data_length_code = 8;
  memcpy(m.data, d, 8);
  twai_transmit(&m, 0);   // never block; with no hub connected the queue just fills and frames are dropped
}

static void canService() {
  if (!canOk) return;
  twai_status_info_t s;
  if (twai_get_status_info(&s) == ESP_OK) {
    if (s.state == TWAI_STATE_BUS_OFF) twai_initiate_recovery();
    else if (s.state == TWAI_STATE_STOPPED) twai_start();
  }
}

static void sendStatus() {
  uint8_t d[8];
  uint8_t flags = 0;
  if (!digitalRead(PIN_RELAY_EN)) flags |= FLAG_CHG_CONN;
  if (inaOk) flags |= FLAG_INA_OK;
  if (resultValid) flags |= FLAG_RESULT_OK;
  uint16_t mv = (uint16_t)constrain(lroundf(busV * 1000), 0L, 65535L);
  int16_t ca = (int16_t)constrain(lroundf(amps * 100), -32768L, 32767L);
  d[0] = state; d[1] = flags;
  d[2] = mv & 0xFF; d[3] = mv >> 8;
  d[4] = ca & 0xFF; d[5] = (uint16_t)ca >> 8;
  d[6] = 0x80; d[7] = (uint8_t)tFet;   // byte 6 is reserved
  canSend(CAN_ID_STATUS + nodeId, d);
}

static void sendResult() {
  uint8_t d[8];
  uint16_t ir = resultValid ? (uint16_t)constrain(lroundf(irMilliohm * 100), 0L, 65534L) : 0xFFFF;
  uint16_t vo = (uint16_t)lroundf(vOpen * 1000), vl = (uint16_t)lroundf(vLoad * 1000);
  d[0] = ir & 0xFF; d[1] = ir >> 8;
  d[2] = vo & 0xFF; d[3] = vo >> 8;
  d[4] = vl & 0xFF; d[5] = vl >> 8;
  d[6] = resultValid ? (uint8_t)constrain(lroundf(iPulse * 10), 0L, 255L) : (uint8_t)lastErr;
  d[7] = resultSeq;
  canSend(CAN_ID_RESULT + nodeId, d);
}

// ---------------------------------------------------------------- relay
static void chargerConnect(bool connect) { digitalWrite(PIN_RELAY_EN, connect ? LOW : HIGH); }

// ---------------------------------------------------------------- the pulse test
static const char *errText(Err e) {
  switch (e) {
    case ERR_NONE: return "ok";
    case ERR_LOW_VOLTAGE: return "battery voltage too low to test";
    case ERR_HOT: return "MOSFET too hot";
    case ERR_NO_PULSE: return "gate driver never turned on (one-shot/driver fault)";
    case ERR_LOAD_OPEN: return "pulse current too low (load resistor or thermostat open?)";
    case ERR_OVERCURRENT: return "pulse current too high";
    case ERR_INA: return "no data from INA226";
    case ERR_STUCK: return "LOAD CURRENT DID NOT STOP - MOSFET may be shorted";
  }
  return "?";
}

// Blocks for roughly 350 ms. The charger must already be disconnected and settled.
static Err runPulse() {
  float v, i;
  if (!inaWaitSample(v, i, 50)) return ERR_INA;
  if (v < MIN_TEST_VOLTS) return ERR_LOW_VOLTAGE;
  if (tFet != -128 && tFet > MAX_FET_TEMP_C) return ERR_HOT;

  double sv = 0, si = 0;
  for (int k = 0; k < BASELINE_SAMPLES; k++) {
    if (!inaWaitSample(v, i, 50)) return ERR_INA;
    sv += v; si += i;
  }
  float v0 = sv / BASELINE_SAMPLES, i0 = si / BASELINE_SAMPLES;

  inaReady();                       // discard any conversion finished before the pulse
  bool fbSeen = false;
  int n = 0;
  sv = 0; si = 0;
  uint32_t t0 = millis(), el;
  digitalWrite(PIN_LOAD_EN, HIGH);
  while ((el = millis() - t0) < PULSE_MS) {
    if (digitalRead(PIN_LOAD_FB)) fbSeen = true;
    if (inaReady() && inaReadVI(v, i) && el >= PULSE_SKIP_MS) { sv += v; si += i; n++; }
  }
  digitalWrite(PIN_LOAD_EN, LOW);

  delay(60);
  float va, ia;
  bool gotAfter = inaWaitSample(va, ia, 50);
  if (gotAfter && ia - i0 > 1.0f) return ERR_STUCK;
  if (!fbSeen) return ERR_NO_PULSE;
  if (n < 3 || !gotAfter) return ERR_INA;

  float v1 = sv / n, i1 = si / n, di = i1 - i0;
  vOpen = v0; vLoad = v1; iPulse = i1;
  if (di < DI_MIN_A) return ERR_LOAD_OPEN;
  if (di > DI_MAX_A) return ERR_OVERCURRENT;
  irMilliohm = (v0 - v1) / di * 1000.0f - leadMilliohm;
  if (irMilliohm < 0) irMilliohm = 0;
  return ERR_NONE;
}

static void finishTest(Err e) {
  lastErr = e;
  resultValid = (e == ERR_NONE);
  resultSeq++;
  resultResend = 3;
  lastTestMs = millis();
  firstTestDone = true;
  if (e == ERR_STUCK) {
    state = ST_FAULT_STUCK;
    chargerConnect(false);          // stop the charger feeding the fault; the battery fuse is the last resort
  } else {
    state = ST_IDLE;
    chargerConnect(!holdChargerOff);
  }
  if (e == ERR_NONE)
    Serial.printf("IR %.2f mOhm  (open %.3f V, loaded %.3f V, %.2f A)\n", irMilliohm, vOpen, vLoad, iPulse);
  else
    Serial.printf("test failed: %s\n", errText(e));
}

static void startTest() {
  if (state == ST_FAULT_STUCK || state == ST_SETTLE || state == ST_TEST) return;
  if (!inaOk) { finishTest(ERR_INA); return; }
  chargerConnect(false);
  settleStart = millis();
  state = ST_SETTLE;
  Serial.printf("charger disconnected, settling %u s\n", settleSec);
}

// ---------------------------------------------------------------- console
static void printStatus() {
  Serial.printf("node %u  state %u  %.3f V  %+.2f A  fet %d C\n", nodeId, state, busV, amps, tFet);
  Serial.printf("ina %s  can %s  charger %s\n", inaOk ? "ok" : "MISSING",
                canOk ? "ok" : "FAILED", digitalRead(PIN_RELAY_EN) ? "disconnected" : "connected");
  if (resultValid) Serial.printf("last IR %.2f mOhm\n", irMilliohm);
  else if (lastErr) Serial.printf("last test failed: %s\n", errText(lastErr));
  Serial.printf("settings: lead %.2f mOhm, auto %u min, settle %u s, good<%.1f warn<%.1f\n",
                leadMilliohm, autoMinutes, settleSec, goodBelow, warnBelow);
}

static void handleLine(String s) {
  s.trim();
  if (!s.length()) return;
  int sp = s.indexOf(' ');
  String cmd = sp < 0 ? s : s.substring(0, sp);
  String arg = sp < 0 ? "" : s.substring(sp + 1);
  arg.trim();
  if (cmd == "status") printStatus();
  else if (cmd == "test") testRequested = true;
  else if (cmd == "id" && arg.length()) {
    int v = arg.toInt();
    if (v >= 1 && v <= 31) { nodeId = v; prefs.putUChar("id", nodeId); Serial.printf("node id %u\n", nodeId); }
    else Serial.println("id must be 1..31");
  }
  else if (cmd == "lead" && arg.length())   { leadMilliohm = arg.toFloat(); prefs.putFloat("lead", leadMilliohm); printStatus(); }
  else if (cmd == "auto" && arg.length())   { autoMinutes = arg.toInt(); prefs.putUShort("auto", autoMinutes); printStatus(); }
  else if (cmd == "settle" && arg.length()) { settleSec = constrain(arg.toInt(), 1L, 120L); prefs.putUShort("settle", settleSec); printStatus(); }
  else if (cmd == "good" && arg.length())   { goodBelow = arg.toFloat(); prefs.putFloat("good", goodBelow); printStatus(); }
  else if (cmd == "warn" && arg.length())   { warnBelow = arg.toFloat(); prefs.putFloat("warn", warnBelow); printStatus(); }
  else if (cmd == "charger" && arg.length()) { holdChargerOff = (arg == "off"); if (state != ST_SETTLE && state != ST_TEST && state != ST_FAULT_STUCK) chargerConnect(!holdChargerOff); }
  else if (cmd == "clear") { if (state == ST_FAULT_STUCK) { state = ST_IDLE; lastErr = ERR_NONE; chargerConnect(!holdChargerOff); } }
  else {
    Serial.println("commands:");
    Serial.println("  status            show readings and settings");
    Serial.println("  test              run an IR test now");
    Serial.println("  id <1..31>        set this node's CAN id (every node on the bus needs its own)");
    Serial.println("  lead <mOhm>       resistance to subtract (cable + connector), see docs/setup.md");
    Serial.println("  auto <minutes>    retest interval while a battery is connected, 0 = off");
    Serial.println("  settle <seconds>  rest after disconnecting the charger, before the pulse");
    Serial.println("  good <mOhm> / warn <mOhm>   LED colour thresholds");
    Serial.println("  charger on|off    reconnect / hold the charger disconnected");
    Serial.println("  clear             clear a latched stuck-load fault");
  }
}

static void consolePoll() {
  static String line;
  while (Serial.available()) {
    char c = Serial.read();
    if (c == '\n' || c == '\r') { handleLine(line); line = ""; }
    else if (line.length() < 60) line += c;
  }
}

// ---------------------------------------------------------------- CAN commands
static void canPoll() {
  if (!canOk) return;
  twai_message_t m;
  while (twai_receive(&m, 0) == ESP_OK) {
    if (m.extd || m.rtr || m.data_length_code < 1) continue;
    if (m.identifier != CAN_ID_CMD && m.identifier != (uint32_t)(CAN_ID_CMD + nodeId)) continue;
    switch (m.data[0]) {
      case CMD_TEST: testRequested = true; break;
      case CMD_CHARGER:
        holdChargerOff = m.data_length_code > 1 && m.data[1] == 1;
        if (state != ST_SETTLE && state != ST_TEST && state != ST_FAULT_STUCK) chargerConnect(!holdChargerOff);
        break;
      case CMD_IDENTIFY: identifyUntil = millis() + 5000; break;
      case CMD_CLEAR_FAULT:
        if (state == ST_FAULT_STUCK) { state = ST_IDLE; lastErr = ERR_NONE; chargerConnect(!holdChargerOff); }
        break;
    }
  }
}

// ---------------------------------------------------------------- setup / loop
void setup() {
  // Outputs first: load off, charger connected, LED off.
  pinMode(PIN_LOAD_EN, OUTPUT);  digitalWrite(PIN_LOAD_EN, LOW);
  pinMode(PIN_RELAY_EN, OUTPUT); digitalWrite(PIN_RELAY_EN, LOW);
  pinMode(PIN_LED_R, OUTPUT); pinMode(PIN_LED_G, OUTPUT); pinMode(PIN_LED_B, OUTPUT);
  led(0, 0, 0);
  pinMode(PIN_LOAD_FB, INPUT);
  pinMode(PIN_INA_ALERT, INPUT);

  Serial.begin(115200);
  loadSettings();

  Wire.begin(PIN_I2C0_SDA, PIN_I2C0_SCL, 400000);
  Wire.setTimeOut(20);
  inaOk = inaInit();
  canOk = canInit();
  analogSetPinAttenuation(PIN_NTC_FET, ADC_11db);
}

void loop() {
  static uint32_t tStatus = 0, tTemp = 0, tResult = 0, tInaRetry = 0;
  uint32_t now = millis();

  consolePoll();
  canPoll();

  // --- readings
  if (inaOk) {
    float v, i;
    if (inaReady() && inaReadVI(v, i)) {
      busV += (v - busV) * 0.1f;
      amps += (i - amps) * 0.1f;
    }
  } else if (now - tInaRetry > 2000) {
    tInaRetry = now;
    inaOk = inaInit();
  }
  if (now - tTemp > 1000) {
    tTemp = now;
    tFet = readNtc(PIN_NTC_FET);
  }
  // --- battery presence and state
  bool present = busV > BATT_PRESENT_V;
  if (present && !battPresent) { battSince = now; firstTestDone = false; }
  if (!present && battPresent) { resultValid = false; lastErr = ERR_NONE; }
  battPresent = present;

  if (state == ST_SETTLE) {
    if (now - settleStart >= (uint32_t)settleSec * 1000) {
      state = ST_TEST;
      updateLed();
      finishTest(runPulse());
    }
  } else if (state != ST_FAULT_STUCK) {
    state = !present ? ST_NO_BATT : (amps < -0.2f ? ST_CHARGING : ST_IDLE);

    bool gapOk = now - lastTestMs > MIN_TEST_GAP_MS || lastTestMs == 0;
    bool wantAuto = false;
    if (present && autoMinutes > 0) {
      if (!firstTestDone) wantAuto = now - battSince > 5000;                       // 5 s after a battery arrives
      else wantAuto = now - lastTestMs > (uint32_t)autoMinutes * 60000UL;
    }
    if ((testRequested || wantAuto) && gapOk) {
      testRequested = false;
      startTest();
    }
  }

  // --- CAN reporting
  if (now - tStatus > 1000) { tStatus = now; canService(); sendStatus(); }
  if (resultResend && now - tResult > 200) { tResult = now; resultResend--; sendResult(); }

  updateLed();
  delay(1);
}
