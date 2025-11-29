import os
import csv
import matplotlib.pyplot as plt

ID_A_NOMBRE = {
    1: "muslo_derecho",
    2: "pecho",
    3: "muslo_izquierdo",
    4: "cintura",
}

PREFIJO_SESION = "imu_capturas"
INDICE_SESION = 5

FACTOR_ACEL = 1.0/4096.0   
FACTOR_GIRO = 1.0/65.5   


def ruta_csv_dispositivo(nombre_base: str, indice_sesion: int) -> str:

    carpeta_sesion = f"{PREFIJO_SESION}{indice_sesion}"
    nombre_disp_con_indice = f"{nombre_base}{indice_sesion}"
    carpeta_disp = os.path.join(carpeta_sesion, nombre_disp_con_indice)
    ruta_csv = os.path.join(carpeta_disp, f"{nombre_disp_con_indice}.csv")
    return ruta_csv


def cargar_datos_sesion(indice_sesion: int):

    datos = {}
    ejes = ["ax", "ay", "az", "gx", "gy", "gz"]

    for _, nombre in ID_A_NOMBRE.items():
        ruta = ruta_csv_dispositivo(nombre, indice_sesion)
        if not os.path.exists(ruta):
            continue  

        print(f"Cargando datos de: {ruta}")
        with open(ruta, newline="") as f:
            reader = csv.DictReader(f)
            datos[nombre] = {eje: [] for eje in ejes}

            for fila in reader:
                datos[nombre]["ax"].append(float(fila["ax"]) * FACTOR_ACEL)
                datos[nombre]["ay"].append(float(fila["ay"]) * FACTOR_ACEL)
                datos[nombre]["az"].append(float(fila["az"]) * FACTOR_ACEL)
                datos[nombre]["gx"].append(float(fila["gx"]) * FACTOR_GIRO)
                datos[nombre]["gy"].append(float(fila["gy"]) * FACTOR_GIRO)
                datos[nombre]["gz"].append(float(fila["gz"]) * FACTOR_GIRO)

    return datos


def graficar_sesion(indice_sesion: int):
    datos = cargar_datos_sesion(indice_sesion)
    if not datos:
        print(f"No se encontraron datos para la sesión {indice_sesion}")
        return

    ejes = ["ax", "ay", "az", "gx", "gy", "gz"]

    for eje in ejes:
        plt.figure()
        for nombre_disp, señales in datos.items():
            y = señales[eje]
            if not y:
                continue
            x = range(len(y))
            plt.plot(x, y, label=nombre_disp)

        plt.title(f"Sesión {indice_sesion} - {eje.upper()}")
        plt.xlabel("Muestra")

        if eje.startswith("a"):
            plt.ylabel("Aceleración (unidades crudas)")
        else:
            plt.ylabel("Velocidad angular (unidades crudas)")

        plt.legend()
        plt.grid(True)
        plt.tight_layout()

    plt.show()


if __name__ == "__main__":
    graficar_sesion(INDICE_SESION)
