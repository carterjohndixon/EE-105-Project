// =====================================================================
//  EE 105 demo board firmware  (Arduino Nano 33 BLE / BLE Sense)
//  One sketch for every demo-board lab. The lab notebooks upload it for
//  you and then talk to it over USB serial, so you never need to open the
//  Arduino IDE for the labs of Chapters 0 to 5.
//
//  Two kinds of commands (115200 baud, one command per line):
//
//  1. Commands you can type (notebook: board.monitor("circuits"), or any
//     serial terminal). They print plain text; "stop" ends the ones that
//     run until stopped. Every command ends its output with "#done".
//       help                         this list
//       module                       which selector position is active (A7)
//       circuits                     touch-panel button pressed and its node voltage
//       divider                      voltage at the divider output A1
//       temperature                  temperature of the thermistor divider on A1
//                                    (10 kOhm NTC, beta 3950, on top; 10 kOhm below)
//       diodes                       diode I-V sweep: V_DAC, V_D, I_D (mA)
//       transistors                  MOSFET output curves: V_GS steps of 0.1 V
//                                    from 1.2 to 2.0 V, V_DAC2 swept 0 to 3.3 V;
//                                    prints V_GS, V_DS, I_D (mA)
//       transfer                     MOSFET transfer curve: V_DAC2 = 3.3 V,
//                                    V_GS swept 0 to 3.3 V; prints V_GS, V_DS, I_D
//       light                        LED pair 1 on, photodiode reading (A6)
//       sensors                      red and infrared PPG from the MAX86916
//       communications send <text>   send text over light (LED pair 2), once a second
//       communications receive       print text received by the photodiode (A6)
//       stop                         stop the running command (also "e" or "exit")
//     The names of the first board sketch (m1na, m1vd, m2d, m2draw,
//     m2tran_vds, m2tran_vgs, m3led, m3pdcurrent, m3stepled, m3ppg,
//     show_pd, lifi_tx, lifi_rx) still work and run the commands above.
//
//  2. Notebook commands (used by the ee105 Python package). Every reply
//     ends with the line "#done" (or "#err <reason>"). Data lines are
//     plain numbers separated by commas; "#cols a,b,c" names the columns.
//       id                                   firmware name and version, board ID
//       read  <pin> <n> <interval_us>        n ADC samples of A<pin>  -> t_us,raw
//       stream <pin> <interval_us>           like read, until you send "stop"
//       dac   <ch> <code>                    set AD5593R DAC channel (code 0..4095)
//       zero                                 all DAC channels to 0 V
//       sweep <ch> <c0> <c1> <step> <pin> <settle_ms> [avg]
//                                            step one DAC, read A<pin>  -> code,raw
//       sweep2 <chA> <a0> <a1> <astep> <chB> <b0> <b1> <bstep> <pin> <settle_ms> [avg]
//                                            outer DAC A, inner DAC B   -> codeA,codeB,raw
//       ppg   <n> [amplitude]                MAX86916 samples           -> t_us,ir,red
//       cap   <pin> <n> <interval_us> [trigger]
//                                            fast capture into memory, then print
//       txclear | txadd <digits> | txgo <ch> <period_us> <L0> [L1 L2 L3]
//                                            send a symbol stream on a DAC channel
//       txcap <ch> <period_us> <pin> <samples_per_symbol> <L0> [L1 L2 L3]
//                                            send the symbols and record A<pin> at
//                                            the same time (one-board loopback test)
//       i2c   <hz>                           I2C clock (default 100000)
//       button <pin>                         wait for a touch-panel press
//       module                               (same command as above)
//
//  Board (black board, rev 1.1). The silkscreen calls the blocks
//  "Module 1/2/3"; the course calls them the circuits, devices and
//  biosensing blocks. Selector S10 powers one block at a time.
//    A0 circuits block, touch network (through J7, Module 1 end, pins 2-3)
//    A1 circuits block, divider header midpoint J2/J3 (through J8, Module 1 end, pins 2-3)
//    A2 devices block, diode: difference amp across the 1 kOhm sense resistor
//    A3 devices block, MOSFET: difference amp across the 1 kOhm drain resistor
//       (drain fed from DAC channel 2 through 1 kOhm, source grounded), so
//       I_D in mA = V_A3 in V and V_DS = V_DAC2 - V_A3
//    A6 biosensing block, photodiode TIA (J5 on P1-A: pair 1, J5 on A-P2: pair 2, RX)
//    A7 selector S10 resistor ladder, measured on one board: 1.8 to 1.9 V (Module 1),
//       0.84 to 0.94 V (Module 2), 0.65 V (Module 3), 0.31 V (Camera), near 0 V (nothing selected); varies by board
//  AD5593R DAC (I2C 0x10): ch0 diode, ch1 MOSFET gate, ch2 MOSFET drain
//    supply, ch3 LED pair 1, ch4 LED pair 2 (communication LED)
//  MAX86916 optical sensor (I2C 0x57): red and infrared PPG.
// =====================================================================

#include <Arduino.h>
#include <Wire.h>
#include <math.h>
#include "AD5593R.h"
#include "MAX86916_eda.h"

#define FW_NAME    "ee105"
#define FW_VERSION "3.2"

// ---- pins and DAC channels -------------------------------------------
#define pin_touch A0
#define pin_divider A1
#define pin_diode A2
#define pin_nmos A3
#define pin_pd A6
#define pin_selector A7

#define dac_diode 0
#define dac_nmos_gate 1
#define dac_nmos_drain 2
#define dac_led1 3
#define dac_led2 4
#define N_DAC 5

#define dac_3p3v 2000          // DAC code for about 3.3 V
#define adc_volts (3.3 / 1024.0)   // V per ADC count
#define dac_volts 0.00165      // V per DAC code
#define ref_voltage 3.3

#define R_FIXED 10000.0        // thermistor divider: bottom resistor (ohm)
#define R0_NTC 10000.0         // thermistor: 10 kOhm at 25 C
#define BETA_NTC 3950.0        // thermistor beta (K)
#define TIA_OHMS 3.0e6         // photodiode transimpedance (ohm)

#define PERIOD 3               // LiFi text: bit period (ms)
#define THRESHOLD 200          // LiFi text: photodiode threshold (counts)

MAX86916_eda ppg;
bool ppg_ready = false;

// ---- capture and transmit buffers -------------------------------------
#define CAP_MAX 40000
uint16_t cap_buf[CAP_MAX];
#define TX_MAX 20000
char tx_buf[TX_MAX + 1];
int tx_len = 0;

// ---- small helpers ------------------------------------------------------
const int analogPins[8] = {A0, A1, A2, A3, A4, A5, A6, A7};

void done() { Serial.println("#done"); }
void err(const char *why) { Serial.print("#err "); Serial.println(why); }

bool is_stop(String s) {
  s.trim();
  s.toLowerCase();
  return s == "stop" || s == "e" || s == "exit";
}

// Returns true if the host sent "stop" (or "e", "exit"): stop the running command.
bool stop_requested() {
  while (Serial.available()) {
    String s = Serial.readStringUntil('\n');
    if (is_stop(s)) return true;
  }
  return false;
}

// delay() that returns early (true) when a stop arrives.
bool wait_or_stop(unsigned long ms) {
  unsigned long t0 = millis();
  while (millis() - t0 < ms) {
    if (stop_requested()) return true;
    delay(2);
  }
  return false;
}

int split(String line, String *tok, int maxTok) {
  int n = 0;
  line.trim();
  while (line.length() > 0 && n < maxTok) {
    int sp = line.indexOf(' ');
    if (sp < 0) { tok[n++] = line; break; }
    tok[n++] = line.substring(0, sp);
    line = line.substring(sp + 1);
    line.trim();
  }
  return n;
}

bool pin_ok(long p) { return p >= 0 && p <= 7; }
bool ch_ok(long c) { return c >= 0 && c < N_DAC; }
uint16_t clamp_code(long c) { return (uint16_t)constrain(c, 0, 4095); }

int read_avg(int pin, int avg) {
  long sum = 0;
  for (int i = 0; i < avg; i++) sum += analogRead(analogPins[pin]);
  return (int)((sum + avg / 2) / avg);   // rounded average
}

float read_volts(int pin, int avg) {
  long sum = 0;
  for (int i = 0; i < avg; i++) sum += analogRead(analogPins[pin]);
  return (float)sum / avg * adc_volts;
}

void print_hex32(uint32_t v) {
  for (int s = 28; s >= 0; s -= 4) Serial.print("0123456789ABCDEF"[(v >> s) & 0xF]);
}

void dac_setup() {
  initADAC(0x10, 1, 1);
  setDACGain(1);
  setDACpin(dac_diode);
  setDACpin(dac_nmos_gate);
  setDACpin(dac_nmos_drain);
  setDACpin(dac_led1);
  setDACpin(dac_led2);
}

void reset_dac() {
  for (int ch = 0; ch < N_DAC; ch++) setDACVal(ch, 0);
}

void ppg_start(int amp) {
  if (!ppg_ready) {
    ppg.begin();
    ppg.setup();
    ppg_ready = true;
  }
  ppg.setPulseAmplitudeRed(amp);
  ppg.setPulseAmplitudeIR(amp);
  ppg.setPulseAmplitudeGreen(amp);
  ppg.setPulseAmplitudeBlue(amp);
}

// =====================================================================
void setup() {
  Wire.begin();
  Serial.begin(115200);
  Serial.setTimeout(2000);
  dac_setup();
  reset_dac();
}

void loop() {
  if (!Serial.available()) return;
  String line = Serial.readStringUntil('\n');
  line.trim();
  if (line.length() == 0) return;

  String t[14];
  int n = split(line, t, 14);
  String c = t[0];
  c.toLowerCase();

  // ------------------------------------------------ notebook commands
  if (c == "id") {
    Serial.print("#"); Serial.print(FW_NAME); Serial.print(" "); Serial.println(FW_VERSION);
    Serial.print("#device_id ");
    print_hex32(NRF_FICR->DEVICEID[1]);
    print_hex32(NRF_FICR->DEVICEID[0]);
    Serial.println();
    done();
  } else if (c == "read" || c == "stream") {
    cmd_read(t, n, c == "stream");
  } else if (c == "dac") {
    if (n < 3 || !ch_ok(t[1].toInt())) { err("usage: dac <ch 0-4> <code 0-4095>"); return; }
    setDACVal(t[1].toInt(), clamp_code(t[2].toInt()));
    done();
  } else if (c == "zero") {
    reset_dac();
    done();
  } else if (c == "sweep") {
    cmd_sweep(t, n);
  } else if (c == "sweep2") {
    cmd_sweep2(t, n);
  } else if (c == "ppg") {
    cmd_ppg(t, n);
  } else if (c == "cap") {
    cmd_cap(t, n);
  } else if (c == "txclear") {
    tx_len = 0;
    done();
  } else if (c == "txadd") {
    if (n < 2) { err("usage: txadd <digits 0-3>"); return; }
    for (unsigned int i = 0; i < t[1].length() && tx_len < TX_MAX; i++) {
      char d = t[1].charAt(i);
      if (d >= '0' && d <= '3') tx_buf[tx_len++] = d;
    }
    Serial.print("#len "); Serial.println(tx_len);
    done();
  } else if (c == "txgo") {
    cmd_txgo(t, n);
  } else if (c == "txcap") {
    cmd_txcap(t, n);
  } else if (c == "i2c") {
    long hz = (n >= 2) ? t[1].toInt() : 0;
    if (hz < 10000 || hz > 1000000) { err("usage: i2c <hz 10000-1000000>"); return; }
    Wire.setClock(hz);
    done();
  } else if (c == "button") {
    cmd_button(t, n);
  }
  // ------------------------------------------------ commands you can type
  // (the names after the first one are the old names, kept as aliases)
  else if (c == "help") cmd_help();
  else if (c == "module") cmd_module();
  else if (c == "circuits" || c == "m1na") cmd_circuits();
  else if (c == "divider" || c == "m1vd") cmd_divider();
  else if (c == "temperature") cmd_temperature();
  else if (c == "diodes" || c == "m2d" || c == "m2draw") cmd_diodes();
  else if (c == "transistors" || c == "m2tran_vds") cmd_transistors();
  else if (c == "transfer" || c == "m2tran_vgs") cmd_transfer();
  else if (c == "light" || c == "m3pdcurrent" || c == "show_pd" || c == "m3led" || c == "m3stepled") cmd_light();
  else if (c == "sensors" || c == "m3ppg") cmd_sensors();
  else if (c == "communications") {
    String sub = (n >= 2) ? t[1] : "";
    sub.toLowerCase();
    if (sub == "send") {
      int at = line.indexOf(' ');               // text = everything after "communications send "
      String rest = line.substring(at + 1);
      rest.trim();
      at = rest.indexOf(' ');
      String text = (at < 0) ? "" : rest.substring(at + 1);
      text.trim();
      comm_send(text);
    } else if (sub == "receive") {
      comm_receive();
    } else {
      err("usage: communications send <text>  |  communications receive");
    }
  }
  else if (c == "lifi_tx") comm_send("");
  else if (c == "lifi_rx") comm_receive();
  else if (is_stop(c)) { reset_dac(); done(); }
  else {
    Serial.print("#err unknown command: ");
    Serial.print(c);
    Serial.println(" (type help for the list)");
  }
}

// =====================================================================
//  Notebook commands
// =====================================================================

// read <pin> <n> <interval_us>   /  stream <pin> <interval_us>
void cmd_read(String *t, int n, bool streaming) {
  long pin = t[1].toInt();
  long count = streaming ? -1 : t[2].toInt();
  long dt = streaming ? t[2].toInt() : t[3].toInt();
  if (n < (streaming ? 3 : 4) || !pin_ok(pin) || dt < 50) {
    err(streaming ? "usage: stream <pin 0-7> <interval_us >= 50>" : "usage: read <pin 0-7> <n> <interval_us >= 50>");
    return;
  }
  Serial.println("#cols t_us,raw");
  unsigned long t0 = micros();
  unsigned long next = t0;
  long i = 0;
  while (count < 0 || i < count) {
    while ((long)(micros() - next) < 0) {}
    unsigned long now = micros();
    int v = analogRead(analogPins[pin]);
    Serial.print(now - t0); Serial.print(','); Serial.println(v);
    next += dt;
    i++;
    if ((i & 31) == 0 && stop_requested()) { Serial.println("#stopped"); break; }
  }
  done();
}

// sweep <ch> <c0> <c1> <step> <pin> <settle_ms> [avg]
void cmd_sweep(String *t, int n) {
  if (n < 7) { err("usage: sweep <ch> <c0> <c1> <step> <pin> <settle_ms> [avg]"); return; }
  long ch = t[1].toInt(), c0 = t[2].toInt(), c1 = t[3].toInt(), step = t[4].toInt();
  long pin = t[5].toInt(), settle = t[6].toInt();
  int avg = (n >= 8) ? max(1L, t[7].toInt()) : 1;
  if (!ch_ok(ch) || !pin_ok(pin) || step <= 0) { err("bad channel, pin or step"); return; }
  Serial.println("#cols code,raw");
  for (long code = c0; code <= c1; code += step) {
    setDACVal(ch, clamp_code(code));
    delay(settle);
    Serial.print(code); Serial.print(','); Serial.println(read_avg(pin, avg));
    if (stop_requested()) { Serial.println("#stopped"); break; }
  }
  setDACVal(ch, 0);
  done();
}

// sweep2 <chA> <a0> <a1> <astep> <chB> <b0> <b1> <bstep> <pin> <settle_ms> [avg]
void cmd_sweep2(String *t, int n) {
  if (n < 11) { err("usage: sweep2 <chA> <a0> <a1> <astep> <chB> <b0> <b1> <bstep> <pin> <settle_ms> [avg]"); return; }
  long chA = t[1].toInt(), a0 = t[2].toInt(), a1 = t[3].toInt(), as = t[4].toInt();
  long chB = t[5].toInt(), b0 = t[6].toInt(), b1 = t[7].toInt(), bs = t[8].toInt();
  long pin = t[9].toInt(), settle = t[10].toInt();
  int avg = (n >= 12) ? max(1L, t[11].toInt()) : 1;
  if (!ch_ok(chA) || !ch_ok(chB) || !pin_ok(pin) || as <= 0 || bs <= 0) { err("bad channel, pin or step"); return; }
  Serial.println("#cols codeA,codeB,raw");
  bool stopped = false;
  for (long a = a0; a <= a1 && !stopped; a += as) {
    setDACVal(chA, clamp_code(a));
    for (long b = b0; b <= b1; b += bs) {
      setDACVal(chB, clamp_code(b));
      delay(settle);
      Serial.print(a); Serial.print(','); Serial.print(b); Serial.print(','); Serial.println(read_avg(pin, avg));
      if (stop_requested()) { stopped = true; Serial.println("#stopped"); break; }
    }
  }
  setDACVal(chA, 0);
  setDACVal(chB, 0);
  done();
}

// ppg <n> [amplitude 0-255]
void cmd_ppg(String *t, int n) {
  if (n < 2) { err("usage: ppg <n> [amplitude 0-255]"); return; }
  long count = t[1].toInt();
  int amp = (n >= 3) ? constrain(t[2].toInt(), 0, 255) : 0x7F;
  ppg_start(amp);
  Serial.println("#cols t_us,ir,red");
  unsigned long t0 = micros();
  for (long i = 0; i < count; i++) {
    // getIR() and getRed() each wait for a new FIFO sample, so the two values are about one sample
    // apart (a few ms), which does not matter at PPG frequencies.
    uint32_t ir = ppg.getIR();
    uint32_t red = ppg.getRed();
    Serial.print(micros() - t0); Serial.print(','); Serial.print(ir); Serial.print(','); Serial.println(red);
    if ((i & 15) == 0 && stop_requested()) { Serial.println("#stopped"); break; }
  }
  done();
}

// cap <pin> <n> <interval_us> [trigger_raw]
//  Samples into memory at an exact interval (no serial traffic while
//  sampling), then prints 16 values per line. With a trigger level the
//  capture starts the first time the input rises above it.
void cmd_cap(String *t, int n) {
  if (n < 4) { err("usage: cap <pin> <n> <interval_us> [trigger_raw]"); return; }
  long pin = t[1].toInt(), count = t[2].toInt(), dt = t[3].toInt();
  long trig = (n >= 5) ? t[4].toInt() : -1;
  if (!pin_ok(pin) || count < 1 || count > CAP_MAX || dt < 20) { err("bad pin, n (1-40000) or interval (>= 20 us)"); return; }
  if (trig >= 0) {
    Serial.println("#waiting for trigger");
    unsigned long tw = millis();
    while (analogRead(analogPins[pin]) <= trig) {
      if (millis() - tw > 30000) { err("no signal above the trigger level within 30 s"); return; }
      if (stop_requested()) { Serial.println("#stopped"); done(); return; }
    }
  }
  unsigned long next = micros();
  unsigned long t0 = next;
  for (long i = 0; i < count; i++) {
    while ((long)(micros() - next) < 0) {}
    cap_buf[i] = analogRead(analogPins[pin]);
    next += dt;
  }
  unsigned long elapsed = micros() - t0;
  print_cap(count, (float)elapsed / count);
}

// Prints the capture buffer: interval, column name, then 16 values per line.
void print_cap(long count, float interval_us) {
  Serial.print("#interval_us "); Serial.println(interval_us, 3);
  Serial.println("#cols raw");
  for (long i = 0; i < count; i++) {
    Serial.print(cap_buf[i]);
    Serial.print(((i % 16) == 15 || i == count - 1) ? '\n' : ',');
  }
  done();
}

// txgo <ch> <period_us> <L0> [L1 L2 L3]
//  Plays the symbols added with txadd (digits 0-3) on DAC channel ch, one
//  symbol every period_us. Symbol k sets the DAC to code Lk.
void cmd_txgo(String *t, int n) {
  if (n < 4) { err("usage: txgo <ch> <period_us> <L0> [L1 L2 L3]"); return; }
  long ch = t[1].toInt(), period = t[2].toInt();
  if (!ch_ok(ch) || period < 500) { err("bad channel or period (>= 500 us)"); return; }
  uint16_t lev[4] = {0, 0, 0, 0};
  int nlev = min(4, n - 3);
  for (int k = 0; k < nlev; k++) lev[k] = clamp_code(t[3 + k].toInt());
  Serial.print("#sending "); Serial.print(tx_len); Serial.println(" symbols");
  unsigned long next = micros();
  for (int i = 0; i < tx_len; i++) {
    int s = tx_buf[i] - '0';
    if (s >= nlev) s = nlev - 1;
    while ((long)(micros() - next) < 0) {}
    setDACVal(ch, lev[s]);
    next += period;
  }
  while ((long)(micros() - next) < 0) {}
  setDACVal(ch, 0);
  done();
}

// txcap <ch> <period_us> <pin> <samples_per_symbol> <L0> [L1 L2 L3]
//  Loopback test with one board: plays the txadd symbols on DAC channel ch
//  (use channel 3, the LED pair that faces the board's own photodiode) and
//  samples A<pin> samples_per_symbol times, evenly spread over every symbol.
void cmd_txcap(String *t, int n) {
  if (n < 6) { err("usage: txcap <ch> <period_us> <pin> <samples_per_symbol> <L0> [L1 L2 L3]"); return; }
  long ch = t[1].toInt(), period = t[2].toInt(), pin = t[3].toInt(), sps = t[4].toInt();
  if (!ch_ok(ch) || !pin_ok(pin) || period < 500 || sps < 1 || sps > 32) {
    err("bad channel, pin, period (>= 500 us) or samples_per_symbol (1-32)");
    return;
  }
  long count = (long)tx_len * sps;
  if (count < 1 || count > CAP_MAX) { err("symbols x samples_per_symbol must be 1 to 40000"); return; }
  uint16_t lev[4] = {0, 0, 0, 0};
  int nlev = min(4, n - 5);
  for (int k = 0; k < nlev; k++) lev[k] = clamp_code(t[5 + k].toInt());
  unsigned long t0 = micros() + 1000;
  for (int i = 0; i < tx_len; i++) {
    int s = tx_buf[i] - '0';
    if (s >= nlev) s = nlev - 1;
    unsigned long ts = t0 + (unsigned long)i * period;
    while ((long)(micros() - ts) < 0) {}
    setDACVal(ch, lev[s]);
    for (int j = 0; j < sps; j++) {
      unsigned long tj = ts + (unsigned long)((2 * j + 1) * period / (2 * sps));
      while ((long)(micros() - tj) < 0) {}
      cap_buf[(long)i * sps + j] = analogRead(analogPins[pin]);
    }
  }
  unsigned long t_end = t0 + (unsigned long)tx_len * period;
  while ((long)(micros() - t_end) < 0) {}
  setDACVal(ch, 0);
  print_cap(count, (float)period / sps);
}

// button <pin>: waits up to 20 s for a press on the touch panel network
// (input leaves its idle level), then reports the settled reading.
void cmd_button(String *t, int n) {
  long pin = (n >= 2) ? t[1].toInt() : 0;
  if (!pin_ok(pin)) { err("usage: button <pin 0-7>"); return; }
  int idle = read_avg(pin, 16);
  Serial.print("#idle "); Serial.println(idle);
  unsigned long tw = millis();
  while (abs(read_avg(pin, 4) - idle) < 20) {
    if (millis() - tw > 20000) { err("no press within 20 s"); return; }
    if (stop_requested()) { Serial.println("#stopped"); done(); return; }
    delay(5);
  }
  delay(30);  // let the contact settle
  Serial.println("#cols raw");
  Serial.println(read_avg(pin, 32));
  done();
}

// =====================================================================
//  Commands you can type
// =====================================================================

void cmd_help() {
  Serial.println("EE 105 demo board, firmware " FW_VERSION ". Commands:");
  Serial.println("  module                      which selector position is active");
  Serial.println("  circuits                    touch-panel button and its node voltage (S10 on Module 1, J7/J8 caps on Module 1 end)");
  Serial.println("  divider                     voltage at the divider output A1 (S10 on Module 1, J7/J8 caps on Module 1 end)");
  Serial.println("  temperature                 thermistor temperature from the divider (S10 on Module 1, J7/J8 caps on Module 1 end)");
  Serial.println("  diodes                      diode I-V sweep: V_DAC, V_D, I_D (S10 on Module 2)");
  Serial.println("  transistors                 MOSFET output curves: V_GS, V_DS, I_D (S10 on Module 2)");
  Serial.println("  transfer                    MOSFET transfer curve: V_GS, V_DS, I_D (S10 on Module 2)");
  Serial.println("  light                       LED pair 1 on, photodiode reading (S10 on Module 3, J5 on P1-A)");
  Serial.println("  sensors                     red and infrared PPG (S10 on Module 3)");
  Serial.println("  communications send <text>  send text over light from TX, once a second (S10 on Module 3)");
  Serial.println("  communications receive      print the text received by RX (S10 on Module 3, J5 on A-P2)");
  Serial.println("  stop                        stop the running command");
  Serial.println("  help                        this list");
  done();
}

// ---- module selector ----------------------------------------------------
// The selector S10 feeds A7 from a resistor ladder (0.5, 1, 2, 3 MOhm from the four rails,
// 1 MOhm to ground). With the blocks that are off drawing nothing it would give 2.20, 1.65,
// 1.10 and 0.83 V; on a real board those blocks load the ladder and the readings are lower
// and vary from board to board. This is a best guess from readings measured on a real board
// (1.85, 0.89, 0.65, 0.31 V); the notebooks check a wide range per position and only warn.
int selector_position(float v) {      // 1, 2, 3, 4 = CAM, 0 = none, -1 = unexpected
  if (v > 2.90) return -1;
  if (v < 0.12) return 0;
  if (v > 1.37) return 1;
  if (v > 0.77) return 2;
  if (v > 0.48) return 3;
  return 4;
}

void cmd_module() {
  float v = read_volts(7, 16);
  int p = selector_position(v);
  Serial.print("selector: ");
  if (p == 1) Serial.print("1 = Module 1 (circuits) ");
  else if (p == 2) Serial.print("2 = Module 2 (devices) ");
  else if (p == 3) Serial.print("3 = Module 3 (biosensing) ");
  else if (p == 4) Serial.print("CAM = Camera ");
  else if (p == 0) Serial.print("none (no block selected) ");
  else Serial.print("unknown (unexpected voltage) ");
  Serial.print(v, 2);
  Serial.println(" V");
  done();
}

// ---- circuits block -------------------------------------------------------
// Network 1 node voltages (nodal analysis) as 10-bit codes, sorted from low to high.
const char *node_name[9] = {"S9", "S6", "S3", "S8", "S5", "S2", "S7", "S4", "S1"};
const int node_code[9]   = {0, 249, 368, 420, 512, 604, 656, 775, 1023};
#define STEADY_COUNTS 26        // largest 20 ms spread of a held button (about 85 mV)

void cmd_circuits() {
  Serial.println("circuits: press a button on the touch panel (S10 on Module 1, J7 and J8 caps on the Module 1 end). Send stop to end.");
  while (true) {
    int lo = 1023, hi = 0;
    long sum = 0;
    for (int i = 0; i < 10; i++) {            // 10 readings over 20 ms: longer than one 60 Hz period
      int v = analogRead(pin_touch);
      lo = min(lo, v);
      hi = max(hi, v);
      sum += v;
      delay(2);
    }
    float mean = sum / 10.0;
    if (hi - lo > STEADY_COUNTS) {
      Serial.println("no button  (A0 is floating)");
    } else {
      int k = 0;                               // nearest node: thresholds halfway between neighbors
      while (k < 8 && mean > (node_code[k] + node_code[k + 1]) / 2.0) k++;
      Serial.print(node_name[k]);
      Serial.print("  ");
      Serial.print(mean * adc_volts, 3);
      Serial.println(" V");
    }
    if (wait_or_stop(180)) break;
  }
  done();
}

void cmd_divider() {
  Serial.println("divider: voltage at the divider output A1 (S10 on Module 1, J7 and J8 caps on the Module 1 end). Send stop to end.");
  while (true) {
    Serial.print("A1 = ");
    Serial.print(read_volts(1, 16), 3);
    Serial.println(" V");
    if (wait_or_stop(250)) break;
  }
  done();
}

void cmd_temperature() {
  Serial.println("temperature: 10 kOhm NTC thermistor (beta 3950) in J1-J2, 10 kOhm in J3-J4 "
                 "(S10 on Module 1, J7 and J8 caps on the Module 1 end). Send stop to end.");
  while (true) {
    float v = read_volts(1, 32);
    Serial.print("A1 = ");
    Serial.print(v, 3);
    Serial.print(" V");
    if (v < 0.05 || v > 3.25) {
      Serial.println("   no thermistor divider? Check the parts in J1-J4 and the J7/J8 caps.");
    } else {
      float r_t = R_FIXED * (ref_voltage / v - 1.0);              // thermistor on top
      float t_k = 1.0 / (1.0 / 298.15 + log(r_t / R0_NTC) / BETA_NTC);
      Serial.print("   R_T = ");
      Serial.print(r_t / 1000.0, 2);
      Serial.print(" kOhm   T = ");
      Serial.print(t_k - 273.15, 1);
      Serial.println(" C");
    }
    if (wait_or_stop(500)) break;
  }
  done();
}

// ---- devices block --------------------------------------------------------
void cmd_diodes() {
  Serial.println("diodes: diode I-V sweep (S10 on Module 2). Columns: V_DAC (V), V_D (V), I_D (mA)");
  for (int code = 0; code <= dac_3p3v; code += 10) {
    setDACVal(dac_diode, code);
    delay(2);
    float v_r = read_volts(2, 4);              // sense resistor voltage: 1 V per mA (1 kOhm)
    float v_dac = code * dac_volts;
    Serial.print(v_dac, 3); Serial.print(", ");
    Serial.print(v_dac - v_r, 3); Serial.print(", ");
    Serial.println(v_r, 3);
    if (stop_requested()) break;
  }
  setDACVal(dac_diode, 0);
  done();
}

// MOSFET: drain supply V_DAC2 through 1 kOhm, A3 = I_D x 1 kOhm, V_DS = V_DAC2 - V_A3.
void print_nmos(int gate_code, int drain_code) {
  float v_a3 = read_volts(3, 4);               // I_D in mA
  float v_ds = drain_code * dac_volts - v_a3;
  Serial.print(gate_code * dac_volts, 3); Serial.print(", ");
  Serial.print(v_ds, 3); Serial.print(", ");
  Serial.println(v_a3, 3);
}

void cmd_transistors() {
  Serial.println("transistors: MOSFET output curves (S10 on Module 2). Columns: V_GS (V), V_DS (V), I_D (mA)");
  bool stopped = false;
  for (int k = 0; k <= 8 && !stopped; k++) {   // V_GS = 1.2, 1.3, ... 2.0 V
    int gate = (int)((1.2 + 0.1 * k) / dac_volts + 0.5);
    setDACVal(dac_nmos_gate, gate);
    for (int d = 0; d <= dac_3p3v; d += 20) {  // V_DAC2 = 0 to 3.3 V in 33 mV steps
      setDACVal(dac_nmos_drain, d);
      delay(2);
      print_nmos(gate, d);
      if (stop_requested()) { stopped = true; break; }
    }
    setDACVal(dac_nmos_drain, 0);
  }
  reset_dac();
  done();
}

void cmd_transfer() {
  Serial.println("transfer: MOSFET transfer curve, V_DAC2 = 3.3 V (S10 on Module 2). Columns: V_GS (V), V_DS (V), I_D (mA)");
  setDACVal(dac_nmos_drain, dac_3p3v);
  for (int g = 0; g <= dac_3p3v; g += 10) {    // V_GS = 0 to 3.3 V in 16.5 mV steps
    setDACVal(dac_nmos_gate, g);
    delay(2);
    print_nmos(g, dac_3p3v);
    if (stop_requested()) break;
  }
  reset_dac();
  done();
}

// ---- biosensing block -----------------------------------------------------
void cmd_light() {
  Serial.println("light: LED pair 1 on, photodiode on A6 (S10 on Module 3, J5 on P1-A). Send stop to end.");
  setDACVal(dac_led1, dac_3p3v);
  while (true) {
    float v = read_volts(6, 16);
    Serial.print("A6 = ");
    Serial.print(v / adc_volts, 0);
    Serial.print(" counts = ");
    Serial.print(v, 3);
    Serial.print(" V, photocurrent ");
    Serial.print(v / TIA_OHMS * 1e9, 0);
    Serial.println(" nA");
    if (wait_or_stop(250)) break;
  }
  setDACVal(dac_led1, 0);
  done();
}

void cmd_sensors() {
  Serial.println("sensors: red and infrared PPG from the MAX86916 (S10 on Module 3). Send stop to end.");
  ppg_start(0x7F);
  while (true) {
    uint32_t ir = ppg.getIR();
    uint32_t red = ppg.getRed();
    Serial.print("red:"); Serial.print(red);
    Serial.print(",ir:"); Serial.println(ir);
    if (stop_requested()) break;
  }
  done();
}

// ---- communication: text over light ---------------------------------------
// One character = 10 slots of PERIOD ms on LED pair 2: start slot (off),
// 8 data bits least significant bit first (on = 1), stop slot (on).
void send_byte(char b) {
  setDACVal(dac_led2, 0);
  delay(PERIOD);
  for (int i = 0; i < 8; i++) {
    setDACVal(dac_led2, (b & (0x01 << i)) ? dac_3p3v : 0);
    delay(PERIOD);
  }
  setDACVal(dac_led2, dac_3p3v);
  delay(PERIOD);
}

void comm_send(String text) {
  if (text.length() == 0) text = "This is a test transmission!";
  if (text.length() > 200) text = text.substring(0, 200);
  Serial.print("communications send: \"");
  Serial.print(text);
  Serial.println("\" once a second on LED pair 2 (S10 on Module 3). Send stop to end.");
  text += "\n";
  bool stopped = false;
  while (!stopped) {
    for (unsigned int i = 0; i < text.length(); i++) {
      send_byte(text.charAt(i));
      if (stop_requested()) { stopped = true; break; }
    }
    if (!stopped) stopped = wait_or_stop(1000);
  }
  setDACVal(dac_led2, 0);
  done();
}

bool light_on() { return analogRead(pin_pd) > THRESHOLD; }

char get_byte() {
  char ret = 0;
  delay(PERIOD * 1.5);                          // from the start edge to the middle of bit 0
  for (int i = 0; i < 8; i++) {
    ret = ret | (light_on() << i);
    delay(PERIOD);
  }
  return ret;
}

void comm_receive() {
  Serial.println("communications receive: text from photodiode pair 2 (S10 on Module 3, J5 on A-P2). Send stop to end.");
  bool previous = false;
  unsigned long n = 0;
  while (true) {
    bool current = light_on();
    if (!current && previous) Serial.print(get_byte());   // on-to-off edge: a start slot
    previous = current;
    if ((++n & 63) == 0 && stop_requested()) break;
  }
  Serial.println();
  done();
}
