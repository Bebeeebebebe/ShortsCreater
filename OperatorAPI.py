from fastapi import FastAPI
from pydantic import BaseModel
from typing import List
from TranscribeAndCutVideoModule import VideoProcessing, SubtitleStyle, ShortsCreater, calc_position
from moviepy.editor import CompositeVideoClip, VideoFileClip, ImageClip
import os
from fastapi import BackgroundTasks
from typing import Literal
import uuid
import subprocess
from AccountLogger import AccountLogger
from PostByAccount import MultiPost, VideoSideTexts, VideoPostRequest
import threading
import asyncio
from moviepy.editor import vfx
#uvicorn OperatorAPI:app --host 0.0.0.0 --port 8000




def get_video_size(path: str):
    cmd = [
        "ffprobe", "-v", "error",
        "-select_streams", "v:0",
        "-show_entries", "stream=width,height",
        "-of", "csv=p=0",
        path
    ]
    out = subprocess.check_output(cmd, text=True).strip()
    w, h = out.split(",")
    return int(w), int(h)
app = FastAPI()

SubtitleStyleObj = SubtitleStyle()
VideoList: list[str] = []
ShortsCreaterConfig: dict | None = None
ShortsCreaterObj: ShortsCreater | None = None
CurrentThreads: int = 2


class OverlayItem(BaseModel):
    file_path: str
    scale: float = 1.0

    anchor: Literal[
        "top-left", "top-center", "top-right",
        "center-left", "center", "center-right",
        "bottom-left", "bottom-center", "bottom-right"
    ]

    offset_x: int = 0
    offset_y: int = 0
    opacity: float = 1.0

    start_ms: int = 0
    end_ms: int = 0
    loop: bool = False

    fade_in: int = 0
    fade_out: int = 0

class CompositionRequest(BaseModel):
    output_dir: str
    subtitle_style: dict | None = None
    overlays: list[OverlayItem]
    threads: int = 2

class ApplyOverlaysRequest(BaseModel):
    output_dir: str
    overlays: list[OverlayItem]
class ShortsCreateRequest(BaseModel):
    video_path: str
    output_dir: str
    clip_mode: str = "blur"
    mode: Literal["TranscribeBasedShorts", "SimpleIntervalShorts"] = "SimpleIntervalShorts"
    interval: float | None = None
    whisper_model: str | None = None
    whisper_language: str | None = None
    min_duration: float | None = None
    max_duration: float | None = None
    max_workers: int = 4

class AddSubtitlesRequest(BaseModel):
    output_dir: str | None = None
    whisper_model: str = "base"
    word_timestamps: bool = True

class AddBannerRequest(BaseModel):
    banner_path: str
    output_dir: str
    anchor: Literal[
        "top-left", "top-center", "top-right",
        "center-left", "center", "center-right",
        "bottom-left", "bottom-center", "bottom-right"
    ] = "top-left"
    offset_x: int = 0
    offset_y: int = 0
    scale: float = 1.0
    opacity: float = 1.0
    start_ms: int = 0
    fade_in: int = 0
    threads: int = 2



class VideoListRequest(BaseModel):
    videos: list[str]


class LoginAccountRequest(BaseModel):
    account_name: str
    platform: Literal["YouTube", "TikTok", "ChatGPT"]

ActiveLoggers: dict[str, AccountLogger] = {}


class VideoSideTextsModel(BaseModel):
    description: str
    hashtags: str
    music_author: str
    music_name: str


class VideoPostRequestModel(BaseModel):
    platform: str
    account_name: str
    videos: dict[str, VideoSideTextsModel]


class MultiPostRequest(BaseModel):
    requests: list[VideoPostRequestModel]

class RenderRequest(BaseModel):
    videos: List[str]

CurrentSubtitleStyle = SubtitleStyle()
CurrentOverlays: list[OverlayItem] = []
CurrentOutputDir: str | None = None


#------------Создание объекта ShortsCreater-a---------------
@app.post("/CreateShortsCreater/")
async def CreateShortsCreater(data: ShortsCreateRequest):
    global ShortsCreaterConfig, ShortsCreaterObj

    ShortsCreaterObj = ShortsCreater(
        video_path=data.video_path,
        output_dir=data.output_dir,
        clip_mode=data.clip_mode,
        mode=data.mode,
        interval=data.interval or 60.0,
        whisper_model=data.whisper_model or "base",
        whisper_language=data.whisper_language or "auto",
        min_duration=data.min_duration or 40.0,
        max_duration=data.max_duration or 120.0,
        max_workers=data.max_workers,
    )

    ShortsCreaterConfig = {
        "video_path": data.video_path,
        "output_dir": data.output_dir,
        "clip_mode": data.clip_mode,
        "mode": data.mode,
        "interval": data.interval or 60.0,
        "whisper_model": data.whisper_model or "base",
        "whisper_language": data.whisper_language or "auto",
        "min_duration": data.min_duration or 40.0,
        "max_duration": data.max_duration or 120.0,
    }
    return {"status": "ok", "mode": data.mode}


@app.post("/CreateShorts/")
async def CreateShorts(background_tasks: BackgroundTasks):
    global ShortsCreaterObj

    if ShortsCreaterObj is None:
        return {
            "status": "error",
            "message": "ShortsCreater object not created"
        }

    try:
        def run_in_thread():
            asyncio.run(ShortsCreaterObj.create_shorts_from_video())

        background_tasks.add_task(run_in_thread)

        return {
            "status": "ok",
            "message": "Shorts creation started"
        }

    except Exception as e:
        return {
            "status": "error",
            "error_type": e.__class__.__name__,
            "message": str(e)
        }
#------------------Кастомизация субтитров--------------------
@app.post("/ChangeSubtitleStyle/{name}/{value}")
async def ChangeSubtitleStyle(name: str, value: str):
    global SubtitleStyleObj

    if not hasattr(SubtitleStyleObj, name):
        return {
            "status": "error",
            "message": f"Field '{name}' does not exist in SubtitleStyle"
        }

    current_value = getattr(SubtitleStyleObj, name)
    field_type = type(current_value)

    try:
        if field_type is bool:
            value_casted = value.lower() == "true"
        else:
            value_casted = field_type(value)
    except Exception:
        return {
            "status": "error",
            "message": f"Cannot convert value '{value}' to {field_type}"
        }

    setattr(SubtitleStyleObj, name, value_casted)

    return {
        "status": "ok",
        "updated_field": name,
        "new_value": value_casted
    }

#----------------------Текущая настройка субтитров--------------------
@app.post("/GetSubtitleStyles")
async def GetSubtitleStyles():
    return SubtitleStyleObj.__dict__
# -----------------------Получение списка видео для обработки------------------
@app.post("/UpdateVideoList/")
async def UpdateVideoList(data: VideoListRequest):
    global VideoList
    VideoList = data.videos
    return {"status": "ok", "video_count": len(VideoList)}


# --------------------Отправка текущего списка видео-------------------------
@app.post("/GetCurrentVideoList", response_model=list[str])
async def GetCurrentVideoList():
    global VideoList
    return VideoList

VideoProcessingObj = VideoProcessing()

@app.post("/AddBanner/")
async def AddBanner(data: AddBannerRequest):
    global VideoList

    if not VideoList:
        return {
            "status": "error",
            "message": "VideoList is empty"
        }

    results = []

    try:
        for video_path in VideoList:
            video_name = os.path.basename(video_path)
            output_path = os.path.join(data.output_dir, video_name)

            VideoProcessingObj.add_banner_until_end(
                input_video=video_path,
                banner_path=data.banner_path,
                output_path=output_path,
                anchor=data.anchor,
                offset_x=data.offset_x,
                offset_y=data.offset_y,
                scale=data.scale,
                opacity=data.opacity,
                start_ms=data.start_ms,
                fade_in=data.fade_in,
                threads=data.threads,
            )

            results.append({
                "video": video_path,
                "output": output_path
            })

        return {
            "status": "ok",
            "message": "Banner added to all videos",
            "processed": len(results),
            "results": results
        }

    except Exception as e:
        return {
            "status": "error",
            "error_type": e.__class__.__name__,
            "message": str(e)
        }

#Добавление субтитров
@app.post("/AddSubtitles/")
async def AddSubtitlesToList(data: AddSubtitlesRequest):
    global VideoList, SubtitleStyleObj, VideoProcessingObj

    if not VideoList:
        return {
            "status": "error",
            "message": "Video list is empty. Use /UpdateVideoList/ first."
        }

    output_videos = []
    errors = []

    for video_path in VideoList:
        try:
            output_video = VideoProcessingObj.add_subtitles_ass(
                input_video=video_path,
                style=SubtitleStyleObj,
                output_dir=data.output_dir,
                whisper_model=data.whisper_model,
                word_timestamps=data.word_timestamps
            )
            output_videos.append(output_video)

        except Exception as e:
            errors.append({
                "video": video_path,
                "error_type": e.__class__.__name__,
                "message": str(e)
            })

    return {
        "status": "ok" if not errors else "partial",
        "processed_videos": output_videos,
        "errors": errors
    }


@app.post("/ApplyOverlays/")
async def ApplyOverlays(data: ApplyOverlaysRequest):
    global VideoList, VideoProcessingObj

    if not VideoList:
        return {"status": "error", "message": "Video list empty"}

    results = []

    overlays_dicts = [o.dict() for o in data.overlays]
    for video in VideoList:
        name, _ = os.path.splitext(os.path.basename(video))
        output = os.path.join(data.output_dir, f"{name}_overlay.mp4")
        VideoProcessingObj.render_composition_ffmpeg(
            input_video=video,
            output_video=output,
            ass_path=None,
            overlays=overlays_dicts
        )
        results.append(output)

    return {
        "status": "ok",
        "processed": len(results),
        "outputs": results
    }


@app.post("/UpdateComposition/")
async def UpdateComposition(data: CompositionRequest):
    global CurrentSubtitleStyle, CurrentOverlays, CurrentOutputDir, CurrentThreads
    CurrentThreads = data.threads
    # применяем стиль субтитров
    if data.subtitle_style:
        for k, v in data.subtitle_style.items():
            if hasattr(CurrentSubtitleStyle, k):
                setattr(
                    CurrentSubtitleStyle,
                    k,
                    type(getattr(CurrentSubtitleStyle, k))(v)
                )
    else:
        CurrentSubtitleStyle = None

    CurrentOverlays = data.overlays
    CurrentOutputDir = data.output_dir

    return {
        "status": "ok",
        "overlays": len(CurrentOverlays)
    }

@app.post("/RenderComposition/")
async def RenderComposition(background_tasks: BackgroundTasks):
    if not VideoList:
        return {"status": "error", "message": "Video list empty"}
    if ShortsCreaterConfig is None:
        return {"status": "error", "message": "ShortsCreater not configured"}

    config_snapshot = dict(ShortsCreaterConfig)
    videos_snapshot = list(VideoList)
    overlays_snapshot = [o.dict() for o in CurrentOverlays]
    subtitle_style_snapshot = CurrentSubtitleStyle
    output_dir_snapshot = CurrentOutputDir
    threads_snapshot = CurrentThreads


    def process():
        for video in videos_snapshot:
            sc = ShortsCreater(
                video_path=video,
                whisper_model=config_snapshot["whisper_model"],
                whisper_language=config_snapshot["whisper_language"],
                output_dir=config_snapshot["output_dir"],
                clip_mode=config_snapshot["clip_mode"],
                min_duration=config_snapshot["min_duration"],
                max_duration=config_snapshot["max_duration"],
                mode=config_snapshot.get("mode", "TranscribeBasedShorts"),
                interval=config_snapshot.get("interval", 60.0),
            )

            vp = VideoProcessing()

            ass_path = None

            if subtitle_style_snapshot is not None:
                transcription = sc.transcribe_video_with_timestamps()

                w, h = get_video_size(video)

                ass_path = f"sub_{uuid.uuid4().hex}.ass"

                vp.generate_ass(
                    subs=transcription["segments"],
                    style=subtitle_style_snapshot,
                    ass_path=ass_path,

                    w=w,
                    h=h
                )

            name, _ = os.path.splitext(os.path.basename(video))
            output = os.path.join(output_dir_snapshot, f"{name}_final.mp4")

            vp.render_composition_ffmpeg(
                input_video=video,
                output_video=output,
                ass_path=ass_path,
                threads=threads_snapshot,
                overlays=overlays_snapshot

            )

            if ass_path is not None:
                os.remove(ass_path)

    background_tasks.add_task(process)
    return {"status": "ok"}

@app.post("/LoginAccount/")
async def LoginAccount(data: LoginAccountRequest):
    key = f"{data.platform}_{data.account_name}"

    if key in ActiveLoggers:
        return {
            "status": "error",
            "message": "Account login already running"
        }

    try:
        logger = AccountLogger(
            account_name=data.account_name,
            site_key=data.platform
        )

        ActiveLoggers[key] = logger

        thread = threading.Thread(
            target=logger.run,
            daemon=True
        )
        thread.start()

        return {
            "status": "ok",
            "message": f"Browser started for {data.platform}/{data.account_name}"
        }

    except Exception as e:
        return {
            "status": "error",
            "error_type": e.__class__.__name__,
            "message": str(e)
        }


@app.post("/StartMultiPost/")
async def StartMultiPost(data: MultiPostRequest, background_tasks: BackgroundTasks):
    try:
        post_requests = []

        for req in data.requests:
            videos_dict = {
                path: VideoSideTexts(
                    description=v.description,
                    hashtags=v.hashtags,
                    music_author=v.music_author,
                    music_name=v.music_name
                )
                for path, v in req.videos.items()
            }

            post_requests.append(
                VideoPostRequest(
                    platform=req.platform,
                    account_name=req.account_name,
                    videos=videos_dict
                )
            )

        multipost = MultiPost(post_requests)

        def run_multipost():
            platforms = {req.platform.lower() for req in data.requests}
            if "tiktok" in platforms:
                multipost.post_to_tiktok()
            if "youtube" in platforms:
                multipost.post_to_youtube()


        background_tasks.add_task(
           run_multipost
        )

        return {
            "status": "ok",
            "message": "Multi-posting started"
        }

    except Exception as e:
        return {
            "status": "error",
            "error_type": e.__class__.__name__,
            "message": str(e)
        }


@app.post("/CreateSimpleClips/")
async def CreateSimpleClips(data: ShortsCreateRequest, background_tasks: BackgroundTasks):
    sc = ShortsCreater(
        video_path=data.video_path,
        output_dir=data.output_dir,
        clip_mode=data.clip_mode,
        mode="SimpleIntervalShorts",
        interval=data.interval or 60.0,
        whisper_model="base",       # не используется, но конструктор требует
        whisper_language="auto",
        max_workers=data.max_workers,
    )

    def run():
        try:
            sc.create_simple_clips()
        except Exception as e:
            print(f"❌ Ошибка в create_simple_clips: {e}")

    background_tasks.add_task(run)
    return {"status": "ok", "message": f"Simple clipping started (interval={data.interval}s)"}