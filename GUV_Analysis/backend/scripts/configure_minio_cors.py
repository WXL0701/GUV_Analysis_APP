import sys
import os
import time

# Add backend to path
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.core.config import settings
from minio import Minio
from minio.cors import CorsConfig
from minio.commonconfig import ENABLED

def configure_minio():
    print(f"Configuring MinIO for bucket: {settings.MINIO_BUCKET}")
    
    client = Minio(
        settings.MINIO_ENDPOINT,
        access_key=settings.MINIO_ACCESS_KEY,
        secret_key=settings.MINIO_SECRET_KEY,
        secure=settings.MINIO_SECURE
    )
    
    # Check if bucket exists
    if not client.bucket_exists(settings.MINIO_BUCKET):
        print(f"Bucket {settings.MINIO_BUCKET} does not exist. Creating...")
        client.make_bucket(settings.MINIO_BUCKET)
    
    print("Setting CORS policy...")
    
    # We need to construct the CORS configuration manually as minio-py removed some helper classes or changed them in recent versions.
    # Actually, minio-py 7.x+ uses client.set_bucket_cors(bucket_name, cors_config)
    # But we need to define the structure correctly.
    # It seems minio library expects a structure.
    
    # Let's try setting it directly if the library supports it.
    # The 'minio' library documentation suggests checking implementation details or using xml.
    # Wait, checking available methods on client object via dir() might help if I was interactive, 
    # but I'll trust the common approach or just use s3cmd if installed. 
    # Since I don't have s3cmd, I'll try the python way.
    
    # Simplified approach: Use a public read-write policy? No, CORS is different from policy.
    # MinIO allows setting CORS.
    
    try:
        # Construct CORS config
        # Note: Depending on minio version, this might vary.
        # Let's try the dict/xml approach or look for set_bucket_cors method signature.
        # Actually, let's use a raw command via 'mc' if available? No.
        
        # Python MinIO Client set_bucket_cors takes a structure.
        # Let's assume we can use the default 'set_bucket_cors' with a dictionary or object.
        # However, `minio` library usually requires `minio.cors.CorsConfig`.
        
        # Let's try to verify if we can set it.
        # Reference: https://github.com/minio/minio-py/blob/master/examples/cors_set.py
        
        # Example from docs:
        # config = CorsConfig([
        #    CorsRule(
        #        allowed_origins=["*"],
        #        allowed_methods=["GET", "PUT", "POST", "DELETE", "HEAD"],
        #        allowed_headers=["*"],
        #        expose_headers=["ETag"],
        #        max_age_seconds=3000,
        #    ),
        # ])
        
        # I need to import CorsRule.
        from minio.cors import CorsConfig, CorsRule
        
        config = CorsConfig([
            CorsRule(
                allowed_origins=["*"],
                allowed_methods=["GET", "PUT", "POST", "DELETE", "HEAD"],
                allowed_headers=["*"],
                expose_headers=["ETag", "x-amz-server-side-encryption", "x-amz-request-id", "x-amz-id-2"],
                max_age_seconds=3000,
            ),
        ])
        
        client.set_bucket_cors(settings.MINIO_BUCKET, config)
        print("[OK] CORS policy set successfully.")
        
    except Exception as e:
        print(f"[FAIL] Failed to set CORS: {e}")
        # Print help
        print("Please check if your MinIO version supports CORS configuration via API.")

if __name__ == "__main__":
    configure_minio()
