import zipfile, os, sys

ZIP_FILE = 'Rentals_V5_code_v7.zip'
EXTRACT_DIR = 'deployed_app'

# Extract the zip if not already done
if not os.path.isdir(EXTRACT_DIR):
    with zipfile.ZipFile(ZIP_FILE, 'r') as zip_ref:
        zip_ref.extractall(EXTRACT_DIR)

# Add extracted project path to sys.path
3sys.path.insert(0, os.path.join(EXTRACT_DIR, 'Rentals_V5'))
sys.path.insert(0, os.path.join(EXTRACT_DIR, 'Rentals_V5'))

# Import the Flask app from the extracted code
from app import app
