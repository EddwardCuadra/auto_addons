import os
import json
import shutil
import subprocess
import zipfile

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
def load_or_initialize_json(file_path):
    if os.path.exists(file_path):
        with open(file_path, "r") as file:
            try:
                data = json.load(file)
                if isinstance(data, list):  # Verifica si es una lista
                    return data
                else:
                    print(f"Advertencia: {file_path} no es una lista. Se inicializará como lista vacía.")
            except json.JSONDecodeError:
                print(f"Advertencia: {file_path} está corrupto. Se inicializará como lista vacía.")
    return []  # Retorna una lista vacía si el archivo no existe o no es válido

# Guardar datos en archivos JSON
def save_json(file_path, data):
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
            with open(manifest_path, "r") as file:
                manifest = json.load(file)
        except json.JSONDecodeError as e:
            print(f"Error al leer el manifest.json en {folder}: {e}")
            print(f"El addon {folder} debe ser revisado manualmente.")
            continue

        header = manifest.get("header", {})
        modules = manifest.get("modules", [])
        uuid = header.get("uuid")
        version = header.get("version")
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
                target_json.append({"pack_id": uuid, "version": version})
                save_json(json_path, target_json)
                shutil.move(folder_path, target_path)
            else:
                print(f"El addon {folder} ya está en su mejor versión")
                shutil.rmtree(folder_path)
                continue
        else:
            # Agregar nuevo UUID y mover carpeta
            target_json.append({"pack_id": uuid, "version": version})
            save_json(json_path, target_json)
            shutil.move(folder_path, target_path)

    print(f"Se añadieron {added_behavior} behavior packs y {added_resource} resource packs.")

def clean_unregistered_addons(behavior_path, resource_path, behavior_json_path, resource_json_path):
    # Cargar los datos registrados en los archivos JSON
    behavior_packs = load_or_initialize_json(behavior_json_path)
    resource_packs = load_or_initialize_json(resource_json_path)

    # Obtener los UUIDs registrados
    registered_behavior_uuids = {pack["pack_id"] for pack in behavior_packs}
    registered_resource_uuids = {pack["pack_id"] for pack in resource_packs}

    # Limpiar behavior_packs
    for folder in os.listdir(behavior_path):
        folder_path = os.path.join(behavior_path, folder)
        manifest_path = os.path.join(folder_path, "manifest.json")
        if os.path.isdir(folder_path) and os.path.exists(manifest_path):
            try:
                with open(manifest_path, "r") as file:
                    manifest = json.load(file)
                    uuid = manifest.get("header", {}).get("uuid")
                    if uuid not in registered_behavior_uuids:
                        print(f"Eliminando addon no registrado en behavior_packs: {folder}")
                        shutil.rmtree(folder_path)
            except (json.JSONDecodeError, KeyError):
                print(f"Error al procesar el manifest.json en {folder}.")
                print(f"Revisar manualmente el addon en la carpeta: {folder_path}")
                print(f"Tipo: {'behavior' if folder_path.startswith(behavior_path) else 'resource'}")
                try:
                    with open(manifest_path, "r") as file:
                        manifest = json.load(file)
                        uuid = manifest.get("header", {}).get("uuid", "Desconocido")
                        version = manifest.get("header", {}).get("version", "Desconocida")
                        print(f"UUID: {uuid}")
                        print(f"Versión: {version}")
                except json.JSONDecodeError:
                    print("El archivo manifest.json está corrupto y no se pudo leer.")

    # Limpiar resource_packs
    for folder in os.listdir(resource_path):
        folder_path = os.path.join(resource_path, folder)
        manifest_path = os.path.join(folder_path, "manifest.json")
        if os.path.isdir(folder_path) and os.path.exists(manifest_path):
            try:
                with open(manifest_path, "r") as file:
                    manifest = json.load(file)
                    uuid = manifest.get("header", {}).get("uuid")
                    if uuid not in registered_resource_uuids:
                        print(f"Eliminando addon no registrado en resource_packs: {folder}")
                        shutil.rmtree(folder_path)
            except (json.JSONDecodeError, KeyError):
                print(f"Error al procesar el manifest.json en {folder}.")
                print(f"Revisar manualmente el addon en la carpeta: {folder_path}")
                print(f"Tipo: {'behavior' if folder_path.startswith(behavior_path) else 'resource'}")
                try:
                    with open(manifest_path, "r") as file:
                        manifest = json.load(file)
                        uuid = manifest.get("header", {}).get("uuid", "Desconocido")
                        version = manifest.get("header", {}).get("version", "Desconocida")
                        print(f"UUID: {uuid}")
                        print(f"Versión: {version}")
                except json.JSONDecodeError:
                    print("El archivo manifest.json está corrupto y no se pudo leer.")

def clean_orphaned_entries(behavior_path, resource_path, behavior_json_path, resource_json_path):
    # Limpiar entradas huérfanas en world_behavior_packs.json
    behavior_packs = load_or_initialize_json(behavior_json_path)
    updated_behavior_packs = []

    for pack in behavior_packs:
        pack_id = pack["pack_id"]
        found = False
        for folder in os.listdir(behavior_path):
            folder_path = os.path.join(behavior_path, folder)
            manifest_path = os.path.join(folder_path, "manifest.json")
            if os.path.isdir(folder_path) and os.path.exists(manifest_path):
                try:
                    with open(manifest_path, "r") as file:
                        manifest = json.load(file)
                        if manifest.get("header", {}).get("uuid") == pack_id:
                            found = True
                            break
                except json.JSONDecodeError:
                    print(f"Error al leer el manifest.json en {folder_path}.")
        if found:
            updated_behavior_packs.append(pack)
        else:
            print(f"Eliminando entrada huérfana en world_behavior_packs.json: {pack_id}")

    save_json(behavior_json_path, updated_behavior_packs)

    # Limpiar entradas huérfanas en world_resource_packs.json
    resource_packs = load_or_initialize_json(resource_json_path)
    updated_resource_packs = []

    for pack in resource_packs:
        pack_id = pack["pack_id"]
        found = False
        for folder in os.listdir(resource_path):
            folder_path = os.path.join(resource_path, folder)
            manifest_path = os.path.join(folder_path, "manifest.json")
            if os.path.isdir(folder_path) and os.path.exists(manifest_path):
                try:
                    with open(manifest_path, "r") as file:
                        manifest = json.load(file)
                        if manifest.get("header", {}).get("uuid") == pack_id:
                            found = True
                            break
                except json.JSONDecodeError:
                    print(f"Error al leer el manifest.json en {folder_path}.")
        if found:
            updated_resource_packs.append(pack)
        else:
            print(f"Eliminando entrada huérfana en world_resource_packs.json: {pack_id}")

    save_json(resource_json_path, updated_resource_packs)

def extract_mcaddon_and_mcpack(addons_path):
    for file in os.listdir(addons_path):
        file_path = os.path.join(addons_path, file)
        if file.endswith(".mcaddon") or file.endswith(".mcpack"):
            try:
                # Crear una carpeta con el mismo nombre que el archivo (sin extensión)
                extract_folder = os.path.join(addons_path, os.path.splitext(file)[0])
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
        # Buscar manifest.json en la carpeta
        manifest_path = os.path.join(folder_path, "manifest.json")
        if os.path.exists(manifest_path):
            print(f"Se encontró manifest.json en {folder_path}. Procediendo con el registro.")
            return True  # Se encontró el manifest.json, se puede registrar

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

clean_unregistered_addons(behavior_path, resource_path, behavior_json_path, resource_json_path)
clean_orphaned_entries(behavior_path, resource_path, behavior_json_path, resource_json_path)
extract_mcaddon_and_mcpack(addons_path)
process_mcaddon_and_mcpack(addons_path)
process_folders_in_addons(addons_path)
process_addons_in_addons_path(addons_path)
process_addons(addons_path, behavior_path, resource_path, behavior_json_path, resource_json_path)

# Ejecutar el servidor Bedrock
try:
    subprocess.run(["./bedrock_server"], check=True)
except subprocess.CalledProcessError as e:
    print(f"Error al iniciar el servidor: {e}")