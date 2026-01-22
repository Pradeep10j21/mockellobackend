import os
import sys
from dotenv import load_dotenv
from pymongo import MongoClient
import bcrypt

# Load environment variables
load_dotenv(dotenv_path=os.path.join(os.path.dirname(__file__), '.env'))

MONGODB_URI = os.getenv("MONGODB_URI")
if not MONGODB_URI:
    print("Error: MONGODB_URI not found in .env file")
    sys.exit(1)

def get_password_hash(password):
    return bcrypt.hashpw(password.encode('utf-8'), bcrypt.gensalt()).decode('utf-8')

def add_admin(email, password):
    try:
        client = MongoClient(MONGODB_URI)
        # Specifically target mockello_mvp_db as per user request
        db = client['mockello_mvp_db']
            
        admins = db.admins
        
        # Check if already exists
        existing = admins.find_one({"email": email})
        if existing:
            print(f"Admin with email {email} already exists. Updating password...")
            result = admins.update_one(
                {"email": email},
                {"$set": {"password_hash": get_password_hash(password), "role": "admin"}}
            )
            if result.modified_count > 0:
                print("Password updated successfully.")
            else:
                print("No changes made.")
        else:
            print(f"Creating new admin: {email}")
            admin_doc = {
                "email": email,
                "password_hash": get_password_hash(password),
                "role": "admin"
            }
            admins.insert_one(admin_doc)
            print("Admin created successfully.")
            
    except Exception as e:
        print(f"An error occurred: {e}")
    finally:
        client.close()

if __name__ == "__main__":
    email = "managementhitroo@gmail.com"
    password = "ro...latha"
    add_admin(email, password)
