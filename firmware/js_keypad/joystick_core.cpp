#include "joystick_core.h"

// Pure core bodies. Each is a pure function of its arguments: no hardware,
// no millis(), no side effects. The public entry point is computeTick(); the
// file-local helpers below each own one job so their names carry the explanation.

Debouncer advanceDebouncer(Debouncer debouncer, boolean rawState, unsigned long nowMillis) {
  if (rawState != debouncer.previousRawState) {
    debouncer.lastChangeTimeMillis = nowMillis;
    debouncer.previousRawState = rawState;
  }
  if ((nowMillis - debouncer.lastChangeTimeMillis) > DebounceDelayMillis) {
    debouncer.stableState = rawState;
  }
  return debouncer;
}

static float normalizeAxisPositiveSide(int rawReading, int center, int maxValue) {
  int spanAboveCenter = maxValue - center;
  if (spanAboveCenter <= 0) {
    return 0.0f;
  }
  float normalized = (float)(rawReading - center) / spanAboveCenter;
  return constrain(normalized, 0.0f, 1.0f);
}

static float normalizeAxisNegativeSide(int rawReading, int minValue, int center) {
  int spanBelowCenter = center - minValue;
  if (spanBelowCenter <= 0) {
    return 0.0f;
  }
  float normalized = (float)(rawReading - center) / spanBelowCenter;
  return constrain(normalized, -1.0f, 0.0f);
}

float normalizeAxisSignedAboutCenter(int rawReading, int minValue, int center, int maxValue) {
  return rawReading >= center
           ? normalizeAxisPositiveSide(rawReading, center, maxValue)
           : normalizeAxisNegativeSide(rawReading, minValue, center);
}

Vector2 applyRadialDeadzone(float normalizedX, float normalizedY) {
  float magnitude = sqrt(normalizedX * normalizedX + normalizedY * normalizedY);
  if (magnitude <= RadialDeadzoneFraction) {
    return { 0.0f, 0.0f };
  }
  float scaledMagnitude = (magnitude - RadialDeadzoneFraction) / (1.0f - RadialDeadzoneFraction);
  if (scaledMagnitude > 1.0f) {
    scaledMagnitude = 1.0f;
  }
  float directionPreservingScale = scaledMagnitude / magnitude;  // magnitude > 0 here
  return { normalizedX * directionPreservingScale, normalizedY * directionPreservingScale };
}

Calibration defaultCalibration() {
  Calibration calibration;
  calibration.magicNumber = CalibrationMagicNumber;
  calibration.x = { 0, DefaultJoystickCenter, AdcMaxValue };
  calibration.y = { 0, DefaultJoystickCenter, AdcMaxValue };
  return calibration;
}

Calibration validateCalibration(Calibration storedCalibration) {
  return storedCalibration.magicNumber == CalibrationMagicNumber
           ? storedCalibration
           : defaultCalibration();
}

// resetRequested (button held at power-on) forces defaults over the stored value.
Calibration resolveInitialCalibration(Calibration storedCalibration, boolean resetRequested) {
  return resetRequested
           ? defaultCalibration()
           : validateCalibration(storedCalibration);
}

AxisCalibration expandAxisToInclude(AxisCalibration axis, int rawReading) {
  if (rawReading < axis.minValue) {
    axis.minValue = rawReading;
  }
  if (rawReading > axis.maxValue) {
    axis.maxValue = rawReading;
  }
  return axis;
}

State makeInitialState(Calibration calibration, boolean calibrationButtonHeldAtBoot) {
  State state;
  state.calibration = calibration;
  state.calibrating = false;
  state.calibrationButtonReleasedSinceBoot = !calibrationButtonHeldAtBoot;
  for (int buttonIndex = 0; buttonIndex < NumGamepadButtons; buttonIndex++) {
    state.gamepadButtonDebouncers[buttonIndex] = { false, false, 0 };
  }
  // Seed to boot state so a held button reads as pressed, not a phantom press edge.
  state.calibrationButtonDebouncer = { calibrationButtonHeldAtBoot, calibrationButtonHeldAtBoot, 0 };
  return state;
}

static State updateGamepadButtons(State state, const Inputs& inputs, Outputs& outputs) {
  for (int buttonIndex = 0; buttonIndex < NumGamepadButtons; buttonIndex++) {
    Debouncer buttonDebouncer = state.gamepadButtonDebouncers[buttonIndex];
    boolean buttonPressedRaw = !inputs.gamepadButtonRaw[buttonIndex];
    Debouncer advancedButtonDebouncer = advanceDebouncer(buttonDebouncer, buttonPressedRaw, inputs.nowMillis);

    state.gamepadButtonDebouncers[buttonIndex] = advancedButtonDebouncer;
    outputs.gamepadButtons[buttonIndex] = advancedButtonDebouncer.stableState;
  }
  return state;
}

static State enterCalibration(State state, const Inputs& inputs) {
  state.calibration.x = { inputs.joystickX, inputs.joystickX, inputs.joystickX };
  state.calibration.y = { inputs.joystickY, inputs.joystickY, inputs.joystickY };
  state.calibrating = true;
  return state;
}

static State exitCalibration(State state, Outputs& outputs) {
  state.calibration.magicNumber = CalibrationMagicNumber;
  outputs.saveCalibration = true;  // write only on exit; EEPROM has limited cycles
  state.calibrating = false;
  return state;
}

static State toggleCalibration(State state, const Inputs& inputs, Outputs& outputs) {
  return state.calibrating ? exitCalibration(state, outputs) : enterCalibration(state, inputs);
}

// Swallows the power-on reset hold; a real toggle needs a fresh release-and-press.
static State consumeBootResetHold(State state, boolean calibrationButtonPressed) {
  if (!calibrationButtonPressed) {
    state.calibrationButtonReleasedSinceBoot = true;
  }
  state.calibrating = false;
  return state;
}

static boolean isCalibrationPressEdge(const State& previous, const Debouncer& advanced) {
  return advanced.stableState && !previous.calibrationButtonDebouncer.stableState;
}

// Momentary toggle: each debounced press edge flips calibration mode.
static State updateCalibrationButton(State state, const Inputs& inputs, Outputs& outputs) {
  boolean calibrationButtonPressedRaw = !inputs.calibrationButtonRaw;
  Debouncer advanced = advanceDebouncer(state.calibrationButtonDebouncer, calibrationButtonPressedRaw, inputs.nowMillis);
  boolean pressEdge = isCalibrationPressEdge(state, advanced);
  state.calibrationButtonDebouncer = advanced;

  if (!state.calibrationButtonReleasedSinceBoot) {
    return consumeBootResetHold(state, advanced.stableState);
  }
  if (!pressEdge) {
    return state;
  }
  return toggleCalibration(state, inputs, outputs);
}

static State trackCalibrationExtremes(State state, const Inputs& inputs) {
  if (state.calibrating) {
    state.calibration.x = expandAxisToInclude(state.calibration.x, inputs.joystickX);
    state.calibration.y = expandAxisToInclude(state.calibration.y, inputs.joystickY);
  }
  return state;
}

static void computeJoystickOutput(const State& state, const Inputs& inputs, Outputs& outputs) {
  if (state.calibrating) {  // hold center while calibrating so sweeping doesn't spray input
    outputs.joystickX = 0;
    outputs.joystickY = 0;
    return;
  }
  AxisCalibration xCalibration = state.calibration.x;
  AxisCalibration yCalibration = state.calibration.y;
  float normalizedX = normalizeAxisSignedAboutCenter(inputs.joystickX, xCalibration.minValue, xCalibration.center, xCalibration.maxValue);
  float normalizedY = normalizeAxisSignedAboutCenter(inputs.joystickY, yCalibration.minValue, yCalibration.center, yCalibration.maxValue);
  Vector2 deflection = applyRadialDeadzone(normalizedX, normalizedY);
  outputs.joystickX = (int)(deflection.x * JoystickOutputMax);
  outputs.joystickY = (int)(deflection.y * JoystickOutputMax);
}

TickResult computeTick(State state, Inputs inputs) {
  Outputs outputs;
  outputs.saveCalibration = false;

  state = updateGamepadButtons(state, inputs, outputs);
  state = updateCalibrationButton(state, inputs, outputs);
  state = trackCalibrationExtremes(state, inputs);
  computeJoystickOutput(state, inputs, outputs);
  outputs.calibrationLed = state.calibrating;

  TickResult result = { state, outputs };
  return result;
}
