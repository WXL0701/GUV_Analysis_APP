import requests
import os
import time
import json

BASE_URL = "http://127.0.0.1:8000/api"

def test_flow():
    print("Starting Integration Test...")
    
    # 1. Create Task
    task_id = "INTEG_TEST_" + str(int(time.time()))
    print(f"1. Creating Task: {task_id}")
    
    payload = {
        "id": task_id,
        "name": "Integration Test Task",
        "filename": "test.nd2",
        "size": 1024
    }
    
    try:
        res = requests.post(f"{BASE_URL}/tasks/", json=payload)
        res.raise_for_status()
        data = res.json()
        print("   Task Created successfully.")
    except Exception as e:
        print(f"!!! Failed to create task: {e}")
        return

    # 2. Upload File via Presigned URL
    print("2. Uploading File via Presigned URL...")
    presigned_url = data['presigned_put_url']
    
    try:
        # Direct PUT to MinIO
        file_content = b"Integration Test Content" * 100
        up_res = requests.put(presigned_url, data=file_content, headers={'Content-Type': 'application/octet-stream'})
        up_res.raise_for_status()
        print("   Upload to MinIO successful.")
        
        # Notify Backend
        comp_res = requests.post(f"{BASE_URL}/tasks/{task_id}/upload/complete")
        comp_res.raise_for_status()
        print("   Backend notified of completion.")
        
    except Exception as e:
        print(f"!!! Failed to upload: {e}")
        return

    # 3. Verify Status
    print("3. Verifying Status...")
    try:
        get_res = requests.get(f"{BASE_URL}/tasks/{task_id}")
        get_res.raise_for_status()
        task_info = get_res.json()
        status = task_info['status']
        print(f"   Current Status: {status}")
        if status != "UPLOADED":
            print(f"!!! Unexpected status: {status}")
    except Exception as e:
        print(f"!!! Failed to get task info: {e}")

    # 4. Test Search & Pagination
    print("4. Testing Search & Pagination...")
    try:
        # Search by specific ID
        search_res = requests.get(f"{BASE_URL}/tasks/", params={"q": task_id, "limit": 10})
        search_res.raise_for_status()
        page_data = search_res.json()
        
        # Verify response structure
        if "items" not in page_data or "total" not in page_data:
            print(f"!!! Invalid pagination response: {page_data.keys()}")
        else:
            items = page_data["items"]
            total = page_data["total"]
            print(f"   Pagination keys present. Total: {total}, Items: {len(items)}")
            
            found = any(t['id'] == task_id for t in items)
            if found:
                print("   Search found the task.")
            else:
                print("!!! Search failed to find the task.")
    except Exception as e:
         print(f"!!! Search request failed: {e}")

    # 5. Delete Task
    print("5. Deleting Task...")
    try:
        del_res = requests.delete(f"{BASE_URL}/tasks/{task_id}")
        del_res.raise_for_status()
        print("   Delete request successful.")
    except Exception as e:
        print(f"!!! Failed to delete task: {e}")
        return

    # 6. Verify Deletion
    print("6. Verifying Deletion...")
    try:
        check_res = requests.get(f"{BASE_URL}/tasks/{task_id}")
        if check_res.status_code == 404:
            print("   Task correctly returned 404 (Not Found).")
        else:
            print(f"!!! Task still exists or unexpected code: {check_res.status_code}")
    except Exception as e:
        print(f"!!! Verification failed: {e}")

    print("Integration Test Completed.")

if __name__ == "__main__":
    test_flow()
