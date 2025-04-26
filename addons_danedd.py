import os
import json
import shutil
import subprocess

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
        if module_type == "data":
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

# Ruta base del servidor
base_path = os.getcwd()
addons_path = os.path.join(base_path, "addons")
level_name = get_level_name()

# Asegurar que las carpetas y archivos necesarios existan
behavior_path, resource_path = ensure_directories_exist(base_path, level_name)
behavior_json_path = os.path.join(base_path, f"worlds/{level_name}/world_behavior_packs.json")
resource_json_path = os.path.join(base_path, f"worlds/{level_name}/world_resource_packs.json")

# Procesar los addons
process_addons(addons_path, behavior_path, resource_path, behavior_json_path, resource_json_path)

# Ejecutar el servidor Bedrock
try:
    subprocess.run(["./bedrock_server"], check=True)
except subprocess.CalledProcessError as e:
    print(f"Error al iniciar el servidor: {e}")