import os
import csv

PREFIJO_SESION = "imu_capturas"

ID_A_NOMBRE = {
    1: "muslo_derecho",
    2: "pecho",
    3: "muslo_izquierdo",
    4: "cintura",
}

def contar_filas_csv(ruta_csv: str):

    if not os.path.exists(ruta_csv):
        return None

    with open(ruta_csv, newline="") as f:
        reader = csv.reader(f)
        filas = list(reader)

    if not filas:
        return 0

    return max(len(filas) - 1, 0)


def obtener_indices_sesion():

    indices = []
    for nombre in os.listdir("."):
        if nombre.startswith(PREFIJO_SESION):
            sufijo = nombre[len(PREFIJO_SESION):]
            if sufijo.isdigit():
                indices.append(int(sufijo))
    return sorted(indices)


def ruta_csv_dispositivo(nombre_base: str, indice_sesion: int) -> str:

    carpeta_sesion = f"{PREFIJO_SESION}{indice_sesion}"
    nombre_con_indice = f"{nombre_base}{indice_sesion}"
    carpeta_disp = os.path.join(carpeta_sesion, nombre_con_indice)
    ruta_csv = os.path.join(carpeta_disp, f"{nombre_con_indice}.csv")
    return ruta_csv


def main():
    indices_sesion = obtener_indices_sesion()

    if not indices_sesion:
        print("No se encontraron carpetas de sesión tipo 'imu_capturasN'.")
        return

    print("Orden:", ", ".join(
        f"{dev_id}:{nombre}" for dev_id, nombre in ID_A_NOMBRE.items()
    ))
    print()

    for n in indices_sesion:
        filas_por_disp = []

        for dev_id, nombre_base in ID_A_NOMBRE.items():
            ruta = ruta_csv_dispositivo(nombre_base, n)
            filas = contar_filas_csv(ruta)
            filas_por_disp.append(filas)

        filas_str = ", ".join("NA" if f is None else str(f) for f in filas_por_disp)

        valores_validos = [f for f in filas_por_disp if isinstance(f, int)]
        if valores_validos:
            minimo = min(valores_validos)
            maximo = max(valores_validos)
            rango = maximo - minimo
        else:
            rango = None

        etiqueta = ""
        if rango is not None:
            if rango > 200:
                etiqueta = "  *** DIF > 200"
            elif rango > 100:
                etiqueta = "  ** DIF > 100"

            print(f"Sesión {n}: {filas_str}  (rango={rango}){etiqueta}")
        else:
            print(f"Sesión {n}: {filas_str}  (sin datos válidos)")

if __name__ == "__main__":
    main()
