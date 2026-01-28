import boto3
from botocore.client import Config
import os
import sys

# Add backend to path
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.core.config import settings

def configure_cors():
    print(f"Configuring CORS for bucket: {settings.MINIO_BUCKET} on {settings.MINIO_ENDPOINT}")
    
    # Boto3 needs a slightly different endpoint format (http://...)
    endpoint_url = settings.MINIO_ENDPOINT
    if not endpoint_url.startswith("http"):
        endpoint_url = f"http://{endpoint_url}"
        
    s3 = boto3.client('s3',
                      endpoint_url=endpoint_url,
                      aws_access_key_id=settings.MINIO_ACCESS_KEY,
                      aws_secret_access_key=settings.MINIO_SECRET_KEY,
                      config=Config(signature_version='s3v4'),
                      region_name='us-east-1') # MinIO default region
    
    cors_configuration = {
        'CORSRules': [{
            'AllowedHeaders': ['*'],
            'AllowedMethods': ['GET', 'PUT', 'POST', 'DELETE'],
            'AllowedOrigins': ['*']
        }]
    }
    
    try:
        s3.put_bucket_cors(Bucket=settings.MINIO_BUCKET, CORSConfiguration=cors_configuration)
        print("[OK] CORS configuration set successfully.")
        
        # Verify
        response = s3.get_bucket_cors(Bucket=settings.MINIO_BUCKET)
        print("Current CORS Rules:", response['CORSRules'])
        
    except Exception as e:
        print(f"[FAIL] Failed to set CORS: {e}")

if __name__ == "__main__":
    configure_cors()
