import sys
import os
from minio import Minio
from minio.error import S3Error

def setup_remote_minio():
    endpoint = "10.30.70.108:9000"
    access_key = "keyuan"
    secret_key = "&keyuan@132"
    bucket_name = "lab-analysis"
    secure = False # HTTP based on curl result

    print(f"Connecting to MinIO at {endpoint}...")
    
    try:
        client = Minio(
            endpoint,
            access_key=access_key,
            secret_key=secret_key,
            secure=secure
        )
        
        # Check connection by listing buckets
        print("Checking connection...")
        buckets = client.list_buckets()
        print(f"Connection successful. Found {len(buckets)} buckets.")
        
        # Check/Create Bucket
        if client.bucket_exists(bucket_name):
            print(f"Bucket '{bucket_name}' already exists.")
        else:
            print(f"Bucket '{bucket_name}' does not exist. Creating...")
            client.make_bucket(bucket_name)
            print(f"Bucket '{bucket_name}' created successfully.")
            
        print("Skipping CORS setup (not supported in this MinIO client version).")
        return True

    except S3Error as e:
        print(f"MinIO Error: {e}")
        return False
    except Exception as e:
        print(f"General Error: {e}")
        return False

if __name__ == "__main__":
    if setup_remote_minio():
        sys.exit(0)
    else:
        sys.exit(1)
