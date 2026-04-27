import os
import json
import json5
import shutil
import subprocess
import zipfile
import time
from typing import Any, cast


def _trim_to_first_json_document(text):
    start = None
    depth = 0
    in_string = False
    escape = False
    quote_char = ""

    for index, char in enumerate(text):
        if start is None:
            if char in "[{":
                start = index
                depth = 1
            continue

        if in_string:
            if escape:
                escape = False
            elif char == "\\":
                escape = True
            elif char == quote_char:
                in_string = False
            continue

        if char in "\"'":
            in_string = True
            quote_char = char
        elif char in "[{":
            depth += 1
        elif char in "]}":
            depth -= 1
            if depth == 0:
                return text[start:index + 1]

    return text[start:] if start is not None else text


def _move_replacing_existing(source_path, destination_path):
    if os.path.isdir(destination_path):
        shutil.rmtree(destination_path)
    elif os.path.lexists(destination_path):
        os.remove(destination_path)
    shutil.move(source_path, destination_path)

# Leer el level-name desde server.properties
def get_level_name():
    default_level_name = "Bedrock level"
    if not os.path.exists("server.properties"):
        print(f"Advertencia: No se encontró server.properties. Usando el valor predeterminado: {default_level_name}")
        return default_level_name

    with open("server.properties", "r") as file:
        for line in file:
            if line.startswith("level-name"):
                return line.split("=")[1].strip()

    print(f"Advertencia: No se encontró 'level-name' en server.properties. Usando el valor predeterminado: {default_level_name}")
    return default_level_name

# Crear carpetas si no existen
def ensure_directories_exist(base_path, level_name):
    level_path = os.path.join(base_path, f"worlds/{level_name}")
    behavior_path = os.path.join(level_path, "behavior_packs")
    resource_path = os.path.join(level_path, "resource_packs")

    # Crear la carpeta del nivel si no existe
    os.makedirs(level_path, exist_ok=True)
    os.makedirs(behavior_path, exist_ok=True)
    os.makedirs(resource_path, exist_ok=True)

    return behavior_path, resource_path

# Leer o inicializar archivos JSON
def load_or_initialize_json(file_path: str) -> list[dict[str, Any]]:
    if os.path.exists(file_path):
        with open(file_path, "r", encoding="utf-8") as file:
            raw_text = file.read()

        try:
            data = json5.loads(raw_text)
        except ValueError:
            try:
                data = json5.loads(_trim_to_first_json_document(raw_text))
            except ValueError:
                print(f"Advertencia: {file_path} está corrupto. Se inicializará como lista vacía.")
                return []

        if isinstance(data, list):  # Verifica si es una lista
            return cast(list[dict[str, Any]], data)
        else:
            print(f"Advertencia: {file_path} no es una lista. Se inicializará como lista vacía.")
    return []  # Retorna una lista vacía si el archivo no existe o no es válido

# Guardar datos en archivos JSON
def save_json(file_path: str, data: list[dict[str, Any]]) -> None:
    with open(file_path, "w") as file:
        json.dump(data, file, indent=4)

# Procesar addons
def process_addons(addons_path, behavior_path, resource_path, behavior_json_path, resource_json_path):
    behavior_packs = load_or_initialize_json(behavior_json_path)
    resource_packs = load_or_initialize_json(resource_json_path)

    added_behavior = 0
    added_resource = 0

    for folder in os.listdir(addons_path):
        folder_path = os.path.join(addons_path, folder)
        if not os.path.isdir(folder_path):
            continue

        manifest_path = os.path.join(folder_path, "manifest.json")
        if not os.path.exists(manifest_path):
            print(f"No se encontró manifest.json en {folder}")
            continue

        try:
            with open(manifest_path, "r", encoding="utf-8") as file:
                raw_manifest = file.read()
            try:
                manifest = cast(dict[str, Any], json5.loads(raw_manifest))
            except ValueError:
                manifest = cast(
                    dict[str, Any],
                    json5.loads(_trim_to_first_json_document(raw_manifest)),
                )
        except ValueError as e:
            print(f"Error al leer el manifest.json en {folder}: {e}")
            print(f"El addon {folder} debe ser revisado manualmente.")
            continue

        header = manifest.get("header", {})
        modules = manifest.get("modules", [])
        uuid = header.get("uuid")
        version = header.get("version")
        pack_name = header.get("name", folder)
        if not uuid or not version or not modules:
            print(f"Manifest.json en {folder} no tiene los datos necesarios. El addon debe ser revisado manualmente.")
            continue

        module_type = modules[0].get("type")
        if module_type in ["data", "script"]:
            target_path = behavior_path
            target_json = behavior_packs
            json_path = behavior_json_path
            added_behavior += 1
        elif module_type == "resources":
            target_path = resource_path
            target_json = resource_packs
            json_path = resource_json_path
            added_resource += 1
        else:
            print(f"Tipo desconocido en {folder}: {module_type}. El addon debe ser revisado manualmente.")
            continue

        # Verificar si el UUID ya existe
        existing = next((item for item in target_json if item["pack_id"] == uuid), None)
        if existing:
            existing_version = existing["version"]
            if version > existing_version:
                print(f"Actualizando {folder} a una nueva versión")
                target_json.remove(existing)
                target_json.append({"pack_id": uuid, "version": version, "name": pack_name})
                save_json(json_path, target_json)
                _move_replacing_existing(folder_path, os.path.join(target_path, folder))
            else:
                print(f"El addon {folder} ya está en su mejor versión")
                shutil.rmtree(folder_path)
                continue
        else:
            # Agregar nuevo UUID y mover carpeta
            target_json.append({"pack_id": uuid, "version": version, "name": pack_name})
            save_json(json_path, target_json)
            _move_replacing_existing(folder_path, os.path.join(target_path, folder))

    print(f"Se añadieron {added_behavior} behavior packs y {added_resource} resource packs.")

def extract_mcaddon_and_mcpack(addons_path):
    for file in os.listdir(addons_path):
        file_path = os.path.join(addons_path, file)
        if file.endswith(".mcaddon") or file.endswith(".mcpack"):
            try:
                # Crear una carpeta con el mismo nombre que el archivo (sin extensión)
                extract_folder = os.path.join(addons_path, os.path.splitext(file)[0] + "_")
                os.makedirs(extract_folder, exist_ok=True)

                # Extraer el contenido del archivo
                with zipfile.ZipFile(file_path, "r") as zip_ref:
                    zip_ref.extractall(extract_folder)
                print(f"Extraído: {file} a {extract_folder}")

                # Eliminar el archivo original inmediatamente después de la extracción
                os.remove(file_path)
                print(f"Eliminado archivo original: {file_path}")
            except zipfile.BadZipFile:
                print(f"Error: {file} no es un archivo ZIP válido.")

def process_mcaddon_and_mcpack(addons_path):
    def process_folder(folder_path):
        manifest_path = os.path.join(folder_path, "manifest.json")
        if os.path.exists(manifest_path):
            try:
                with open(manifest_path, "r") as file:
                        manifest = json5.load(file)
                print(f"Se encontró manifest.json en {folder_path}. Procediendo con el registro.")
                return True
            except ValueError as e:
                print(f"Error al leer el manifest.json en {folder_path}: {e}")
                print(f"El addon debe ser revisado manualmente.")
                return False

        # Si no hay manifest.json, verificar subcarpetas o archivos .mcpack/.mcaddon
        subfolders = [os.path.join(folder_path, f) for f in os.listdir(folder_path)]
        if not subfolders:
            print(f"No se encontró manifest.json ni contenido válido en {folder_path}. Eliminando carpeta.")
            shutil.rmtree(folder_path)
            return False

        # Mover subcarpetas y archivos .mcpack/.mcaddon al nivel principal
        for subfolder in subfolders:
            if os.path.isdir(subfolder) or subfolder.endswith((".mcpack", ".mcaddon")):
                shutil.move(subfolder, addons_path)
        print(f"Contenido de {folder_path} movido al nivel principal.")
        shutil.rmtree(folder_path)  # Eliminar la carpeta vacía
        return False

    def process_file(file_path):
        # Extraer archivo .mcaddon o .mcpack
        if file_path.endswith(".mcaddon") or file_path.endswith(".mcpack"):
            try:
                extract_folder = os.path.join(addons_path, os.path.splitext(os.path.basename(file_path))[0])
                os.makedirs(extract_folder, exist_ok=True)

                with zipfile.ZipFile(file_path, "r") as zip_ref:
                    zip_ref.extractall(extract_folder)
                print(f"Extraído: {file_path} a {extract_folder}")

                # Eliminar el archivo original inmediatamente después de la extracción
                os.remove(file_path)
                print(f"Eliminado archivo original: {file_path}")

                # Verificar y procesar la carpeta extraída
                while not process_folder(extract_folder):
                    # Repetir el proceso para los archivos movidos al nivel principal
                    for item in os.listdir(addons_path):
                        item_path = os.path.join(addons_path, item)
                        if os.path.isdir(item_path):
                            process_folder(item_path)
                        elif item_path.endswith((".mcpack", ".mcaddon")):
                            process_file(item_path)
            except zipfile.BadZipFile:
                print(f"Error: {file_path} no es un archivo ZIP válido.")

    # Procesar todas las carpetas y archivos en addons_path
    for item in os.listdir(addons_path):
        item_path = os.path.join(addons_path, item)
        if os.path.isdir(item_path):
            process_folder(item_path)
        else:
            process_file(item_path)

def process_folders_in_addons(addons_path):
    for folder in os.listdir(addons_path):
        folder_path = os.path.join(addons_path, folder)
        if not os.path.isdir(folder_path):
            continue

        # Buscar manifest.json en la carpeta
        manifest_path = os.path.join(folder_path, "manifest.json")
        if os.path.exists(manifest_path):
            print(f"Se encontró manifest.json en {folder_path}.")
            continue  # Pasar a la siguiente carpeta

        # Si no hay manifest.json, mover contenido al nivel principal
        print(f"No se encontró manifest.json en {folder_path}. Procesando contenido...")
        for item in os.listdir(folder_path):
            item_path = os.path.join(folder_path, item)
            shutil.move(item_path, addons_path)  # Mover al nivel principal
        shutil.rmtree(folder_path)  # Eliminar la carpeta vacía
        print(f"Contenido de {folder_path} movido al nivel principal y carpeta eliminada.")

def process_addons_in_addons_path(addons_path):
    while True:
        # Paso 1: Extraer archivos .mcpack y .mcaddon en la carpeta principal
        extract_mcaddon_and_mcpack(addons_path)

        # Paso 2: Revisar carpetas en busca de manifest.json y mover contenido si es necesario
        process_folders_in_addons(addons_path)

        # Verificar si quedan archivos .mcpack o .mcaddon en la carpeta principal
        remaining_files = [f for f in os.listdir(addons_path) if f.endswith(".mcpack") or f.endswith(".mcaddon")]
        if not remaining_files:
            break  # Salir del bucle si no quedan archivos .mcpack o .mcaddon

    print("Todas las carpetas en addons contienen manifest.json y no hay más archivos .mcpack o .mcaddon.")

def register_addons(addons_path, behavior_path, resource_path, behavior_json_path, resource_json_path):
    print("Registrando addons...")
    process_addons(addons_path, behavior_path, resource_path, behavior_json_path, resource_json_path)
    print("Registro de addons completado.")

# Ruta base del servidor
base_path = os.getcwd()
addons_path = os.path.join(base_path, "addons")
level_name = get_level_name()

# Asegurar que las carpetas y archivos necesarios existan
behavior_path, resource_path = ensure_directories_exist(base_path, level_name)
behavior_json_path = os.path.join(base_path, f"worlds/{level_name}/world_behavior_packs.json")
resource_json_path = os.path.join(base_path, f"worlds/{level_name}/world_resource_packs.json")

# Procesar los addons

# clean_unregistered_addons(behavior_path, resource_path, behavior_json_path, resource_json_path)
# clean_orphaned_entries(behavior_path, resource_path, behavior_json_path, resource_json_path)
extract_mcaddon_and_mcpack(addons_path)
process_mcaddon_and_mcpack(addons_path)
process_folders_in_addons(addons_path)
process_addons_in_addons_path(addons_path)
process_addons(addons_path, behavior_path, resource_path, behavior_json_path, resource_json_path)

print(r"""
 /$$$$$$$                                      /$$       /$$
| $$__  $$                                    | $$      | $$
| $$  \ $$  /$$$$$$  /$$$$$$$   /$$$$$$   /$$$$$$$  /$$$$$$$
| $$  | $$ |____  $$| $$__  $$ /$$__  $$ /$$__  $$ /$$__  $$
| $$  | $$  /$$$$$$$| $$  \ $$| $$$$$$$$| $$  | $$| $$  | $$
| $$  | $$ /$$__  $$| $$  | $$| $$_____/| $$  | $$| $$  | $$
| $$$$$$$/|  $$$$$$$| $$  | $$|  $$$$$$$|  $$$$$$$|  $$$$$$$
|_______/  \_______/|__/  |__/ \_______/ \_______/ \_______/
                                                            
                                                            
                                                            
Instalador de addons para Server Minecraft Bedrock Edition creado por Danedd.
      """)

time.sleep(3)
# Ejecutar el servidor Bedrock
try:
    subprocess.run(["./bedrock_server"], check=True)
except Exception as e:
    print(f"Error al iniciar el servidor: {e}")