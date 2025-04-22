#!/usr/bin/env python3
"""
This script performs the following steps:
  0) Checks that the Linux 7z command-line utility is available.
  1) Creates a directory called "UnrealTournament" in the user's home directory.
     If such a directory already exists, it renames the old one by appending a random string.
  2) Creates an "Installer" folder inside "UnrealTournament" and downloads ut99.iso from a given URL.
  3) Checks the md5sum of ut99.iso against the expected checksum.
  4) Fetches the latest patch URL by processing a JSON file (using our "Fetch Linux Asset" function)
     and downloads the patch file into the Installer folder.
  5) Downloads configuration files (UnrealTournament.ini, User.ini, skip.txt) from a given URL.
  6) Unpacks both the ISO and patch files using 7z.
  7) Iterates through the Maps/ directory (from the unpacked ISO) looking for *.uz files,
     and runs ucc to decompress. ucc for some reason installs these into ~/.utpg/Maps and ~/.utpg/System
  8) Copies configuration files into the System directory.
  9) Creates a Linux desktop icon that launches the game binary.
  
Be sure to adjust URLs (for the JSON patch and configuration files) as needed.
"""

import sys

# Check if 'requests' library is installed.
try:
    import requests
except ImportError:
    print("Error: The 'requests' library is not installed.")
    print("Please install it using the following command:")
    print("    pip install requests")
    sys.exit(1)

import os
import subprocess
import shutil
import hashlib
import random
import string
import glob
import stat

# Define the base URL for all downloads (only defined once)
SERVER_ISO_BASE_URL = "https://archive.org/download/ut-goty/"
SERVER_ISO_FILE     = "UT_GOTY_CD1.iso"

# Mirror
#SERVER_ISO_BASE_URL = "http://51.161.128.43:1400/ut99/"
#SERVER_ISO_FILE     = "UT_GOTY_CD1.iso"

# Expected MD5SUM of the iso file, as per the one on the archive.org site.
expected_iso_md5 = "e5127537f44086f5ed36a9d29f992c00"
    
# ut99 working .ini's / Install skip.txt file
SERVER_CFG_BASE_URL = "https://raw.githubusercontent.com/mrcodetastic/ut99-linux-amd64-Installer/refs/heads/main/"


def log(msg):
    print("[*]", msg)

def run_cmd(cmd, cwd=None):
    log("Running command: " + cmd)
    result = subprocess.run(cmd, shell=True, cwd=cwd)
    return result.returncode

def check_7z():
    if shutil.which("7z") is None:
        log("7z command not found. Please install p7zip-full (or equivalent) and try again.")
        sys.exit(1)
    else:
        log("7z found.")
        

def check_curl():
    if shutil.which("curl") is None:
        log("curl command not found. Please install curl (or equivalent) and try again.")
        sys.exit(1)
    else:
        log("curl found.")        

def create_directory(dir_path):
    if os.path.exists(dir_path):
        # If the directory exists, rename it by appending a random string.
        rand_suffix = ''.join(random.choices(string.ascii_lowercase + string.digits, k=8))
        new_name = f"{dir_path}_{rand_suffix}"
        log(f"Directory '{dir_path}' already exists. Renaming it to '{new_name}'")
        os.rename(dir_path, new_name)
    os.makedirs(dir_path)
    log(f"Created directory: {dir_path}")

def download_file(url, dest):
    log(f"Downloading {url} -> {dest}")
    # Use curl to download (the -L option follows redirects)
    cmd = f'curl -L -o "{dest}" "{url}"'
    ret = subprocess.run(cmd, shell=True)
    if ret.returncode != 0:
        log(f"Error downloading file from {url}")
        sys.exit(1)

def md5sum(filename):
    hash_md5 = hashlib.md5()
    with open(filename, "rb") as f:
        for chunk in iter(lambda: f.read(4096), b""):
            hash_md5.update(chunk)
    return hash_md5.hexdigest()

def get_linux_amd64_download_url(json_url):
    """
    Fetches the JSON from json_url and returns the browser_download_url for the asset
    whose "name" field contains "Linux-amd64". (Replace json_url with the proper URL.)
    """
    log(f"Fetching patch info from JSON: {json_url}")
    response = requests.get(json_url)
    response.raise_for_status()
    data = response.json()
    for asset in data.get("assets", []):
        if "Linux-amd64" in asset.get("name", ""):
            patch_url = asset.get("browser_download_url")
            log(f"Found patch asset: {asset.get('name')} -> {patch_url}")
            return patch_url
    return None

def process_uz_files(base_dir, system64_dir):
    """
    Searches the Maps/ directory (under base_dir) for all *.uz files, unpacks these.
    
    On linux, the decompressed files will be placed into the users .utpg/System directory
    This is good enough.
    
    """
    ucc_path = os.path.join(system64_dir, "ucc-bin-amd64")
    ucc_stat = os.stat(ucc_path)
    if ucc_stat.st_mode & (stat.S_IXUSR | stat.S_IXOTH | stat.S_IXGRP) == 0:
        print("ucc executeable not set to executable, attempting to fix.")
        try:
            os.chmod(ucc_path,
                ucc_stat.st_mode | stat.S_IXUSR | stat.S_IXOTH | stat.S_IXGRP)
        except OSError as e:
            print(f"Failed to set executable bit on {ucc_path} - {e}")
            return
    maps_dir = os.path.join(base_dir, "Maps")
    if not os.path.exists(maps_dir):
        log("Maps directory not found in the unpacked ISO. Skipping .uz file processing.")
        return
    
    # Find all .uz files recursively within the Maps directory.
    uz_files = glob.glob(os.path.join(maps_dir, '**', '*.uz'), recursive=True)
    total = len(uz_files)
    if total == 0:
        log("No .uz files found in the Maps directory.")
        return
    
    log("Unpacking game files from .uz files...")
    done = 0
    for uz in uz_files:
        done += 1
        progress = round(100.0 * done / total, 1)
        log(f"Processing {uz} ({progress}%)")
    
            
        # Build and run the decompress command using ucc-bin-amd64 from system64_dir.
        cmd = f'"{ucc_path}" decompress "{uz}"'
        if run_cmd(cmd) != 0:
            log(f"Error decompressing {uz}")
            continue
  
  
def main():

    # Step 0: Check that 7z is available.
    check_7z()
    
    # Step 0: Check that curl is available.
    check_curl()    
    
    # Determine home directory and set up base folders.
    home = os.path.expanduser("~")
    base_dir = os.path.join(home, "UnrealTournament")
    
    # Step 1: Create (or rename & create) the UnrealTournament directory.
    if os.path.exists(base_dir):
        rand_suffix = ''.join(random.choices(string.ascii_lowercase + string.digits, k=8))
        new_name = f"{base_dir}_{rand_suffix}"
        log(f"Directory '{base_dir}' already exists. Renaming it to '{new_name}'")
        os.rename(base_dir, new_name)
    os.makedirs(base_dir)
    log(f"Created new directory: {base_dir}")
    
    # Create subdirectories: Installer and System.
    installer_dir = os.path.join(base_dir, "Installer")
    system_dir = os.path.join(base_dir, "System")
    os.makedirs(installer_dir, exist_ok=True)
    os.makedirs(system_dir, exist_ok=True)
    
    # Step 2: Download ut99.iso into the Installer directory.
    ut99_url = f"{SERVER_ISO_BASE_URL}{SERVER_ISO_FILE}"
    ut99_dest = os.path.join(installer_dir, "ut99.iso")
    download_file(ut99_url, ut99_dest)
    
    # Step 3: Verify the md5sum of ut99.iso.
    actual_md5 = md5sum(ut99_dest)
    if actual_md5 != expected_iso_md5:
        log(f"MD5 mismatch for {SERVER_ISO_FILE}: expected {expected_iso_md5}, got {actual_md5}")
        sys.exit(1)
    else:
        log(f"{SERVER_ISO_FILE} MD5 checksum verified.")
    
    # Step 4: Download the latest patch using the Fetch Linux Asset code.
    # Replace the following json_url with the actual URL that returns the JSON asset info.
    json_url = "https://api.github.com/repos/OldUnreal/UnrealTournamentPatches/releases/latest" 
    try:
        patch_url = get_linux_amd64_download_url(json_url)
    except Exception as e:
        log("Error fetching patch info: " + str(e))
        sys.exit(1)
    if not patch_url:
        log("No matching Linux-amd64 patch asset found.")
        sys.exit(1)
    
    patch_filename = os.path.basename(patch_url)
    patch_dest = os.path.join(installer_dir, patch_filename)
    download_file(patch_url, patch_dest)
    
    # Step 5: Download configuration files: UnrealTournament.ini, User.ini, skip.txt.
    for filename in ["UnrealTournament.ini", "User.ini", "skip.txt"]:
        file_url = f"{SERVER_CFG_BASE_URL}{filename}"
        dest_path = os.path.join(installer_dir, filename)
        download_file(file_url, dest_path)
    
    # Step 6: Unpack the ut99.iso and patch ZIP files.
    # (We run the 7z commands from within the Installer directory so that -o.. puts output in base_dir.)
    log("Unpacking game ISO...")
    iso_cmd = f'7z x -aoa -o.. -x@skip.txt ut99.iso'
    if run_cmd(iso_cmd, cwd=installer_dir) != 0:
        log("Error unpacking game ISO.")
        sys.exit(1)
    
    log("Unpacking Linux path .tar.bz2...")
#    patch_cmd = f'7z x -aoa -o.. {patch_filename}'
    # Explanation:
    # 7z x → Extracts files with full paths (useful for archives with directory structures).
    #  OldUnreal-UTPatch469e-Linux-amd64.tar.bz2 → The archive to extract.
    # -o../ → Specifies the output directory as ../ (the parent of the current directory).
    # Since .tar.bz2 is a two-layered archive (.bz2 compression around a .tar file), 7z will first extract the .tar file. After that, you will need to extract the .tar contents (via. piping).
    patch_cmd = f'7z x \'{patch_filename}\' -so | 7z x -si -ttar -o../ -aoa'
    if run_cmd(patch_cmd, cwd=installer_dir) != 0:
        log("Error unpacking patch ZIP.")
        sys.exit(1)
    
    # Step 7: Process *.uz files from the Maps directory.
    # Need the ucc binary from the System64 directory from the patch 
    system64_dir = os.path.join(base_dir, "System64")
    if not os.path.exists(system64_dir):
        log(f"Warning: System64 directory not found at {system64_dir}. Can't do .uz processing. Existing.")
        sys.exit(1)
    else:
        process_uz_files(base_dir, system64_dir)
    
    # Step 8: Copy configuration files to the System directory.
    try:
        shutil.copy(os.path.join(installer_dir, "UnrealTournament.ini"),
                    os.path.join(system_dir, "UnrealTournament.ini"))
        shutil.copy(os.path.join(installer_dir, "User.ini"),
                    os.path.join(system_dir, "User.ini"))
        log("Copied configuration files to the System directory.")
    except Exception as e:
        log("Error copying configuration files: " + str(e))
    
    # Step 9: Create a Linux desktop icon.
    # We assume the main executable is at: ~/UnrealTournament/System64/ut-bin-amd64
    exec_path = os.path.join(base_dir, "System64", "ut-bin-amd64")
    icon_path = os.path.join(base_dir, "Help", "Unreal.ico")
    desktop_entry = f"""[Desktop Entry]
Name=Unreal Tournament
Exec={exec_path}
Icon={icon_path}
Type=Application
Terminal=false
"""
    # Place the desktop file on the user's Desktop if available, or fallback to home.
    desktop_dir = os.path.join(home, "Desktop")
    if not os.path.exists(desktop_dir):
        desktop_dir = home
    desktop_file = os.path.join(desktop_dir, "Unreal Tournament.desktop")
    with open(desktop_file, "w") as f:
        f.write(desktop_entry)
    # Make the desktop file executable.
    os.chmod(desktop_file, 0o755)
    log(f"Desktop icon created at {desktop_file}")
    
    print("")
    print("")
    print("INSTALL COMPLETED")
    print("")    
    print("HAPPY FRAGGING!")                    
    print("")
    print("Helpful tip: On first run of the game it is advised to first adjust the default game video resolution.")    

if __name__ == "__main__":
    main()

