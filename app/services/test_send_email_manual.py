import asyncio

from app.services.email_service import send_email

async def main():
    ok = await send_email(
        to="risenbass@yandex.ru",
        subject="Тестовое письмо",
        body="Привет! Это тест из бота.",
        # attachment_path="/path/to/file.txt",  # можно проверить и вложение
    )
    print("RESULT:", ok)

if __name__ == "__main__":
    asyncio.run(main())
