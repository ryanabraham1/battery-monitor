# Rev B: 120 A pulse load

Rev B raises the test pulse from about 12 A to about 105–125 A (depending on the load bank), so
the battery is measured at a current close to what a robot actually draws. The logic, CAN, NFC,
USB and supply sections are the same as rev A (`main` branch). Only the high-current path changed.

Nothing here has been built. The numbers below are calculations from datasheet-level figures I
could look up; the items in "Check before trusting it" are the ones I could not verify.

## What changed

| | Rev A (`main`) | Rev B (this branch) |
|---|---|---|
| Pulse current | ~12 A | ~105 A with 0.1 Ω, ~123 A with 0.083 Ω |
| Load (off-board) | 1 × 1 Ω 100 W | 2 × 0.2 Ω 100 W in parallel (or 3 × 0.25 Ω for the full 120 A) |
| Battery fuse | 15 A ATO blade in an on-board holder | 60 A bolt-down MIDI fuse across two M5 studs on the board |
| Charger fuse | shared with the battery fuse | its own 10 A SMD fuse (F1) |
| Shunt R1 | 1 mΩ | 0.5 mΩ 3 W (INA226 full scale 164 A) |
| Flyback diode D2 | SS54, SMA | SS56C, SMC (150 A surge rating) |
| Bulk capacitor | none | C18, 100 µF 35 V across VNODE |
| Gate resistor R12 | 10 Ω | 470 Ω (switches the current over ~10 µs) |
| MOSFET position | mid-board, return through the ground pour | next to the BATT− lug, 5 mm return path |
| BATT+ connection | M4 pad | M5 stud shared with the fuse |
| Battery / load wire | 10 AWG / 14 AWG | 6–8 AWG / 8 AWG |

## How the current flows

```
BATT+ ring terminal ─┐
                     ├─ stud J1 ══ MIDI fuse 60 A ══ stud J14 ── R1 0.5 mΩ ── VNODE ── LOAD+ lug
BATT+ voltage sense ─┘                                                          │
                                                                    load bank 0.1 Ω (off-board)
                                                                                │
BATT− lug ── Q1 source      Q1 drain ───────────────────────────────────── LOAD− lug
```

The battery's ring terminal sits directly on the fuse blade, so the 120 A never passes through
the J1 pad itself; the pad only feeds the voltage sense. The charger joins at VNODE through the
relay and F1, as before.

## Calculations

**Pulse current.** Loop resistance = load + battery + everything else. With a healthy 12 mΩ
battery, 0.5 mΩ shunt, ~1 mΩ fuse, ~2 mΩ MOSFET and ~4 mΩ of leads and contacts:

- 2 × 0.2 Ω (0.100 Ω): 12.7 V / 0.120 Ω ≈ **106 A**
- 3 × 0.25 Ω (0.083 Ω): 12.7 V / 0.103 Ω ≈ **123 A**

A weak 40 mΩ battery gives about 85 A and sags to roughly 9 V at its terminals, which the buck
converter (3.8 V minimum) rides through.

**Pulse energy.** 110 A × 11 V × 0.1 s ≈ 120 J per test, almost all of it in the load bank. If
firmware hangs with the pin high, the hardware one-shot still ends the pulse at ~220 ms (≈ 270 J).

**Copper.** A 100 ms pulse is too short for the usual steady-state trace tables, so the limit is
adiabatic heating: ΔT = I²·ρ·t / (A²·c). The narrowest pour in the loop is 9 mm wide on both
layers of 2 oz copper (A = 1.26 mm²): ΔT ≈ 120² × 1.7e-8 × 0.1 / ((1.26e-6)² × 3.45e6) ≈ **4.5 °C
per pulse**. Firmware enforces 30 s between tests, so it never accumulates.

**MOSFET (IRLB3034).** Rated 195 A (package limit), 1.4 mΩ typical at 10 V gate drive.
Conduction loss 120² × 2 mΩ ≈ 29 W for 0.1 s = 2.9 J. Switching 120 A × 12 V over ~10 µs adds
about 7 mJ per edge.

**Shunt.** 120² × 0.5 mΩ = 7.2 W for 0.1 s = 0.72 J in a 3 W part. Signal at 110 A is 55 mV,
inside the INA226's ±81.9 mV range; current resolution is 5 mA.

**Turn-off energy.** Battery leads (~1 µH) store ½·L·I² ≈ 7 mJ at 120 A. C18 absorbs it with a
rise of about 1 V (ΔV ≈ E / (C·V)); the TVS D3 is the backstop. The load leads' energy circulates
through D2.

**Accuracy.** The voltage step is now 110 A × 15 mΩ ≈ 1.6 V instead of 0.18 V, against the same
1.25 mV resolution, so resolution and noise matter about nine times less than on rev A. The
ground-return error also shrinks: the MOSFET source is 5 mm from the BATT− lug (≈ 0.05 mΩ of
copper) instead of crossing the board. Lead and contact resistance between the lugs and the
battery is still included in the reading and is still removed with the `lead` setting.

**Fuse.** A 0.1 s pulse at 120 A is 200 % of a 60 A fuse. MIDI-type fuses are slow at 200 %
(typically one to tens of seconds to open), so normal pulses use a small fraction of the fuse's
melting energy. A shorted MOSFET leaves 100+ A flowing continuously, which opens the fuse; until
it does, the load bank is absorbing over 1 kW.

## Check before trusting it

1. **Fuse time-current curve.** I did not read a datasheet curve for a specific 60 A MIDI fuse.
   Confirm that the one you buy takes well over 1 s to open at 120 A (so pulses do not age it) and
   opens within a few tens of seconds at 100 A (so a stuck MOSFET is cleared). If pulses blow it,
   go to 70 or 80 A.
2. **Load resistor pulse rating.** 100 W aluminium-housed wirewound resistors normally tolerate
   short overloads of this size, but check the pulse/overload figure for the exact part: each of
   two resistors sees about 600 W for 0.1 s (60 J).
3. **MOSFET stock.** Infineon IRLB3034PBF was low at LCSC when I checked. It is a hand-soldered
   part, so buying genuine ones from Digi-Key or Mouser is fine. Avoid unbranded clones at this
   current.
4. **Fuse height.** The fuse body is thicker than its blades, so each stud needs an M5 nut under
   the fuse as a spacer (bolt from below, nut, fuse, ring terminal, washer, lock nut).
5. **First power-up.** Do the first pulses with a current clamp or scope on the load lead and a
   bench supply or a known-good battery, and feel the load bank, fuse and MOSFET for warmth.

## What you gain and what it costs

A 120 A pulse loads the battery like a robot does, so it exposes weak cells and bad internal
connections that a 12 A pulse can miss, and the larger voltage step makes each reading less
noisy. It is still not an Auto Meter replacement in one respect: there is no charge-and-retest
logic or CCA estimate, only resistance, voltage, a charge estimate and a verdict.

The price is a hotter, higher-energy fault case. With rev A a stuck MOSFET dissipates 144 W in
the resistor; with rev B it is over 1 kW until the fuse opens. Mount the load bank on metal, away
from anything that burns, and fit the thermostat.
