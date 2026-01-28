import sys
import os
import requests

# Add backend to path
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.core.config import settings
from minio import Minio
from minio.error import S3Error

def check_minio():
    print(f"Checking MinIO connection to {settings.MINIO_ENDPOINT}...")
    print(f"Access Key: {settings.MINIO_ACCESS_KEY}")
    # Don't print secret key
    print(f"Bucket: {settings.MINIO_BUCKET}")

    try:
        client = Minio(
            settings.MINIO_ENDPOINT,
            access_key=settings.MINIO_ACCESS_KEY,
            secret_key=settings.MINIO_SECRET_KEY,
            secure=settings.MINIO_SECURE
        )
        
        # 1. Check if server is reachable
        try:
            client.list_buckets()
            print("[OK] MinIO server is reachable.")
        except Exception as e:
            print(f"[FAIL] Cannot reach MinIO server: {e}")
            return

        # 2. Check Bucket
        if client.bucket_exists(settings.MINIO_BUCKET):
            print(f"[OK] Bucket '{settings.MINIO_BUCKET}' exists.")
        else:
            print(f"[WARN] Bucket '{settings.MINIO_BUCKET}' does not exist. Attempting to create...")
            client.make_bucket(settings.MINIO_BUCKET)
            print(f"[OK] Bucket created.")

        # 3. Check CORS
        # MinIO python client might not have direct method for CORS easily exposed or it's just set_bucket_cors?
        # Let's try to get it.
        # Actually, standard S3 client uses get_bucket_cors. MinIO client doesn't always expose it directly in the same way?
        # Let's skip complex CORS check via code for a moment and test basic upload.
        
        # 4. Test Presigned URL generation
        try:
            url = client.presigned_put_object(settings.MINIO_BUCKET, "test_check.txt")
            print(f"[OK] Presigned URL generated: {url}")
            
            # 5. Test Upload using the URL (simulate frontend)
            print("Attempting to upload via presigned URL...")
            resp = requests.put(url, data="test content")
            if resp.status_code >= 200 and resp.status_code < 300:
                print("[OK] Upload via presigned URL successful.")
            else:
                print(f"[FAIL] Upload via presigned URL failed. Status: {resp.status_code}, Response: {resp.text}")
                
        except Exception as e:
            print(f"[FAIL] Presigned URL test failed: {e}")

    except Exception as e:
        print(f"[FAIL] Unexpected error: {e}")

if __name__ == "__main__":
    check_minio()
