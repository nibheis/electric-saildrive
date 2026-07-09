# VESC Motor and Application Setup Guide

## ENGIRO 205W-04013-ABC with VESC Maxim 120

**Application:** Electric Saildrive Propulsion  
**Date:** July 2026  
**Configuration:** FOC (Field Oriented Control) with Sin/Cos Encoder

---

## 1. System Overview

### 1.1 Motor

| Parameter | Value |
|---|---|
| **Manufacturer** | ENGIRO GmbH |
| **Model** | 205W-04013-ABC |
| **Type** | Permanent Magnet Synchronous Machine (PMSM) |
| **Cooling** | Liquid-cooled (water/glycol 50/50) |
| **Pole Pairs** | **4** (8 poles total) |
| **Nominal Power (S1)** | 12 kW |
| **Max Power (S2, 10s)** | 20 kW |
| **Nominal Torque** | 34 Nm |
| **Max Torque (10s)** | 94 Nm |
| **Nominal Speed** | 3270 rpm |
| **Max Speed** | 8000 rpm (motor only) |
| **Nominal Voltage** | 48 V DC |
| **Max Voltage** | 200 V DC |
| **Nominal Phase Current** | 310 A rms |
| **Max Phase Current (10s)** | 960 A rms |
| **Torque Constant** | 0.12 Nm / A rms |
| **Back-EMF Constant (Ke)** | 0.032 Vpeak / (rad*s^-1) |
| **U/n Constant (AC L-L rms)** | 7.9 V / 1000 rpm |
| **Max Efficiency** | 96% |
| **Protection** | IP6K9K |
| **Temp Sensor** | KTY84-130 |
| **Position Sensor** | Sin/Cos Encoder (Type E) |
| **Rotor Inertia** | 0.0091 kg*m^2 |

### 1.2 VESC Controller

| Parameter | Value |
|---|---|
| **Manufacturer** | Vesc Labs |
| **Model** | Maxim 120 |
| **Input Voltage Range** | 30 - 120 V |
| **Continuous Motor Current** | **400 A** |
| **Pulsed Motor Current (10-30s)** | **600 A** |
| **Max Input Current** | **400 A** |
| **PWM Switching Frequency** | 30 kHz |
| **Auxiliary 5V Output** | 2 A |
| **Auxiliary 12V Output** | 3 A (direct) / 2 A per switched channel |
| **ADC Inputs** | 0 - 5.5 V (Sin/Cos tolerant) |
| **Temp Motor Input** | 0 - 3.3 V (KTY compatible) |
| **Protection** | Fully potted, IP rated |
| **Cooling Requirement** | Liquid cooling block recommended for full continuous power |

### 1.3 Battery Pack

| Parameter | Value |
|---|---|
| **Type** | LiFePO4 (Lithium Iron Phosphate) |
| **Configuration** | **3 units in PARALLEL** |
| **Cell Configuration** | 16S per unit |
| **Nominal Voltage** | **51.2 V** (3.2 V/cell x 16) |
| **Max Charge Voltage** | **57.6 V** (3.6 V/cell x 16) |
| **Minimum Voltage** | ~40 V (2.5 V/cell x 16) |
| **Capacity** | **600 Ah total** (3 x 200 Ah parallel) |

> **CRITICAL:** Batteries must be wired in **parallel**. Wiring in series would produce ~154 V and permanently destroy the Maxim 120.

### 1.4 Cooling System

| Parameter | Value |
|---|---|
| **Pump** | Bosch 0 392 023 004 |
| **Pump Voltage** | 12 V DC |
| **Pump Flow (free)** | 900 L/h = **15 L/min** |
| **Pump Max Pressure** | **0.1 bar** |
| **Motor Cooling Requirement** | **8 L/min** minimum |
| **Motor Max Pressure** | 0.5 bar |
| **Coolant Type** | Water/Glycol 50/50, **OAT (e.g., G12/G30)** |
| **Coolant Inlet Temp** | <= 45 degC |
| **Duty Cycle** | S1 (continuous) |
| **Protection** | IP69K |

> **Warning:** Do NOT use IAT or HOAT coolants (G11, G48, G12++, G13, G40) as they contain silicates that can damage the motor housing seals.

### 1.5 Drivetrain

| Parameter | Value |
|---|---|
| **Application** | Marine saildrive |
| **Reduction Ratio** | **2.13:1** |
| **Max Motor RPM** | **3300 RPM** |
| **Max Propeller RPM** | ~1550 RPM |
| **Propeller Type** | Folding propeller |
| **Control Mode** | FOC (Field Oriented Control) |

> The folding propeller does **not** back-drive the motor while sailing. This eliminates overvoltage risk from freewheeling.

---

## 2. VESC Tool Configuration

> **Note:** This guide is synced with **VESC Tool 7.00** parameter names and structure. Parameter paths use the exact internal names from `parameters_mcconf.xml`.

### 2.1 Motor Type and Sensor Port Setup

| Setting | Value | Parameter Name | Notes |
|---|---|---|---|
| **Motor Type** | **FOC** | `motor_type` | Field Oriented Control for PMSM (enum value: 2) |
| **Sensor Port Mode** | **Sin/Cos Encoder** | `m_sensor_port_mode` | Select "Sin/Cos Encoder" from dropdown (enum value: 4) |
| **FOC Sensor Mode** | **Encoder** | `foc_sensor_mode` | Select "Encoder" from dropdown (enum value: 1) |
| **Pole Pairs** | **4** | N/A (entered during FOC Wizard) | From motor datasheet |

> **Important:** In VESC Tool 7.00, there are two sensor-related settings:
> - `m_sensor_port_mode` — tells the hardware which physical sensor is connected (Sin/Cos, Hall, ABI, etc.)
> - `foc_sensor_mode` — tells the FOC algorithm which sensor to use for commutation
>
> For this motor, set BOTH to encoder-related options as shown above.
>
> **Why FOC?** The ENGIRO motor has a high-resolution Sin/Cos encoder (Type E), which provides the precise rotor position feedback needed for smooth FOC operation. FOC delivers higher efficiency, quieter operation, and superior low-speed torque control compared to BLDC mode.

### 2.2 Encoder Configuration (Sin/Cos)

The VESC Maxim 120 ADC inputs are **5.5 V tolerant**, so the encoder can be connected **directly** without a voltage divider.

| Setting | Value | Parameter Name | Notes |
|---|---|---|---|
| **Sine Amplitude** | **1.25 V** | `m_encoder_sin_amp` | 2.5 Vpp / 2. Default VESC value is 1.0 V, adjust to match your encoder |
| **Sine Offset** | **2.5 V** | `m_encoder_sin_offset` | 50% of 5 V supply. Default VESC value is 1.65 V, adjust to match your encoder |
| **Cosine Amplitude** | **1.25 V** | `m_encoder_cos_amp` | Should match sine amplitude |
| **Cosine Offset** | **2.5 V** | `m_encoder_cos_offset` | Should match sine offset |
| **Sin/Cos Filter** | **0.5** | `m_encoder_sincos_filter_constant` | 0 = most filtering/lag, 1 = no filtering. Default is usually fine. |
| **Sin/Cos Phase Correction** | **0 deg** | `m_encoder_sincos_phase_correction` | Adjust if sin/cos signals have phase mismatch (-45 to +45 deg) |
| **Encoder Offset** | **Measured during detection** | `foc_encoder_offset` | FOC wizard will auto-detect. Range: 0 - 360 deg |
| **Encoder Ratio** | **1** | `foc_encoder_ratio` | Encoder cycles per motor pole-pair. For 1:1 direct encoder: 1. For 4 pole-pairs with 1 rev/cycle: ratio = 1 |
| **Encoder Inverted** | **No** | `foc_encoder_inverted` | Toggle if motor spins in wrong direction with correct phase wiring |

> **Note on amplitude defaults:** The ENGIRO encoder outputs 2.5 Vpp (1.25 V amplitude) with 2.5 V offset. VESC Tool defaults are 1.0 V amplitude and 1.65 V offset. **You must manually adjust these values** to match the ENGIRO Type E encoder specifications.
>
> **Note on encoder ratio:** For the ENGIRO 205W Type E encoder (1 sine/cosine cycle per mechanical revolution, 4 pole pairs), the ratio can be set to **1** if the FOC wizard correctly identifies the relationship. Some VESC versions calculate this automatically during detection.

#### Encoder Wiring

| Signal | VESC Pin | ENGIRO Hummel 10P |
|---|---|---|
| **Sin** | Pin 8 (ADC3) | Pin 10 |
| **Cos** | Pin 21 (ADC4) | Pin 9 |
| **+5V Supply** | Pin 20 or 33 (+5VA) | Pin 8 |
| **GND** | Pin 10 / 23 / 36 (GND) | Pin 7 |
| **KTY84-130 +** | Pin 7 (Temp Motor) | Pin 5 |
| **KTY84-130 -** | GND | Pin 1 |

> **Shielding:** The sensor cable shield must be connected to GND at the **inverter side only**. Do NOT connect the shield to the motor housing.

### 2.3 Speed and RPM Limits

| Setting | Value | Notes |
|---|---|---|
| **Max ERPM** | **14,000** | 3300 RPM x 4 pole pairs = 13,200. Extra margin added. |
| **Max Duty Cycle** | 95% | |

> **No Field Weakening Required:** At 3300 RPM, the motor back-EMF is only ~26 Vrms (line-to-line), which is well below the battery voltage. Field weakening should remain **disabled**.

### 2.4 Current Limits

| Setting | Value | Notes |
|---|---|---|
| **Motor Current Max** | **400 A** | VESC Maxim 120 continuous limit. This equals ~283 A phase RMS, which is below the motor's 310 A continuous rating. Motor is thermally safe. |
| **Motor Current Max Brake** | **400 A** | Set according to regen and mechanical constraints. |
| **Absolute Maximum Current** | **600 A** | VESC pulsed limit (10-30s depending on cooling). Well within motor's 960 A capability. |
| **Battery Current Max** | **300 A** | Set to ~250-300 A (based on 12 kW / 51 V). Do not exceed your BMS limit. |
| **Battery Current Max Regen** | Per BMS | Check your LiFePO4 BMS charge current limit. |

> **Important:** The VESC input current limit is 400 A. If your BMS maximum discharge current is lower than 300 A, set the battery current limit to the BMS value.

### 2.5 Voltage Limits

| Setting | Value | Notes |
|---|---|---|
| **Minimum Input Voltage** | **40 V** | LiFePO4 empty (~2.5 V/cell). Prevents over-discharge. |
| **Maximum Input Voltage** | **60 V** | Safely above max charge (57.6 V) but below VESC 120 V max. |
| **Battery Voltage Cutoff Start** | **42 V** | ~2.6 V/cell. Start reducing power. |
| **Battery Voltage Cutoff End** | **40 V** | ~2.5 V/cell. Hard cutoff. |

### 2.6 Temperature Limits

#### Motor Temperature (KTY84-130)

| Setting | Value | Parameter Name | Notes |
|---|---|---|---|
| **Motor Temp Sensor Type** | **KTY84/130** | `m_motor_temp_sens_type` | Select "KTY84/130" from dropdown (enum value: 4) |
| **Motor Temp Cutoff Start** | **110 degC** | `l_temp_motor_start` | Start derating early to protect motor |
| **Motor Temp Cutoff End** | **140 degC** | `l_temp_motor_end` | Motor absolute maximum from datasheet |

#### VESC (MOSFET) Temperature

| Setting | Value | Parameter Name |
|---|---|---|
| **MOSFET Temp Cutoff Start** | **85 degC** | `l_temp_fet_start` |
| **MOSFET Temp Cutoff End** | **95 degC** | `l_temp_fet_end` |

> **Cooling is mandatory:** The Maxim 120 can only reach its full 400 A continuous potential with a **liquid cooling block**. At 400 A and 51 V, even at 96% efficiency, the VESC dissipates ~800 W. Without active cooling, it will thermal-throttle quickly.
>
> **Temperature compensation:** If your motor exhibits resistance/inductance changes with temperature, you can enable `foc_temp_comp` with a base temperature of 25 degC. This is optional.

### 2.7 FOC Advanced Settings

| Setting | Value | Parameter Name | Notes |
|---|---|---|---|
| **PWM Switching Frequency** | **30 kHz** | `foc_f_sw` or hardware default | Matches Maxim 120 typical rating |
| **MTPA Mode** | **IQ Measured** | `foc_mtpa_mode` | Select "IQ Measured" from dropdown (enum value: 2) for best performance |
| **Field Weakening Current Max** | **0 A** | `foc_fw_current_max` | Disabled. Not needed for this application |
| **Field Weakening Duty Start** | **90%** | `foc_fw_duty_start` | Only active if FW current > 0. Not applicable here |
| **Observer Type** | **Ortega Lambda Comp** | `foc_observer_type` | Default value: 3 (FOC_OBSERVER_ORTEGA_LAMBDA_COMP). Usually best for PMSM |
| **Observer Gain** | **Auto-detected** | `foc_observer_gain` | FOC wizard will set this. Default: 6.206e+07 |
| **Observer Gain Slow** | **0.05** | `foc_observer_gain_slow` | At minimum duty cycle. Default is usually fine |
| **Current Controller KP** | **Auto-detected** | `foc_current_kp` | FOC wizard will set this |
| **Current Controller KI** | **Auto-detected** | `foc_current_ki` | FOC wizard will set this |

> **Field Weakening Note:** Since your max RPM (3300) is well below the voltage-limited speed (~4200 RPM at 58 V), field weakening provides no benefit and only generates extra heat. Keep `foc_fw_current_max = 0`.

### 2.8 App / Control Settings

| Setting | Recommendation |
|---|---|
| **Control Type** | Current Control (recommended for propeller load) |
| **Input Device** | Throttle (ADC1, Pin 9) |
| **Direction** | Forward only (unless reverse is needed for maneuvering) |
| **Throttle Curve** | Smooth / exponential (avoid aggressive ramping due to propeller inertia) |

> In the VESC Setup Wizard, answer **"Yes"** to direct drive. The propeller is a direct mechanical load through the saildrive reduction.

---

## 3. FOC Detection Wizard

Before first operation, run the **FOC Setup Wizard** in VESC Tool:

### Pre-Detection Setup (MANUAL - Critical!)

The FOC wizard does NOT configure the sensor port or encoder type automatically. You **must** set these manually first:

1. Navigate to **Motor Settings -> General**
2. Set `motor_type` = **FOC** (value 2)
3. Navigate to **Motor Settings -> Advanced**
4. Set `m_sensor_port_mode` = **Sin/Cos Encoder** (value 4)
5. Navigate to **Motor Settings -> FOC -> General**
6. Set `foc_sensor_mode` = **Encoder** (value 1)

### Running the Wizard

7. Go to **Welcome & Wizards -> Setup Motors FOC**
8. Confirm loading default parameters
9. Select usage profile closest to marine / boat
10. Select motor size (large, > 5 kW)
11. Select battery type: **LiFePO4**
12. Enter **16 cells** in series
13. Enter **600 Ah** capacity
14. Select **Direct Drive = Yes**
15. Enter pulley ratio: Motor = 2.13, Wheel = 1.0 (or equivalent)
16. Enter **8 motor poles** (4 pole pairs)
17. Click **Run Detection**

### Post-Detection Checks

After detection completes, verify these auto-detected parameters:

- **`foc_motor_r`** (Phase Resistance) — Should be very low (likely < 5-10 milliohms)
- **`foc_motor_l`** (Phase Inductance) — Typically in the 10-100 microhenry range for this motor type
- **`foc_motor_flux_linkage`** — Cross-check with calculation:
  - Ke (peak, line-to-line) = 0.032 Vpeak / (rad/s)
  - Phase Ke = Ke_LL / sqrt(3) = 0.032 / 1.732 = 0.0185 Vpeak / (rad/s)
  - lambda = Phase Ke / (pole pairs) = 0.0185 / 4 = **0.0046 V*s/rad** (= **4.6 mWb**)
  - Verify detected value is close to this theoretical value (expect ~4-5 mWb)
- **`foc_encoder_offset`** — Should be a value between 0-360 degrees
- **`foc_current_kp`** and **`foc_current_ki`** — Current controller gains (auto-tuned)
- **`foc_observer_gain`** — Observer gain (auto-tuned)

18. Check motor direction with **FWD / REV** buttons
19. If incorrect, use the **`foc_encoder_inverted`** toggle (do not swap phase wires if direction is already correct)

> **Safety:** Ensure motor shaft is free to rotate and propeller is clear before running detection.

---

## 4. Wiring Checklist

### 4.1 Power Connections

| Connection | Detail |
|---|---|
| **Battery + to VESC BAT+** | Through 400 A fuse (included in VESC wiring diagram) |
| **Battery - to VESC BAT-** | Direct, heavy gauge cable |
| **Precharge Circuit** | Required if BMS does not have integrated precharge |
| **Phase U, V, W** | Heavy gauge, max current density < 6 A/mm2 |
| **Phase Terminal Torque** | **22 Nm +/- 1 Nm** |

### 4.2 Signal Connections (39-Pin Connector)

| Function | VESC Pin | Notes |
|---|---|---|
| **Throttle** | Pin 9 (ADC1) | 0 - 5V analog |
| **Temp Motor** | Pin 7 | KTY84-130 to STM ADC Temp |
| **Encoder Sin** | Pin 8 (ADC3) | 0 - 5V tolerant |
| **Encoder Cos** | Pin 21 (ADC4) | 0 - 5V tolerant |
| **+5V Supply** | Pin 20 or 33 | For encoder |
| **GND** | Pin 10 / 23 / 36 | Signal ground |
| **CAN H** | Pin 4 | Isolated CAN (if needed) |
| **CAN L** | Pin 5 | Isolated CAN (if needed) |
| **EN (Power On)** | Pin 28 | Connect to +BATT to power up |
| **+BATT** | Pin 29 | VBATT output, 3A max |

### 4.3 Cooling Pump Wiring

| Option | Pin | Rating | Suitability |
|---|---|---|---|
| **Direct 12V** | Pin 17 or 30 (+12VA) | 12V, **3A** | Best for continuous operation if pump <= 3A |
| **Switched 12V** | Pin 18 (SW1) | 12V, **2A** | Use for on/off control via script |
| **Switched 12V** | Pin 19 (SW2) | 12V, **2A** | Alternative switched output |

> The Bosch pump draws approximately 1.5 - 3 A. If it exceeds 2A, do **not** use switched outputs directly - use them to drive a relay or external MOSFET instead.

### 4.4 Equipotential Bonding (Critical for Marine)

- Use a **tinned copper braided strap** between motor housing and VESC chassis
- Cross-section should be approximately equal to phase cable cross-section
- Connect to the boat's main bonding system
- Two motor housing options:
  1. M6 brass stud inside rear flange (4 Nm +/- 4%)
  2. M10 threaded bore at rear (31 Nm +/- 4%)

---

## 5. Pre-Operation Checklist

### 5.1 Mechanical

- [ ] Motor securely mounted in correct orientation (self-bleeding position)
- [ ] Saildrive properly connected and lubricated
- [ ] Propeller installed and folding mechanism free
- [ ] All mounting screws torqued to specification

### 5.2 Cooling System

- [ ] Coolant loop filled with correct mixture (50/50 water/glycol, OAT type)
- [ ] System bled - no air trapped in motor housing
- [ ] Pump wired to 12V supply and running
- [ ] **Actual coolant flow measured >= 8 L/min** at operating temperature
- [ ] Hoses secured and routed away from hot/moving parts
- [ ] Raw-water heat exchanger sized for system losses
- [ ] VESC cooling block connected (if using liquid cooling for VESC)

### 5.3 Electrical

- [ ] Batteries wired in **parallel** (verified!)
- [ ] Phase cables connected in correct order (U-V-W for CCW rotation)
- [ ] Phase terminal torque: 22 Nm
- [ ] Encoder wired correctly (Sin/Cos/5V/GND)
- [ ] KTY84-130 wired to Temp Motor pin
- [ ] Sensor cable shield grounded at **VESC side only**
- [ ] Equipotential bonding strap installed
- [ ] 400 A fuse installed on battery positive
- [ ] Precharge circuit present (if BMS lacks it)
- [ ] All cable glands properly sealed (maintain IP rating)

### 5.4 Software

- [ ] Latest VESC Tool **7.00** installed from vesc-project.com
- [ ] **`motor_type`** set to **FOC** before running wizard
- [ ] **`m_sensor_port_mode`** set to **Sin/Cos Encoder** (value 4) before running wizard
- [ ] **`foc_sensor_mode`** set to **Encoder** (value 1) before running wizard
- [ ] FOC Setup Wizard completed successfully
- [ ] `foc_motor_r`, `foc_motor_l`, `foc_motor_flux_linkage` values reasonable after detection
- [ ] `foc_encoder_offset` value present (0-360 deg range)
- [ ] Motor direction verified correct
- [ ] Sin/Cos encoder readings stable (check in Realtime Data)
- [ ] `m_encoder_sin_amp` = 1.25 V, `m_encoder_sin_offset` = 2.5 V
- [ ] `m_encoder_cos_amp` = 1.25 V, `m_encoder_cos_offset` = 2.5 V
- [ ] KTY84-130 temperature reading accurate at ambient
- [ ] `m_motor_temp_sens_type` = **KTY84/130** (value 4)
- [ ] Max ERPM set to 14,000
- [ ] Motor current max set to 400 A
- [ ] Battery current max set appropriately (<= BMS limit)
- [ ] Voltage limits configured (40-60 V)
- [ ] Temperature protection enabled
- [ ] Field weakening disabled (`foc_fw_current_max` = 0)

### 5.5 First Power-On

- [ ] System powered on in controlled environment
- [ ] No abnormal sounds, smells, or heat
- [ ] Realtime data shows all temperatures normal
- [ ] Motor spins smoothly at low throttle
- [ ] Propeller rotation direction correct
- [ ] No water leaks from cooling system

---

## 6. Safety Warnings

### General Safety

- **High Voltage:** This system operates at lethal voltages. Only qualified personnel should install or service it.
- **Moving Parts:** Ensure all personnel are clear of the propeller before powering the motor.
- **Water + Electricity:** All electrical connections must be properly sealed for marine use.

### Motor-Specific

- **Permanent Magnet Machine:** The motor generates voltage when spun manually. Even with a folding propeller, avoid rotating the motor shaft during maintenance.
- **Rotation Direction:** Incorrect phase order or sensor alignment will cause unpredictable behavior, low torque, or uncontrolled spin-up ("runaway").
- **Temperature:** Operating without coolant or with blocked flow will cause immediate thermal damage.

### Battery-Specific

- **Parallel Connection:** Verify batteries are in parallel. Series connection will produce 154 V and destroy the VESC.
- **Precharge:** Always use a precharge circuit or BMS with integrated precharge. Connecting a fully discharged capacitor bank directly to the battery can cause welding/arcing.

### VESC-Specific

- **Ground Loops:** When configuring over USB, run your laptop on battery power if the VESC is powered from a bench supply. Ground loops through USB can permanently damage the VESC.
- **Current Limits:** Do NOT exceed the VESC Maxim 120 current limits. The device has built-in thermal protection, but sustained overloads can cause damage.
- **Cooling:** The VESC requires liquid cooling to sustain 400 A continuously. Air cooling alone is insufficient for full power.

---

## 7. Troubleshooting Quick Reference

| Symptom | Possible Cause | Solution |
|---|---|---|
| Motor does not rotate | Wrong phase/sensor order | Check ENGIRO Table 3 (U-V-W) and sensor wiring |
| | Sensor fault | Check encoder signals in Realtime Data |
| | Insufficient voltage | Check battery state of charge |
| Motor rotates wrong direction | Phase or sensor inversion | Use "Inverted" toggle in VESC Tool |
| High vibration / noise | Unbalanced propeller | Check propeller and shaft alignment |
| | Bad FOC parameters | Re-run detection wizard |
| Motor overheats quickly | Low or no coolant flow | Check pump operation and flow rate |
| | Coolant too hot | Check heat exchanger sizing |
| | Over-current operation | Verify current limits and load |
| VESC overheats | Insufficient VESC cooling | Add liquid cooling block to VESC |
| | Ambient too hot | Improve ventilation |
| Temperature reading wrong | KTY polarity reversed | Check polarity - KTY is polarized |
| | Wrong sensor type selected | Verify KTY84-130 selected in VESC Tool |
| Encoder fault/error | Poor signal connection | Check wiring and shield grounding |
| | Amplitude/offset wrong | Verify `m_encoder_sin_amp` = 1.25 V, `m_encoder_sin_offset` = 2.5 V |
| | | Verify `m_encoder_cos_amp` = 1.25 V, `m_encoder_cos_offset` = 2.5 V |

---

## 8. Useful Formulas

### Back-EMF at Given RPM

```
Back-EMF (Vrms L-L) = U/n_constant x RPM / 1000
At 3300 RPM: 7.9 x 3.3 = 26.1 Vrms
```

### ERPM Calculation

```
ERPM = Mechanical_RPM x Pole_Pairs
At 3300 RPM: 3300 x 4 = 13,200 ERPM
```

### Approximate Power Output

```
Power (W) = Battery_Current (A) x Battery_Voltage (V) x Efficiency
Example: 300 A x 51 V x 0.96 = 14,688 W (limited by battery current)
```

### Propeller Load Torque (approximate)

```
Torque load increases with the square of RPM for a propeller.
At 1550 propeller RPM (3300 motor RPM), torque demand depends
on propeller pitch/diameter and hull characteristics.
```

---

## 9. References

- ENGIRO 205W Manual V01.10 (May 2025)
- ENGIRO 205W-04013-ABC Datasheet V010.02
- VESC Maxim 120 Datasheet (Revised February 2026)
- Bosch Water Circulation Pump 0 392 023 004 Datasheet
- IEC 60034-8:2007 (Phase labeling and rotation direction)
- EN 60204-1:2019 (Electrical installation requirements)

---

*This configuration guide is for informational purposes. Always verify settings against your specific hardware and consult manufacturer documentation. Improper configuration can result in equipment damage or personal injury.*
