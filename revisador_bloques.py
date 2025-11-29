import os
import re
import csv


BASE_DIR = r"C:\Users\sotog\Desktop\TESIS"

PREFIJO_SESION = "imu_capturas"
MUESTRAS_POR_BLOQUE = 21  

DISPOSITIVOS = ["muslo_derecho", "pecho", "muslo_izquierdo", "cintura"]

PATRON_SESION = re.compile(rf"^{PREFIJO_SESION}(\d+)$")



def encontrar_sesiones(base_dir):
    sesiones = []
    for nombre in os.listdir(base_dir):
        m = PATRON_SESION.match(nombre)
        if m:
            n = int(m.group(1))
            sesiones.append((n, nombre))
    sesiones.sort(key=lambda x: x[0])
    return sesiones


def detectar_bloques_ceros_en_csv(ruta_csv):

    bloques_ceros = []

    if not os.path.isfile(ruta_csv):
        return bloques_ceros

    with open(ruta_csv, newline="") as f:
        reader = csv.reader(f)
        first_row = True

        current_seq = None
        any_non_zero = False
        filas_en_bloque = 0

        def cerrar_bloque():
            nonlocal current_seq, any_non_zero, filas_en_bloque, bloques_ceros
            if current_seq is None:
                return
            if (not any_non_zero) and (filas_en_bloque == MUESTRAS_POR_BLOQUE):
                bloques_ceros.append((current_seq, filas_en_bloque))

        for row in reader:
            if not row:
                continue

            if first_row:
                first_row = False
                try:
                    int(row[0])
                except ValueError:
                    continue

            try:
                seq = int(row[0])
            except ValueError:
                continue

            valores = row[1:7]
            all_zero_this_row = True
            for v in valores:
                try:
                    if int(v) != 0:
                        all_zero_this_row = False
                        break
                except ValueError:
                    try:
                        if float(v) != 0.0:
                            all_zero_this_row = False
                            break
                    except ValueError:
                        all_zero_this_row = False
                        break

            if current_seq is None:
                current_seq = seq
                filas_en_bloque = 1
                any_non_zero = not all_zero_this_row
            elif seq == current_seq:
                filas_en_bloque += 1
                if not all_zero_this_row:
                    any_non_zero = True
            else:
                cerrar_bloque()
                current_seq = seq
                filas_en_bloque = 1
                any_non_zero = not all_zero_this_row

        cerrar_bloque()

    return bloques_ceros


def revisar_sesion(base_dir, n_sesion, nombre_carpeta):

    ruta_sesion = os.path.join(base_dir, nombre_carpeta)
    resultado = {}

    for disp in DISPOSITIVOS:
        subcarpeta = f"{disp}{n_sesion}"
        ruta_sub = os.path.join(ruta_sesion, subcarpeta)
        ruta_csv = os.path.join(ruta_sub, f"{subcarpeta}.csv")

        if not os.path.isfile(ruta_csv):

            continue

        bloques_ceros = detectar_bloques_ceros_en_csv(ruta_csv)
        if bloques_ceros:
            resultado[disp] = bloques_ceros

    return resultado


def main():
    sesiones = encontrar_sesiones(BASE_DIR)
    if not sesiones:
        print("No se encontraron carpetas del tipo 'imu_capturasN' en:", BASE_DIR)
        return

    print(f"Revisando sesiones en {BASE_DIR} ...\n")

    sesiones_con_ceros = []

    for n_sesion, nombre_carpeta in sesiones:
        info = revisar_sesion(BASE_DIR, n_sesion, nombre_carpeta)
        if not info:
            print(f"Sesión {n_sesion} ({nombre_carpeta}): OK, sin bloques de ceros.")
        else:
            sesiones_con_ceros.append((n_sesion, info))
            print(f"Sesión {n_sesion} ({nombre_carpeta}): con bloques de ceros")
            for disp, bloques in info.items():
                seqs = [b[0] for b in bloques]
                print(f"  - {disp}{n_sesion}: {len(bloques)} bloques de ceros.")
                if len(seqs) > 10:
                    print(f"      block_seq (ejemplo): {seqs[:10]} ...")
                else:
                    print(f"      block_seq: {seqs}")

    print("\n===== RESUMEN =====")
    if not sesiones_con_ceros:
        print("Ninguna sesión tiene bloques de ceros (relleno por pérdidas).")
    else:
        print("Sesiones con al menos un bloque de ceros:")
        for n_sesion, info in sesiones_con_ceros:
            dispositivos = ", ".join(sorted(info.keys()))
            print(f"  - imu_capturas{n_sesion} (dispositivos: {dispositivos})")


if __name__ == "__main__":
    main()
