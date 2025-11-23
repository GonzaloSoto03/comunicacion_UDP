# recv_imu_csv.py (Hotspot, con block_seq, relleno de pérdidas y sesiones de 10 s)
import socket, struct, time, os, csv
from datetime import datetime

IP_ESCUCHA   = "0.0.0.0"
PUERTO_ESCUCHA = 50000

# Mapea IDs a nombres/carpetas base (sin número)
ID_A_NOMBRE = {
    1: "brazo_izquierdo",
    2: "brazo_derecho",
    3: "pierna_izquierda",
    4: "pierna_derecha",
}

# Prefijo base para las sesiones
PREFIJO_SESION   = "imu_capturas"
DURACION_SESION  = 5.0  # segundos por sesión

# Estado de sesión
indice_sesion       = 1
tiempo_inicio_sesion = time.time()

MARCA_MAGICA      = b"IMU2"
FORMATO_CABECERA  = "<4s B B H I I I"  # magic(4), ver(1), dev_id(1), rsv(2), seq(u32), ms(u32), len(u32)
TAMANO_CABECERA   = struct.calcsize(FORMATO_CABECERA)

# Estructuras por dispositivo
escritores      = {}  # id_disp -> csv.writer
archivos        = {}  # id_disp -> file object
ultima_seq      = {}  # id_disp -> última seq recibida
paquetes        = {}  # id_disp -> paquetes recibidos (contados)
perdidas        = {}  # id_disp -> paquetes perdidos (estimados por salto en seq)
filas_escritas  = {}  # id_disp -> filas escritas

MUESTRAS_POR_BLOQUE = 85   #1024 = 85*12+4
ENCABEZADO_CSV      = ["block_seq", "ax", "ay", "az", "gx", "gy", "gz"]


def raiz_sesion_actual():
    """Nombre de carpeta raíz de la sesión actual,como por ejempl0 imu_capturas1"""
    return f"{PREFIJO_SESION}{indice_sesion}"


def abrir_csv_para(id_disp):
    """Crea carpeta de sesión mas subcarpeta por dispositivo y abre CSV (append) para el dispositivo."""
    nombre = ID_A_NOMBRE.get(id_disp, f"id{id_disp}")  # ej: 'brazo_izquierdo'
    raiz   = raiz_sesion_actual()                      # ej: 'imu_capturas1'

    # Subcarpeta y archivo con número de sesión, ej: 'brazo_izquierdo1/brazo_izquierdo1.csv'
    nombre_disp_con_indice = f"{nombre}{indice_sesion}"
    carpeta = os.path.join(raiz, nombre_disp_con_indice)
    os.makedirs(carpeta, exist_ok=True)

    ruta = os.path.join(carpeta, f"{nombre_disp_con_indice}.csv")
    f = open(ruta, "a", newline="")
    w = csv.writer(f)
    if f.tell() == 0:
        w.writerow(ENCABEZADO_CSV)

    archivos[id_disp]       = f
    escritores[id_disp]     = w
    ultima_seq[id_disp]     = None
    paquetes[id_disp]       = 0
    perdidas[id_disp]       = 0
    filas_escritas[id_disp] = 0
    print(f"[+] (sesión {indice_sesion}) Grabando en {ruta}")


def cerrar_todos_los_archivos():
    """Cierra todos los CSV abiertos."""
    for f in archivos.values():
        try:
            f.close()
        except:
            pass


def rotar_sesion():
    """Cierra archivos, limpia estado y avanza a la siguiente sesión."""
    global indice_sesion, tiempo_inicio_sesion
    if archivos:
        print(f"--- Cerrando sesión {indice_sesion} ---")
    cerrar_todos_los_archivos()

    escritores.clear()
    archivos.clear()
    ultima_seq.clear()
    paquetes.clear()
    perdidas.clear()
    filas_escritas.clear()

    indice_sesion += 1
    tiempo_inicio_sesion = time.time()
    print(f"--- Nueva sesión {indice_sesion} (carpeta raíz: {raiz_sesion_actual()}) ---")


def verificar_cambio_sesion():
    """Verifica si han pasado DURACION_SESION segundos y, de ser así, crea nueva sesión."""
    ahora = time.time()
    if ahora - tiempo_inicio_sesion >= DURACION_SESION:
        rotar_sesion()


def decodificar_carga(payload):
    """
    Convierte el bloque de 1024 bytes en lista de 85 tuplas (ax,ay,az,gx,gy,gz).
    Cada muestra: 12 bytes = 6 * int16 (big-endian). Los últimos 4 bytes son footer.
    """
    muestras = []
    util = len(payload) - 4
    for i in range(0, util, 12):
        fragmento = payload[i:i+12]
        if len(fragmento) < 12:
            break
        datos = struct.unpack(">6h", fragmento)  # big-endian, 6 x int16
        muestras.append(datos)
    return muestras


def escribir_filas_bloque(id_disp, secuencia_bloque, muestras):
    """Escribe 85 filas para un bloque recibido (usa datos reales)."""
    escritor = escritores[id_disp]
    for tupla in muestras:
        escritor.writerow([secuencia_bloque, *tupla])
    filas_escritas[id_disp] += len(muestras)


def escribir_bloque_ceros(id_disp, secuencia_bloque):
    """Escribe 85 filas en cero para un bloque perdido."""
    escritor = escritores[id_disp]
    fila_cero = [0, 0, 0, 0, 0, 0]  # ax..gz = 0
    for _ in range(MUESTRAS_POR_BLOQUE):
        escritor.writerow([secuencia_bloque, *fila_cero])
    filas_escritas[id_disp] += MUESTRAS_POR_BLOQUE


def vaciar_si_corresponde(id_disp):
    """Flush periódico para asegurar persistencia."""
    if (paquetes[id_disp] % 100) == 0:
        archivos[id_disp].flush()


# Socket UDP
socket_udp = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
socket_udp.setsockopt(socket.SOL_SOCKET, socket.SO_RCVBUF, 1_000_000)  # buffer grande
socket_udp.bind((IP_ESCUCHA, PUERTO_ESCUCHA))
socket_udp.settimeout(2.0)
print(f"Escuchando en {IP_ESCUCHA}:{PUERTO_ESCUCHA} ... (Hotspot)")

tiempo_ultimo_reporte = time.time()

try:
    while True:
        # Cada iteración revisamos si hay que cambiar de sesión
        verificar_cambio_sesion()

        try:
            datos, direccion = socket_udp.recvfrom(4096)
        except socket.timeout:
            # reporte periódico
            ahora = time.time()
            if ahora - tiempo_ultimo_reporte >= 5.0:
                resumen = " | ".join(
                    f"id{d}:{ID_A_NOMBRE.get(d,'?')} paqs={paquetes.get(d,0)} "
                    f"perd={perdidas.get(d,0)} filas={filas_escritas.get(d,0)}"
                    for d in sorted(paquetes.keys())
                )
                if resumen:
                    print(f"[{time.strftime('%H:%M:%S')}] (sesión {indice_sesion}) {resumen}")
                tiempo_ultimo_reporte = ahora
            continue

        # Chequeo mínimo de tamaño (header)
        if len(datos) < TAMANO_CABECERA:
            continue

        # Desempaquetar header
        marca, ver, id_disp, rsv, seq, ms, longitud = struct.unpack(
            FORMATO_CABECERA, datos[:TAMANO_CABECERA]
        )
        if marca != MARCA_MAGICA or ver != 1 or longitud <= 0:
            continue

        payload = datos[TAMANO_CABECERA:]
        if len(payload) != longitud:
            continue

        # Asegurar CSV abierto para la sesión actual
        if id_disp not in archivos:
            abrir_csv_para(id_disp)

        # Detectar reset de secuencia (p. ej., reinicio del ESP32).
        if ultima_seq[id_disp] is not None and seq < ultima_seq[id_disp]:
            print(
                f"[!] id{id_disp}: secuencia reiniciada "
                f"(ultima_seq={ultima_seq[id_disp]} -> seq={seq}). "
                f"No se contabilizan pérdidas en este salto."
            )
            ultima_seq[id_disp] = None

        # Si hay huecos, rellenar con bloques de ceros (uno por seq faltante)
        if ultima_seq[id_disp] is not None and seq > (ultima_seq[id_disp] + 1):
            faltantes = seq - ultima_seq[id_disp] - 1
            perdidas[id_disp] += faltantes
            inicio_faltante = ultima_seq[id_disp] + 1
            fin_faltante    = seq - 1
            for seq_faltante in range(inicio_faltante, fin_faltante + 1):
                escribir_bloque_ceros(id_disp, seq_faltante)

        # Procesar bloque recibido
        muestras = decodificar_carga(payload)
        # Asegurar 85 filas: si por algún motivo vinieran menos, rellenamos (raro, pero robusto)
        if len(muestras) < MUESTRAS_POR_BLOQUE:
            faltan = MUESTRAS_POR_BLOQUE - len(muestras)
            muestras.extend([(0, 0, 0, 0, 0, 0)] * faltan)

        escribir_filas_bloque(id_disp, seq, muestras)

        # Actualizar contadores
        ultima_seq[id_disp] = seq
        paquetes[id_disp]   += 1
        vaciar_si_corresponde(id_disp)

        # Estado cada 256 paquetes
        if (paquetes[id_disp] % 256) == 0:
            print(
                f"id{id_disp} {ID_A_NOMBRE.get(id_disp,'?')} "
                f"paqs={paquetes[id_disp]} perd={perdidas[id_disp]} ultima_seq={seq}"
            )

except KeyboardInterrupt:
    print("\nInterrumpido por usuario.")
finally:
    cerrar_todos_los_archivos()
    socket_udp.close()
    print("Cerrado.")
