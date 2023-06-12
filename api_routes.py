import os
from flask import Blueprint, jsonify, render_template, request, redirect, url_for, current_app, send_from_directory
from utils import calculate_sha256, debugPrint
from app import db, basedir
from models import Package, PackageVersion, Installer

api = Blueprint('api', __name__)

@api.route('/add_package', methods=['POST'])
def add_package():
    name = request.form['name']
    identifier = request.form['identifier']
    publisher = request.form['publisher']
    architecture = request.form['architecture']
    installer_type = request.form['type']
    version = request.form['version']

    # Get file
    file = request.files['file']
    package = Package(package_identifier=identifier, package_name=name, publisher=publisher)
    if file and version:
        debugPrint("File and version found")
        save_directory = os.path.join(basedir, 'packages', publisher, identifier, version, architecture)
        # Create directory if it doesn't exist
        if not os.path.exists(save_directory):
            os.makedirs(save_directory)
        # Save file
        file_path = os.path.join(save_directory, file.filename)
        file.save(file_path)
        # Get file hash
        hash = calculate_sha256(file_path)
        package_version = PackageVersion(package_version=version, package_locale="en-US", short_description=name,package_identifier=identifier)
        installer = Installer(architecture=architecture, installer_type=installer_type, file_name=file.filename, installer_sha256=hash, scope="user")        
        package_version.installers.append(installer)
        package.versions.append(package_version)
    db.session.add(package)
    db.session.commit()
    return "Package added", 200

@api.route('/update_package_info', methods=['POST'])
def update_package_info():
    id = request.form['id']
    name = request.form['name']
    identifier = request.form['identifier']
    publisher = request.form['publisher']

    package = Package.query.filter_by(id=id).first()
    if package is None:
        return redirect(request.referrer)
    
    package.package_name = name
    package.package_identifier = identifier
    package.publisher = publisher
    db.session.commit()
    return redirect(request.referrer)

    
@api.route('/add_package_version', methods=['POST'])
def add_package_version():
    package_identifier = request.form['package_identifier']
    package_version = request.form['package_version']
    package_locale = request.form['package_locale']
    short_description = request.form['short_description']

    package = Package.query.filter_by(package_identifier=package_identifier).first()
    if package is None:
        return redirect(request.referrer)

    
    package_version = PackageVersion(package_version=package_version, package_locale=package_locale, short_description=short_description)
    package.versions.append(package_version)
    db.session.commit()
    return redirect(request.referrer)



@api.route('/add_installer', methods=['POST'])
def add_installer():
    package_identifier = request.form['package_identifier']
    package_version = request.form['package_version']
    architecture = request.form['architecture']
    installer_type = request.form['installer_type']
    file = request.files['file']
    scope = request.form['scope']

    package = Package.query.filter_by(package_identifier=package_identifier).first()
    if package is None:
        return redirect(request.referrer)
    
    package_version = PackageVersion.query.filter_by(package_version=package_version).first()
    if package_version is None:
        return redirect(request.referrer)
    
    if file:
        file.save(os.path.join(basedir, 'static', 'packages', file.filename))
        # Get file hash
        hash = calculate_sha256(os.path.join(basedir, 'static', 'packages', file.filename))
        installer = Installer(architecture=architecture, installer_type=installer_type, installer_url='https://thilojaeggi-psychic-tribble-jrg579jpj935p64-5000.preview.app.github.dev/static/packages/' + file.filename, installer_sha256=hash, scope=scope)
        package_version.installers.append(installer)
        db.session.commit()

    
    return redirect(request.referrer)
    



@api.route('/information')
def information():
    return jsonify({"Data": {"SourceIdentifier": "api.wingetty", "ServerSupportedVersions": ["1.4.0"]}})
    
@api.route('/packageManifests/<name>', methods=['GET'])
def get_package_manifest(name):
    package = Package.query.filter_by(package_identifier=name).first()
    if package is None:
        
        return jsonify({}), 204
    return jsonify(package.generate_output())



@api.route('/manifestSearch', methods=['POST'])
def manifestSearch():
    # Output all post request data
    request_data = request.get_json()
    debugPrint(request_data)

    maximum_results = request_data.get('MaximumResults')
    fetch_all_manifests = request_data.get('FetchAllManifests')
        
    query = request_data.get('Query')
    if query is not None:
        keyword = query.get('KeyWord')
        match_type = query.get('MatchType')

    inclusions = request_data.get('Inclusions')
    if inclusions is not None:
        package_match_field = inclusions[0].get('PackageMatchField')
        request_match = inclusions[0].get('RequestMatch')
        if query is None:
            keyword = request_match.get('KeyWord')
            match_type = request_match.get('MatchType')

    filters = request_data.get('Filters')
    if filters is not None:
        package_match_field_filter = filters[0].get('PackageMatchField')
        request_match_filter = filters[0].get('RequestMatch')
        keyword_filter = request_match_filter.get('KeyWord')
        match_type_filter = request_match_filter.get('MatchType')


    # Get packages by keyword and match type (exact or partial)
    packages = []
    if keyword is not None and match_type is not None:
        if match_type == "Exact":
            packages_query = Package.query.filter_by(package_identifier=keyword)
            # Also search for package name if no package identifier is found
            if packages_query.first() is None:
                debugPrint("No package found with identifier, searching for package name")
                packages_query = Package.query.filter_by(package_name=keyword)
        elif match_type == "Partial" or match_type == "Substring":
            packages_query = Package.query.filter(Package.package_name.ilike(f'%{keyword}%'))
            # Also search for package identifier if no package name is found
            if packages_query.first() is None:
                debugPrint("No package found with name, searching for package identifier")
                packages_query = Package.query.filter(Package.package_identifier.ilike(f'%{keyword}%'))
        else:
            return jsonify({}), 204

        if maximum_results is not None:
            packages_query = packages_query.limit(maximum_results)
        
        packages = packages_query.all()

    if not packages:
        return jsonify({}), 204


    output_data = []
    for package in packages:
        # If a package is added to the output without any version associated with it WinGet will error out
        if len(package.versions) > 0:
            output_data.append(package.generate_output_manifest_search())
    
    output = {"Data": output_data}
    debugPrint(output)
    return jsonify(output)

@api.route('/download/<identifier>/<version>/<architecture>')
def download(identifier, version, architecture):
    package = Package.query.filter_by(package_identifier=identifier).first()
    if package is None:
        return "Package not found", 404
    
    # Get version of package and also match package
    package_version = PackageVersion.query.filter_by(package_version=version, package_identifier=identifier).first()
    if package_version is None:
        return "Package version not found", 404
    # Get installer of package version and also match architecture and identifier
    installer = Installer.query.filter_by(package_version_id=package_version.id, architecture=architecture).first()
    if installer is None:
        return "Installer not found", 404
    

    installer_path = os.path.join(basedir, 'packages', package.publisher, package.package_identifier, package_version.package_version, installer.architecture)

    package.download_count += 1
    db.session.commit()

    if current_app.debug:
        debugPrint("Starting download for package:")
        debugPrint(f"Package name: {package.package_name}")
        debugPrint(f"Package identifier: {package.package_identifier}")
        debugPrint(f"Package version: {package_version.package_version}")
        debugPrint(f"Architecture: {installer.architecture}")
        debugPrint(f"Installer file name: {installer.file_name}")
        debugPrint(f"Installer SHA256: {installer.installer_sha256}")
        debugPrint(f"Download URL: {installer_path}")
    

    
    return send_from_directory(installer_path, installer.file_name, as_attachment=True)