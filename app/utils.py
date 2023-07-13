import hashlib
import os
from flask import current_app, request
from werkzeug.utils import secure_filename
from app.models import Installer, InstallerSwitch, NestedInstallerFile
from app.constants import installer_switches


basedir = os.path.abspath(os.path.dirname(__file__))

def create_installer(publisher, identifier, version, installer_form):
    file = installer_form.file.data
    architecture = installer_form.architecture.data
    installer_type = installer_form.installer_type.data
    scope = installer_form.installer_scope.data
    nestedinstallertype = installer_form.nestedinstallertype.data
    nestedinstallerpath = installer_form.nestedinstallerpath.data

    file_name = secure_filename(file.filename)
    file_name = f'{scope}.' + file_name.rsplit('.', 1)[1]

    hash = save_file(file, file_name, publisher, identifier, version, architecture)
    if hash is None:
        return "Error saving file", 500
    
    installer = Installer(
        architecture=architecture,
        installer_type=installer_type,
        file_name=file_name,
        installer_sha256=hash,
        scope=scope
    )

    for field_name in installer_switches:
        debugPrint(f"Checking for field name {field_name}")
        if field_name in request.form:
            debugPrint(f"Field name found {field_name}")
            field_value = request.form.get(field_name)
            installer_switch = InstallerSwitch()
            installer_switch.parameter = field_name
            installer_switch.value = field_value
            installer.switches.append(installer_switch)

    if nestedinstallertype is not None and nestedinstallerpath is not None:
        installer.nested_installer_type = nestedinstallertype
        nested_installer_file = NestedInstallerFile(relative_file_path=nestedinstallerpath)
        installer.nested_installer_files.append(nested_installer_file)
    elif nestedinstallertype is not None or nestedinstallerpath is not None:
        return "Nested installer type and path should be provided together", 500

    return installer

def calculate_sha256(filename):
    sha256_hash = hashlib.sha256()

    with open(filename, 'rb') as file:
        # Read the file in chunks to efficiently handle large files
        for chunk in iter(lambda: file.read(4096), b''):
            sha256_hash.update(chunk)

    return sha256_hash.hexdigest()

def debugPrint(message):
    if current_app.config['DEBUG']:
        print(message)

def save_file(file, file_name, publisher, identifier, version, architecture):
    publisher = secure_filename(publisher)
    identifier = secure_filename(identifier)
    version = secure_filename(version)
    architecture = secure_filename(architecture)

    # Create directory if it doesn't exist
    save_directory = os.path.join(basedir, 'packages', publisher, identifier, version, architecture)
        # Create directory if it doesn't exist
    if not os.path.exists(save_directory):
        os.makedirs(save_directory)


    # Save file
    file_path = os.path.join(save_directory, file_name)
    file.save(file_path)
    # Get file hash
    hash = calculate_sha256(file_path)
    return hash