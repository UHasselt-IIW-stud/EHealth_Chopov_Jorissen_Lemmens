#include <SPI.h>
#include <esp32-hal-gpio.h>
#include <HardwareSerial.h>

#if defined(ESP32)
  #include <WiFiMulti.h>
  WiFiMulti wifiMulti;
  #define DEVICE "ESP32"
  #elif defined(ESP8266)
  #include <ESP8266WiFiMulti.h>
  ESP8266WiFiMulti wifiMulti;
  #define DEVICE "ESP8266"
  #endif

#include <Arduino.h>
#include "Preferences.h"
#include <Wire.h>
#include <Adafruit_Sensor.h>
#include <Adafruit_ADXL345_U.h>
#include <Adafruit_NeoPixel.h>
#include "MAX30105.h"


unsigned long PrevMicros = 0;
uint16_t Sample_TimeUS = 1000*1000/10; //Sample time in microseconds
MAX30105 ppgSensor;
Adafruit_ADXL345_Unified accel = Adafruit_ADXL345_Unified(12345);

#include <InfluxDbClient.h>
#include <InfluxDbCloud.h>

#define I2C_SDA_PIN 8
#define I2C_SCL_PIN 10
// WiFi AP SSID
#define WIFI_SSID SSID_Uhasselt
// WiFi password
#define WIFI_PASSWORD Password_Uhasselt
#define INFLUXDB_URL url_Uhasselt
#define INFLUXDB_TOKEN "H1DRZGTLN5Dcau4KwiHIdGnZFOe-ZSJf4m9uNJ6Uu99LYf3_wE_JPrWL29SXwybYPDL6HtnuTJO2fatfCLBhhg==" 
#define INFLUXDB_ORG "EHealth"
#define INFLUXDB_BUCKET "Raw_Data_ecg_bloeddruk"

// Time zone info
#define TZ_INFO "UTC-1"

// Declare InfluxDB client instance with preconfigured InfluxCloud certificate
InfluxDBClient client(INFLUXDB_URL, INFLUXDB_ORG, INFLUXDB_BUCKET, INFLUXDB_TOKEN, InfluxDbCloud2CACert);
// Declare Data point
Point sensor("GSR_Data");
Point sensorNetworks("GSR_buffer");

Point accelerator("ACC_Data");
Point acceleratorBuffer("ACC_buffer");

Point ppgmeter("PPG_Data");
Point ppgmeterBuffer("PPG_buffer");

const int GSR=1; //
int sensorValue=0; //

void setup() {
  delay(10000);
  Serial.begin(115200);
  
  WiFi.setTxPower(WIFI_POWER_8_5dBm);
  WiFi.mode(WIFI_STA);
  wifiMulti.addAP(WIFI_SSID, WIFI_PASSWORD);
  
  Serial.print("Connecting to wifi");
  while (wifiMulti.run() != WL_CONNECTED) {
    Serial.print(".");
    delay(100);
  }
  Serial.println("");

  timeSync(TZ_INFO, "pool.ntp.org", "time.nis.gov");

  if (client.validateConnection()) {
    Serial.print("Connected to InfluxDB_1: ");
    Serial.println(client.getServerUrl());
  } else {
    Serial.print("InfluxDB connection failed: ");
    Serial.println(client.getLastErrorMessage());
  }
  
  Serial.println("\tAvailable RAM memory: " + String(esp_get_free_heap_size()) + " bytes");

  // Set write options for batching and precision
  client.setWriteOptions(
      WriteOptions()
          .writePrecision(WritePrecision::MS)
          .batchSize(1000)
          .bufferSize(2500)
          .flushInterval(100)
  );

  // Set HTTP options for the client
  client.setHTTPOptions(
      HTTPOptions().connectionReuse(true)
  );  


  Serial.println("Accelerometer Test");
  Serial.println("");
 
  Wire.begin(I2C_SDA_PIN, I2C_SCL_PIN); // Initialize I2C on GPIO pins for SDA and SCL
  accel.begin();

  if (!accel.begin()) {
    Serial.println("Ooops, no ADXL345 detected... Check your wiring!");
    while (1);
  }

  accel.setRange(ADXL345_RANGE_16_G);

  ppgSensor.begin();

  if (!ppgSensor.begin()) {
    Serial.println("Error initializing PPG sensor");
    while (1);
  }

  ppgSensor.setup(); //Configure sensor with default settings
  ppgSensor.setPulseAmplitudeRed(0x0A); //Turn Red LED to low to indicate sensor is running
  ppgSensor.setPulseAmplitudeGreen(0); //Turn off Green LED

  Serial.println("");
}

void sendDataToInfluxDB(float gsrValue, float acceleration_X, float acceleration_Y, float acceleration_Z, float ppgData) {
    // Add fields to the point
    if (client.isBufferEmpty()) {
      Serial.print("Buffer is empty\n");
      // Additional actions or logic after successful data transmission
      // Add data to sensorNetworks point and write it to the buffer
      sensorNetworks.addField("gsr_value", gsrValue); // Add new field to point (Field != indexed datapoint, used for raw data)
      acceleratorBuffer.addField("acceleration_X", acceleration_X);
      acceleratorBuffer.addField("acceleration_Y", acceleration_Y);
      acceleratorBuffer.addField("acceleration_Z", acceleration_Z);
      ppgmeterBuffer.addField("ppg_value", ppgData);
      client.writePoint(ppgmeterBuffer);
      client.writePoint(sensorNetworks); // Write point into buffer
      client.writePoint(acceleratorBuffer); // Write point into buffer
    }
    else{
    sensor.addField("gsr_value", gsrValue);
    accelerator.addField("acceleration_X", acceleration_X);
    accelerator.addField("acceleration_Y", acceleration_Y);
    accelerator.addField("acceleration_Z", acceleration_Z);
    ppgmeter.addField("ppg_value", ppgData);
    // Write the point to InfluxDB
    if (client.writePoint(sensor) and client.writePoint(accelerator) and client.writePoint(ppgmeter)) {
      //Serial.println("Data sent to InfluxDB successfully!");
      Serial.println("\tAvailable RAM memory: " + String(esp_get_free_heap_size()) + " bytes");
    } else {
      Serial.print("InfluxDB write failed: ");
      Serial.println(client.getLastErrorMessage());
    }
    // Clear previous data from the point
    sensor.clearFields();
    accelerator.clearFields();
    ppgmeter.clearFields();
  }
}

void loop(){
  if (micros() >= PrevMicros + Sample_TimeUS){
    PrevMicros = micros();
    /* Get a new sensor event */ 
    sensors_event_t event; 
    accel.getEvent(&event);
    float sensorValue = analogRead(GSR);
    float ppgData = ppgSensor.getIR();
    float acceleration_X = event.acceleration.x;
    float acceleration_Y = event.acceleration.y;
    float acceleration_Z = event.acceleration.z;
    
    /*
    Serial.print("\ngsrValue: " + String(sensorValue));
    Serial.print("");
    Serial.print("\n[");
    Serial.print(event.acceleration.x); Serial.print(", ");
    Serial.print(event.acceleration.y); Serial.print(", ");
    Serial.print(event.acceleration.z); Serial.println("] ");
    Serial.print("ppgValue: " + String(ppgData));
    Serial.print("");
    delay(500);
    */
    
    sendDataToInfluxDB(sensorValue, acceleration_X, acceleration_Y, acceleration_Z, ppgData);
  }
}