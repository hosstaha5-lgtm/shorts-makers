import os, re, shutil, subprocess, tempfile
from pathlib import Path
from typing import List, Dict
import streamlit as st
import yt_dlp
from yt_dlp.utils import download_range_func

OUTPUT_DIR = Path("output_shorts")
OUTPUT_DIR.mkdir(exist_ok=True)

def check_ffmpeg() -> bool:
    return shutil.which("ffmpeg") is not None

def sanitize_filename(name: str) -> str:
    cleaned = re.sub(r'[\\/*?:"<>|]+', "", name).strip()
    return cleaned[:60] if cleaned else "youtube_short"

def format_time(seconds: float) -> str:
    seconds = max(0, int(seconds))
    m, s = divmod(seconds, 60)
    h, m = divmod(m, 60)
    return f"{h:02d}:{m:02d}:{s:02d}" if h > 0 else f"{m:02d}:{s:02d}"

def extract_video_metadata(url: str) -> Dict:
    ydl_opts = {"quiet": True, "no_warnings": True, "noplaylist": True, "skip_download": True}
    with yt_dlp.YoutubeDL(ydl_opts) as ydl:
        return ydl.extract_info(url, download=False)
  def pick_best_segments(info: Dict, num_clips: int = 1, clip_duration: int = 45) -> List[Dict[str, float]]:
    duration = float(info.get("duration") or 0)
    if duration <= 0:
        return [{"start": 0.0, "end": float(clip_duration)}]
    if duration <= clip_duration:
        return [{"start": 0.0, "end": duration}]

    selected = []
    heatmap = info.get("heatmap") or []
    if heatmap:
        for pt in sorted(heatmap, key=lambda x: x.get("value", 0), reverse=True):
            center = (float(pt["start_time"]) + float(pt["end_time"])) / 2.0
            start = max(0.0, center - clip_duration * 0.35)
            end = min(duration, start + clip_duration)
            start = max(0.0, end - clip_duration)
            if not any(not (end <= s["start"] + 5 or start >= s["end"] - 5) for s in selected):
                selected.append({"start": round(start, 2), "end": round(end, 2)})
            if len(selected) >= num_clips:
                break

    if len(selected) < num_clips:
        usable_start = min(duration * 0.08, 15.0) if duration > 90 else 0.0
        step = max(duration - clip_duration - usable_start, 1.0) / max(num_clips, 1)
        for i in range(num_clips):
            if len(selected) >= num_clips:
                break
            start = min(usable_start + i * step, max(0.0, duration - clip_duration))
            end = min(duration, start + clip_duration)
            if not any(not (end <= s["start"] + 5 or start >= s["end"] - 5) for s in selected):
                selected.append({"start": round(start, 2), "end": round(end, 2)})

    return sorted(selected, key=lambda x: x["start"])

def download_segment(url: str, start: float, end: float, out_path: Path) -> Path:
    template = str(out_path.with_suffix("")) + ".%(ext)s"
    ydl_opts = {
        "format": "bv*[height<=1080][ext=mp4]+ba[ext=m4a]/b[height<=1080][ext=mp4]/bv*[height<=1080]+ba/b",
        "outtmpl": template, "merge_output_format": "mp4", "noplaylist": True,
        "quiet": True, "no_warnings": True,
        "download_ranges": download_range_func(None, [(start, end)]),
        "force_keyframes_at_cuts": True,
    }
    with yt_dlp.YoutubeDL(ydl_opts) as ydl:
        ydl.download([url])
    expected = out_path.with_suffix(".mp4")
    if expected.exists():
        return expected
    files = list(out_path.parent.glob(f"{out_path.stem}.*"))
    if files:
        return files[0]
    raise FileNotFoundError("فشل تنزيل المقطع")
                    def convert_to_short(input_path: Path, output_path: Path, mode: str = "blur"):
    if mode == "crop":
        vf = "crop=ih*9/16:ih:(iw-ow)/2:0,scale=1080:1920,setsar=1"
    else:
        vf = (
            "[0:v]split=2[bg][fg];"
            "[bg]scale=1080:1920:force_original_aspect_ratio=increase,crop=1080:1920,boxblur=25:5[b];"
            "[fg]scale=1080:-2[f];"
            "[b][f]overlay=(W-w)/2:(H-h)/2,setsar=1"
        )
    cmd = ["ffmpeg", "-y", "-i", str(input_path), "-vf", vf, "-c:v", "libx264", "-preset", "fast",
           "-crf", "22", "-c:a", "aac", "-b:a", "128k", "-movflags", "+faststart", str(output_path)]
    subprocess.run(cmd, check=True, stdout=subprocess.DEVNULL, stderr=subprocess.PIPE)

st.set_page_config(page_title="صانع الشورتس - عالم الألعاب", page_icon="🎮", layout="centered")
st.title("🎮 صانع YouTube Shorts الذكي")
st.caption("حول أي فيديو يوتيوب إلى مقاطع شورتس تلقائياً")

url = st.text_input("🔗 ضع رابط فيديو اليوتيوب هنا:")
col1, col2 = st.columns(2)
with col1:
    num_clips = st.slider("عدد المقاطع", 1, 5, 3)
with col2:
    clip_dur = st.slider("مدة المقطع (ثانية)", 15, 60, 25)

mode_choice = st.selectbox("🎨 شكل الفيديو (9:16)", ["خلفية ضبابية مع كامل الشاشة (للألعاب)", "قص مركزي (Center Crop)"])

if st.button("🚀 اصنع الشورتس الآن", use_container_width=True):
    if not url:
        st.error("أدخل رابط الفيديو أولاً!")
    elif not check_ffmpeg():
        st.error("أداة FFmpeg غير مثبتة.")
    else:
        with st.spinner("⏳ جاري التحليل والتقطيع..."):
            try:
                info = extract_video_metadata(url)
                st.success(f"تم العثور على: {info.get('title')}")
                segments = pick_best_segments(info, num_clips, clip_dur)
                with tempfile.TemporaryDirectory() as tmp_dir:
                    tmp_path = Path(tmp_dir)
                    for i, seg in enumerate(segments, 1):
                        st.info(f"📥 تجهيز المقطع {i}/{len(segments)} ({format_time(seg['start'])} ➔ {format_time(seg['end'])})...")
                        raw_file = download_segment(url, seg["start"], seg["end"], tmp_path / f"raw_{i}")
                        final_file = OUTPUT_DIR / f"short_{i}_{sanitize_filename(info.get('title', 'video'))}.mp4"
                        convert_to_short(raw_file, final_file, "crop" if "قص" in mode_choice else "blur")
                        st.video(str(final_file))
                        with open(final_file, "rb") as f:
                            st.download_button(f"⬇️ تحميل الشورت {i}", f, final_file.name, "video/mp4", key=f"dl_{i}")
                st.balloons()
            except Exception as e:
                st.error(f"حدث خطأ: {e}")
