"""Demo board facts used by every lab: pins, DAC channels, the selector and conversions.

These numbers come from the board schematic (black board, rev 1.1) and the course
firmware; the textbook uses the same ones (Chapter 0 describes the board).

The board's silkscreen calls its blocks "Module 1/2/3" and prints the selector positions
around S10 as Module 1, Module 2, Module 3 and Camera. The course calls the blocks the
circuits block, the devices block and the biosensing block; in code the positions are
1, 2, 3 and "CAM".
"""

VREF = 3.3                    # ADC reference and supply (V)
ADC_BITS = 10
ADC_COUNTS = 2 ** ADC_BITS    # 1024
ADC_V_PER_COUNT = VREF / ADC_COUNTS          # 3.22 mV per count
DAC_V_PER_CODE = 0.00165                     # 1.65 mV per DAC code (course calibration)
DAC_MAX_CODE = 4095
DAC_CODE_3V3 = 2000                          # about 3.3 V; higher codes saturate at the supply

# Analog input pins (the number after "A")
PIN_TOUCH = 0        # A0  circuits block, Network 1 touch panel (buttons S1..S9), through J7 (Module 1 end, pins 2-3)
PIN_DIVIDER = 1      # A1  circuits block, divider header midpoint (J2/J3), through J8 (Module 1 end, pins 2-3)
PIN_DIODE = 2        # A2  devices block, diode: difference amp (gain 1) across the 1 kOhm sense resistor
PIN_NMOS = 3         # A3  devices block, MOSFET: difference amp (gain 1) across the 1 kOhm drain resistor
PIN_PD = 6           # A6  biosensing block, photodiode TIA (J5 on P1-A, pins 1-2: pair 1; on A-P2, pins 2-3: pair 2, RX)
PIN_SELECT = 7       # A7  module selector S10 (resistor ladder)

# AD5593R DAC channels
DAC_DIODE = 0        # diode drive, through the 1 kOhm sense resistor
DAC_GATE = 1         # MOSFET gate (pull-down resistor to ground on the board)
DAC_DRAIN = 2        # MOSFET drain supply V_DAC2, through the 1 kOhm drain sense resistor
DAC_LED1 = 3         # LED pair 1 (faces the board's own photodiode)
DAC_LED2 = 4         # LED pair 2 (communication LED, faces outward)

R_SENSE_DIODE = 1e3  # ohm, in series with the diode
R_SENSE_NMOS = 1e3   # ohm, the drain sense resistor between DAC channel 2 and the drain (A3 reads across it)
NMOS_V_PER_MA = 1.0  # A3 = I_D x 1 kOhm: 1 V at A3 per mA of drain current
NMOS_I_MAX_MA = VREF / (R_SENSE_NMOS / 1e3)  # 3.3 mA: the schematic's upper bound, V_DAC2 / 1 kOhm
# Measured on a real board (November 2026): the whole drain path from DAC channel 2 is about
# 4.6 kOhm (the sense resistor plus about 3.6 kOhm more; the cause is not known yet), so the drain
# current levels off near 0.62 mA at V_DAC2 = 3.3 V. Lab 2.1 measures this path (step C3) on every
# board: R_path = V_DAC2 / I_max, from the top of the transfer curve.
R_DRAIN_PATH_MEASURED = 4.6e3   # ohm, one board; use your own board's R_path from Lab 2.1

# Divider header of the circuits block: J1 = 3.3 V, J2 and J3 = midpoint (to A1), J4 = GND.
# The top part plugs into J1-J2, the bottom part into J3-J4.
THERMISTOR_R0 = 10e3      # Lab 3.1 NTC thermistor: 10 kOhm at 25 C ...
THERMISTOR_BETA = 3950.0  # ... beta 3950 K, in J1-J2 (top)
THERMISTOR_R_FIXED = 10e3  # 10 kOhm in J3-J4 (bottom)

# Network 1 (touch panel) node voltages, from nodal analysis of the board
TOUCH_NODE_V = {"S1": 3.300, "S2": 1.946, "S3": 1.185, "S4": 2.496, "S5": 1.650,
                "S6": 0.804, "S7": 2.115, "S8": 1.354, "S9": 0.000}   # textbook Chapter 1

# Module selector S10 on A7. The schematic's ladder (0.5, 1, 2 and 3 MOhm from the four rails,
# 1 MOhm to ground) gives 2.20, 1.65, 1.10 and 0.83 V when the blocks that are off draw nothing
# (SELECTOR_V_UNLOADED). On a real board the blocks that are off load the ladder and the readings
# come out lower, by an amount that varies from board to board. The toolkit therefore accepts a
# wide range for each position (SELECTOR_RANGE) and only warns when a reading does not fit.
SELECTOR_V_UNLOADED = {1: 2.20, 2: 1.65, 3: 1.10, "CAM": 0.83}
SELECTOR_V = {1: 1.85, 2: 0.89, 3: 0.65, "CAM": 0.31}         # typical reading (best guess), measured on a real board
SELECTOR_RANGE = {1: (1.20, 2.70), 2: (0.55, 1.95), 3: (0.25, 1.40), "CAM": (0.15, 1.00)}
SELECTOR_NONE_BELOW = 0.12      # below this, no position is selected
SELECTOR_MAX = 2.90             # above this, the reading fits no position
SELECTOR_NAME = {1: "circuits", 2: "devices", 3: "biosensing", "CAM": "camera"}
SELECTOR_LABEL = {1: "Module 1", 2: "Module 2", 3: "Module 3", "CAM": "Camera"}   # printed on the board


def selector_fits(position, volts):
    """True if an A7 reading (volts) fits the selector position (1, 2, 3 or "CAM")."""
    lo, hi = SELECTOR_RANGE[position]
    return lo <= float(volts) <= hi


def selector_text(position):
    """How the notebooks name a selector position: "Module 1 (circuits block)", ..., "Camera"."""
    if position == "CAM":
        return "Camera"
    return f"{SELECTOR_LABEL[position]} ({SELECTOR_NAME[position]} block)"


def selector_line_label(position):
    """Label printed after "selector:" by the firmware and the simulators."""
    if position is None:
        return "none (no block selected)"
    if position == "CAM":
        return "CAM = Camera"
    return f"{position} = {SELECTOR_LABEL[position]} ({SELECTOR_NAME[position]})"


def selector_position(volts):
    """Best guess of the selector position (1, 2, 3, "CAM") from the A7 voltage: the nearest
    typical level. None if no block is selected, "unknown" above SELECTOR_MAX. The ranges of
    neighboring positions overlap, so use selector_fits() to check a position the lab needs."""
    v = float(volts)
    if v > SELECTOR_MAX:
        return "unknown"
    if v < SELECTOR_NONE_BELOW:
        return None
    if v > (SELECTOR_V[1] + SELECTOR_V[2]) / 2:        # 1.37 V
        return 1
    if v > (SELECTOR_V[2] + SELECTOR_V[3]) / 2:        # 0.77 V
        return 2
    if v > (SELECTOR_V[3] + SELECTOR_V["CAM"]) / 2:    # 0.48 V
        return 3
    return "CAM"


def adc_to_volts(raw):
    """ADC counts (0..1023) to volts. Works on numbers and numpy arrays."""
    return raw * ADC_V_PER_COUNT


def volts_to_dac(volts):
    """Volts to the nearest AD5593R code, limited to 0..4095."""
    code = int(round(float(volts) / DAC_V_PER_CODE))
    return max(0, min(DAC_MAX_CODE, code))


def dac_to_volts(code):
    """DAC code to the output voltage (saturates at the 3.3 V supply)."""
    import numpy as np
    return np.minimum(np.asarray(code) * DAC_V_PER_CODE, VREF)


def nmos_from_a3(v_dac2, v_a3, r_path_kohm=R_SENSE_NMOS / 1e3):
    """(I_D in mA, V_DS in V) from the drain supply V_DAC2 and the A3 reading (both in volts).

    A3 is the voltage across the 1 kOhm drain sense resistor, so I_D = V_A3 / 1 kOhm. KVL around
    the drain loop gives V_DS = V_DAC2 - I_D x R_path, where R_path (kOhm) is the whole drain path
    from DAC channel 2. The default, the sense resistor alone, gives V_DS = V_DAC2 - V_A3; a real
    board has more (Lab 2.1 step C3 measures it), so pass r_path_kohm when V_DS matters.
    Works on numbers and numpy arrays.
    """
    i_ma = v_a3 / NMOS_V_PER_MA
    return i_ma, v_dac2 - i_ma * r_path_kohm


def thermistor_ohms(v_out, r_fixed=THERMISTOR_R_FIXED):
    """Thermistor resistance (ohm) from the divider output, thermistor on top:
    V_out = 3.3 V * R / (R + R_T), so R_T = R (3.3 V / V_out - 1)."""
    return r_fixed * (VREF / v_out - 1)


def thermistor_celsius(r_t, r0=THERMISTOR_R0, beta=THERMISTOR_BETA, t0_k=298.15):
    """Beta model: 1/T = 1/T0 + ln(R_T / R0) / beta, T in kelvin; returns degrees Celsius."""
    import numpy as np
    return 1.0 / (1.0 / t0_k + np.log(r_t / r0) / beta) - 273.15
