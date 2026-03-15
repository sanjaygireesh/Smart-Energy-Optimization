#include "DHT.h"
#include <Servo.h>

#define DHTPIN 2     
#define DHTTYPE DHT11   

// --- HARDWARE FIX ---
const int fanPin = 6;  // MOVED TO PIN 6 (Pin 10 dies when Servo is used)
const int servoPin = 9;

DHT dht(DHTPIN, DHTTYPE);
Servo myServo;

String inputString = "";         
boolean stringComplete = false;  

void setup() {
  Serial.begin(9600);
  dht.begin();
  
  pinMode(fanPin, OUTPUT);
  myServo.attach(servoPin);
  
  // Reserve memory
  inputString.reserve(200);
  
  // Startup Kick (Proven to work now)
  analogWrite(fanPin, 255);
  delay(500);
  analogWrite(fanPin, 0);
}

void loop() {
  // 1. Send Temp Data
  static unsigned long lastTime = 0;
  if (millis() - lastTime > 1000) {  
    lastTime = millis();
    float t = dht.readTemperature();
    if (!isnan(t)) {
      Serial.print("TEMP:");
      Serial.println(t);
    }
  }

  // 2. Process Command
  if (stringComplete) {
    parseCommand(inputString);
    inputString = "";
    stringComplete = false;
  }
}

void parseCommand(String data) {
  int commaIndex = data.indexOf(',');
  
  if (commaIndex != -1) {
    String speedStr = data.substring(0, commaIndex);
    String angleStr = data.substring(commaIndex + 1);
    
    int speed = speedStr.toInt();
    int angle = angleStr.toInt();
    
    // Safety Clamps
    if (speed > 255) speed = 255;
    if (speed < 0) speed = 0;
    if (angle > 180) angle = 180;
    if (angle < 0) angle = 0;

    analogWrite(fanPin, speed);
    myServo.write(angle);
  }
}

// Fast Serial Reading
void serialEvent() {
  while (Serial.available()) {
    char inChar = (char)Serial.read();
    if (inChar == '\n') {
      stringComplete = true;
    } else {
      inputString += inChar;
    }
  }
}