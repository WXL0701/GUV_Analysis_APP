import inspect
from minio import Minio

print(inspect.signature(Minio.set_bucket_cors))
print(Minio.set_bucket_cors.__doc__)
