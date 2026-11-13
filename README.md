# CofeSave — @cofesavebot

YouTube (video va Shorts), Instagram (Reels / video post), TikTok uchun Telegram bot.
Python 3.12+, aiogram 3, yt-dlp, FFmpeg va Node.js 22 ishlatiladi.

## Imkoniyatlar

- O'zbekcha `/start` (welcome rasm bilan), `/help`, administrator uchun `/stats`.
- YouTube uchun format tanlash, Instagram va TikTok uchun avtomatik yuklash.
- Davomiylik chegarasi yo'q. Yuklash darhol boshlanadi; `WORKERS` joylari band bo'lsa,
  bot darhol xabar beradi. Keshdagi videolar yuklash joyini band qilmaydi.
- Bir foydalanuvchi ketma-ket bir nechta video havola yubora oladi.
- Bir xil havolalarni normallashtirish va Telegram `file_id` orqali qayta yuborish.
- SQLite'da kesh, foydalanuvchi ID'lari va yuborishlar statistikasi; token saqlanmaydi.
- Alohida downloader jarayoni, vaqt / disk chegaralari, vaqtinchalik fayllarni tozalash.

## Lokal ishga tushirish (Windows PowerShell)

```powershell
cd "$env:USERPROFILE\OneDrive\Desktop\downloaderbot"
uv venv --python 3.12 .venv
uv pip install --python .venv\Scripts\python.exe -r requirements.lock
Copy-Item .env.example .env
```

`.env` ichiga `BOT_TOKEN` yozing. Tokenni chat, GitHub yoki skrinshotda ulashmang.
`ADMIN_IDS` ixtiyoriy: Telegram raqamli user ID'lari, vergul bilan ajratiladi.

FFmpeg va Node.js 22 PATH'da mavjud bo'lishi kerak:

```powershell
ffmpeg -version
node --version
.venv\Scripts\python.exe bot.py
```

`.env` fayli avtomatik yuklanadi. Bot tokenisiz ishga tushmaydi.
Bir bot tokeni uchun faqat bitta polling jarayoni ishlasin.

## Docker

```powershell
docker build -t cofesave .
docker run --rm --env-file .env -v cofesave-data:/data cofesave
```

Docker ichida FFmpeg va Node.js mavjud. Videolar vaqtinchalik saqlanadi, SQLite `/data` ichida.

## Railway

1. Loyihani o'zingizning yopiq GitHub repository'ingizga yuklang.
2. Railway'da shu repository'dan service yarating. `Dockerfile` avtomatik ishlatiladi.
3. Variables: `BOT_TOKEN`, ixtiyoriy `ADMIN_IDS`. Boshqa qiymatlar `.env.example` da.
4. Kesh restartdan keyin saqlanishi uchun bitta volume ulang: mount path `/data`.
5. Bitta replica ishlating. Domen, port, HTTP healthcheck va webhook kerak emas — long polling.
6. Xarajat chegarasini Railway hisobingizda belgilang, sarfni kuzating.

Deploy yoki restart paytida tugallanmagan havolani qayta yuborish kerak.
SQLite bitta replica uchun mo'ljallangan. Bir nechta replica va katta yuklama uchun arxitekturani
alohida queue va umumiy database'ga o'tkazish kerak.

## Limitlar va platforma cheklovlari

### Guruhlarda ishlatish

Bot shaxsiy chat, guruh va superguruhlarda video havolalarini qabul qiladi.
Guruhdagi oddiy suhbatlar va fayllarga javob bermaydi.
Oddiy havolalar botga yetib kelishi uchun uni guruhga administrator sifatida qo'shing
yoki BotFather'da `/setprivacy` → `@cofesavebot` → `Disable` qiling.
Privacy sozlamasi o'zgargach botni guruhdan chiqarib, qayta qo'shish kerak.
Guruhda botga xabar va video yuborish ruxsati ham berilgan bo'lsin.
[Telegram guruh privacy hujjati](https://core.telegram.org/bots/features#privacy-mode)

### Video cheklovlari

Telegram'ning standart Bot API'si yangi video fayllarini 50 MB gacha qabul qiladi, shu sababli
48 MB xavfsiz chegara saqlanadi. YouTube uchun MP3, 360p, 720p, 1080p yoki Avtomatik
variantini tanlang. Raqamli sifat tanlanganda bot manba va hajmga qarab pastroq
sifatdagi MP4 yuborishi mumkin. Instagram va TikTok uchun eng sifatli mavjud oqimlar
avtomatik yuklanadi va qayta kodlanmaydi. MP4 video sifatida, boshqa formatlar esa
fayl sifatida yuboriladi. Eng sifatli nusxa hajm chegarasidan oshsa, bot xabar beradi.

Media yuborilgach, bot shu so'rovga o'zi jo'natgan format menyusini o'chiradi.

Yopiq kontent, jonli efir, pleylist, Stories va foto albomlar qo'llanmaydi. Instagram karuselida
faqat birinchi element tekshiriladi; u video bo'lmasa yuklash rad etiladi. Instagram / YouTube /
TikTok server IP'larini cheklashi yoki login talab qilishi mumkin. Uchala platforma uchun
kod mavjudligi har bir havola Railway'da ochilishini kafolatlamaydi. Real havolalar bilan
deploy qilingan serverdan tekshirish kerak. Cookies ham server IP cheklovini doim hal qilmaydi.

Zarur bo'lsa Netscape formatidagi cookie faylini xavfsiz joyga joylang va `COOKIES_FILE`
yo'lini ko'rsating. Cookie faylini Git'ga qo'shmang. Shu fayl bilan downloader ishlaydi.

Format tanlash, extractor va platforma o'zgarishlari uchun yt-dlp yangilanib turishi kerak.
Qulflangan paketlarni yangilash: `uv pip compile requirements.txt -o requirements.lock`,
keyin tekshiruvlarni qayta bajarish va qayta build qilish.

### 2 GB gacha fayllar

1. [Telegram Bot API serverini](https://github.com/tdlib/telegram-bot-api#usage) alohida xizmat
   sifatida `--local` rejimida ishga tushiring. Shu xizmatga `TELEGRAM_API_ID` va
   `TELEGRAM_API_HASH` kerak.
2. CofeSave sozlamalarida `TELEGRAM_LOCAL_API_URL` ga o'zingiz boshqaradigan API server
   manzilini va `MAX_FILE_MB=2000` ni yozing. Bir kompyuterda manzil
     `http://127.0.0.1:8081` bo'lishi mumkin. Alohida xizmatlar orasida ichki tarmoqdan foydalaning.
3. Ishlab turgan botni ko'chirishda avval eski polling jarayonini to'xtating. Cloud API'da
   [`logOut`](https://core.telegram.org/bots/api#logout) ni bir marta chaqiring va CofeSave'ni
   yangi sozlamalar bilan ishga tushiring. Cloud API'ga qaytishdan oldin 10 daqiqa kutish kerak.

48 MB dan yuqori limit tanlansa, yuklab olish va Telegram'ga yuborish uchun standart vaqt
1800 soniyadan. `DOWNLOAD_TIMEOUT_SECONDS` va `UPLOAD_TIMEOUT_SECONDS` orqali sozlash mumkin.
Audio va video oqimlarini birlashtirish uchun yakuniy fayldan tashqari vaqtinchalik disk joyi
kerak bo'ladi. Disk cheklangan bo'lsa, `WORKERS=1` va kichikroq hajm chegarasini qo'llang.

## Tekshiruvlar

```powershell
uv pip install --python .venv\Scripts\python.exe -r requirements-dev.txt
.venv\Scripts\python.exe -m pytest
.venv\Scripts\python.exe -m ruff check .
.venv\Scripts\python.exe -m compileall -q bot.py cofesave tests
```

Testlar Telegram'ga ulanmaydi: URL chegaralari, format / limitlar, parallel yuklash, kesh,
yuklash jarayonining timeout'i va tozalashini tekshiradi. Haqiqiy token bilan uchala
platformaning ochiq videolarini alohida tekshirish zarur.

## Brend fayllari

- `assets/brand/cofesave-avatar.png` — bot avatari.
- `assets/brand/cofesave-welcome.png` — `/start` xabari rasmi.

## Manbalar

- [aiogram long polling](https://docs.aiogram.dev/en/latest/dispatcher/long_polling.html)
- [yt-dlp](https://github.com/yt-dlp/yt-dlp)
- [Telegram video cheklovlari](https://core.telegram.org/bots/api#sendvideo)
