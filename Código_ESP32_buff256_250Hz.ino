#include <WiFi.h>
#include <WiFiUdp.h>
#include <Wire.h>
#include "freertos/FreeRTOS.h"
#include "freertos/task.h"
#include "freertos/queue.h"

#define DEVICE_ID   4   

#define PIN_LED     13
#define I2C_SDA     21
#define I2C_SCL     22
#define MPU_ADDR    0x69

const char* WIFI_SSID = "redcompu";     
const char* WIFI_PASS = "cocoso99";    

IPAddress DEST_IP(192,168,137,1);
const uint16_t DEST_PORT = 50000;

const uint16_t TAM_BLOQUE      = 256;
const uint8_t  MUESTRAS_BLOQUE = 21;   

#define NUM_BUFS 12  
static uint8_t buffers[NUM_BUFS][TAM_BLOQUE];
static QueueHandle_t qVacios;  
static QueueHandle_t qLlenos;  

TaskHandle_t tAdq;
TaskHandle_t tNet;
WiFiUDP udp;

struct __attribute__((packed)) UdpHdr {
  uint8_t  magic[4];
  uint8_t  ver;
  uint8_t  dev_id;
  uint16_t rsv;
  uint32_t seq;
  uint32_t ms;
  uint32_t len;
};
volatile uint32_t g_seq = 0;

void taskAdquisicion(void* pv);
void taskNetwork(void* pv);
bool leerMPU(int16_t* d);
void iniciarMPU();
void configurarMPU();
void wr(uint8_t r, uint8_t v);
void llenarBloque(uint8_t* buf);
inline void ledOn(bool on){ digitalWrite(PIN_LED, on?HIGH:LOW); }
inline void ledBlink(uint16_t t){ digitalWrite(PIN_LED,HIGH); delay(t); digitalWrite(PIN_LED,LOW); delay(t); }

void setup() {
  pinMode(PIN_LED, OUTPUT);
  ledOn(false);

  Wire.begin(I2C_SDA, I2C_SCL);
  Wire.setClock(200000);
  Wire.setTimeout(50);
  iniciarMPU();
  configurarMPU();

  qVacios = xQueueCreate(NUM_BUFS, sizeof(uint8_t));
  qLlenos = xQueueCreate(NUM_BUFS, sizeof(uint8_t));
  for (uint8_t i=0;i<NUM_BUFS;i++) xQueueSend(qVacios, &i, 0);

  WiFi.mode(WIFI_STA);
  WiFi.setSleep(false);
  WiFi.begin(WIFI_SSID, WIFI_PASS);
  uint32_t t0 = millis();
  while (WiFi.status() != WL_CONNECTED && (millis()-t0) < 10000) { ledBlink(80); }
  if (WiFi.status() == WL_CONNECTED) { udp.begin(0); ledOn(true); } else { ledOn(false); }

  xTaskCreatePinnedToCore(taskAdquisicion, "ADQ", 4096, NULL, 3, &tAdq, 0);
  xTaskCreatePinnedToCore(taskNetwork,     "NET", 4096, NULL, 2, &tNet, 1);
}

void loop() {
  vTaskDelay(pdMS_TO_TICKS(1000));
}

void taskAdquisicion(void* pv) {
  uint8_t idx;
  TickType_t tick = xTaskGetTickCount();
  for (;;) {
    if (xQueueReceive(qVacios, &idx, portMAX_DELAY) == pdTRUE) {
      llenarBloque(buffers[idx]);
      xQueueSend(qLlenos, &idx, portMAX_DELAY);
    }
    vTaskDelayUntil(&tick, pdMS_TO_TICKS(1));
  }
}

void taskNetwork(void* pv) {
  UdpHdr hdr;
  hdr.magic[0]='I'; hdr.magic[1]='M'; hdr.magic[2]='U'; hdr.magic[3]='2';
  hdr.ver=1; hdr.dev_id=DEVICE_ID; hdr.rsv=0; hdr.len=TAM_BLOQUE;

  uint8_t idx;
  for (;;) {
    if (xQueueReceive(qLlenos, &idx, portMAX_DELAY) == pdTRUE) {
      if (WiFi.status() != WL_CONNECTED) {
        WiFi.disconnect(); WiFi.begin(WIFI_SSID, WIFI_PASS);
        vTaskDelay(pdMS_TO_TICKS(100));
        if (WiFi.status() != WL_CONNECTED) {
          xQueueSend(qVacios, &idx, portMAX_DELAY);
          ledOn(false);
          continue;
        } else {
          udp.begin(0);
          ledOn(true);
        }
      }
      hdr.seq = g_seq++;
      hdr.ms  = millis();

      udp.beginPacket(DEST_IP, DEST_PORT);
      udp.write((uint8_t*)&hdr, sizeof(hdr));
      udp.write(buffers[idx], TAM_BLOQUE);
      bool ok = udp.endPacket();

      xQueueSend(qVacios, &idx, portMAX_DELAY);
      if (!ok) { ledBlink(40); }
    }
  }
}

void llenarBloque(uint8_t* buf) {
  uint16_t k=0;
  for (uint8_t s=0; s<MUESTRAS_BLOQUE; s++) {
    int16_t d[6];
    bool ok=false;
    for (uint8_t r=0;r<2 && !ok;r++){
      ok=leerMPU(d);
      if(!ok) vTaskDelay(pdMS_TO_TICKS(1));
    }
    if (!ok) {
      for (uint8_t i=0;i<6;i++){
        buf[k++]=0;
        buf[k++]=0;
      }
    } else {
      for (uint8_t i=0;i<6;i++){
        buf[k++]=(uint8_t)(d[i]>>8);
        buf[k++]=(uint8_t)(d[i]&0xFF);
      }
    }
    vTaskDelay(pdMS_TO_TICKS(4));
  }
  buf[252]=0; buf[253]=0; buf[254]=0; buf[255]=0;
}

bool leerMPU(int16_t* d){
  Wire.beginTransmission(MPU_ADDR);
  Wire.write(0x3B);
  if (Wire.endTransmission(false)!=0) return false;
  if (Wire.requestFrom((int)MPU_ADDR, 14, (int)true) < 14) return false;
  for (uint8_t i=0;i<3;i++) d[i]=(Wire.read()<<8)|Wire.read();
  Wire.read(); Wire.read();
  for (uint8_t i=3;i<6;i++) d[i]=(Wire.read()<<8)|Wire.read();
  return true;
}
void iniciarMPU(){
  Wire.beginTransmission(MPU_ADDR);
  Wire.write(0x6B);
  Wire.write(0x00);
  Wire.endTransmission();
  vTaskDelay(pdMS_TO_TICKS(5));
}
void configurarMPU(){
  wr(0x1B,0x08);
  wr(0x1C,0x10);
  wr(0x19, 0x03); 
  wr(0x1A, 0x03);
  wr(0x1D, 0x03);
}
void wr(uint8_t r,uint8_t v){
  Wire.beginTransmission(MPU_ADDR);
  Wire.write(r);
  Wire.write(v);
  Wire.endTransmission();
}
