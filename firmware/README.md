# Firmware

You do not need to open these sketches: `ee105.connect()` and `ee105.connect_camera()` compile and
upload them when a board is not already running them (or runs an older major version).

## ee105_board (all demo-board labs), version 3.0

One sketch for every demo-board lab. Board: Arduino Nano 33 BLE / BLE Sense
(FQBN `arduino:mbed_nano:nano33ble`). The AD5593R DAC and MAX86916 PPG drivers are in the sketch
folder. It speaks a line-based text protocol at 115200 baud.

Commands you can type (a notebook's `board.monitor("circuits")`, or any serial terminal at 115200
baud; `help` prints this list):

| Command | Selector S10 on | What it prints |
|---|---|---|
| `module` | any | which selector position is active, for example `selector: 2 = Module 2 (devices) 1.64 V` |
| `circuits` | Module 1 | which touch-panel button is pressed and its node voltage, until `stop` |
| `divider` | Module 1 | the voltage at the divider output A1, four times a second |
| `temperature` | Module 1 | the thermistor temperature (10 kOhm NTC, beta 3950, on top in J1-J2; 10 kOhm in J3-J4) |
| `diodes` | Module 2 | diode I-V sweep: V_DAC, V_D, I_D (mA) per line |
| `transistors` | Module 2 | MOSFET output curves: V_GS = 1.2 to 2.0 V in 0.1 V steps, V_DAC2 swept 0 to 3.3 V; V_GS, V_DS, I_D |
| `transfer` | Module 2 | MOSFET transfer curve at V_DAC2 = 3.3 V, V_GS swept 0 to 3.3 V; V_GS, V_DS, I_D |
| `light` | Module 3 | LED pair 1 on, the photodiode reading on A6 (J5 on P1-A) |
| `sensors` | Module 3 | red and infrared PPG from the MAX86916 |
| `communications send <text>` | Module 3 | sends the text over the TX LED (pair 2) once a second |
| `communications receive` | Module 3 | prints the text received by the RX photodiode on A6 (J5 on A-P2) |
| `stop` (or `e`, `exit`) | | stops the running command |

The names of the first board sketch (`m1na`, `m1vd`, `m2d`, `m2draw`, `m2tran_vds`, `m2tran_vgs`,
`m3led`, `m3pdcurrent`, `m3stepled`, `m3ppg`, `show_pd`, `lifi_tx`, `lifi_rx`) still run the
matching commands above.

Notebook commands (used by the toolkit; every reply ends with `#done` or `#err reason`, and
`#cols a,b` names the columns): `id` (firmware version and the 16-hex-digit board ID from the
nRF52840 `FICR->DEVICEID`), `module`, `read`, `stream`, `dac`, `zero`, `sweep`, `sweep2`, `ppg`,
`cap`, `txclear`/`txadd`/`txgo`, `txcap`, `i2c`, `button`. The header of `ee105_board.ino` lists
their arguments.

Transistor measurement: the drain is fed from DAC channel 2 through a 1 kOhm sense resistor, the
source is grounded, and a unity-gain difference amplifier across the resistor drives A3. So
I_D (mA) = V_A3 (V) and V_DS = V_DAC2 - V_A3; the drain current can never exceed
V_DAC2 / 1 kOhm = 3.3 mA.

The module selector S10 feeds A7 through a resistor ladder: about 2.20 V (Module 1, circuits
block), 1.65 V (Module 2, devices), 1.10 V (Module 3, biosensing), 0.83 V (Camera), near 0 V
(nothing selected). The
firmware uses thresholds halfway between these levels.

## ee105_camera (Lab 4.2), version 2.0

For the Nano 33 BLE Sense on the demo board with the OV7675 camera on header J6 (selector S10 on Camera,
both caps of jumpers J7 and J8 on the Camera end; put them back on the Module 1 end after the lab). Commands: `id` (with the
board ID), `module`, `snap [width] [height]` (grayscale picture as base64, default 160 x 120),
`test 0|1`. The Arduino_OV767X library (GPL-2.0, Arduino SA) is included in `src/`, so no library
install is needed.
