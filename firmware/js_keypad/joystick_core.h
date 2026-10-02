#ifndef JOYSTICK_CORE_H
#define JOYSTICK_CORE_H

#include <Arduino.h>

// Pure core: types, constants, function declarations. No hardware, no millis(),
// no side effects. Definitions live in joystick_core.cpp.

const int AdcMaxValue = 1023;  // 10 bit
const unsigned long DebounceDelayMillis = 25;
const float RadialDeadzoneFraction = 0.05;
const int DefaultJoystickCenter = AdcMaxValue / 2;
const int JoystickOutputMax = 32767;             // signed joystick output range
const uint16_t CalibrationMagicNumber = 0x4A53;  // 'JS' — marks EEPROM as holding valid calibration

// Must match ButtonConfigs[] in the sketch; a static_assert there enforces it.
const int NumGamepadButtons = 1;

// Per-axis calibrated endpoints; center may sit off AdcMaxValue/2, range may be narrow.
struct AxisCalibration {
  int minValue;
  int center;
  int maxValue;
};

struct Calibration {
  uint16_t magicNumber;
  AxisCalibration x;
  AxisCalibration y;
};

struct Debouncer {
  boolean previousRawState;
  boolean stableState;
  unsigned long lastChangeTimeMillis;
};

struct Vector2 {
  float x;
  float y;
};

struct State {
  Calibration calibration;
  boolean calibrating;                         // true while in calibration mode (toggled by press edges)
  boolean calibrationButtonReleasedSinceBoot;  // false during a power-on reset hold
  Debouncer gamepadButtonDebouncers[NumGamepadButtons];
  Debouncer calibrationButtonDebouncer;
};

// Everything the core reads this tick. Gathered by the shell.
struct Inputs {
  unsigned long nowMillis;
  int joystickX;
  int joystickY;
  boolean gamepadButtonRaw[NumGamepadButtons];  // raw digitalRead (LOW = pressed)
  boolean calibrationButtonRaw;                 // raw digitalRead (LOW = pressed)
};

// Everything the core wants applied this tick. Applied by the shell.
struct Outputs {
  boolean gamepadButtons[NumGamepadButtons];
  int joystickX;
  int joystickY;
  boolean calibrationLed;
  boolean saveCalibration;  // shell persists calibration to EEPROM
};

struct TickResult {
  State state;
  Outputs outputs;
};

Debouncer advanceDebouncer(Debouncer debouncer, boolean rawState, unsigned long nowMillis);
float normalizeAxisSignedAboutCenter(int rawReading, int minValue, int center, int maxValue);
Vector2 applyRadialDeadzone(float normalizedX, float normalizedY);
Calibration defaultCalibration();
Calibration validateCalibration(Calibration storedCalibration);
Calibration resolveInitialCalibration(Calibration storedCalibration, boolean resetRequested);
AxisCalibration expandAxisToInclude(AxisCalibration axis, int rawReading);
State makeInitialState(Calibration calibration, boolean calibrationButtonHeldAtBoot);
TickResult computeTick(State state, Inputs inputs);

#endif  // JOYSTICK_CORE_H
