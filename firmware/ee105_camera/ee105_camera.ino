// =====================================================================
//  EE 105 camera firmware  (Arduino Nano 33 BLE Sense on the demo board,
//  OV7675 camera on header J6; selector S10 on Camera, both caps of jumpers
//  J7 and J8 on the Camera end, pins 1-2, so the camera reaches A0 and A1)
//  The Lab 4.2 notebook uploads this sketch for you and asks it for
//  pictures over USB serial. Commands (one per line, replies end "#done"):
//    id                      firmware name and version, board ID
//    module                  which selector position is active (A7)
//    snap [width] [height]   one grayscale picture, scaled to width x height
//                            (default 160 x 120, at most 320 x 240), sent as
//                            "#size w h" and one line of base64 (row by row)
//    test 0|1                camera test pattern off / on
//  After the lab, put J7 and J8 back on the Module 1 end (pins 2-3).
//  The OV767X camera library (GPL-2.0, Arduino SA) is included in src/, so
//  no library has to be installed.
// =====================================================================

#include <Arduino.h>
#include "src/Arduino_OV767X/Arduino_OV767X.h"

#define FW_NAME    "ee105cam"
#define FW_VERSION "2.2"

static uint8_t *frame = NULL;      // full QVGA frame from the camera
static bool cam_ok = false;
static const char B64[] = "ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789+/";

void setup() {
  Serial.begin(115200);
  cam_ok = Camera.begin(QVGA, GRAYSCALE, 5, OV7675);
  if (cam_ok) {
    frame = (uint8_t *)malloc(Camera.width() * Camera.height() * Camera.bytesPerPixel());
    if (!frame) cam_ok = false;
  }
  if (cam_ok) Camera.readFrame(frame);   // the first frame after power-up is often dark
}

// Writes base64 for a stream of bytes, a few at a time.
static char outbuf[256];
static int outlen = 0;
static uint8_t trip[3];
static int ntrip = 0;

void b64_flush() {
  if (outlen) Serial.write((const uint8_t *)outbuf, outlen);
  outlen = 0;
}

void b64_put(uint8_t b) {
  trip[ntrip++] = b;
  if (ntrip == 3) {
    outbuf[outlen++] = B64[trip[0] >> 2];
    outbuf[outlen++] = B64[((trip[0] & 3) << 4) | (trip[1] >> 4)];
    outbuf[outlen++] = B64[((trip[1] & 15) << 2) | (trip[2] >> 6)];
    outbuf[outlen++] = B64[trip[2] & 63];
    ntrip = 0;
    if (outlen > 250) b64_flush();
  }
}

void b64_end() {
  if (ntrip == 1) {
    outbuf[outlen++] = B64[trip[0] >> 2];
    outbuf[outlen++] = B64[(trip[0] & 3) << 4];
    outbuf[outlen++] = '=';
    outbuf[outlen++] = '=';
  } else if (ntrip == 2) {
    outbuf[outlen++] = B64[trip[0] >> 2];
    outbuf[outlen++] = B64[((trip[0] & 3) << 4) | (trip[1] >> 4)];
    outbuf[outlen++] = B64[(trip[1] & 15) << 2];
    outbuf[outlen++] = '=';
  }
  ntrip = 0;
  b64_flush();
  Serial.println();
}

void snap(int w, int h) {
  int W = Camera.width(), H = Camera.height(), bpp = Camera.bytesPerPixel();
  Camera.readFrame(frame);
  Serial.print("#size "); Serial.print(w); Serial.print(' '); Serial.println(h);
  for (int y = 0; y < h; y++) {
    int sy = (int)((long)y * H / h);
    for (int x = 0; x < w; x++) {
      int sx = (int)((long)x * W / w);
      b64_put(frame[bpp * (sy * W + sx)]);   // grayscale: the first byte of each pixel
    }
  }
  b64_end();
}

void print_hex32(uint32_t v) {
  for (int s = 28; s >= 0; s -= 4) Serial.print("0123456789ABCDEF"[(v >> s) & 0xF]);
}

// Selector S10 on A7, a resistor ladder whose readings vary from board to board. Best guess
// from readings measured on a real board: 1.85 V (Module 1), 0.89 V (Module 2), 0.65 V
// (Module 3), 0.31 V (Camera), about 0 V (none); the notebooks check a wide range and only warn.
void cmd_module() {
  long sum = 0;
  for (int i = 0; i < 16; i++) sum += analogRead(A7);
  float v = sum / 16.0 * 3.3 / 1024.0;
  Serial.print("selector: ");
  if (v > 2.90) Serial.print("unknown (unexpected voltage) ");
  else if (v < 0.12) Serial.print("none (no block selected) ");
  else if (v > 1.37) Serial.print("1 = Module 1 (circuits) ");
  else if (v > 0.77) Serial.print("2 = Module 2 (devices) ");
  else if (v > 0.48) Serial.print("3 = Module 3 (biosensing) ");
  else Serial.print("CAM = Camera ");
  Serial.print(v, 2);
  Serial.println(" V");
  Serial.println("#done");
}

void loop() {
  if (!Serial.available()) return;
  String line = Serial.readStringUntil('\n');
  line.trim();
  if (line.length() == 0) return;
  int sp = line.indexOf(' ');
  String c = sp < 0 ? line : line.substring(0, sp);
  String rest = sp < 0 ? "" : line.substring(sp + 1);
  rest.trim();

  if (c == "id") {
    Serial.print("#"); Serial.print(FW_NAME); Serial.print(" "); Serial.println(FW_VERSION);
    Serial.print("#device_id ");
    print_hex32(NRF_FICR->DEVICEID[1]);
    print_hex32(NRF_FICR->DEVICEID[0]);
    Serial.println();
    Serial.println("#done");
  } else if (c == "module") {
    cmd_module();
  } else if (!cam_ok) {
    Serial.println("#err camera not found: check the camera on J6, the selector (Camera) and J7, J8 (Camera end), then press RESET");
  } else if (c == "snap") {
    int w = 160, h = 120;
    if (rest.length()) {
      int sp2 = rest.indexOf(' ');
      w = rest.substring(0, sp2 < 0 ? rest.length() : sp2).toInt();
      h = sp2 < 0 ? w * 3 / 4 : rest.substring(sp2 + 1).toInt();
    }
    if (w < 8 || h < 8 || w > Camera.width() || h > Camera.height()) {
      Serial.println("#err size must be 8x8 to 320x240");
      return;
    }
    snap(w, h);
    Serial.println("#done");
  } else if (c == "test") {
    if (rest.toInt()) Camera.testPattern(); else Camera.noTestPattern();
    Serial.println("#done");
  } else if (c == "e" || c == "exit" || c == "stop") {
    Serial.println("#done");
  } else {
    Serial.print("#err unknown command: "); Serial.println(c);
  }
}
