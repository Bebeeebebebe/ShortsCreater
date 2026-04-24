import uuid
import os
import tempfile
import argparse
import subprocess
import re
import asyncio
import datetime
from moviepy.editor import VideoFileClip
from dataclasses import dataclass

from typing import Type, Optional

from SimpleGPT import SimpleGPT
from pathlib import Path

from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.remote.webelement import WebElement
from selenium.webdriver.support import expected_conditions as EC
import time
#Нужно переписать функции по дроблению чанков
#и оставить только ту, что дробит на маленькие
# отрезки и собирает по контексту
from faster_whisper import WhisperModel
from typing import Type, Optional, Literal


WHISPER_MODEL = None
ShortsMode = Literal["TranscribeBasedShorts", "SimpleIntervalShorts"]

def get_whisper(model_name="medium"):
    global WHISPER_MODEL
    if WHISPER_MODEL is None:
        print(f"🔊 Загружаю Whisper модель: {model_name}")

        total_cores = os.cpu_count() or 4
        whisper_threads = max(1, total_cores - 3)  # оставляем 3 ядра системе
        print(f"🧵 CPU ядер: {total_cores}, используем для Whisper: {whisper_threads}")

        WHISPER_MODEL = WhisperModel(model_name, device="cpu", compute_type="int8", cpu_threads=whisper_threads)
    return WHISPER_MODEL

def calc_position(
    base_size: tuple[int, int],
    banner_size: tuple[int, int],
    anchor: str,
    offset: tuple[int, int]
):
    bw, bh = base_size
    iw, ih = banner_size
    ox, oy = offset

    anchors = {
        "top-left": (0, 0),
        "top-center": ((bw - iw) // 2, 0),
        "top-right": (bw - iw, 0),

        "center-left": (0, (bh - ih) // 2),
        "center": ((bw - iw) // 2, (bh - ih) // 2),
        "center-right": (bw - iw, (bh - ih) // 2),

        "bottom-left": (0, bh - ih),
        "bottom-center": ((bw - iw) // 2, bh - ih),
        "bottom-right": (bw - iw, bh - ih),
    }

    x, y = anchors[anchor]
    return x + ox, y + oy

def get_output_path(input_video):
    base, ext = os.path.splitext(input_video)
    counter = 0
    while True:
        if counter == 0:
            output_video = f"{base}_subtitle{ext}"
        else:
            output_video = f"{base}_subtitle_{counter}{ext}"
        if not os.path.exists(output_video):
            return output_video
        counter += 1


@dataclass
class SubtitleStyle:
    font: str = "DejaVu Sans"
    fontsize: int = 48
    primary_color: str = "&H00FFFFFF&"   # BGR + альфа (&HAABBGGRR)
    outline_color: str = "&H00000000&"
    outline_width: float = 3.0
    shadow_width: float = 0.0
    bold: bool = False
    italic: bool = False
    alignment: int = 2                 # 2 = по центру снизу
    margin_v: int = 60                 # отступ от низа
    margin_l: int = 30
    margin_r: int = 30
    fade_in: int = 0                   # миллисекунды
    fade_out: int = 0

class ShortsCreater:
    # =================Конструктор (вызывается при создании объекта)==========
    def __init__(self, video_path: str, output_dir: str,
                 whisper_language: str = "auto",
                 clip_mode: str = "blur",
                 min_duration: float = 40.0,
                 max_duration: float = 120.0,
                 mode: ShortsMode = "SimpleIntervalShorts",
                 interval: float = 60.0,
                 whisper_model: str = "base",  # перемещён в конец, теперь опциональный
                 max_workers: int = 4,
                 ):
        self.video_path = video_path
        self._whisper_model_name = whisper_model
        self._whisper = None
        self.whisper_language = whisper_language
        self.output_dir = output_dir
        self.clip_mode = clip_mode
        self.min_duration = min_duration
        self.max_duration = max_duration
        self.gpt_queue = None
        self.gpt_workers = []
        self.gpt_retry_attempts = -1  # сколько попыток (−1 = бесконечно)
        self.gpt_retry_delay = 4  # базовая задержка между попытками
        self.gpt_retry_backoff = 1  # множитель увеличения задержки
        self.gpt_retry_on_empty = True  # ретраить ли при пустом ответе
        self.mode = mode
        self.interval = interval
        self.max_workers = max_workers

    @property
    def whisper(self):
        if self._whisper is None:
            self._whisper = get_whisper(self._whisper_model_name)
        return self._whisper
    #===== Вспомогательные функции, написаные для работы остальных =========
    def sec_to_time(self, seconds: float) -> str:
        """Преобразует секунды в формат mm:ss"""
        m = int(seconds // 60)
        s = int(seconds % 60)
        return f"{m}:{s:02d}"

    def get_video_duration_ffprobe(self) -> float:
        cmd = [
            "ffprobe", "-v", "error",
            "-show_entries", "format=duration",
            "-of", "default=noprint_wrappers=1:nokey=1",
            self.video_path
        ]
        result = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
        if result.returncode != 0:
            raise RuntimeError(f"ffprobe error: {result.stderr.strip()}")
        return float(result.stdout.strip())

    async def _clip_worker(
            self,
            queue: asyncio.Queue,
            worker_id: int
    ):
        """Воркер берёт (start, end, output_path) из очереди и нарезает."""
        while True:
            item = await queue.get()
            if item is None:  # сигнал завершения
                queue.task_done()
                break
            start, end, output_path = item
            try:
                print(f"[worker-{worker_id}] {start:.2f}–{end:.2f} → {output_path}")
                await asyncio.to_thread(
                    self._export_single_clip, start, end, output_path
                )
            except Exception as e:
                print(f"[worker-{worker_id}] ❌ Ошибка: {e}")
            finally:
                queue.task_done()


    async def export_video_clips_parallel(self, clips: list):
        """
        Экспортирует клипы параллельно через пул воркеров.
        clips: [{"start": float, "end": float, ...}, ...]
        """
        clips = [c for c in clips if (c["end"] - c["start"]) >= 1.0]
        if not clips:
            print("❌ Нет валидных клипов.")
            return

        if not self.output_dir or self.output_dir.strip() == "":
            date_str = datetime.datetime.now().strftime("%d_%m_%Y")
            self.output_dir = os.path.join(os.getcwd(), f"clips_{date_str}")
        os.makedirs(self.output_dir, exist_ok=True)

        queue: asyncio.Queue = asyncio.Queue()

        # Кладём задачи в очередь
        for idx, clip in enumerate(clips, 1):
            output_path = os.path.join(self.output_dir, f"clip_{idx:02d}.mp4")
            await queue.put((clip["start"], clip["end"], output_path))

        # Кладём стоп-сигналы
        for _ in range(self.max_workers):
            await queue.put(None)

        # Запускаем воркеров
        workers = [
            asyncio.create_task(self._clip_worker(queue, i))
            for i in range(self.max_workers)
        ]
        await queue.join()
        await asyncio.gather(*workers)
        print(f"✅ Все клипы экспортированы ({len(clips)} шт.)")

    def create_simple_clips(self):
        asyncio.run(self._create_simple_clips_async())

    async def _create_simple_clips_async(self):
        if not os.path.isfile(self.video_path):
            raise FileNotFoundError(f"Файл не найден: {self.video_path}")

        duration = self.get_video_duration_ffprobe()
        clips = [
            {"start": s, "end": e}
            for s, e in self.split_interval(0, duration, self.interval)
            if (e - s) >= 1.0
        ]
        if not clips:
            print("❌ Нет валидных клипов.")
            return

        if not self.output_dir or self.output_dir.strip() == "":
            date_str = datetime.datetime.now().strftime("%d_%m_%Y")
            self.output_dir = os.path.join(os.getcwd(), f"clips_{date_str}")
        os.makedirs(self.output_dir, exist_ok=True)

        await self.export_video_clips_parallel(clips)

    def _export_single_clip(self, start: float, end: float, output_path: str):
        threads_per_worker = str(max(1, os.cpu_count() // self.max_workers))

        base_cmd = [
            "ffmpeg", "-y",
            "-i", self.video_path,
            "-ss", str(start),
            "-to", str(end),
        ]

        if self.clip_mode == "letterbox":
            vf = (
                "scale=1080:1920:force_original_aspect_ratio=decrease,"
                "pad=1080:1920:(ow-iw)/2:(oh-ih)/2"
            )
            cmd = base_cmd + [
                "-vf", vf,
                "-map", "0:v",
                "-map", "0:a?",
                "-c:v", "libx264",
                "-preset", "veryfast",
                "-crf", "18",
                "-c:a", "aac",
                "-b:a", "128k",
                "-threads", threads_per_worker,
                output_path
            ]
        elif self.clip_mode == "blur":
            filter_complex = (
                "[0:v]"
                "scale=1080:1920:force_original_aspect_ratio=increase,"
                "crop=1080:1920,"
                "boxblur=40:5"
                "[bg];"
                "[0:v]"
                "scale=1080:1920:force_original_aspect_ratio=decrease"
                "[fg];"
                "[bg][fg]"
                "overlay=(W-w)/2:(H-h)/2"
                "[outv]"
            )
            cmd = base_cmd + [
                "-filter_complex", filter_complex,
                "-map", "[outv]",
                "-map", "0:a?",
                "-c:v", "libx264",
                "-preset", "veryfast",
                "-crf", "18",
                "-c:a", "aac",
                "-b:a", "128k",
                "-threads", threads_per_worker,
                output_path
            ]
        else:
            raise ValueError(f"Неизвестный clip_mode: {self.clip_mode}")

        subprocess.run(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)

    def init_gpt_drivers(self, account_paths: list[str]):
        """
        Инициализирует GPT драйверы на основе списка аккаунтов (.pkl).

        1 аккаунт = 1 драйвер.
        Если аккаунтов больше/меньше — сообщает об этом.
        """

        self.gpt_drivers = []

        if not account_paths:
            raise ValueError("Список аккаунтов пуст")

        total_requested = len(account_paths)
        successfully_initialized = 0
        failed_accounts = []

        for idx, path_str in enumerate(account_paths, start=1):

            account_path = Path(path_str)

            if not account_path.exists():
                print(f"❌ Аккаунт не найден: {path_str}")
                failed_accounts.append(path_str)
                continue

            try:
                print(f"🚀 Инициализация GPT driver{idx} | {path_str}")

                gpt = SimpleGPT(
                    session_path=str(account_path)
                )

                # Ждём загрузку страницы
                WebDriverWait(gpt.driver, 30).until(
                    lambda d: d.find_element(By.ID, "prompt-textarea")
                )
                time.sleep(7)

                project_name = f"driver{idx}"

                folder = gpt.find_project_by_name(project_name)

                if folder is None:
                    print(f"📁 Создаю проект {project_name}")
                    created = gpt.create_folder_for_asking(project_name)
                    time.sleep(2)
                    WebDriverWait(gpt.driver, 60).until(
                        lambda d: d.find_element(By.ID, "prompt-textarea")
                    )

                    if not created:
                        raise RuntimeError(f"Не удалось создать проект {project_name}")
                else:
                    print(f"📂 Проект {project_name} уже существует")

                time.sleep(2)
                # Открываем проект
                WebDriverWait(gpt.driver, 30).until(
                    lambda d: d.find_element(By.ID, "prompt-textarea")
                )

                project = gpt.find_project_by_name(project_name)

                if project:
                    project.click()

                self.gpt_drivers.append(gpt)
                successfully_initialized += 1

            except Exception as e:
                print(f"❌ Ошибка при инициализации {path_str}: {e}")
                failed_accounts.append(path_str)

        # 📊 Итоговая статистика
        print("\n========== GPT INIT SUMMARY ==========")
        print(f"Запрошено аккаунтов: {total_requested}")
        print(f"Успешно инициализировано: {successfully_initialized}")
        print(f"Не удалось инициализировать: {len(failed_accounts)}")

        if failed_accounts:
            print("Список проблемных аккаунтов:")
            for acc in failed_accounts:
                print(f" - {acc}")

        if successfully_initialized == 0:
            raise RuntimeError("❌ Не удалось инициализировать ни одного GPT драйвера")

        print("======================================\n")
    def split_interval(self, start, end, step):
        segments = []
        cur = start

        while cur < end:
            next_end = min(cur + step, end)
            segments.append((cur, next_end))
            cur = next_end

        return segments

    def get_answer_gpt(
            self,
            gpt: SimpleGPT,
            message: str,
            promt: str,
            project_name: str = None
    ) -> str:

        content = (message + " " + promt).strip()

        attempts = 0
        delay = self.gpt_retry_delay

        while True:

            try:
                if project_name is not None:

                    folder = gpt.find_project_by_name(project_name)

                    if folder is None:
                        print(f"📁 Проект '{project_name}' не найден → создаю")
                        created = gpt.create_folder_for_asking(project_name)
                        time.sleep(2)
                        if not created:
                            raise RuntimeError("Не удалось создать проект")


                        folder = gpt.find_project_by_name(project_name)

                        if folder is None:
                            raise RuntimeError("Проект создан, но не найден")

                    folder.click()

                gpt.human_pause(1.0, 2.0)

                response = gpt.get_answer(content)

                # 🔹 Проверка пустого ответа
                if not response or not response.get("text"):

                    if not self.gpt_retry_on_empty:
                        raise ValueError("Пустой ответ от GPT")

                    raise RuntimeError("GPT вернул пустой ответ")

                return response["text"].strip()

            except Exception as e:

                attempts += 1

                # 🔥 Если лимит попыток достигнут
                if self.gpt_retry_attempts != -1 and attempts > self.gpt_retry_attempts:
                    print(f"❌ GPT окончательно упал после {attempts} попыток")
                    raise e

                print(
                    f"⚠️ GPT ошибка: {e} | попытка {attempts} | "
                    f"следующая через {delay:.1f} сек"
                )

                time.sleep(delay)

                # увеличиваем задержку (экспоненциальный backoff)
                delay *= self.gpt_retry_backoff

        #======================================================================


    def build_chunks_from_segments(self, segments, max_len=600):
        chunks = []

        buffer = []
        chunk_start = None

        for seg in segments:
            if not buffer:
                chunk_start = seg["start"]

            buffer.append(seg)

            duration = seg["end"] - chunk_start

            if duration >= max_len:
                chunks.append({
                    "start": chunk_start,
                    "end": seg["end"],
                    "text": " ".join(s["text"] for s in buffer)
                })
                buffer = []
                chunk_start = None

        # хвост
        if buffer:
            chunks.append({
                "start": chunk_start,
                "end": buffer[-1]["end"],
                "text": " ".join(s["text"] for s in buffer)
            })

        return chunks
    #===== Основные функции ====================================================

    async def start_gpt_workers(self):
        """
        Создаёт воркеры по количеству драйверов.
        Каждый воркер работает со своим GPT.
        """

        self.gpt_queue = asyncio.Queue()

        for idx, gpt in enumerate(self.gpt_drivers):
            worker = asyncio.create_task(
                self._gpt_worker(gpt, f"driver{idx + 1}")
            )
            self.gpt_workers.append(worker)

    async def _gpt_worker(self, gpt: SimpleGPT, project_name: str):
        """
        Один воркер = один драйвер.
        Берёт задачи из очереди и выполняет их.
        """

        while True:
            task = await self.gpt_queue.get()

            if task is None:  # сигнал завершения
                break

            prompt, future = task

            try:
                # Selenium блокирует поток → выносим в thread
                result = await asyncio.to_thread(
                    self.get_answer_gpt,
                    gpt,
                    "",
                    prompt,
                    project_name
                )

                future.set_result(result)

            except Exception as e:
                future.set_exception(e)

            finally:
                self.gpt_queue.task_done()

    async def ask_gpt(self, prompt: str):
        """
        Отправляет задачу в очередь.
        Возвращает awaitable.
        """

        loop = asyncio.get_running_loop()
        future = loop.create_future()

        await self.gpt_queue.put((prompt, future))

        return await future

    async def stop_gpt_workers(self):
        for _ in self.gpt_workers:
            await self.gpt_queue.put(None)

        await asyncio.gather(*self.gpt_workers)




    def whisper_transcribe_safe(self, audio_path: str, **kwargs):
        """
        Безопасный вызов Whisper:
        - если язык None / '' / 'auto' → НЕ передаём language
        """
        segments_gen, info = self.whisper.transcribe(audio_path, **kwargs)
        segments = [
            {
                "start": round(seg.start, 2),
                "end": round(seg.end, 2),
                "text": seg.text.strip()
            }
            for seg in segments_gen
        ]
        return {
            "text": " ".join(s["text"] for s in segments),
            "segments": segments
        }
    def transcribe_video_with_timestamps(self):
        """
        Принимает путь к видео, извлекает аудио (ffmpeg),
        передаёт его в Whisper и возвращает:
          - полный текст
          - список сегментов с таймкодами: [{start, end, text}, ...]
        """

        if not os.path.isfile(self.video_path):
            raise FileNotFoundError(f"Файл не найден: {self.video_path}")

        tmp_dir = tempfile.mkdtemp(prefix="vid2wh_")
        wav_path = os.path.join(tmp_dir, "audio.wav")

        try:
            # Извлекаем аудио из видео (16 кГц, моно)
            cmd = (
                f'ffmpeg -y -i "{self.video_path}" -vn '
                f'-acodec pcm_s16le -ar 16000 -ac 1 "{wav_path}"'
            )
            print("Извлекаю аудио с помощью ffmpeg...")
            rc = os.system(cmd)
            if rc != 0:
                raise RuntimeError("Ошибка при вызове ffmpeg — убедитесь, что ffmpeg установлен.")

            options = {}

            if self.whisper_language and self.whisper_language.lower() != "auto":
                options["language"] = self.whisper_language

            print("Транскрибирую аудио...")
            segments_gen, info = self.whisper.transcribe(wav_path, **options)
            print(f"✅ Генератор получен, язык: {info.language}, длительность: {info.duration}")

            segments = [
                {
                    "start": round(seg.start, 2),
                    "end": round(seg.end, 2),
                    "text": seg.text.strip()
                }
                for seg in segments_gen  # генератор, не словарь — поэтому seg.start а не seg["start"]
            ]
            full_text = " ".join(s["text"] for s in segments)

            video_duration = segments[-1]["end"] if segments else 0

            return {
                "text": full_text,
                "segments": segments,
                "duration": video_duration
            }

        finally:
            try:
                if os.path.exists(wav_path):
                    os.remove(wav_path)
                if os.path.isdir(tmp_dir):
                    os.rmdir(tmp_dir)
            except Exception:
                pass



    # ======= Основная функция =======
    async def process_video_in_chunks(self):
        """
        1. Транскрибирует видео через Whisper.
        2. Делит результат на чанки по 10 мин.
        3. Если встречается отрезок >10 мин — детально разбивает и пересобирает по контексту.
        4. Отправляет каждый чанк в GPT и возвращает результаты.
        """
        print("[Транскрипция делится на чанки]")
        transcription = self.transcribe_video_with_timestamps()
        segments = transcription["segments"]

        chunks = self.build_chunks_from_segments(segments)

        results = []
        for chunk in chunks:
            results.append({
                "start": chunk["start"],
                "end": chunk["end"],
                "transcription": chunk.get("text", "")
            })

        return results

    # ======= Вспомогательная функция =======
    async def analyze_and_rebuild_long_segment(self, start, end):
        """
        1. Делит большой сегмент на предотрезки по 2 минуты.
        2. Каждый предотрезок делит на мелкие куски по 10 секунд.
        3. Анализирует их при помощи GPT и собирает смысловые чанки.
        4. Возвращает список новых чанков.
        """

        total_duration = end - start
        refined_chunks = []

        # 1️⃣ Делим на предотрезки по 2 минуты
        pre_segments = [
            (start + i * 120, min(start + (i + 1) * 120, end))
            for i in range(int(total_duration // 120) + 1)
        ]

        for ps_start, ps_end in pre_segments:
            print(f"🔍 Анализирую предотрезок {round(ps_start, 1)}–{round(ps_end, 1)} сек...")

            # Делим на 20-секундные куски
            small_parts = [
                (ps_start + j * 20, min(ps_start + (j + 1) * 20, ps_end))
                for j in range(int((ps_end - ps_start) // 20) + 1)
            ]

            # === Whisper (без изменений) ===
            small_transcripts = []
            for sp_start, sp_end in small_parts:
                with tempfile.TemporaryDirectory() as tmpdir:
                    tmp_audio = os.path.join(tmpdir, "tmp.wav")
                    cmd = [
                        "ffmpeg", "-y",
                        "-ss", str(sp_start), "-to", str(sp_end),
                        "-i", self.video_path,
                        "-vn", "-acodec", "pcm_s16le", "-ar", "16000", "-ac", "1",
                        tmp_audio
                    ]
                    proc = subprocess.run(
                        cmd,
                        stdout=subprocess.DEVNULL,
                        stderr=subprocess.PIPE,
                        text=True
                    )

                    if proc.returncode != 0 or not os.path.exists(tmp_audio):
                        print("⚠️ ffmpeg не создал аудио:")
                        print(proc.stderr)
                        continue  # ПРОПУСКАЕМ этот кусок

                    result = self.whisper_transcribe_safe(
                        tmp_audio,
                        language=self.whisper_language
                    )

                    text = result.get("text", "").strip()
                    if text:
                        small_transcripts.append({
                            "start": sp_start,
                            "end": sp_end,
                            "text": text
                        })

            if len(small_transcripts) < 2:
                continue

            # 3️⃣ GPT — формируем ПАРАЛЛЕЛЬНЫЕ запросы
            gpt_tasks = []
            for i in range(len(small_transcripts) - 1):
                cur = small_transcripts[i]
                nxt = small_transcripts[i + 1]

                check_prompt = (
                    f"Эти два фрагмента транскрибции одного видео идут подряд:\n"
                    f"1️⃣ {cur['text']}\n"
                    f"2️⃣ {nxt['text']}\n\n"
                    f"Продолжают ли они один и тот же контекст, не обязательно строго, важно, чтобы было интересно и хоть немного в тему"
                    f"Ответь строго одним словом: 'yes' или 'no'."
                )

                gpt_tasks.append(
                    self.ask_gpt(check_prompt)
                )

            # 4️⃣ Ждём ВСЕ ответы GPT
            decisions = await asyncio.gather(*gpt_tasks, return_exceptions=True)

            # 5️⃣ Последовательно собираем чанки (логика сохранена)
            merged = []
            buffer_text = []
            buffer_start = small_transcripts[0]["start"]

            for i, decision in enumerate(decisions):
                # 🔥 ВСТАВИТЬ СЮДА
                if isinstance(decision, Exception):
                    print(f"⚠️ GPT ошибка в паре {i}: {decision}")
                    continue
                answer = decision

                cur = small_transcripts[i]
                nxt = small_transcripts[i + 1]

                buffer_text.append(cur["text"])

                if "no" in answer.lower():
                    merged.append({
                        "start": buffer_start,
                        "end": cur["end"],
                        "transcription": " ".join(buffer_text).strip()
                    })
                    buffer_text = []
                    buffer_start = nxt["start"]

            # хвост
            if buffer_text:
                merged.append({
                    "start": buffer_start,
                    "end": small_transcripts[-1]["end"],
                    "transcription": " ".join(buffer_text).strip()
                })

            refined_chunks.extend(merged)

        return refined_chunks

    def refine_phrase_timing(self, phrase: str, segment_threshold: float = 30.0):
        """
        Находит фразу в видео и, если исходный сегмент длиннее segment_threshold секунд,
        уточняет тайминг, прогоняя только этот отрезок заново через Whisper.
        """
        result = self.whisper_transcribe_safe(self.video_path, language=self.whisper_language)
        phrase_lower = phrase.lower()

        # --- Поиск фразы среди сегментов ---
        for seg in result["segments"]:
            start, end, text = seg["start"], seg["end"], seg["text"]

            if phrase_lower in text.lower():
                print(f"Фраза найдена в сегменте {round(start, 2)}–{round(end, 2)} сек")

                # Если сегмент короткий — возвращаем как есть
                if (end - start) <= segment_threshold:
                    return {"start": round(start, 2), "end": round(end, 2), "text": text}

                # --- Если сегмент слишком длинный: уточняем ---
                print(f"Сегмент длинный ({round(end - start, 1)} сек). Уточняю тайминги...")

                with tempfile.TemporaryDirectory() as tmpdir:
                    subclip_path = os.path.join(tmpdir, "subclip.wav")

                    # Вырезаем аудио этого сегмента через ffmpeg
                    cmd = [
                        "ffmpeg", "-y",
                        "-ss", str(start),
                        "-to", str(end),
                        "-i", self.video_path,
                        "-vn", "-acodec", "pcm_s16le", "-ar", "16000", "-ac", "1",
                        subclip_path
                    ]
                    subprocess.run(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)

                    # Прогоняем только этот кусок заново
                    refined = self.whisper_transcribe_safe(subclip_path, language=self.whisper_language, word_timestamps=True)

                    # --- Поиск фразы в уточнённом отрезке ---
                    for subseg in refined.get("segments", []):
                        if phrase_lower in subseg["text"].lower():
                            return {
                                "start": round(start + subseg["start"], 2),  # смещение относительно оригинала
                                "end": round(start + subseg["end"], 2),
                                "text": subseg["text"]
                            }

                print("Не удалось уточнить тайминг — возвращаю грубую оценку.")
                return {"start": round(start, 2), "end": round(end, 2), "text": text}

        return None

    async def refine_chunks_by_duration(self, chunks: list):
        """
        Разбивает длинные чанки (более 2 минут) на более короткие (вводимые данные),
        используя ту же стратегию, что и analyze_and_rebuild_long_segment().
        """
        print("[Чанки делятся на чанки]")
        refined_result = []

        for ch in chunks:
            start, end = ch["start"], ch["end"]
            duration = end - start

            if duration <= self.max_duration:
                # если чанк уже короткий — оставляем
                refined_result.append(ch)
                continue

            print(f"🔧 Разбиваю длинный чанк ({round(duration, 1)} сек) на более короткие...")
            refined_subchunks = await self.analyze_and_rebuild_long_segment_custom(
                start=start,
                end=end,
                subchunk_len=int(self.max_duration),
                microchunk_len=int(self.min_duration / 4)  # например, для 40 сек → 10 сек
            )

            refined_result.extend(refined_subchunks)

        return refined_result

    async def analyze_and_rebuild_long_segment_custom(
            self,
            start,
            end,
            subchunk_len=300,
            microchunk_len=20
    ):
        """
        Более гибкая версия analyze_and_rebuild_long_segment:
        - делит на subchunk_len (по умолчанию 2 минуты),
        - внутри — на microchunk_len (по умолчанию 10 секунд).
        """

        total_duration = end - start
        refined_chunks = []

        # 1️⃣ Делим на subchunks
        sub_segments = self.split_interval(start, end, subchunk_len)

        for ss_start, ss_end in sub_segments:
            print(f"🔹 Анализ субчанка {round(ss_start, 1)}–{round(ss_end, 1)} сек...")

            micro_segments = self.split_interval(
                ss_start,
                ss_end,
                microchunk_len
            )

            # === Whisper (без изменений) ===
            micro_transcripts = []
            for ms_start, ms_end in micro_segments:
                with tempfile.TemporaryDirectory() as tmpdir:
                    tmp_audio = os.path.join(tmpdir, "tmp.wav")
                    cmd = [
                        "ffmpeg", "-y",
                        "-ss", str(ms_start), "-to", str(ms_end),
                        "-i", self.video_path,
                        "-vn", "-acodec", "pcm_s16le", "-ar", "16000", "-ac", "1",
                        tmp_audio
                    ]
                    proc = subprocess.run(
                        cmd,
                        stdout=subprocess.DEVNULL,
                        stderr=subprocess.PIPE,
                        text=True
                    )

                    if proc.returncode != 0 or not os.path.exists(tmp_audio):
                        print("⚠️ ffmpeg не создал аудио:")
                        print(proc.stderr)
                        continue  # ПРОПУСКАЕМ этот кусок

                    result = self.whisper_transcribe_safe(
                        tmp_audio,
                        language=self.whisper_language
                    )

                    text = result.get("text", "").strip()
                    if text:
                        micro_transcripts.append({
                            "start": ms_start,
                            "end": ms_end,
                            "text": text
                        })

            if len(micro_transcripts) < 2:
                continue

            # === GPT: ПАРАЛЛЕЛЬНЫЕ ЗАПРОСЫ ===
            gpt_tasks = []
            for i in range(len(micro_transcripts) - 1):
                cur = micro_transcripts[i]
                nxt = micro_transcripts[i + 1]

                prompt = (
                    f"Эти два фрагмента транскрибции одного видео идут подряд:\n"
                    f"1️⃣ {cur['text']}\n"
                    f"2️⃣ {nxt['text']}\n\n"
                    f"Продолжают ли они один и тот же контекст, не обязательно строго, важно, чтобы было интересно и хоть немного в тему"
                    f"Ответь строго одним словом: 'yes' или 'no'."
                )

                gpt_tasks.append(
                    self.ask_gpt(prompt)
                )
            decisions = await asyncio.gather(*gpt_tasks, return_exceptions=True)

            # === Последовательная сборка (логика сохранена) ===
            merged = []
            buffer_text = []
            buffer_start = micro_transcripts[0]["start"]

            for i, decision in enumerate(decisions):
                if isinstance(decision, Exception):
                    print(f"⚠️ GPT ошибка в паре {i}: {decision}")
                    continue
                answer = decision
                cur = micro_transcripts[i]
                nxt = micro_transcripts[i + 1]

                buffer_text.append(cur["text"])

                if "no" in answer.lower():
                    merged.append({
                        "start": buffer_start,
                        "end": cur["end"],
                        "transcription": " ".join(buffer_text).strip()
                    })
                    buffer_text = []
                    buffer_start = nxt["start"]

            # хвост
            if buffer_text:
                merged.append({
                    "start": buffer_start,
                    "end": micro_transcripts[-1]["end"],
                    "transcription": " ".join(buffer_text).strip()
                })

            refined_chunks.extend(merged)

        return refined_chunks

    async def evaluate_top_moments(
            self,
            chunks: list,
            promt: str,
            group_size: int = 3
    ):
        def extract_intervals(gpt_response: str):
            """
            Возвращает список [(start_sec, end_sec), ...]
            или пустой список, если формат невалиден
            """
            matches = re.findall(r'(\d+):(\d+)-(\d+):(\d+)', gpt_response)

            intervals = []
            for sm, ss, em, es in matches:
                start = int(sm) * 60 + int(ss)
                end = int(em) * 60 + int(es)

                if end > start:  # защита от бреда
                    intervals.append((start, end))

            return intervals
        """
        Обрабатывает чанки группами (по group_size) и возвращает список
        отфильтрованных чанков на основе интересности.
        Каждый чанк: {"start": float, "end": float, "text": str}
        """
        print("[Выбираются лучшие видео]")

        filtered_chunks = []

        # === 1️⃣ Формируем группы заранее ===
        groups = [
            chunks[i:i + group_size]
            for i in range(0, len(chunks), group_size)
            if chunks[i:i + group_size]
        ]

        # === 2️⃣ Готовим GPT-запросы ===
        gpt_tasks = []
        group_payloads = []  # чтобы потом сопоставить ответ с группой

        for idx, group in enumerate(groups):
            group_text = "\n\n".join([
                f"Фрагмент [{self.sec_to_time(ch['start'])}-{self.sec_to_time(ch['end'])}] {ch.get('transcription', '')}"
                for ch in group
                if ch.get("start") is not None and ch.get("end") is not None
            ])
            print("=== GROUP SENT TO GPT ===")
            print(group_text)
            print(f"🧠 Планирую анализ группы чанков {idx + 1}–{idx + len(group)}...")

            gpt_tasks.append(
                self.ask_gpt(group_text+ "\n" + promt)
            )
            group_payloads.append(group)

        # === 3️⃣ Параллельно ждём ВСЕ ответы GPT ===
        gpt_responses = await asyncio.gather(*gpt_tasks)

        # === 4️⃣ Последовательно применяем ответы (логика сохранена) ===
        for group, decision in zip(group_payloads, gpt_responses):
            if not decision:
                continue

            gpt_response = decision
            gpt_response = gpt_response.strip()

            print("Gpt_response: ", gpt_response)

            # --- Парсим интервалы из ответа GPT ---
            intervals = extract_intervals(gpt_response)

            if not intervals:
                print("🚫 GPT ответ не содержит таймкодов — пропуск")
                continue
            for start_sec, end_sec in intervals:

                # Находим все чанки из группы, которые пересекаются с этим интервалом
                for ch in group:
                    if ch["end"] > start_sec and ch["start"] < end_sec:
                        filtered_chunks.append({
                            "start": max(ch["start"], start_sec),
                            "end": min(ch["end"], end_sec),
                            "text": ch.get("transcription", ch.get("text", ""))
                        })

        return filtered_chunks

    def export_video_clips(self, clips: list):
        """
        mode = 'letterbox'  — вписать с пустыми полями
        mode = 'blur'       — TikTok стиль с размытым фоном
        """

        # ===== SAFETY-ФИЛЬТР =====
        clips = [c for c in clips if (c["end"] - c["start"]) >= 1.0]
        if not clips:
            print("❌ Нет валидных клипов для экспорта.")
            return

        # ===== output_dir =====
        if not self.output_dir or self.output_dir.strip() == "":
            date_str = datetime.datetime.now().strftime("%d_%m_%Y")
            self.output_dir = os.path.join(os.getcwd(), f"clips_{date_str}")

        os.makedirs(self.output_dir, exist_ok=True)

        for idx, clip in enumerate(clips, 1):
            start = clip["start"]
            end = clip["end"]
            output_path = os.path.join(self.output_dir, f"clip_{idx:02d}.mp4")

            print(f"🎬 Экспорт клипа {idx}: {clip['start']:.2f}-{clip['end']:.2f} → {output_path}")
            self._export_single_clip(clip["start"], clip["end"], output_path)
    #======================================================================


    #=========== Сборка ======================
    async def create_shorts_from_video(self):
        if self.mode == "SimpleIntervalShorts":
            await asyncio.to_thread(self.create_simple_clips)
            return
        promt = """
       Тебе предоставленны отрезки видео с транскрипцией и тайм кодами, формата [минуты:секунды-минуты:секунды], тебе нужно определить самые интересные моменты и выписать их тайм коды в нужном формате. Ответ нужно прислать как последовательный список интервалов (топ), вот пример: 0:00-1:30, 2:11-3:00 и т.д. (это только пример формата вывода, ответ должен строится исключительно на предоставленных фрагментах) Вывод должен быть строго таким, так как он будет подаваться на вход другой программе и она принимает только такой формат
        """
        accounts = [
            "Accounts/chatgpt/1.pkl",
            "Accounts/chatgpt/2.pkl",
            "Accounts/chatgpt/3.pkl",
        ]

        self.init_gpt_drivers(accounts)

        await self.start_gpt_workers()

        result_chunks = await self.process_video_in_chunks()

        # Теперь дробим их на более мелкие
        refined_chunks = await  self.refine_chunks_by_duration(
            chunks=result_chunks,
        )

        moments = await self.evaluate_top_moments(refined_chunks, promt)

        self.export_video_clips(moments)


class VideoProcessing:
    def __init__(self):
       pass

    def get_video_duration(self, path: str) -> float:
        cmd = [
            "ffprobe",
            "-v", "error",
            "-show_entries", "format=duration",
            "-of", "default=noprint_wrappers=1:nokey=1",
            path
        ]

        result = subprocess.run(
            cmd,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True
        )

        return float(result.stdout.strip())

    def render_composition_ffmpeg(
            self,
            input_video: str,
            output_video: str,
            ass_path: str | None,
            overlays: list[dict],
            threads: int = 2,  # ← новый параметр
    ):
        # Получаем длительность основного видео
        duration = self.get_video_duration(input_video)

        inputs = ["-i", input_video]
        filter_parts = []

        last_video = "[0:v]"
        input_idx = 1

        # ================== 1️⃣ СУБТИТРЫ ==================
        if ass_path:
            filter_parts.append(f"{last_video}ass={ass_path}[v0]")
            last_video = "[v0]"

        # ================== 2️⃣ OVERLAYS ==================
        if overlays:
            for i, o in enumerate(overlays):

                if not os.path.exists(o["file_path"]):
                    print(f"⚠️ banner not found: {o['file_path']}")
                    continue

                if o.get("loop", False):
                    inputs += ["-stream_loop", "-1"]

                inputs += ["-i", o["file_path"]]

                start = o["start_ms"] / 1000
                end = o["end_ms"] / 1000 if o["end_ms"] and o["end_ms"] > o["start_ms"] else None

                enable = (
                    f"between(t,{start},{end})"
                    if end is not None
                    else f"gte(t,{start})"
                )

                # ✅ trim обрезает оверлей по длине основного видео — петля не выходит за границу
                chain = f"[{input_idx}:v]trim=duration={duration},setpts=PTS-STARTPTS"
                chain += f",scale=iw*{o['scale']}:ih*{o['scale']}"

                if o["fade_in"] > 0:
                    chain += f",fade=t=in:st={start}:d={o['fade_in'] / 1000}"

                if o["fade_out"] > 0 and end:
                    out_start = end - start - (o["fade_out"] / 1000)
                    chain += f",fade=t=out:st={out_start}:d={o['fade_out'] / 1000}"

                chain += f",format=rgba,colorchannelmixer=aa={o['opacity']}[b{i}]"
                filter_parts.append(chain)

                pos_map = {
                    "top-left": ("0", "0"),
                    "top-center": ("(W-w)/2", "0"),
                    "top-right": ("W-w", "0"),
                    "center-left": ("0", "(H-h)/2"),
                    "center": ("(W-w)/2", "(H-h)/2"),
                    "center-right": ("W-w", "(H-h)/2"),
                    "bottom-left": ("0", "H-h"),
                    "bottom-center": ("(W-w)/2", "H-h"),
                    "bottom-right": ("W-w", "H-h"),
                }

                x, y = pos_map[o["anchor"]]
                x = f"{x}+{o['offset_x']}"
                y = f"{y}+{o['offset_y']}"

                filter_parts.append(
                    f"{last_video}[b{i}]overlay="
                    f"x={x}:y={y}:enable='{enable}'[v{i + 1}]"
                )

                last_video = f"[v{i + 1}]"
                input_idx += 1

        # ================== 3️⃣ СБОРКА ==================
        filter_complex = ";".join(filter_parts) if filter_parts else None

        cmd = ["ffmpeg", "-y"]
        cmd += inputs
        # ✅ -t на уровне выхода — жёсткий стоп по длине исходника
        cmd += ["-t", str(duration)]

        if filter_complex:
            cmd += ["-filter_complex", filter_complex]
            cmd += ["-map", last_video]
        else:
            cmd += ["-map", "0:v"]

        cmd += ["-map", "0:a?"]

        cmd += [
            "-c:v", "libx264",
            "-preset", "veryfast",
            "-crf", "18",
            "-c:a", "aac",
            "-b:a", "128k",
            "-threads", str(threads),
            output_video
        ]

        print("🎬 Запуск рендера:")
        print(" ".join(cmd))

        subprocess.run(cmd, check=True)

    def add_banner_until_end(
            self,
            input_video: str,
            banner_path: str,
            output_path: str,
            anchor: str = "bottom-right",
            offset_x: int = 0,
            offset_y: int = 0,
            scale: float = 1.0,
            opacity: float = 1.0,
            start_ms: int = 0,
            fade_in: int = 0,
            threads: int = 2,
    ):
        # Получаем длительность видео
        cmd_probe = [
            "ffprobe", "-v", "error",
            "-show_entries", "format=duration",
            "-of", "default=noprint_wrappers=1:nokey=1",
            input_video
        ]
        result = subprocess.run(cmd_probe, stdout=subprocess.PIPE, text=True)
        duration = float(result.stdout.strip())

        start = start_ms / 1000
        enable = f"gte(t,{start})"

        # Фильтр для баннера
        banner_filter = f"scale=iw*{scale}:ih*{scale}"

        if fade_in > 0:
            banner_filter += f",fade=t=in:st={start}:d={fade_in / 1000}"

        banner_filter += f",format=rgba,colorchannelmixer=aa={opacity}"

        pos_map = {
            "top-left": ("0", "0"),
            "top-center": ("(W-w)/2", "0"),
            "top-right": ("W-w", "0"),
            "center-left": ("0", "(H-h)/2"),
            "center": ("(W-w)/2", "(H-h)/2"),
            "center-right": ("W-w", "(H-h)/2"),
            "bottom-left": ("0", "H-h"),
            "bottom-center": ("(W-w)/2", "H-h"),
            "bottom-right": ("W-w", "H-h"),
        }

        x_expr, y_expr = pos_map[anchor]
        x_expr = f"{x_expr}+{offset_x}"
        y_expr = f"{y_expr}+{offset_y}"

        filter_complex = (
            f"[1:v]{banner_filter}[b];"
            f"[0:v][b]overlay=x={x_expr}:y={y_expr}"
            f":enable='{enable}':shortest=1"
        )

        cmd = [
            "ffmpeg",
            "-y",
            "-i", input_video,
            "-stream_loop", "-1",  # 🔁 зацикливаем баннер бесплатно — на уровне демуксера
            "-i", banner_path,
            "-filter_complex", filter_complex,
            "-map", "0:v",  # видео из основного потока
            "-map", "0:a?",  # аудио из основного потока (если есть)
            "-c:v", "libx264",
            "-preset", "veryfast",  # 💨 минимальная нагрузка
            "-crf", "18",
            "-c:a", "copy",  # аудио без перекодирования
            "-t", str(duration),  # длина = длина исходного видео
            "-threads", str(threads),
            output_path
        ]

        print("🎬 Рендер с зацикленным баннером:")
        print(" ".join(cmd))

        subprocess.run(cmd, check=True)

    def cut_duration(self, input_path: str, output_path: str, seconds: float, from_start: bool = True):
        """
        Обрезает видео на указанное количество секунд.
        :param input_path: путь к входному видео
        :param output_path: путь к выходному видео
        :param seconds: сколько секунд обрезать (может быть float)
        :param from_start: True — обрезать с начала, False — с конца
        """
        clip = VideoFileClip(input_path)
        duration = clip.duration

        if seconds >= duration:
            raise ValueError("Количество секунд для обрезки больше или равно длине видео.")

        if from_start:
            # Оставляем часть после seconds
            trimmed = clip.subclip(seconds, duration)
        else:
            # Оставляем часть от начала до duration - seconds
            trimmed = clip.subclip(0, duration - seconds)

        trimmed.write_videofile(
            output_path,
            codec="libx264",
            audio_codec="aac",
            preset="medium"
        )

    def generate_ass(self, subs, style: SubtitleStyle, ass_path: str, w: int, h: int):

        outline = style.outline_width
        shadow = style.shadow_width
        font = style.font if style.font else "DejaVu Sans"
        bold = -1 if style.bold else 0
        italic = -1 if style.italic else 0

        header = f"""[Script Info]
ScriptType: v4.00+
PlayResX: {w}
PlayResY: {h}
Collisions: Normal

[V4+ Styles]
Format: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, OutlineColour, BackColour, Bold, Italic, Underline, StrikeOut, ScaleX, ScaleY, Spacing, Angle, BorderStyle, Outline, Shadow, Alignment, MarginL, MarginR, MarginV, Encoding
Style: Default,{font},{style.fontsize},{style.primary_color},&H00000000,{style.outline_color},&H00000000,{bold},{italic},0,0,100,100,0,0,1,{outline},{shadow},{style.alignment},{style.margin_l},{style.margin_r},{style.margin_v},0

[Events]
Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text
"""

        def sec_to_ass(t: float) -> str:
            h = int(t // 3600)
            m = int((t % 3600) // 60)
            s = t % 60
            return f"{h}:{m:02d}:{s:05.2f}"

        events = []

        for seg in subs:
            start = sec_to_ass(seg["start"])
            end = sec_to_ass(seg["end"])
            text = seg["text"].replace("\n", r"\N")

            fade = ""
            if style.fade_in or style.fade_out:
                fade = f"{{\\fad({style.fade_in},{style.fade_out})}}"

            override = (
                f"{{"
                f"\\bord{outline}"
                f"\\shad{shadow}"
                f"}}"
            )

            events.append(
                f"Dialogue: 0,{start},{end},Default,,"
                f"{style.margin_l},{style.margin_r},{style.margin_v},,"
                f"{override}{fade}{text}\n"
            )
        with open(ass_path, "w", encoding="utf-8") as f:
            f.write(header + "".join(events))

    def add_subtitles_ass(self,
                          input_video: str,
                          style: SubtitleStyle,
                          output_dir: str = None,
                          whisper_model: str = "medium",
                          word_timestamps: bool = True):
        # Генерация имени выходного файла с учётом директории
        def get_output_path(input_video, output_dir=None):
            base_name, ext = os.path.splitext(os.path.basename(input_video))
            counter = 0
            while True:
                if counter == 0:
                    file_name = f"{base_name}_subtitle{ext}"
                else:
                    file_name = f"{base_name}_subtitle_{counter}{ext}"
                if output_dir:
                    os.makedirs(output_dir, exist_ok=True)
                    output_video = os.path.join(output_dir, file_name)
                else:
                    output_video = os.path.join(os.path.dirname(input_video), file_name)
                if not os.path.exists(output_video):
                    return output_video
                counter += 1

        output_video = get_output_path(input_video, output_dir)

        # Транскрибирование видео
        # СТАЛО:
        model = get_whisper(whisper_model)
        segments_gen, info = model.transcribe(input_video, word_timestamps=word_timestamps)
        segments = [
            {
                "start": round(seg.start, 2),
                "end": round(seg.end, 2),
                "text": seg.text.strip()
            }
            for seg in segments_gen
        ]

        # Генерация ASS субтитров
        ass_path = f"subtitles_{uuid.uuid4().hex}.ass"
        clip = VideoFileClip(input_video)
        w, h = clip.size
        self.generate_ass(segments, style, ass_path, w, h)

        # Встраивание субтитров через ffmpeg
        cmd = [
            "ffmpeg",
            "-y",
            "-i", input_video,
            "-vf", f"ass={ass_path}",
            "-c:a", "copy",
            output_video
        ]
        subprocess.run(cmd, check=True)

        # Удаление временного файла субтитров
        os.remove(ass_path)

        return output_video  # путь к итоговому видео



