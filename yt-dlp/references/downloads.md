# 下载示例

将 URL、OUTPUT_DIR、BROWSER 等占位符替换为实际值，并保持 shell 参数引用。输出目录遵循用户或项目约定。

## 下载 YouTube

除非用户已经指定格式，否则先查看元数据或格式，避免下载错误版本：

```bash
yt-dlp --no-playlist -F "YOUTUBE_URL"
```

### 视频

默认下载最佳可用视频和音频，并让 FFmpeg 在需要时合并：

```bash
mkdir -p "OUTPUT_DIR"
yt-dlp --no-playlist \
  -P "OUTPUT_DIR" \
  -o "%(title).180B [%(id)s].%(ext)s" \
  "YOUTUBE_URL"
```

限制到 1080p 时：

```bash
yt-dlp --no-playlist \
  -f "bv*[height<=1080]+ba/b[height<=1080]" \
  -P "OUTPUT_DIR" \
  -o "%(title).180B [%(id)s].%(ext)s" \
  "YOUTUBE_URL"
```

不要无条件强制 MP4 或重新编码。只有用户需要特定兼容性时才指定容器或编码，以免降低质量或增加大量处理时间。

### 音频

用户未指定格式时，使用 `-x --audio-format best` 保留最佳可用音频格式；下面是用户指定 M4A 或 MP3 时的示例：

```bash
# 用户需要 M4A 时提取或转换
yt-dlp --no-playlist -x --audio-format m4a \
  -P "OUTPUT_DIR" \
  -o "%(title).180B [%(id)s].%(ext)s" \
  "YOUTUBE_URL"

# 用户明确需要 MP3
yt-dlp --no-playlist -x --audio-format mp3 --audio-quality 0 \
  -P "OUTPUT_DIR" \
  -o "%(title).180B [%(id)s].%(ext)s" \
  "YOUTUBE_URL"
```

### 字幕

下载匹配语言的人工和自动字幕；如只需要人工字幕，去掉 `--write-auto-subs`：

```bash
yt-dlp --no-playlist --skip-download \
  --write-subs --write-auto-subs \
  --sub-langs "zh-Hans,zh-Hant,zh.*,en.*" \
  --sub-format "srt/vtt/best" \
  --convert-subs srt \
  -P "OUTPUT_DIR" \
  -o "%(title).180B [%(id)s].%(ext)s" \
  "YOUTUBE_URL"
```

先用下面的命令查看实际可用语言，避免误判“没有字幕”：

```bash
yt-dlp --no-playlist --list-subs "YOUTUBE_URL"
```

如果用户同时需要视频和字幕，去掉 `--skip-download`，保留字幕选项即可。需要把字幕封装进视频时，先确认用户想要软字幕还是烧录字幕；不要默认烧录。

## 下载普通网页中的媒体

先把网页 URL 直接交给 yt-dlp。它对已支持网站和许多常见嵌入播放器能自动识别：

```bash
yt-dlp --no-playlist \
  -P "OUTPUT_DIR" \
  -o "%(title).180B [%(id)s].%(ext)s" \
  "PAGE_URL"
```

提取音频时使用同样的 `-x --audio-format m4a` 或用户指定格式。

如果网页 URL 无法识别：

1. 用 `yt-dlp --verbose --simulate --no-playlist "PAGE_URL"` 记录真实错误。
2. 检查页面公开 HTML 中的 `<video>`、`<source>`、`.m3u8`、`.mpd` 或直链媒体地址；有浏览器工具时，也可查看该页面自身发起的媒体网络请求。
3. 对公开的直链、HLS 或 DASH manifest，把媒体 URL 交给 yt-dlp，并保留来源页：

   ```bash
   yt-dlp --referer "PAGE_URL" -P "OUTPUT_DIR" "MEDIA_OR_MANIFEST_URL"
   ```

4. 如果访问依赖登录态，在确认用户有权下载且明确同意读取浏览器登录信息后，才使用：

   ```bash
   yt-dlp --cookies-from-browser "BROWSER" --referer "PAGE_URL" \
     -P "OUTPUT_DIR" "PAGE_URL_OR_MEDIA_URL"
   ```

5. 如果检测到 DRM 或必须规避访问控制，停止并说明限制，不尝试绕过。

不要把抓到的临时、带签名媒体 URL 当成永久链接公开输出；它可能包含短期访问凭据。

