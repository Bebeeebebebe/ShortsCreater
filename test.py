import time
from PostByAccount import VideoPostRequest, VideoSideTexts, MultiPost
from AccountLogger import AccountLogger
from typing import Type, Optional
from g4f.client import Client
from g4f.Provider import BaseProvider
from gpt4all import GPT4All
import uuid
import os
import tempfile
import whisper
import argparse
import subprocess
import re
import asyncio
import datetime
from moviepy.editor import VideoFileClip
from dataclasses import dataclass
from SimpleGPT import SimpleGPT

# Ваши импорты и класс MultiPost должны быть уже здесь
def test_Posting():
    vidSide = VideoSideTexts(
        description="йцуйцуйцу",
        hashtags="#govno",
        music_author="машуля#mm⚜️",
        music_name="машуляmm"
    )
    requests = [
        VideoPostRequest(
            platform="TikTok",
            account_name="test",
            videos={"clip_01.mp4": vidSide}
        )
    ]

    multi = MultiPost(requests)

    multi.post_to_tiktok()
    input("Нажать для конца")

def test_logger():
    logger = AccountLogger("test", "TikTok")
    logger.run()


async def get_answer_gpt(
        message: str,
        promt: str,
        provider: Optional[Type[BaseProvider]] = None,
        retries: int = 3,
        timeout: int = 50,
        retry_delay: float = 2.0
) -> tuple[str, Optional[Type[BaseProvider]]]:

    def is_valid_timestamps_answer(text: str) -> bool:
        return bool(re.search(r'\d+:\d{2}-\d+:\d{2}', text))

    def is_g4f_ratelimit(e: Exception | None, text: str | None = None) -> bool:
        haystack = ""
        if e:
            haystack += str(e).lower()
        if text:
            haystack += text.lower()

        return any(k in haystack for k in (
            "rate limit",
            "ratelimit",
            "too many requests"
        ))

    content = (message + " " + promt).strip()
    attempt = 1
    provider_local = provider  # 🔑 локальная копия

    def _sync_gpt_call():
        client = Client(provider=provider_local) if provider_local else Client()

        response = client.chat.completions.create(
            model="gpt-4o-mini",
            messages=[{"role": "user", "content": content}],
            timeout=timeout
        )

        used_provider = getattr(response, "provider", None)
        answer = response.choices[0].message.content.strip().lower()

        return answer, used_provider

    while retries == -1 or attempt <= retries:
        try:
            answer_text, used_provider = await asyncio.to_thread(_sync_gpt_call)

            if not answer_text:
                raise ValueError("Пустой ответ от GPT")

            # 🚨 ВАЖНО: g4f rate limit — это текст
            if is_g4f_ratelimit(None, answer_text):
                raise RuntimeError("G4F rate limit detected")

            return answer_text, used_provider

        except Exception as e:
            print(
                f"⚠️ GPT ошибка (попытка {attempt}): "
                f"{type(e).__name__} | {e}"
            )

            # 🔥 КЛЮЧЕВОЙ МОМЕНТ
            if is_g4f_ratelimit(e):
                print("🔄 Rate limit → сбрасываю provider (g4f сам выберет следующий)")
                provider_local = None  # 💥 вот это решает проблему

            attempt += 1

            if retries != -1 and attempt > retries:
                break

            await asyncio.sleep(retry_delay)

    print("❌ GPT не ответил после всех попыток — использую 'no answer'")
    return "no answer", None

        #======================================================================

#test_logger()
#test_Posting()
async def main():
    #async def generate(local_model,model_path):
    #    return await asyncio.to_thread(
    #        local_model.generate,
    #        "Выбери 1 или 2"
    #    )
    #answer = await get_answer_gpt("Дай ответ 1 или 2", "", retries=-1)
    #print(answer)

    import os
    print(os.cpu_count())

if __name__ == "__main__":
    asyncio.run(main())
