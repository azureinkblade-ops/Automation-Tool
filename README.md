# Chapter Promo Builder

A local browser app for turning a novel chapter into a small promo pack:

- three TikTok/Instagram-ready promo images
- three dramatic phrases pulled from the chapter
- captions and short notes for Royal Road and Patreon
- a video helper script that can create a voiceover and a simple vertical MP4 when local tools are available
- a YouTube helper script that randomly selects three background videos from `C:\Users\David\Documents\Novels`
- daily Instagram/X post packs from `C:\Users\David\Documents\Promo Images`

## Start

Double-click `start.bat`, then open:

```text
http://127.0.0.1:8765
```

Paste a chapter, add a title, and choose **Build Promo Pack**.

For daily social posts, choose the novel abbreviation and day, then choose **Create Instagram/X Post**. The app uses:

- `EN` = Eternal Nexus
- `HA` = Heavenly Ascension System
- `SF` = Soul Forge Era
- `HP` = Hundredfold Path

Daily images should follow the existing pattern, such as `EN_Monday.png` or `SF_Friday.png`.

The reusable social prompt lives in `social_prompt_template.txt`, so you can tune the standard wording once and keep using it.

## FFmpeg

The app looks for FFmpeg in this order:

1. `FFMPEG_EXE` from `.env.local`
2. `tools\ffmpeg\bin\ffmpeg.exe`
3. any `ffmpeg.exe` under `tools\`
4. system `PATH`

Run this once to install the portable build into `tools\ffmpeg`:

```text
python setup_ffmpeg.py
```

If Windows cannot reach the download URL, download `ffmpeg-8.1.1-essentials_build.zip` from Gyan's FFmpeg builds, put it in `tools\`, then run `setup_ffmpeg.py` again.

## OpenAI Setup

The app looks for `OPENAI_API_KEY` in the environment or in `.env.local`.

When that key is available, it uses ChatGPT for phrases, captions, platform notes, and image prompts. It also tries to generate three images with the OpenAI image API.

When no key is available, it still works: it pulls three strong phrases from the chapter and downloads free placeholder images from an online image source.

## Output

Each run creates a folder under `campaigns/` with:

- `promo-1.png`, `promo-2.png`, `promo-3.png`
- `phrases.txt`
- `caption.txt`
- `royal-road-note.txt`
- `patreon-note.txt`
- `video-text.txt`
- `make_video.py`
- `make_youtube_video.py`
- `youtube-project-notes.txt`

Daily social post runs create a folder under `social-posts/` with:

- the selected promo image
- `instagram.txt`
- `x.txt`
- `alt-text.txt`
- `prompt-template.txt`

## Instagram Publishing

The app can publish a generated social post to Instagram through Meta's official Instagram publishing API.

Add these to `.env.local`:

```text
INSTAGRAM_ACCOUNT_ID=your_instagram_professional_account_id
INSTAGRAM_ACCESS_TOKEN=your_meta_access_token
INSTAGRAM_PUBLIC_BASE_URL=https://your-public-host/social-posts
META_GRAPH_API_VERSION=v25.0
```

Instagram requires the image to be reachable through a public HTTPS URL. Local files such as `C:\...social-posts\...png` cannot be posted directly. The app stores the post pack locally, then builds the public URL from `INSTAGRAM_PUBLIC_BASE_URL`.

After creating a daily post pack, choose **Post to Instagram**.

For the safer manual flow, choose **Manual Instagram Assist**. It opens Instagram, opens the generated post folder, and copies the caption to your clipboard. After you publish in Instagram, choose **Mark Posted** to record completion in the post metadata.

You can also paste the account ID and token into the app's **Connections** panel. Use **Find Account ID** after saving a token to look up connected Instagram business accounts.

## X Publishing

For the safer manual flow, choose **Manual X Assist**. It opens X, opens the generated post folder, and copies the X post text to your clipboard. After you publish in X, choose **Mark X Posted**.

For API posting, save an OAuth 2.0 user access token with posting and media permissions in the **Connections** panel or in `.env.local`:

```text
X_ACCESS_TOKEN=your_x_user_access_token
```

Then choose **API Post to X** from a generated social post pack.

## Buffer Publishing

Buffer can act as the publishing hub for Instagram, TikTok, YouTube, and other connected channels.

In Buffer:

1. Connect your YouTube, Instagram, and TikTok channels.
2. Go to Buffer API settings and create a personal API key.
3. Paste the API key into **Connections**.
4. Choose **Find Buffer Channels** to list your connected channel IDs.
5. Paste the channel IDs you want to use into **Buffer channel IDs** as a comma-separated list.

The current recommended flow is **Manual Buffer Assist**:

1. Generate a social or TikTok pack.
2. Choose **Manual Buffer Assist**.
3. The app opens Buffer, opens the local media folder, and copies the caption.
4. In Buffer, use its Google Drive/media picker to attach the media.
5. Paste the copied caption.
6. Choose **Mark Buffer Queued** in the app.

The Buffer API key is still useful for checking the account/channel connection, but media posting is handled manually because Buffer's API requires public HTTPS media URLs and Cloudflare R2 requires billing setup.

## GitHub Code And Media Storage

This folder is intended to sync with:

```text
https://github.com/azureinkblade-ops/Automation-tool
```

Generated working folders such as `campaigns/`, `social-posts/`, `tiktok-posts/`, and `youtube-videos/` stay local by default. Generated media is automatically copied into GitHub Pages storage, committed, and pushed when `GITHUB_AUTO_PUBLISH_MEDIA=1`:

```text
docs/media/
```

Enable GitHub Pages for the repository using the `main` branch and `/docs` folder. After Pages finishes publishing, media files are available under:

```text
https://azureinkblade-ops.github.io/Automation-tool/media/
```

If you use a different Pages URL, set it in **Connections** or `.env.local`:

```text
GITHUB_REMOTE_URL=https://github.com/azureinkblade-ops/Automation-tool.git
GITHUB_PAGES_MEDIA_BASE_URL=https://your-pages-host/Automation-tool/media
GITHUB_TOKEN=your_fine_grained_token_with_contents_read_write
GITHUB_AUTO_PUBLISH_MEDIA=1
```

When `GITHUB_TOKEN` is saved, the app uploads media through the GitHub API and does not depend on local Git authentication or `.git` folder ownership. The app records public URLs in the generated pack's `metadata.json`, including `public_image_url` for Instagram-compatible image posts. Buffer API posting also uses GitHub Pages URLs automatically when Cloudflare R2 is not configured.

## TikTok Posting

The app scans:

```text
C:\Users\David\Documents\CloudFlare
```

It uses image groups like `EN_10_1.png`, `EN_10_2.png`, `EN_10_3.png`, and randomly chooses one sound file from the MP3/WAV files in that same folder.

If the image group for a chapter does not exist yet, enter the chapter number and a TikTok image prompt. The app will generate `ABBR_CHAPTER_1`, `ABBR_CHAPTER_2`, and `ABBR_CHAPTER_3` into the CloudFlare folder before creating the TikTok pack.

Choose **Create TikTok Pack**, then:

- **Manual TikTok Assist** opens TikTok upload, opens the generated folder, and copies the caption.
- **Build TikTok Video** creates `tiktok-video.mp4` from the three images and selected sound using FFmpeg.
- **Mark TikTok Posted** records completion locally.

## Patreon And Royal Road

Chapter promo campaigns include platform-specific notes:

- `patreon-note.txt`
- `royal-road-note.txt`

Use the buttons in the chapter promo result:

- **Manual Patreon Assist** opens Patreon, opens the campaign folder, and copies the Patreon note.
- **Mark Patreon Posted** records completion locally.
- **Manual Royal Road Assist** opens Royal Road, opens the campaign folder, and copies the Royal Road note.
- **Mark Royal Road Posted** records completion locally.

Royal Road does not appear to provide an official public posting API. Patreon has API documentation, but Patreon states developer support for its API is no longer provided, so the app uses the safer manual assistant flow for now.

## Posting Schedule

The schedule manager uses:

- Chapter advertising days: Monday, Wednesday, Friday, Sunday
- General promotion days: Tuesday, Thursday, Saturday
- Patreon releases first
- Royal Road releases 14 days after Patreon
- Every scheduled item includes separate Instagram and X copy

The schedule settings live in:

```text
posting_schedule.json
```

By default, each novel starts at Chapter 1. Edit `nextChapter` and `startDate` in that file when you want the planner to match the real chapter queue.

## Writing New Chapters

Use **Write New Chapter + Build Promo** to have ChatGPT draft a chapter from your outline and continuity notes. The app saves:

- the chapter text under `chapters/`
- summary and continuity notes
- a generated promo campaign under `campaigns/`

This requires `OPENAI_API_KEY` in `.env.local` or saved through the **Connections** panel.

## YouTube Videos From Text

Use **YouTube Video** to paste chapter text and create:

- `youtube-title.txt`
- `youtube-description.txt`
- `youtube-tags.txt`
- `youtube-voiceover.wav`
- `youtube-video.mp4`

The app creates YouTube metadata from the chapter text, picks background videos from `C:\Users\David\Documents\Novels`, and uses FFmpeg plus Windows speech to build the MP4.

Run `make_video.py` inside a campaign folder to try creating a voiceover and vertical MP4. It uses Windows speech for audio and `ffmpeg` for video if available. If you prefer OpenShot, import the generated images and `voiceover.wav` into a vertical 1080x1920 project.

Run `make_youtube_video.py` inside a campaign folder to create `youtube-video.mp4` from three randomly selected `BG_*.mp4` background videos. It uses Windows speech for narration and `ffmpeg` for the final MP4 when available. If `ffmpeg` is not installed, use `youtube-project-notes.txt` to recreate the project in OpenShot with the selected videos, narration, and text overlays.

To point the background picker somewhere else, add this to `.env.local`:

```text
BACKGROUND_VIDEO_DIR=C:\Users\David\Documents\Novels
```

## Moving Novel Folders

You do not need to move your novels yet. The **Scan Examples** button looks nearby for prior images, videos, and text files. If you later put examples inside this folder, the scan will find those too.
