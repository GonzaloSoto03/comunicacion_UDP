#include <WiFi.h>
#include <WiFiUdp.h>
#include <Wire.h>
#include "freertos/FreeRTOS.h"
#include "freertos/task.h"
#include "freertos/queue.h"

// nodo
#define ID_DISPOSITIVO   3   // usa 1,2,3,4 según brazo/pierna

#define PIN_LED        13
#define PIN_I2C_SDA    21
#define PIN_I2C_SCL    22
#define MPU_DIRECCION  0x69


const char* WIFI_SSID  = "redcompu";   
const char* WIFI_CLAVE = "abcdefg";   

IPAddress IP_DESTINO(192,168,137,1);
const uint16_t PUERTO_DESTINO = 50000;

const uint16_t TAMANO_BLOQUE       = 1024;
const uint8_t  MUESTRAS_POR_BLOQUE = 85;   // 85*(6*2)=1020 + 4 footer

#define NUMERO_BUFFERS 12  // más margen para evitar drops con Wi-Fi
static uint8_t buffers[NUMERO_BUFFERS][TAMANO_BLOQUE];
static QueueHandle_t colaBuffersVacios;  // índices disponibles
static QueueHandle_t colaBuffersLlenos;  // índices llenos para envío

//Tareas
TaskHandle_t tareaAdquisicionHandle;
TaskHandle_t tareaRedHandle;
WiFiUDP udp;

//Cabecera UDP 20 bytes
struct __attribute__((packed)) CabeceraUDP {
  uint8_t  marcaMagica[4]; // "IMU2"
  uint8_t  version;        // 1
  uint8_t  idDispositivo;  // 1 2 3 4
  uint16_t reservado;      // 0
  uint32_t secuencia;      // contador
  uint32_t milisegundos;   // millis()
  uint32_t longitud;       // 1024
};

volatile uint32_t contadorSecuencia = 0;

//Prototipos
void tareaAdquisicion(void* parametro);
void tareaRed(void* parametro);
bool leerIMU(int16_t* datos);
void iniciarIMU();
void configurarIMU();
void escribirRegistro(uint8_t registro, uint8_t valor);
void llenarBloque(uint8_t* buffer);

inline void encenderLED(bool encendido) {
  digitalWrite(PIN_LED, encendido ? HIGH : LOW);
}

inline void parpadearLED(uint16_t tiempoMs) {
  digitalWrite(PIN_LED, HIGH);
  delay(tiempoMs);
  digitalWrite(PIN_LED, LOW);
  delay(tiempoMs);
}

void setup() {
  pinMode(PIN_LED, OUTPUT);
  encenderLED(false);

  Wire.begin(PIN_I2C_SDA, PIN_I2C_SCL);
  Wire.setClock(200000);
  Wire.setTimeout(50);
  iniciarIMU();
  configurarIMU();

  //Colas de indicess
  colaBuffersVacios = xQueueCreate(NUMERO_BUFFERS, sizeof(uint8_t));
  colaBuffersLlenos = xQueueCreate(NUMERO_BUFFERS, sizeof(uint8_t));
  for (uint8_t i = 0; i < NUMERO_BUFFERS; i++) {
    xQueueSend(colaBuffersVacios, &i, 0);
  }

  //desactivar ahorro de energía para estabilidad
  WiFi.mode(WIFI_STA);
  WiFi.setSleep(false);
  WiFi.begin(WIFI_SSID, WIFI_CLAVE);
  uint32_t t0 = millis();
  while (WiFi.status() != WL_CONNECTED && (millis() - t0) < 10000) {
    parpadearLED(80);
  }
  if (WiFi.status() == WL_CONNECTED) {
    udp.begin(0);
    encenderLED(true);
  } else {
    encenderLED(false);
  }

  // Tareas en cores distintos
  xTaskCreatePinnedToCore(tareaAdquisicion, "ADQ", 4096, NULL, 3, &tareaAdquisicionHandle, 0);
  xTaskCreatePinnedToCore(tareaRed,          "RED", 4096, NULL, 2, &tareaRedHandle,          1);
}

void loop() {
  vTaskDelay(pdMS_TO_TICKS(1000));
}

//Adquisición en Core 0
void tareaAdquisicion(void* parametro) {
  uint8_t indiceBuffer;
  TickType_t marcaTiempo = xTaskGetTickCount();

  for (;;) {
    if (xQueueReceive(colaBuffersVacios, &indiceBuffer, portMAX_DELAY) == pdTRUE) {
      llenarBloque(buffers[indiceBuffer]);
      xQueueSend(colaBuffersLlenos, &indiceBuffer, portMAX_DELAY);
    }
    vTaskDelayUntil(&marcaTiempo, pdMS_TO_TICKS(1));
  }
}

// Red en Core 1
void tareaRed(void* parametro) {
  CabeceraUDP cabecera;
  cabecera.marcaMagica[0] = 'I';
  cabecera.marcaMagica[1] = 'M';
  cabecera.marcaMagica[2] = 'U';
  cabecera.marcaMagica[3] = '2';
  cabecera.version       = 1;
  cabecera.idDispositivo = ID_DISPOSITIVO;
  cabecera.reservado     = 0;
  cabecera.longitud      = TAMANO_BLOQUE;

  uint8_t indiceBuffer;
  for (;;) {
    if (xQueueReceive(colaBuffersLlenos, &indiceBuffer, portMAX_DELAY) == pdTRUE) {

      // Reintento de conexión WiFi al hostpot si se pierde
      if (WiFi.status() != WL_CONNECTED) {
        WiFi.disconnect();
        WiFi.begin(WIFI_SSID, WIFI_CLAVE);
        vTaskDelay(pdMS_TO_TICKS(100));

        if (WiFi.status() != WL_CONNECTED) {
          xQueueSend(colaBuffersVacios, &indiceBuffer, portMAX_DELAY);
          encenderLED(false);
          continue;
        } else {
          udp.begin(0);
          encenderLED(true);
        }
      }

      cabecera.secuencia    = contadorSecuencia++;
      cabecera.milisegundos = millis();

      udp.beginPacket(IP_DESTINO, PUERTO_DESTINO);
      udp.write((uint8_t*)&cabecera, sizeof(cabecera));
      udp.write(buffers[indiceBuffer], TAMANO_BLOQUE);
      bool envioCorrecto = udp.endPacket();

      xQueueSend(colaBuffersVacios, &indiceBuffer, portMAX_DELAY);

      if (!envioCorrecto) {
        parpadearLED(40);
      }
    }
  }
}

// Rellenar un bloque de 1024 bytes
void llenarBloque(uint8_t* buffer) {
  uint16_t k = 0;

  for (uint8_t muestra = 0; muestra < MUESTRAS_POR_BLOQUE; muestra++) {
    int16_t datos[6];
    bool lecturaCorrecta = false;

    // 2 reintentos max de lectura de la IMU
    for (uint8_t reintento = 0; reintento < 2 && !lecturaCorrecta; reintento++) {
      lecturaCorrecta = leerIMU(datos);
      if (!lecturaCorrecta) {
        vTaskDelay(pdMS_TO_TICKS(1));
      }
    }

    if (!lecturaCorrecta) {
      // Si falla se llena la muestra con ceros
      for (uint8_t i = 0; i < 6; i++) {
        buffer[k++] = 0;
        buffer[k++] = 0;
      }
    } else {
      // Datos válidpos se escribe en big-endian
      for (uint8_t i = 0; i < 6; i++) {
        buffer[k++] = (uint8_t)(datos[i] >> 8);
        buffer[k++] = (uint8_t)(datos[i] & 0xFF);
      }
    }

    vTaskDelay(pdMS_TO_TICKS(1));
  }

  // Footer
  buffer[1020] = 0;
  buffer[1021] = 0;
  buffer[1022] = 0;
  buffer[1023] = 0;
}

bool leerIMU(int16_t* datos) {
  Wire.beginTransmission(MPU_DIRECCION);
  Wire.write(0x3B);
  if (Wire.endTransmission(false) != 0) return false;

  if (Wire.requestFrom((int)MPU_DIRECCION, 14, (int)true) < 14) return false;

  // Acelerómetro 3 ejes
  for (uint8_t i = 0; i < 3; i++) {
    datos[i] = (Wire.read() << 8) | Wire.read();
  }

  // Temperatura se descarta
  Wire.read();
  Wire.read();

  // Giroscopio 3 ejes
  for (uint8_t i = 3; i < 6; i++) {
    datos[i] = (Wire.read() << 8) | Wire.read();
  }

  return true;
}

void iniciarIMU() {
  Wire.beginTransmission(MPU_DIRECCION);
  Wire.write(0x6B);   // PWR_MGMT_1
  Wire.write(0x00);   // despertar
  Wire.endTransmission();
  vTaskDelay(pdMS_TO_TICKS(5));
}

void configurarIMU() {
  // Configuracion rango giroscopio y acelerometro
  escribirRegistro(0x1B, 0x08); // ±500 dps
  escribirRegistro(0x1C, 0x10); // ±8 g
  // escribirRegistro(0x1A, 0x03); // filtro DLPF
}

void escribirRegistro(uint8_t registro, uint8_t valor) {
  Wire.beginTransmission(MPU_DIRECCION);
  Wire.write(registro);
  Wire.write(valor);
  Wire.endTransmission();
}
