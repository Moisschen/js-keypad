#include <Keyboard.h>

#include <EEPROM.h>
#include <HID.h>
#include <avr/wdt.h>

#include "joystick_core.h"

// JS-Keypad: 12 finger keys (4 fingers x 3 rows) and a thumb key under the stick, one pin each
// (no matrix), plus the thumb stick.
// The keys always type keyboard keys. The stick has three modes: keyboard (stick types keys),
// gamepad (generic HID, Steam can turn it into an Xbox pad) or mouse. The gamepad / mouse
// descriptor is only registered in its mode, so in keyboard mode games see no controller.
// Switching saves the mode and reboots the board so Windows re-enumerates it.
//
// Key codes are stored as HID usage IDs (0x04 = A ... 0xE7 = right GUI, 0 = unbound), so a
// binding means the same physical key on every keyboard layout (QWERTZ, AZERTY, ...).

const int ModeEepromAddress = 96;  // after the KeyMap
const int RotationEepromAddress = 98;  // int8 degrees, -90..90 (0xFF from a fresh EEPROM reads as -1, so a magic byte guards it)
const int RotationMagicEepromAddress = 99;
const uint8_t RotationMagic = 0xA5;
const int MouseSpeedEepromAddress = 100;  // uint8 1..20, 0xFF from a fresh EEPROM falls back to the default
const uint8_t ModeKeyboard = 0;
const uint8_t ModeGamepad = 1;
const uint8_t ModeMouse = 2;
const uint8_t GamepadReportId = 3;  // 1 and 2 are taken by Mouse/Keyboard
const uint8_t MouseReportId = 4;
const uint8_t DefaultMouseSpeed = 8;
const char FirmwareVersion[] = "1.1";  // bump on every release; the web mapper compares it with docs/firmware-version.txt
uint8_t mouseSpeed = DefaultMouseSpeed;  // pixels per 8 ms at full deflection

static const uint8_t GamepadDescriptor[] PROGMEM = {
  0x05, 0x01,        // Usage Page (Generic Desktop)
  0x09, 0x05,        // Usage (Game Pad)
  0xA1, 0x01,        // Collection (Application)
  0x85, GamepadReportId,
  0x09, 0x30,        //   Usage (X)
  0x09, 0x31,        //   Usage (Y)
  0x16, 0x01, 0x80,  //   Logical Minimum (-32767)
  0x26, 0xFF, 0x7F,  //   Logical Maximum (32767)
  0x75, 0x10,        //   Report Size (16)
  0x95, 0x02,        //   Report Count (2)
  0x81, 0x02,        //   Input (Data, Var, Abs)
  0x05, 0x09,        //   Usage Page (Button)
  0x19, 0x01,        //   Usage Minimum (1)
  0x29, 0x10,        //   Usage Maximum (16)
  0x15, 0x00,        //   Logical Minimum (0)
  0x25, 0x01,        //   Logical Maximum (1)
  0x75, 0x01,        //   Report Size (1)
  0x95, 0x10,        //   Report Count (16)
  0x81, 0x02,        //   Input (Data, Var, Abs)
  0xC0               // End Collection
};

// Mouse mode: the stick moves the pointer, the stick click is the left button.
static const uint8_t MouseDescriptor[] PROGMEM = {
  0x05, 0x01,        // Usage Page (Generic Desktop)
  0x09, 0x02,        // Usage (Mouse)
  0xA1, 0x01,        // Collection (Application)
  0x09, 0x01,        //   Usage (Pointer)
  0xA1, 0x00,        //   Collection (Physical)
  0x85, MouseReportId,
  0x05, 0x09,        //     Usage Page (Button)
  0x19, 0x01, 0x29, 0x03,        // Usage Minimum (1) .. Maximum (3)
  0x15, 0x00, 0x25, 0x01,        // Logical Minimum (0) .. Maximum (1)
  0x75, 0x01, 0x95, 0x03,        // Report Size (1), Count (3)
  0x81, 0x02,        //     Input (Data, Var, Abs)
  0x75, 0x05, 0x95, 0x01,        // 5 bits padding
  0x81, 0x03,        //     Input (Const)
  0x05, 0x01,        //     Usage Page (Generic Desktop)
  0x09, 0x30, 0x09, 0x31, 0x09, 0x38,  // Usage X, Y, Wheel
  0x15, 0x81, 0x25, 0x7F,        // Logical Minimum (-127) .. Maximum (127)
  0x75, 0x08, 0x95, 0x03,        // Report Size (8), Count (3)
  0x81, 0x06,        //     Input (Data, Var, Rel)
  0xC0, 0xC0         //   End Collection, End Collection
};

struct MouseReport {
  uint8_t buttons;
  int8_t x;
  int8_t y;
  int8_t wheel;
};

struct GamepadReport {
  int16_t x;
  int16_t y;
  uint16_t buttons;  // bit 0 = stick click, the rest only come from the mapper (BTN command)
};

// Virtual button pressed by the mapper, so Steam's setup wizard can be walked through
// even though the stick only has one physical button.
uint8_t virtualButton = 0;  // 1..16 = button, 17..20 = stick left/right/up/down, 0 = none
unsigned long virtualButtonStartMillis = 0;
const unsigned long VirtualButtonMillis = 400;

// Runs during static init, before USB enumerates, so the descriptor is there in time.
struct GamepadRegistrar {
  uint8_t mode;
  GamepadRegistrar() {
    uint8_t stored = EEPROM.read(ModeEepromAddress);
    mode = (stored == ModeGamepad || stored == ModeMouse) ? stored : ModeKeyboard;
    if (mode == ModeGamepad) {
      static HIDSubDescriptor node(GamepadDescriptor, sizeof(GamepadDescriptor));
      HID().AppendDescriptor(&node);
    } else if (mode == ModeMouse) {
      static HIDSubDescriptor node(MouseDescriptor, sizeof(MouseDescriptor));
      HID().AppendDescriptor(&node);
    }
  }
};
GamepadRegistrar gamepadRegistrar;

const boolean InvertLeftXAxis = false;
const boolean InvertLeftYAxis = true;  // raw high = down

const int Pin_LeftJoyX = A1;
const int Pin_LeftJoyY = A0;

const int Pin_CalibrationLed = 2;
const int CalibrationEepromAddress = 0;
const int KeyMapEepromAddress = 64;  // after Calibration (well below 64 bytes)

const unsigned long TickIntervalMicros = 1000;
const int ReleaseHysteresisPercent = 15;  // release this far below the press threshold

const unsigned long VirtualPressMillis = 100;

const uint16_t KeyMapMagicNumber = 0x504C;  // 'LP' - 1.0 had one key less

// Slots 0..11 are the finger keys, row by row (top, home, bottom), each row index, middle, ring,
// pinky; slot 12 is the thumb key under the stick.
const int NumKeys = 13;
enum StickSlot { SlotUp = NumKeys, SlotDown, SlotLeft, SlotRight, SlotClick, NumSlots };

// Each key between its pin and GND (INPUT_PULLUP). Same order as the slots.
const uint8_t KeyPins[NumKeys] = {
  0, 1, 3, 4,      // top row
  5, 6, 7, 8,      // home row
  9, 10, A2, A3,   // bottom row
  15,              // thumb key (pin 15 was the calibration button; calibration now only runs from the mapper)
};
const unsigned long KeyLockoutMillis = 8;  // ignore contact bounce right after a change

struct KeyMap {
  uint16_t magicNumber;
  uint8_t keys[NumSlots];    // HID usage IDs, 0 = unbound
  uint8_t thresholdPercent;  // stick travel needed to press a direction key
};

const KeyMap DefaultKeyMap = { KeyMapMagicNumber, {
  0x21, 0x20, 0x1F, 0x1E,  // 4 3 2 1
  0x15, 0x08, 0x14, 0x2B,  // R E Q Tab
  0x2C, 0x0A, 0x09, 0xE0,  // Space G F Ctrl
  0x06,                    // thumb key: C
  0x1A, 0x16, 0x04, 0x07,  // stick W S A D
  0xE1,                    // stick click: Shift
}, 50 };

struct ButtonConfig {
  int pin;
};

const ButtonConfig ButtonConfigs[] = {
  { 14 },
};

// Some boards have the stick click wired to pin 16; either pin pulled LOW counts as a press.
const int Pin_StickClickAlt = 16;

// Digital pins the wiring check watches. Not pin 2 (LED output) and not A0/A1 (stick axes,
// a pull-up there would skew the reading). A2/A3 are key inputs here, so they are watched.
const uint8_t DiagPins[] = { 0, 1, 3, 4, 5, 6, 7, 8, 9, 10, 14, 15, 16, A2, A3 };

static int readButtonPin(int buttonIndex) {
  if (buttonIndex == 0 && digitalRead(Pin_StickClickAlt) == LOW) {
    return LOW;
  }
  return digitalRead(ButtonConfigs[buttonIndex].pin);
}

static_assert(sizeof(ButtonConfigs) / sizeof(ButtonConfigs[0]) == NumGamepadButtons,
              "ButtonConfigs size must match NumGamepadButtons in joystick_core.h");

// A watchdog reset leaves the watchdog running; switch it off before anything else.
// (Defined below the types because the Arduino builder puts prototypes above the first function.)
void disableWatchdogAtBoot() __attribute__((naked, used, section(".init3")));
void disableWatchdogAtBoot() {
  MCUSR = 0;
  wdt_disable();
}

KeyMap keyMap;
boolean slotPressed[NumSlots];
boolean keyStable[NumKeys];  // debounced key state, true = pressed
unsigned long keyChangeMillis[NumKeys];

// Last values, reported to the mapper tool for its live preview.
int lastRawX = 0;
int lastRawY = 0;
int lastStickX = 0;
int lastStickY = 0;
boolean lastCalibrating = false;
boolean serialCalibrationPressPending = false;

static boolean isValidKeyMap(const KeyMap& candidate) {
  return candidate.magicNumber == KeyMapMagicNumber
         && candidate.thresholdPercent >= 20 && candidate.thresholdPercent <= 95;
}

// HID usage -> Keyboard.h code: modifiers are 128..135, other raw usages are offset by 136.
static uint8_t keyboardCode(uint8_t usage) {
  if (usage >= 0xE0 && usage <= 0xE7) return 128 + (usage - 0xE0);
  if (usage >= 0x04 && usage < 120) return usage + 136;
  return 0;  // unbound or out of Keyboard.h's range
}

// The click at boot does two things: held long it opens the bootloader (the rescue path on a
// glued-shut case, since RST is unreachable), released earlier it cycles the mode.
// Same mechanism the Arduino core uses for its 1200 baud reset (Caterina magic key + watchdog).
const unsigned long BootloaderHoldMillis = 3000;
boolean shortClickAtBoot = false;

void handleClickAtBoot() {
  pinMode(ButtonConfigs[0].pin, INPUT_PULLUP);
  pinMode(Pin_StickClickAlt, INPUT_PULLUP);
  delay(50);  // let the pull-ups settle before reading
  if (readButtonPin(0) != LOW) return;

  unsigned long startMillis = millis();
  while (readButtonPin(0) == LOW) {
    if (millis() - startMillis >= BootloaderHoldMillis) {
      USBDevice.detach();
      *(volatile uint16_t*)0x0800 = 0x7777;  // MAGIC_KEY / MAGIC_KEY_POS from the Arduino core
      wdt_enable(WDTO_120MS);
      while (true) {
      }
    }
  }
  shortClickAtBoot = true;
}

static void rebootIntoMode(uint8_t mode, boolean replyOverSerial);

// Plugging in with the stick held selects the mode without the mapper: up = keyboard,
// right = gamepad, down = mouse. A short click while plugging in cycles through the three.
static void applyPlugInModeChoice() {
  Calibration stored;
  EEPROM.get(CalibrationEepromAddress, stored);
  Calibration calibration = validateCalibration(stored);

  long x = 0, y = 0;
  for (int sample = 0; sample < 8; sample++) {
    x += analogRead(Pin_LeftJoyX);
    y += analogRead(Pin_LeftJoyY);
    delay(5);
  }
  x /= 8;
  y /= 8;

  long dx = x - calibration.x.center;
  long dy = calibration.y.center - y;  // raw high = down, so flip it: positive = up

  // Half of the calibrated travel, so it works on sticks with a small raw swing too.
  long travelX = max(calibration.x.maxValue - calibration.x.center, calibration.x.center - calibration.x.minValue);
  long travelY = max(calibration.y.maxValue - calibration.y.center, calibration.y.center - calibration.y.minValue);
  const long MinTravel = 60;  // fallback for an uncalibrated stick
  long thresholdX = max(travelX / 2, MinTravel);
  long thresholdY = max(travelY / 2, MinTravel);
  uint8_t wanted;
  if (dy > thresholdY && abs(dy) > abs(dx)) wanted = ModeKeyboard;
  else if (-dy > thresholdY && abs(dy) > abs(dx)) wanted = ModeMouse;
  else if (dx > thresholdX) wanted = ModeGamepad;
  else if (shortClickAtBoot) wanted = (gamepadRegistrar.mode + 1) % 3;  // short click cycles the modes
  else return;  // stick resting or pushed left: keep the saved mode

  if (wanted != gamepadRegistrar.mode) rebootIntoMode(wanted, false);
}

void setup() {
  handleClickAtBoot();
  for (int buttonIndex = 0; buttonIndex < NumGamepadButtons; buttonIndex++) {
    pinMode(ButtonConfigs[buttonIndex].pin, INPUT_PULLUP);
  }
  pinMode(Pin_StickClickAlt, INPUT_PULLUP);
  for (uint8_t i = 0; i < sizeof(DiagPins); i++) {
    pinMode(DiagPins[i], INPUT_PULLUP);  // defined level, so the wiring check can spot a button on any pin
  }
  for (int key = 0; key < NumKeys; key++) {
    pinMode(KeyPins[key], INPUT_PULLUP);
  }
  pinMode(Pin_CalibrationLed, OUTPUT);
  digitalWrite(Pin_CalibrationLed, LOW);

  loadRotation();
  uint8_t storedSpeed = EEPROM.read(MouseSpeedEepromAddress);
  mouseSpeed = (storedSpeed >= 1 && storedSpeed <= 20) ? storedSpeed : DefaultMouseSpeed;
  EEPROM.get(KeyMapEepromAddress, keyMap);
  if (!isValidKeyMap(keyMap)) {
    keyMap = DefaultKeyMap;
  }

  applyPlugInModeChoice();

  Serial.begin(115200);
  Keyboard.begin();
}

static boolean isTimeForNextTick(unsigned long& nextTickMicros) {
  if ((long)(micros() - nextTickMicros) < 0) {
    return false;
  }
  nextTickMicros += TickIntervalMicros;
  if ((long)(micros() - nextTickMicros) > 0) {
    nextTickMicros = micros() + TickIntervalMicros;
  }
  return true;
}

// A CAL command from the tool becomes one virtual calibrate press lasting VirtualPressMillis.
static boolean serialCalibrationPulse(unsigned long nowMillis) {
  static unsigned long pulseStartMillis = 0;
  static boolean pulsing = false;

  if (serialCalibrationPressPending) {
    serialCalibrationPressPending = false;
    pulsing = true;
    pulseStartMillis = nowMillis;
  }
  if (pulsing && nowMillis - pulseStartMillis >= VirtualPressMillis) {
    pulsing = false;
  }
  return pulsing;
}

static Inputs readInputs() {
  Inputs inputs;
  inputs.nowMillis = millis();
  inputs.joystickX = analogRead(Pin_LeftJoyX);
  inputs.joystickY = analogRead(Pin_LeftJoyY);
  for (int buttonIndex = 0; buttonIndex < NumGamepadButtons; buttonIndex++) {
    inputs.gamepadButtonRaw[buttonIndex] = readButtonPin(buttonIndex);
  }
  // Calibration is only started from the mapper (CAL), so the stick click can be held in games.
  boolean virtualPress = serialCalibrationPulse(inputs.nowMillis);
  inputs.calibrationButtonRaw = !virtualPress;  // HIGH = released
  return inputs;
}

static void setSlotPressed(int slot, boolean pressed) {
  if (pressed == slotPressed[slot]) {
    return;
  }
  slotPressed[slot] = pressed;
  uint8_t code = keyboardCode(keyMap.keys[slot]);
  if (code == 0) {
    return;  // unbound: still shown pressed in the mapper, but types nothing
  }
  if (pressed) {
    Keyboard.press(code);
  } else {
    Keyboard.release(code);
  }
}

static void releaseAllSlots() {
  for (int slot = 0; slot < NumSlots; slot++) {
    setSlotPressed(slot, false);
  }
}

// Press acts at once; a change within KeyLockoutMillis of the last one is contact bounce.
static void updateKeys(unsigned long now) {
  for (int key = 0; key < NumKeys; key++) {
    boolean raw = digitalRead(KeyPins[key]) == LOW;
    if (raw != keyStable[key] && now - keyChangeMillis[key] >= KeyLockoutMillis) {
      keyStable[key] = raw;
      keyChangeMillis[key] = now;
    }
    setSlotPressed(key, keyStable[key]);
  }
}

// Presses above the threshold, releases only once back below threshold minus hysteresis.
static void updateDirectionSlot(int slot, int deflection) {
  long pressLevel = (long)JoystickOutputMax * keyMap.thresholdPercent / 100;
  long releaseLevel = (long)JoystickOutputMax * (keyMap.thresholdPercent - ReleaseHysteresisPercent) / 100;
  setSlotPressed(slot, deflection > (slotPressed[slot] ? releaseLevel : pressLevel));
}

// Sends only on change to keep the USB bus quiet. HID Y grows downwards.
static void sendGamepadReport(int x, int y, boolean clickPressed) {
  static GamepadReport lastReport = { 0, 0, 0xFFFF };
  uint16_t buttons = clickPressed ? 1 : 0;
  if (virtualButton != 0) {
    if (millis() - virtualButtonStartMillis < VirtualButtonMillis) {
      switch (virtualButton) {
        case 17: x = -JoystickOutputMax; y = 0; break;
        case 18: x = JoystickOutputMax; y = 0; break;
        case 19: x = 0; y = JoystickOutputMax; break;
        case 20: x = 0; y = -JoystickOutputMax; break;
        default: buttons |= (uint16_t)1 << (virtualButton - 1);
      }
    } else {
      virtualButton = 0;
    }
  }
  // Live preview in the mapper; the stick slots type nothing in this mode.
  slotPressed[SlotUp] = y > JoystickOutputMax / 2;
  slotPressed[SlotDown] = -y > JoystickOutputMax / 2;
  slotPressed[SlotLeft] = -x > JoystickOutputMax / 2;
  slotPressed[SlotRight] = x > JoystickOutputMax / 2;
  slotPressed[SlotClick] = clickPressed;
  GamepadReport report = { (int16_t)x, (int16_t)(-y), buttons };
  if (memcmp(&report, &lastReport, sizeof(report)) == 0) {
    return;
  }
  lastReport = report;
  HID().SendReport(GamepadReportId, &report, sizeof(report));
}

const int MouseDeadzone = JoystickOutputMax / 10;
const unsigned long MouseIntervalMillis = 8;

// Squared response: small movements stay precise, full deflection is fast.
static float mouseStep(int value) {
  if (abs(value) < MouseDeadzone) return 0.0f;
  float normalized = (float)(abs(value) - MouseDeadzone) / (JoystickOutputMax - MouseDeadzone);
  float step = normalized * normalized * mouseSpeed;
  return value < 0 ? -step : step;
}

// Short press = left click (sent on release), holding = right click while held.
const unsigned long MouseHoldMillis = 500;
const unsigned long MouseClickMillis = 60;

static uint8_t mouseButtons(boolean clickPressed, unsigned long now) {
  static boolean wasPressed = false;
  static unsigned long pressStartMillis = 0;
  static boolean stillUndecided = false;  // pressed, but not held long enough to be a right click
  static unsigned long leftClickUntil = 0;

  if (clickPressed && !wasPressed) {
    pressStartMillis = now;
    stillUndecided = true;
  } else if (!clickPressed && wasPressed && stillUndecided) {
    leftClickUntil = now + MouseClickMillis;  // released in time: tap the left button
    stillUndecided = false;
  }
  wasPressed = clickPressed;

  if (clickPressed && stillUndecided && now - pressStartMillis >= MouseHoldMillis) stillUndecided = false;
  if (clickPressed && !stillUndecided) return 2;  // held long enough: right button
  if ((long)(leftClickUntil - now) > 0) return 1;
  return 0;
}

static void sendMouseReport(int x, int y, boolean clickPressed) {
  static unsigned long lastMillis = 0;
  static float carryX = 0, carryY = 0;  // keep the fraction, so slow movement still creeps along
  static uint8_t lastButtons = 0xFF;

  slotPressed[SlotClick] = clickPressed;
  unsigned long now = millis();
  if (now - lastMillis < MouseIntervalMillis) return;
  lastMillis = now;

  uint8_t buttons = mouseButtons(clickPressed, now);

  carryX += mouseStep(x);
  carryY -= mouseStep(y);  // HID Y grows downwards
  int8_t dx = (int8_t)constrain((int)carryX, -127, 127);
  int8_t dy = (int8_t)constrain((int)carryY, -127, 127);
  carryX -= dx; carryY -= dy;

  if (dx == 0 && dy == 0 && buttons == lastButtons) return;
  lastButtons = buttons;
  MouseReport report = { buttons, dx, dy, 0 };
  HID().SendReport(MouseReportId, &report, sizeof(report));
}

static void rebootIntoMode(uint8_t mode, boolean replyOverSerial) {
  releaseAllSlots();
  EEPROM.update(ModeEepromAddress, mode);
  if (replyOverSerial) {
    Serial.println(F("OK"));
    Serial.flush();
  }
  delay(100);
  USBDevice.detach();
  delay(200);
  // Clear the bootloader magic key so the watchdog reset starts the sketch, not the bootloader.
  *(volatile uint16_t*)0x0800 = 0;
  *(volatile uint16_t*)(RAMEND - 1) = 0;
  wdt_enable(WDTO_15MS);
  while (true) {
  }
}

// Stick rotation to correct a stick mounted slightly crooked. Positive = clockwise.
int8_t rotationDegrees = 0;
float rotationCos = 1.0f;
float rotationSin = 0.0f;

static void setRotation(int8_t degrees) {
  rotationDegrees = degrees;
  float radians = degrees * (float)M_PI / 180.0f;
  rotationCos = cos(radians);
  rotationSin = sin(radians);
}

static void loadRotation() {
  int8_t stored = (int8_t)EEPROM.read(RotationEepromAddress);
  boolean valid = EEPROM.read(RotationMagicEepromAddress) == RotationMagic && stored >= -90 && stored <= 90;
  setRotation(valid ? stored : 0);
}

static int clampAxis(float value) {
  if (value > JoystickOutputMax) return JoystickOutputMax;
  if (value < -JoystickOutputMax) return -JoystickOutputMax;
  return (int)value;
}

static void applyOutputs(const Outputs& outputs, const State& state, const Inputs& inputs) {
  int rawX = InvertLeftXAxis ? -outputs.joystickX : outputs.joystickX;
  int rawY = InvertLeftYAxis ? -outputs.joystickY : outputs.joystickY;  // positive = up
  int x = clampAxis(rawX * rotationCos + rawY * rotationSin);
  int y = clampAxis(rawY * rotationCos - rawX * rotationSin);

  updateKeys(inputs.nowMillis);
  if (gamepadRegistrar.mode == ModeGamepad) {
    sendGamepadReport(x, y, outputs.gamepadButtons[0] && !state.calibrating);
  } else if (gamepadRegistrar.mode == ModeMouse) {
    sendMouseReport(state.calibrating ? 0 : x, state.calibrating ? 0 : y, outputs.gamepadButtons[0] && !state.calibrating);
  } else {
    updateDirectionSlot(SlotRight, x);
    updateDirectionSlot(SlotLeft, -x);
    updateDirectionSlot(SlotUp, y);
    updateDirectionSlot(SlotDown, -y);
    setSlotPressed(SlotClick, outputs.gamepadButtons[0] && !state.calibrating);
  }
  digitalWrite(Pin_CalibrationLed, outputs.calibrationLed ? HIGH : LOW);

  if (outputs.saveCalibration) {
    EEPROM.put(CalibrationEepromAddress, state.calibration);
  }

  lastRawX = inputs.joystickX;
  lastRawY = inputs.joystickY;
  lastStickX = x;
  lastStickY = y;
  lastCalibrating = state.calibrating;
}

// ---- Serial protocol (one command per line) ----
// Slots: 0..11 finger keys (top/home/bottom row, each index, middle, ring, pinky), 12 thumb key,
//        13..17 stick up, down, left, right, click. Codes are HID usage IDs, 0 = unbound.
//   GET                          -> CFG <18 codes> <threshold>
//   SET <18 codes> <threshold>   -> OK | ERR   (saved to EEPROM)
//   RESETKEYS                    -> CFG ...    (defaults, saved)
//   STATE                        -> STATE <rawX> <rawY> <x> <y> <calibrating> <18 chars 0/1, one per slot>
//   CAL                          -> OK          (toggles calibration)
//   MODE                         -> MODE <0 keyboard | 1 gamepad | 2 mouse>
//   MODE <0|1|2>                 -> OK          (board reboots on change)
//   VER                          -> VER <firmware version>
//   DEV                          -> DEV JS-KEYPAD
//   SPD                          -> SPD <1..20>
//   SPD <1..20>                  -> OK | ERR    (mouse speed, saved)
//   DIAG                         -> DIAG <A0> <A1> <pins reading LOW, comma separated or ->
//   ROT                          -> ROT <degrees>
//   ROT <-90..90>                -> OK | ERR    (stick rotation, clockwise positive, saved)
//   BTN <1..20>                  -> OK | ERR    (gamepad mode: taps button 1..16 or pushes the
//                                                stick left/right/up/down (17..20) for 400 ms)

static void printKeyMap() {
  Serial.print(F("CFG"));
  for (int slot = 0; slot < NumSlots; slot++) {
    Serial.print(' ');
    Serial.print(keyMap.keys[slot]);
  }
  Serial.print(' ');
  Serial.println(keyMap.thresholdPercent);
}

static void saveKeyMap(const KeyMap& newKeyMap) {
  releaseAllSlots();  // release with the old codes before they change
  keyMap = newKeyMap;
  EEPROM.put(KeyMapEepromAddress, keyMap);
}

static void handleSetCommand(char* arguments) {
  KeyMap candidate = keyMap;
  for (int field = 0; field <= NumSlots; field++) {
    char* token = strtok(field == 0 ? arguments : NULL, " ");
    if (token == NULL) {
      Serial.println(F("ERR"));
      return;
    }
    long value = atol(token);
    if (value < 0 || value > 255) {
      Serial.println(F("ERR"));
      return;
    }
    if (field < NumSlots) {
      candidate.keys[field] = (uint8_t)value;
    } else {
      candidate.thresholdPercent = (uint8_t)value;
    }
  }
  if (!isValidKeyMap(candidate)) {
    Serial.println(F("ERR"));
    return;
  }
  saveKeyMap(candidate);
  Serial.println(F("OK"));
}

static void printState() {
  Serial.print(F("STATE "));
  Serial.print(lastRawX);
  Serial.print(' ');
  Serial.print(lastRawY);
  Serial.print(' ');
  Serial.print(lastStickX);
  Serial.print(' ');
  Serial.print(lastStickY);
  Serial.print(' ');
  Serial.print(lastCalibrating ? 1 : 0);
  Serial.print(' ');
  for (int slot = 0; slot < NumSlots; slot++) {
    Serial.print(slotPressed[slot] ? '1' : '0');
  }
  Serial.println();
}

// Raw readings for the web mapper's wiring check.
static void printDiag() {
  Serial.print(F("DIAG "));
  Serial.print(analogRead(A0));
  Serial.print(' ');
  Serial.print(analogRead(A1));
  Serial.print(' ');
  boolean any = false;
  for (uint8_t i = 0; i < sizeof(DiagPins); i++) {
    if (digitalRead(DiagPins[i]) == LOW) {
      if (any) Serial.print(',');
      Serial.print(DiagPins[i]);
      any = true;
    }
  }
  if (!any) Serial.print('-');
  Serial.println();
}

static void handleCommand(char* line) {
  if (strcmp(line, "GET") == 0) {
    printKeyMap();
  } else if (strncmp(line, "SET ", 4) == 0) {
    handleSetCommand(line + 4);
  } else if (strcmp(line, "RESETKEYS") == 0) {
    saveKeyMap(DefaultKeyMap);
    printKeyMap();
  } else if (strcmp(line, "STATE") == 0) {
    printState();
  } else if (strcmp(line, "CAL") == 0) {
    serialCalibrationPressPending = true;
    Serial.println(F("OK"));
  } else if (strncmp(line, "BTN ", 4) == 0) {
    int button = atoi(line + 4);
    if (gamepadRegistrar.mode != ModeGamepad || button < 1 || button > 20) {
      Serial.println(F("ERR"));
    } else {
      virtualButton = (uint8_t)button;
      virtualButtonStartMillis = millis();
      Serial.println(F("OK"));
    }
  } else if (strcmp(line, "VER") == 0) {
    Serial.print(F("VER "));
    Serial.println(FirmwareVersion);
  } else if (strcmp(line, "DEV") == 0) {
    Serial.println(F("DEV JS-KEYPAD"));
  } else if (strcmp(line, "SPD") == 0) {
    Serial.print(F("SPD "));
    Serial.println(mouseSpeed);
  } else if (strncmp(line, "SPD ", 4) == 0) {
    int speed = atoi(line + 4);
    if (speed < 1 || speed > 20) {
      Serial.println(F("ERR"));
    } else {
      mouseSpeed = (uint8_t)speed;
      EEPROM.update(MouseSpeedEepromAddress, mouseSpeed);
      Serial.println(F("OK"));
    }
  } else if (strcmp(line, "DIAG") == 0) {
    printDiag();
  } else if (strcmp(line, "ROT") == 0) {
    Serial.print(F("ROT "));
    Serial.println(rotationDegrees);
  } else if (strncmp(line, "ROT ", 4) == 0) {
    int degrees = atoi(line + 4);
    if (degrees < -90 || degrees > 90) {
      Serial.println(F("ERR"));
    } else {
      setRotation((int8_t)degrees);
      EEPROM.update(RotationEepromAddress, (uint8_t)(int8_t)degrees);
      EEPROM.update(RotationMagicEepromAddress, RotationMagic);
      Serial.println(F("OK"));
    }
  } else if (strcmp(line, "MODE") == 0) {
    Serial.print(F("MODE "));
    Serial.println(gamepadRegistrar.mode);
  } else if (strcmp(line, "MODE 0") == 0 || strcmp(line, "MODE 1") == 0 || strcmp(line, "MODE 2") == 0) {
    uint8_t mode = line[5] - '0';
    if (mode == gamepadRegistrar.mode) {
      Serial.println(F("OK"));
    } else {
      rebootIntoMode(mode, true);
    }
  } else if (line[0] != '\0') {
    Serial.println(F("ERR"));
  }
}

static void pollSerial() {
  static char line[96];  // SET with 18 codes is up to ~80 characters
  static int length = 0;

  while (Serial.available() > 0) {
    char received = Serial.read();
    if (received == '\r') {
      continue;
    }
    if (received == '\n') {
      line[length] = '\0';
      handleCommand(line);
      length = 0;
    } else if (length < (int)sizeof(line) - 1) {
      line[length++] = received;
    }
  }
}

void loop() {
  static boolean initialized = false;
  static State state;
  static unsigned long nextTickMicros = 0;

  if (!initialized) {
    Calibration storedCalibration;
    EEPROM.get(CalibrationEepromAddress, storedCalibration);
    state = makeInitialState(resolveInitialCalibration(storedCalibration, false), false);
    nextTickMicros = micros();
    initialized = true;
  }

  pollSerial();

  if (!isTimeForNextTick(nextTickMicros)) {
    return;
  }

  Inputs inputs = readInputs();
  TickResult result = computeTick(state, inputs);
  state = result.state;
  applyOutputs(result.outputs, state, inputs);
}
