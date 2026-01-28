import requests
import json
import os
import sys

BASE_URL = "http://localhost:8000/api/v1"
ADMIN_USER = "Admin"
ADMIN_PASS = "12345678"

def login():
    print("Logging in as Admin...")
    resp = requests.post(f"{BASE_URL}/auth/access-token", data={
        "username": ADMIN_USER,
        "password": ADMIN_PASS
    })
    if resp.status_code != 200:
        print(f"Login failed: {resp.text}")
        sys.exit(1)
    return resp.json()["access_token"]

def verify_version(token):
    print("Verifying /system/version...")
    headers = {"Authorization": f"Bearer {token}"}
    resp = requests.get(f"{BASE_URL}/system/version", headers=headers)
    if resp.status_code != 200:
        print(f"Version check failed: {resp.text}")
    else:
        data = resp.json()
        print(f"Version: {data.get('version')}")
        if data.get('version') == "Unknown":
            print("WARNING: Version is Unknown. Check folder structure.")
        else:
            print("Version check passed.")

def verify_minio_health(token):
    print("Verifying /system/minio/health...")
    headers = {"Authorization": f"Bearer {token}"}
    resp = requests.get(f"{BASE_URL}/system/minio/health", headers=headers)
    if resp.status_code != 200:
        print(f"Minio health check failed: {resp.text}")
    else:
        print("Minio health check passed.")

def verify_queue_logs(token):
    print("Verifying /tasks/queue/logs...")
    headers = {"Authorization": f"Bearer {token}"}
    resp = requests.get(f"{BASE_URL}/tasks/queue/logs", headers=headers)
    if resp.status_code != 200:
        print(f"Queue logs check failed: {resp.text}")
    else:
        logs = resp.json()
        print(f"Fetched {len(logs)} logs.")
        if len(logs) > 0:
            log = logs[0]
            print(f"Sample log keys: {log.keys()}")
            if "started_at" in log and "completed_at" in log:
                print("Queue logs schema check passed.")
            else:
                print("FAILED: started_at or completed_at missing from logs.")
        else:
            print("No logs to verify schema (empty list). Assuming schema is correct if endpoint returned 200.")

def verify_task_creation_filename(token):
    print("Verifying task creation filename logic...")
    headers = {"Authorization": f"Bearer {token}"}
    task_id = "VerifyTask01"
    filename = "test_image.nd2"
    
    # Check if exists, delete if so (requires delete endpoint which might not exist fully or working)
    # Just try create, if fail (duplicate), ignore or try another ID
    
    data = {
        "id": task_id,
        "name": "Verification Task",
        "filename": filename,
        "size": 1024
    }
    
    resp = requests.post(f"{BASE_URL}/tasks/", json=data, headers=headers)
    if resp.status_code == 200:
        res = resp.json()
        print(f"Task created. Object key: {res['nd2_object_key']}")
        expected_key = f"{task_id}/{filename}"
        if res['nd2_object_key'] == expected_key:
            print("Filename logic passed (initial creation).")
        else:
            print(f"Filename logic unexpected: {res['nd2_object_key']}")
    elif resp.status_code == 400 and "already exists" in resp.text:
         print("Task already exists, skipping creation check.")
    else:
        print(f"Task creation failed: {resp.text}")

if __name__ == "__main__":
    try:
        token = login()
        verify_version(token)
        verify_minio_health(token)
        verify_queue_logs(token)
        verify_task_creation_filename(token)
        print("\nAll verifications completed.")
    except Exception as e:
        print(f"\nVerification failed with error: {e}")
