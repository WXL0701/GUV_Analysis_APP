from minio import Minio
print([m for m in dir(Minio) if 'cors' in m.lower()])
