import os
import re

BASE_DIR = r"C:\Users\sotog\Desktop\TESIS"  

NUMERO_INICIAL = 1  

PATRON_IMU = re.compile(r"^imu_capturas(\d+)$")


def encontrar_capturas(base_dir):
    
    capturas = []
    for nombre in os.listdir(base_dir):
        m = PATRON_IMU.match(nombre)
        if m:
            n_viejo = int(m.group(1))
            capturas.append((n_viejo, nombre))

    capturas.sort(key=lambda x: x[0])  
    return capturas


def renombrar_estructura(base_dir, numero_inicial):
    capturas = encontrar_capturas(base_dir)
    if not capturas:
        print("No se encontraron carpetas del tipo 'imu_capturasN' en", base_dir)
        return

    print("Se encontraron las siguientes carpetas:")
    for idx, (n_viejo, nombre_viejo) in enumerate(capturas):
        n_nuevo = numero_inicial + idx
        nombre_nuevo = f"imu_capturas{n_nuevo}"
        print(f"  {nombre_viejo}  ->  {nombre_nuevo}")

    confirmar = input("\n¿Continuar con el renombrado? [s/N]: ").strip().lower()
    if confirmar != "s":
        print("Operación cancelada.")
        return

    for idx in reversed(range(len(capturas))):
        n_viejo, nombre_viejo = capturas[idx]
        n_nuevo = numero_inicial + idx

        ruta_vieja = os.path.join(base_dir, nombre_viejo)
        nombre_nuevo = f"imu_capturas{n_nuevo}"
        ruta_nueva = os.path.join(base_dir, nombre_nuevo)

        if ruta_vieja == ruta_nueva:
            print(f"[OK] Sin cambio en carpeta: {ruta_vieja}")
        else:
            print(f"[REN] {ruta_vieja} -> {ruta_nueva}")
            os.rename(ruta_vieja, ruta_nueva)

        capturas[idx] = (n_viejo, nombre_nuevo)

    partes = ["muslo_derecho", "pecho", "muslo_izquierdo", "cintura"]

    for idx, (n_viejo, nombre_carpeta_imu) in enumerate(capturas):
        n_nuevo = numero_inicial + idx
        ruta_imu = os.path.join(base_dir, nombre_carpeta_imu)
        print(f"\nDentro de {ruta_imu} (N viejo={n_viejo}, N nuevo={n_nuevo}):")

        for parte in partes:
            sub_vieja = f"{parte}{n_viejo}"
            sub_nueva = f"{parte}{n_nuevo}"

            ruta_sub_vieja = os.path.join(ruta_imu, sub_vieja)
            ruta_sub_nueva = os.path.join(ruta_imu, sub_nueva)

            dir_actual = None

            if os.path.isdir(ruta_sub_vieja):
                if sub_vieja != sub_nueva:
                    print(f"  [REN DIR] {ruta_sub_vieja} -> {ruta_sub_nueva}")
                    os.rename(ruta_sub_vieja, ruta_sub_nueva)
                    dir_actual = ruta_sub_nueva
                else:
                    print(f"  [OK DIR] {ruta_sub_vieja} (sin cambio)")
                    dir_actual = ruta_sub_vieja
            elif os.path.isdir(ruta_sub_nueva):
                print(f"  [INFO] Ya existe: {ruta_sub_nueva}")
                dir_actual = ruta_sub_nueva
            else:
                print(f"  [AVISO] No se encontró carpeta: {ruta_sub_vieja}")
                continue  

            csv_viejo = os.path.join(dir_actual, f"{parte}{n_viejo}.csv")
            csv_nuevo = os.path.join(dir_actual, f"{parte}{n_nuevo}.csv")

            if os.path.isfile(csv_viejo):
                if csv_viejo != csv_nuevo:
                    print(f"    [REN CSV] {csv_viejo} -> {csv_nuevo}")
                    os.rename(csv_viejo, csv_nuevo)
                else:
                    print(f"    [OK CSV] {csv_viejo} (sin cambio)")
            elif os.path.isfile(csv_nuevo):
                print(f"    [INFO] Ya existe CSV con nombre nuevo: {csv_nuevo}")
            else:
                print(f"    [AVISO] No se encontró CSV: {csv_viejo}")


if __name__ == "__main__":
    renombrar_estructura(BASE_DIR, NUMERO_INICIAL)
