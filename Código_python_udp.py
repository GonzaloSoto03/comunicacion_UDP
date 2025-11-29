import socket, struct, time, os, csv
from datetime import datetime

IP_ESCUCHA     = "0.0.0.0"
PUERTO_ESCUCHA = 50000


ID_A_NOMBRE = {
    1: "muslo_derecho",
    2: "pecho",
    3: "muslo_izquierdo",
    4: "cintura",
}


PREFIJO_SESION   = "imu_capturas"
DURACION_SESION  = 6.0  


indice_sesion        = 100
tiempo_inicio_sesion = time.time()

MARCA_MAGICA      = b"IMU2"
FORMATO_CABECERA  = "<4s B B H I I I"  
TAMANO_CABECERA   = struct.calcsize(FORMATO_CABECERA)


escritores      = {}  
archivos        = {}  
ultima_seq      = {}  
paquetes        = {}  
perdidas        = {}  
filas_escritas  = {}  

MUESTRAS_POR_BLOQUE = 21   
ENCABEZADO_CSV      = ["block_seq", "ax", "ay", "az", "gx", "gy", "gz"]


def raiz_sesion_actual():
    """Nombre de carpeta raíz de la sesión actual, como por ejemplo imu_capturas1."""
    return f"{PREFIJO_SESION}{indice_sesion}"


def abrir_csv_para(id_disp):
    """Crea carpeta de sesión más subcarpeta por dispositivo y abre CSV (append) para el dispositivo."""
    nombre = ID_A_NOMBRE.get(id_disp, f"id{id_disp}")  
    raiz   = raiz_sesion_actual()                      

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

    for f in archivos.values():
        try:
            f.close()
        except:
            pass


def rotar_sesion():

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

    ahora = time.time()
    if ahora - tiempo_inicio_sesion >= DURACION_SESION:
        rotar_sesion()


def decodificar_carga(payload):

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
    escritor = escritores[id_disp]
    for tupla in muestras:
        escritor.writerow([secuencia_bloque, *tupla])
    filas_escritas[id_disp] += len(muestras)


def escribir_bloque_ceros(id_disp, secuencia_bloque):
    escritor = escritores[id_disp]
    fila_cero = [0, 0, 0, 0, 0, 0]  # ax..gz = 0
    for _ in range(MUESTRAS_POR_BLOQUE):
        escritor.writerow([secuencia_bloque, *fila_cero])
    filas_escritas[id_disp] += MUESTRAS_POR_BLOQUE


def vaciar_si_corresponde(id_disp):
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

        verificar_cambio_sesion()

        try:
            datos, direccion = socket_udp.recvfrom(4096)
        except socket.timeout:

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


        if len(datos) < TAMANO_CABECERA:
            continue


        marca, ver, id_disp, rsv, seq, ms, longitud = struct.unpack(
            FORMATO_CABECERA, datos[:TAMANO_CABECERA]
        )
        if marca != MARCA_MAGICA or ver != 1 or longitud <= 0:
            continue

        payload = datos[TAMANO_CABECERA:]
        if len(payload) != longitud:
            continue


        if id_disp not in archivos:
            abrir_csv_para(id_disp)


        if ultima_seq[id_disp] is not None and seq < ultima_seq[id_disp]:
            print(
                f"[!] id{id_disp}: secuencia reiniciada "
                f"(ultima_seq={ultima_seq[id_disp]} -> seq={seq}). "
                f"No se contabilizan pérdidas en este salto."
            )
            ultima_seq[id_disp] = None


        if ultima_seq[id_disp] is not None and seq > (ultima_seq[id_disp] + 1):
            faltantes = seq - ultima_seq[id_disp] - 1
            perdidas[id_disp] += faltantes
            inicio_faltante = ultima_seq[id_disp] + 1
            fin_faltante    = seq - 1
            for seq_faltante in range(inicio_faltante, fin_faltante + 1):
                escribir_bloque_ceros(id_disp, seq_faltante)


        muestras = decodificar_carga(payload)

        if len(muestras) < MUESTRAS_POR_BLOQUE:
            faltan = MUESTRAS_POR_BLOQUE - len(muestras)
            muestras.extend([(0, 0, 0, 0, 0, 0)] * faltan)

        escribir_filas_bloque(id_disp, seq, muestras)


        ultima_seq[id_disp] = seq
        paquetes[id_disp]   += 1
        vaciar_si_corresponde(id_disp)


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
