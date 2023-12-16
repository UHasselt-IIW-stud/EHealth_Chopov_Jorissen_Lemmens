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
#include "spo2_algorithm.h"
#include "heartRate.h"

unsigned long PrevMicros = 0;
uint16_t Sample_TimeUS = 1000*1000/100; //Sample time in microseconds
MAX30105 ppgSensor;
Adafruit_ADXL345_Unified accel = Adafruit_ADXL345_Unified(12345);

#include <InfluxDbClient.h>
#include <InfluxDbCloud.h>

#define I2C_SDA_PIN 8
#define I2C_SCL_PIN 10
// WiFi AP SSID
#define WIFI_SSID SSID_thuis
// WiFi password
#define WIFI_PASSWORD Password_thuis
#define INFLUXDB_URL url_thuis
#define INFLUXDB_TOKEN "H1DRZGTLN5Dcau4KwiHIdGnZFOe-ZSJf4m9uNJ6Uu99LYf3_wE_JPrWL29SXwybYPDL6HtnuTJO2fatfCLBhhg==" 
#define INFLUXDB_ORG "EHealth"
#define INFLUXDB_BUCKET "Raw_Data_ecg_bloeddruk"

// Time zone info
#define TZ_INFO "UTC1"

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

#define MAX_BRIGHTNESS 255

uint32_t irBuffer[100]; //infrared LED sensor data
uint32_t redBuffer[100];  //red LED sensor data

int32_t bufferLength; //data length
int32_t spo2; //SPO2 value
int8_t validSPO2; //indicator to show if the SPO2 calculation is valid
int32_t heartRate; //heart rate value calcualated as per Maxim's algorithm
int8_t validHeartRate; //indicator to show if the heart rate calculation is valid


long lastBeat = 0; //Time at which the last beat occurred

float beatsPerMinute; //stores the BPM as per custom algorithm
int beatAvg = 0, sp02Avg = 0; //stores the average BPM and SPO2 
float ledBlinkFreq; //stores the frequency to blink the pulseLED

#define MAX30105_I2C_ADDRESS 0x57 // MAX30105 sensor I2C address
#define ADXL345_I2C_ADDRESS 0x53  // or 0x1D depending on the ADXL345 address configuration

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
          .batchSize(240)
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
  
  if (!accel.begin()) {
    Serial.println("Ooops, no ADXL345 detected... Check your wiring!");
    setup();
  }

  accel.setRange(ADXL345_RANGE_16_G);

  Serial.print("Initializing Pulse Oximeter..");
  if (!ppgSensor.begin(Wire, I2C_SPEED_FAST)) {
    Serial.println("Error initializing PPG sensor");
    while(1);
  }

  byte ledBrightness = 50; //Options: 0=Off to 255=50mA
  byte sampleAverage = 1; //Options: 1, 2, 4, 8, 16, 32
  byte ledMode = 2; //Options: 1 = Red only, 2 = Red + IR, 3 = Red + IR + Green
  byte sampleRate = 100; //Options: 50, 100, 200, 400, 800, 1000, 1600, 3200
  int pulseWidth = 69; //Options: 69, 118, 215, 411
  int adcRange = 4096; //Options: 2048, 4096, 8192, 16384

  ppgSensor.setup(ledBrightness, sampleAverage, ledMode, sampleRate, pulseWidth, adcRange); //Configure sensor with these settings

}

void sendDataToInfluxDB(float gsrValue, float acceleration_X, float acceleration_Y, float acceleration_Z, float sp02Avg, float beatAvg) {
    // Add fields to the point
    if (client.isBufferEmpty()) {
      Serial.print("Buffer is empty\n");
      // Additional actions or logic after successful data transmission
      // Add data to sensorNetworks point and write it to the buffer
      sensorNetworks.addField("gsr_value", gsrValue); // Add new field to point (Field != indexed datapoint, used for raw data)
      acceleratorBuffer.addField("acceleration_X", acceleration_X);
      acceleratorBuffer.addField("acceleration_Y", acceleration_Y);
      acceleratorBuffer.addField("acceleration_Z", acceleration_Z);
      ppgmeterBuffer.addField("sp02", sp02Avg);
      ppgmeterBuffer.addField("bpm", beatAvg);
      client.writePoint(ppgmeterBuffer);
      client.writePoint(sensorNetworks); // Write point into buffer
      client.writePoint(acceleratorBuffer); // Write point into buffer
    }
    else{
    sensor.addField("gsr_value", gsrValue);
    accelerator.addField("acceleration_X", acceleration_X);
    accelerator.addField("acceleration_Y", acceleration_Y);
    accelerator.addField("acceleration_Z", acceleration_Z);
    ppgmeter.addField("sp02", sp02Avg);
    ppgmeter.addField("bpm", beatAvg);
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
  bufferLength = 100; //buffer length of 100 stores 4 seconds of samples running at 25sps
  
  //read the first 100 samples, and determine the signal range
  for (byte i = 0 ; i < bufferLength ; i++)
  {
    while (ppgSensor.available() == false) //do we have new data?
      ppgSensor.check(); //Check the sensor for new data
  
    redBuffer[i] = ppgSensor.getIR();
    irBuffer[i] = ppgSensor.getRed();
    ppgSensor.nextSample(); //We're finished with this sample so move to next sample
  
    Serial.print(F("red: "));
    Serial.print(redBuffer[i], DEC);
    Serial.print(F("\t ir: "));
    Serial.println(irBuffer[i], DEC);
  }
  
  //calculate heart rate and SpO2 after first 100 samples (first 4 seconds of samples)
  maxim_heart_rate_and_oxygen_saturation(irBuffer, bufferLength, redBuffer, &spo2, &validSPO2, &heartRate, &validHeartRate);
  
  //Continuously taking samples from MAX30102.  Heart rate and SpO2 are calculated every 1 second
  while (1)
  {
    //dumping the first 25 sets of samples in the memory and shift the last 75 sets of samples to the top
    for (byte i = 25; i < 100; i++)
    {
      redBuffer[i - 25] = redBuffer[i];
      irBuffer[i - 25] = irBuffer[i];
    }
    long irValue;
    //take 25 sets of samples before calculating the heart rate.
    for (byte i = 75; i < 100; i++)
    {
      while (ppgSensor.available() == false) //do we have new data?
        ppgSensor.check(); //Check the sensor for new data

    
      redBuffer[i] = ppgSensor.getRed();
      irBuffer[i] = ppgSensor.getIR();
      ppgSensor.nextSample(); //We're finished with this sample so move to next sample

      irValue = irBuffer[i];

      //Calculate BPM independent of Maxim Algorithm. 
      if (checkForBeat(irValue) == true && irValue > 50000)
      {
        //We sensed a beat!
        long delta = millis() - lastBeat;
        lastBeat = millis();
      
        beatsPerMinute = 60 / (delta / 1000.0);
        beatAvg = (beatAvg+beatsPerMinute)/2;
      }
      if(millis() - lastBeat > 10000)
      {
        beatsPerMinute = 0;
        beatAvg = (beatAvg+beatsPerMinute)/2;
      }
    }
  
    //After gathering 25 new samples recalculate HR and SP02
    maxim_heart_rate_and_oxygen_saturation(irBuffer, bufferLength, redBuffer, &spo2, &validSPO2, &heartRate, &validHeartRate);
  
    //Calculates average SPO2 to display smooth transitions on Blynk App
    if(validSPO2 == 1 && spo2 < 100 && spo2 > 0 && irValue > 50000)
    {
      sp02Avg = (sp02Avg+spo2)/2;
    }

    sensors_event_t event; 
    accel.getEvent(&event);
    float sensorValue = analogRead(GSR);
    float acceleration_X = event.acceleration.x;
    float acceleration_Y = event.acceleration.y;
    float acceleration_Z = event.acceleration.z;
    sendDataToInfluxDB(sensorValue, acceleration_X, acceleration_Y, acceleration_Z, sp02Avg, beatAvg);
  }
}