import os

from flask import (
    Blueprint, jsonify, render_template, request,
    redirect, url_for, current_app, send_from_directory, flash
)
from flask_login import login_required
from werkzeug.http import parse_range_header
from werkzeug.utils import secure_filename

from app import db
from app.decorators import permission_required
from app.forms import AddInstallerForm, AddPackageForm, AddVersionForm
from app.models import InstallerSwitch, Package, PackageVersion, Installer, User
from app.utils import create_installer, debugPrint, save_file, basedir
from app.constants import installer_switches
api = Blueprint('api', __name__)

@api.route('/')
def index():
    return "API is running, see documentation for more information", 200

@api.route('/add_package', methods=['POST'])
@login_required
@permission_required('add:package')
def add_package():
    form = AddPackageForm(meta={'csrf': False})
    installer_form = form.installer

    if not form.validate_on_submit():
        validation_errors = form.errors
        return str("Form validation error"), 500
    
    name = form.name.data
    publisher = form.publisher.data
    identifier = form.identifier.data
    version = installer_form.version.data
    file = installer_form.file.data
    

    package = Package(identifier=identifier, name=name, publisher=publisher)
    if file and version:
        debugPrint("File and version found")
        installer = create_installer(publisher, identifier, version, installer_form)
        if installer is None:
            return "Error creating installer", 500

        version_code = PackageVersion(version_code=version, package_locale="en-US", short_description=name, identifier=identifier)
        version_code.installers.append(installer)
        package.versions.append(version_code)
        
    try:
        db.session.add(package)
        db.session.commit()
        print("Commited to db")
    except Exception as e:
        db.session.rollback()
        print("Error committing to the database:", str(e))
        return "Database error", 500

    flash('Package added successfully.', 'success')
    return "Package added", 200

@api.route('/package/<identifier>', methods=['POST'])
@login_required
@permission_required('edit:package')
def update_package(identifier):
    package = Package.query.filter_by(identifier=identifier).first()
    if package is None:
        return "Package not found", 404
    name = request.form['name']
    publisher = request.form['publisher']
    package.name = name
    package.publisher = publisher
    db.session.commit()
    return redirect(request.referrer)

@api.route('/package/<identifier>', methods=['DELETE'])
@login_required
@permission_required('delete:package')
def delete_package(identifier):
    package = Package.query.filter_by(identifier=identifier).first()
    if package is None:
        return "Package not found", 404

    for version in package.versions:
        for installer in version.installers:
            filepath = os.path.join(basedir, 'packages', package.publisher, package.identifier, version.version_code, installer.architecture, installer.file_name)
            if os.path.exists(filepath):
                os.remove(filepath)
            db.session.delete(installer)
        db.session.delete(version)
    db.session.delete(package)
    db.session.commit()

    return "", 200


@api.route('/package/<identifier>/add_version', methods=['POST'])
@login_required
@permission_required('add:version')
def add_version(identifier):
    form = AddVersionForm(meta={'csrf': False})

    installer_form = form.installer

    if not form.validate_on_submit():
        validation_errors = form.errors
        print(validation_errors)
        return jsonify(validation_errors), 400
    
    version = installer_form.version.data
    
    

    package = Package.query.filter_by(identifier=identifier).first()
    if package is None:
        return "Package not found", 404
    file = installer_form.file.data
    version_code = PackageVersion(version_code=version, package_locale="en-US", short_description=package.name, identifier=identifier)
    if file and version:
        debugPrint("File and version found")
        installer = create_installer(package.publisher, identifier, version, installer_form)
        if installer is None:
            return "Error creating installer", 500

        version_code.installers.append(installer)

    package.versions.append(version_code)
    db.session.commit()

    return redirect(request.referrer)


@api.route('/package/<identifier>/add_installer', methods=['POST'])
@login_required
@permission_required('add:installer')
def add_installer(identifier):
    form = AddInstallerForm(meta={'csrf': False})
    installer_form = form.installer

    if not form.validate_on_submit():
        validation_errors = form.errors
        print(validation_errors)
        return jsonify(validation_errors), 400
    
    print(installer_form.version.data)
    
    
    package = Package.query.filter_by(identifier=identifier).first()
    if package is None:
        return "Package not found", 404
    
    # get version by id
    version = PackageVersion.query.filter_by(id=installer_form.version.data).first()
    if version is None:
        return "Package version not found", 404

    if installer_form.file:
        debugPrint("File found")
        installer = create_installer(package.publisher, identifier, version.version_code, installer_form)
        if installer is None:
            return "Error creating installer", 500

        version.installers.append(installer)
        db.session.commit()

        return redirect(request.referrer)
    

@api.route('/package/<identifier>/edit_installer', methods=['POST'])
@login_required
@permission_required('edit:installer')
def edit_installer(identifier):
    id = request.form['installer_id']
    # Get installer
    installer = Installer.query.filter_by(id=id).first()
    if installer is None:
        return "Installer not found", 404
    
    # Go through each installer switch and update it if it exists
    for field_name in installer_switches:
        debugPrint(f"Checking for field name {field_name}")
        if field_name in request.form:
            debugPrint(f"Field name found {field_name}")
            field_value = request.form.get(field_name)
            installer_switch = InstallerSwitch.query.filter_by(installer_id=id, parameter=field_name).first()
            if installer_switch is None:
                installer_switch = InstallerSwitch()
                installer_switch.parameter = field_name                
                installer_switch.value = field_value
                installer.switches.append(installer_switch)
            else:
                installer_switch.value = field_value
        else:
            # If the field name isn't in the request form, check if it exists in the database and delete it if it does
            installer_switch = InstallerSwitch.query.filter_by(installer_id=id, parameter=field_name).first()
            if installer_switch is not None:
                db.session.delete(installer_switch)

        db.session.commit()

    return redirect(request.referrer)

                



@api.route('/package/<identifier>/<version>/<installer>', methods=['DELETE'])
@login_required
@permission_required('delete:installer')
def delete_installer(identifier, version, installer):
    package = Package.query.filter_by(identifier=identifier).first()
    if package is None:
        debugPrint("Package not found")
        return "Package not found", 404
    
    version = PackageVersion.query.filter_by(identifier=identifier, version_code=version).first()
    if version is None:
        debugPrint("Version not found")
        return "Version not found", 404

    installer = Installer.query.filter_by(id=installer).first()
    if installer is None:
        return "Installer not found", 404
    
    installer_path = os.path.join(basedir, 'packages', package.publisher, package.identifier, version.version_code, installer.architecture, installer.file_name)
    if os.path.exists(installer_path):
        os.remove(installer_path)    
    
    db.session.delete(installer)
    db.session.commit()

    return "", 200

@api.route('/package/<identifier>/<version>', methods=['DELETE'])
@login_required
@permission_required('delete:version')
def delete_version(identifier, version):
    package = Package.query.filter_by(identifier=identifier).first()
    if package is None:
        debugPrint("Package not found")
        return "Package not found", 404
    
    version = PackageVersion.query.filter_by(identifier=identifier, version_code=version).first()
    if version is None:
        debugPrint("Version not found")
        return "Version not found", 404

    for installer in version.installers:
        installer_path = os.path.join(basedir, 'packages', package.publisher, package.identifier, version.version_code, installer.architecture, installer.file_name)
        if os.path.exists(installer_path):
            os.remove(installer_path)    
        db.session.delete(installer)
    db.session.delete(version)
    db.session.commit()

    return "", 200

@api.route('/update_user', methods=['POST'])
@login_required
@permission_required('edit:own_user')
def update_user():
    id = request.form['id']
    username = request.form['username'].lower().replace(" ", "")
    email = request.form['email'].lower().replace(" ", "")
    password = request.form['password']    

    user = User.query.filter_by(id=id).first()
    if user is None:
        return "User not found", 404
    
    # Check that email or username or both aren't used by another user before updating except for the current user
    if User.query.filter(User.id != id, User.email == email).first():
        flash('Email already in use', 'error')
        return redirect(request.referrer)
    if User.query.filter(User.id != id, User.username == username).first():
        flash('Username already in use', 'error')
        return redirect(request.referrer)
    
    user.username = username
    user.email = email
    if password:
        user.set_password(password)
        db.session.commit()
        flash('Password changed, please login again.', 'success')

    db.session.commit()
    flash('User updated successfully.', 'success')
    return redirect(request.referrer)


@api.route('/delete_user/<id>', methods=['DELETE'])
@login_required
@permission_required('delete:user')
def delete_user(id):
    user = User.query.filter_by(id=id).first()
    print(user)
    if user is None:
        return "User not found", 404
    db.session.delete(user)
    db.session.commit()
    return "", 200

@api.route('/download/<identifier>/<version>/<architecture>/<scope>')
def download(identifier, version, architecture, scope):
    # TODO: Improve this function to be more efficient, also when a package's publisher is renamed the file won't be found anymore

    package = Package.query.filter_by(identifier=identifier).first()
    if package is None:
        debugPrint("Package not found")
        return "Package not found", 404
    
    # Get version of package and also match package
    version_code = PackageVersion.query.filter_by(version_code=version, identifier=identifier).first()
    if version_code is None:
        debugPrint("Package version not found")
        return "Package version not found", 404
    # Get installer of package version and also match architecture and identifier
    installer = Installer.query.filter_by(version_id=version_code.id, architecture=architecture, scope=scope).first()
    if installer is None:
        debugPrint("Installer not found")
        return "Installer not found", 404


    installer_path = os.path.join(basedir, 'packages', package.publisher, package.identifier, version_code.version_code, installer.architecture)
    debugPrint("Starting download for package:")
    debugPrint(f"Package name: {package.name}")
    debugPrint(f"Package identifier: {package.identifier}")
    debugPrint(f"Package version: {version_code.version_code}")
    debugPrint(f"Architecture: {installer.architecture}")
    debugPrint(f"Installer file name: {installer.file_name}")
    debugPrint(f"Installer SHA256: {installer.installer_sha256}")
    debugPrint(f"Download URL: {installer_path}/{installer.file_name}")


    # Check if the Range header is present
    range_header = request.headers.get('Range')

    is_partial = range_header is not None
    if is_partial:
        request.range = parse_range_header(range_header)
        if request.range is None:
            return "Invalid range header", 400

    # Only add to download_count for a whole file download not part of it (winget uses range)
    if (is_partial and range_header and range_header == "bytes=0-1") or not is_partial:
        package.download_count += 1
        db.session.commit()

    debugPrint(f"Installer path: {installer_path + '/' + installer.file_name}")


    return send_from_directory(installer_path, installer.file_name, as_attachment=True)