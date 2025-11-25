#!/usr/bin/env python3
import os
import boto3
from datetime import datetime
import shutil
import logging

# Настройка логирования
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# Настройки из переменных окружения
S3_ENDPOINT_URL = os.getenv('S3_ENDPOINT_URL')
S3_BUCKET = os.getenv('S3_BUCKET_NAME')
S3_REGION = os.getenv('S3_REGION', 'ru-1')
S3_ACCESS_KEY = os.getenv('S3_ACCESS_KEY')
S3_SECRET_KEY = os.getenv('S3_SECRET_KEY')
DB_PATH = os.getenv('DATABASE_PATH', '/app/data/database.db')
BACKUP_RETENTION_DAYS = int(os.getenv('BACKUP_RETENTION_DAYS', '30'))

def backup_database():
    """Создание резервной копии базы данных и загрузка в S3"""
    try:
        # Проверка наличия базы данных
        if not os.path.exists(DB_PATH):
            logger.error(f"Database file not found: {DB_PATH}")
            return False

        # Создание временной копии
        timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
        temp_backup = f"/tmp/database_backup_{timestamp}.db"

        logger.info(f"Creating backup: {temp_backup}")
        shutil.copy2(DB_PATH, temp_backup)

        # Получаем размер файла
        file_size = os.path.getsize(temp_backup)
        logger.info(f"Backup file size: {file_size} bytes ({file_size / 1024 / 1024:.2f} MB)")

        # Подключение к S3-совместимому хранилищу
        s3_client = boto3.client(
            's3',
            endpoint_url=S3_ENDPOINT_URL,
            region_name=S3_REGION,
            aws_access_key_id=S3_ACCESS_KEY,
            aws_secret_access_key=S3_SECRET_KEY
        )

        # Загрузка в S3
        s3_key = f"uk_lubdom_bot/database_{timestamp}.db"
        logger.info(f"Uploading to S3: {S3_ENDPOINT_URL}/{S3_BUCKET}/{s3_key}")

        s3_client.upload_file(
            temp_backup,
            S3_BUCKET,
            s3_key,
            ExtraArgs={
                'Metadata': {
                    'backup-date': datetime.now().isoformat(),
                    'source': 'auto-backup',
                    'size': str(file_size)
                }
            }
        )

        logger.info(f"✅ Backup uploaded successfully: {s3_key}")

        # Удаление временного файла
        os.remove(temp_backup)
        logger.info("Temporary backup file removed")

        # Очистка старых бэкапов
        cleanup_old_backups(s3_client)

        return True

    except Exception as e:
        logger.error(f"❌ Backup failed: {e}", exc_info=True)
        return False


def cleanup_old_backups(s3_client):
    """Удаление бэкапов старше BACKUP_RETENTION_DAYS"""
    try:
        from datetime import timedelta

        logger.info(f"Cleaning up backups older than {BACKUP_RETENTION_DAYS} days")

        response = s3_client.list_objects_v2(
            Bucket=S3_BUCKET,
            Prefix='backups/'
        )

        if 'Contents' not in response:
            logger.info("No backups found for cleanup")
            return

        cutoff_date = datetime.now() - timedelta(days=BACKUP_RETENTION_DAYS)
        deleted_count = 0

        for obj in response['Contents']:
            if obj['LastModified'].replace(tzinfo=None) < cutoff_date:
                logger.info(f"Deleting old backup: {obj['Key']} (modified: {obj['LastModified']})")
                s3_client.delete_object(Bucket=S3_BUCKET, Key=obj['Key'])
                deleted_count += 1

        if deleted_count > 0:
            logger.info(f"✅ Deleted {deleted_count} old backups")
        else:
            logger.info("No old backups to delete")

    except Exception as e:
        logger.error(f"Cleanup failed: {e}", exc_info=True)


if __name__ == "__main__":
    logger.info("=" * 50)
    logger.info("Starting database backup process")
    logger.info(f"S3 Endpoint: {S3_ENDPOINT_URL}")
    logger.info(f"S3 Bucket: {S3_BUCKET}")
    logger.info(f"S3 Region: {S3_REGION}")
    logger.info(f"Database Path: {DB_PATH}")
    logger.info(f"Retention Days: {BACKUP_RETENTION_DAYS}")
    logger.info("=" * 50)

    success = backup_database()

    if success:
        logger.info("✅ Backup completed successfully")
        exit(0)
    else:
        logger.error("❌ Backup failed")
        exit(1)