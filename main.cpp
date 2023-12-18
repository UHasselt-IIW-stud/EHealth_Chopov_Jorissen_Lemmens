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
#include "MAX30105.h"
#include "spo2_algorithm.h"
#include "heartRate.h"
#include <InfluxDbClient.h>
#include <InfluxDbCloud.h>
#include <WiFi.h>
#include <ESPAsyncWebServer.h>
#include <SPIFFS.h>

#define I2C_SDA_PIN 8
#define I2C_SCL_PIN 10
// WiFi AP SSID
#define WIFI_SSID SSID_4G
// WiFi password
#define WIFI_PASSWORD Password_4G
#define INFLUXDB_URL url_4G
#define INFLUXDB_TOKEN TOKEN
#define INFLUXDB_ORG ORG
#define INFLUXDB_BUCKET BUCKET
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

//ACC sensor
Adafruit_ADXL345_Unified accel = Adafruit_ADXL345_Unified(12345);

//PPG sensor
MAX30105 ppgSensor;
long lastBeat = 0; // Time at which the last beat occurred
float beatsPerMinute; // Stores the BPM as per custom algorithm
int beatAvg = 0, sp02Avg = 0; // Stores the average BPM and SPO2
uint32_t irBuffer[100];   // Infrared LED sensor data
uint32_t redBuffer[100];  // Red LED sensor data
int32_t bufferLength; // Data length
int32_t spo2;        // SPO2 value
int8_t validSPO2;    // Indicator to show if the SPO2 calculation is valid
int32_t heartRate;   // Heart rate value calculated as per Maxim's algorithm
int8_t validHeartRate; // Indicator to show if the heart rate calculation is valid

//GSR sensor
const int GSR = 1; // pin used by gsr sensor
int sensorValue = 0; // sensorvalue

//Personal information from webserver
String name;
int age = 0;
String gender;
float weight = 0;
float height= 0;

AsyncWebServer server(80);
void handleRoot(AsyncWebServerRequest *request);
void handleSubmit(AsyncWebServerRequest *request);

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

  // Handle root and submit paths
	
  server.on("/", HTTP_GET, [](AsyncWebServerRequest *request) {
		request->send(SPIFFS, "/ehealth.html");
	});

	server.on("/", HTTP_GET, [](AsyncWebServerRequest *request) {
		request->send(SPIFFS, "/ehealth.css");
	});
  
  // Initialize SPIFFS
  if (!SPIFFS.begin()) {
      Serial.println("Failed to mount file system");
      return;
  }

  server.serveStatic("/ehealth.css", SPIFFS, "/ehealth.css");
  
  // Start the server
  server.begin();

  // When connected, print ESP32's IP address
  Serial.print("ESP32 IP address: ");
  Serial.println("\n" + WiFi.localIP());
  delay(10000);
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
    ppgmeter.addTag("name:", name);
    ppgmeter.clearTags();

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
    //take 25 sets of samples before calculating the heart rate.
    for (byte i = 75; i < 100; i++)
    {
      while (ppgSensor.available() == false) //do we have new data?
        ppgSensor.check(); //Check the sensor for new data

    
      redBuffer[i] = ppgSensor.getRed();
      irBuffer[i] = ppgSensor.getIR();
      ppgSensor.nextSample(); //We're finished with this sample so move to next sample

      long irValue = irBuffer[i];

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
    if(validSPO2 == 1 && spo2 < 100 && spo2 > 0 && beatAvg > 40)
    {
      sp02Avg = (sp02Avg+spo2)/2;
    }
    else if (beatAvg == 0)
    {
      sp02Avg = 0;
    }
    //server.handleClient();
    sensors_event_t event; 
    accel.getEvent(&event);
    float sensorValue = analogRead(GSR);
    float acceleration_X = event.acceleration.x;
    float acceleration_Y = event.acceleration.y;
    float acceleration_Z = event.acceleration.z;
    sendDataToInfluxDB(sensorValue, acceleration_X, acceleration_Y, acceleration_Z, sp02Avg, beatAvg);
  }
}

void handleRoot(AsyncWebServerRequest *request) {
    if (request->url() == "/") {
        request->send(SPIFFS, "/ehealth.html", "text/html");
    } else if (request->url() == "/ehealth.css") {
        request->send(SPIFFS, "/ehealth.css", "text/css");
    }
}

void handleSubmit(AsyncWebServerRequest *request) {
    // Handle form submission
    if (request->hasArg("name") && request->hasArg("age") && request->hasArg("gender") && request->hasArg("weight") && request->hasArg("height")) {
        name = request->arg("name");
        age = request->arg("age").toInt();
        gender = request->arg("gender");
        weight = request->arg("weight").toFloat();
        height = request->arg("height").toFloat();

        // Now you can use these values as needed, e.g., send them to InfluxDB
        // Send a response to the client
        request->send(200, "text/plain", "Data submitted successfully!");
    } else {
        request->send(400, "text/plain", "Bad Request");
    }
}