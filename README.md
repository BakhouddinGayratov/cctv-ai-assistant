# CCTV AI Assistant — xodimlar boshqaruvi

Hikvision NVR (17 kamera) + yuz tanish + AI chat (Gemini → Groq).

## Ishga tushirish

```bash
pip install -r requirements.txt
cd frontend && npm install && npm run build && cd ..
python main.py
```

Sayt: **http://127.0.0.1:8090** (8000 port boshqa loyihada band bo'lgani uchun 8090).

Birinchi ishga tushishda yuz tanish modellari (`models/`, ~39 MB) avtomatik yuklanadi.

## O'rnatish (ofis kompyuterida)

1. **Git va GitHub CLI** o'rnating, GitHub'ga kiring (bir marta):
   `winget install Git.Git GitHub.cli` → yangi terminal → `gh auth login`
2. **Kodni oling:** `gh repo clone BakhouddinGayratov/cctv-ai-assistant "D:\Camera AI\cctv_ai_assistant"`
3. **Maxfiy sozlamalar (.env):** eski kompyuterdagi `.env` faylini fleshka orqali shu papkaga ko'chiring. U GitHub'da yo'q (parollar va kalitlar). Ko'chirmasangiz, `ornatish.bat` bo'sh `.env` ochadi — to'ldirasiz.
4. **Xodimlar ma'lumoti (ixtiyoriy):** eski xodimlar va yuzlar kerak bo'lsa, `data` papkasini ham ko'chiring. Ko'chirilmasa toza baza bilan boshlanadi.
5. `ornatish.bat` → o'ng tugma → "Administrator sifatida ishga tushirish". Python, ffmpeg, kutubxonalar va modellarni o'zi o'rnatadi, kompyuterga kirilganda serverni oynasiz yoqadigan qilib qo'yadi, uxlash rejimini o'chiradi va kirish manzilini ko'rsatadi.
6. **Tashqaridan kirish:** shu kompyuterga va telefonga Tailscale o'rnating (bitta akkaunt), keyin `http://<tailscale-IP>:<PORT>`.

**Yangilash:** `yangilash.bat` ni ishga tushiring — GitHub'dan yangi versiyani oladi va serverni qayta yoqadi.

Server to'xtasa `ishga_tushirish.bat` uni 10 soniyada qayta yoqadi, tarixi `server_restart.log` da.
## Kirish

Ikki rol: `xojayin` (Bugun, Kameralar, Arxiv, Hisobot) va `admin` (hammasi). Parollar `.env` da: `BOSS_PASSWORD`, `ADMIN_PASSWORD`. O'zgartirgach serverni qayta ishga tushiring. Telegram bot `.env` dagi `KAMERA_KALIT` CCTV'dagi `BOT_API_KEY` bilan bir xil bo'lishi kerak.

## Frontend

`frontend/` — React 19 + TypeScript (strict) + Vite + Tailwind CSS v4 + Motion + Three.js.
Build natijasi (`frontend/dist`) ni FastAPI o'zi beradi, alohida server kerak emas.

Ishlab chiqish rejimi (kod o'zgarishi darhol ko'rinadi, `/api` 8090 ga proksi qilinadi):

```bash
python main.py            # backend
cd frontend && npm run dev  # http://127.0.0.1:5173
```

| Papka | Vazifasi |
|---|---|
| `src/app` | Maket, marshrutlar, mavzu (qorong'i/yorug') |
| `src/components/ui` | Dizayn tizimi: Button, Card, Badge, Modal/Sheet, Tilt (3D), CountUp… |
| `src/features/monitor` | Jonli pleer, kameralar setkasi, NVR arxiv |
| `src/features/network3d` | 17 kamerali interaktiv 3D tarmoq (Three.js, lazy yuklanadi) |
| `src/features/chat` | AI yordamchi |
| `src/features/attendance` | Davomat, haftalik grafik, kun chizig'i |
| `src/features/employees` | Xodimlar, yuz namunalari, ish stoli zonasi |
| `src/features/grid` | 1/4/6/9/16 kamerali setka (server mozaikasi — bitta ulanish) |
| `src/features/archive` | NVR vaqt chizig'i, semantik qidiruv, lavha va video-xulosa |
| `src/features/analytics` | Grafiklar, issiqlik xaritasi, Excel/PDF hisobot |
| `src/features/alerts` | Ogohlantirishlar (SSE jonli lenta, qo'ng'iroqcha) |
| `src/features/settings` | Telegram, xavfsizlik, AI agent, indeksator sozlamalari |

## Sahifalar

| Sahifa | Nima qiladi |
|---|---|
| `/` Kuzatuv | Bugungi ko'rsatkichlar, jonli kamera, 17 kamera (setka yoki 3D xarita), NVR arxiv, AI chat |
| `/attendance` Davomat | Kelish-ketish, kechikish, ofisdagi va ish stolidagi vaqt, effektivlik %, 7 kunlik grafik, kun chizig'i, lenta |
| `/employees` Xodimlar | Xodim qo'shish, yuzni o'rgatish (drag&drop / kamera), ish stoli zonasi, notanish yuzlarni biriktirish |
| `/grid` Setka | 4/6/9/16 kamera bir vaqtda; katakdagi kamerani almashtirish, ikki marta bosish — asosiy pleerda ochish |
| `/archive` Arxiv | NVR yozuvlari vaqt chizig'i (harakat/hodisa), shu daqiqadagi kadrlar, 30 s lavha, 30 s kunlik video-xulosa, "qizil kurtkali odam" kabi qidiruv |
| `/analytics` Analitika | Davr bo'yicha KPI, kelish vaqti taqsimoti, soatlik faollik, kameralar, issiqlik xaritasi, Excel/PDF yuklab olish |
| `/alerts` Hodisalar | Barcha ogohlantirishlar (notanish yuz, ish vaqtidan keyin harakat, kamera oflayn, AI agent), tasdiqlash |
| `/settings` Sozlamalar | Telegram bot, qaysi kameralar qo'riqlanadi, ish vaqtidan tashqari oyna, kunlik/haftalik hisobot vaqti, AI agent |

## Ogohlantirishlar va Telegram

1. Telegramda @BotFather → `/newbot` → token oling.
2. Botga istalgan xabar yozing (yoki guruhga qo'shing), so'ng `https://api.telegram.org/bot<TOKEN>/getUpdates` dan `chat.id` ni oling.
3. **Sozlamalar → Telegram** ga token va chat ID ni kiriting → "Sinov xabari".

Shundan keyin quyidagilar rasm (va kerak bo'lsa 10 s video) bilan Telegramga keladi:

| Hodisa | Qanday aniqlanadi |
|---|---|
| Ish vaqtidan keyin harakat | Qo'riqlanadigan kameralarda harakat + YOLO odam/mashina tasdig'i |
| Kamera oflayn | NVR yoki kanal javob bermasa |
| AI agent | Xodim uzoq vaqt joyida yo'q, kelmaganlar ro'yxati, notanishlar ko'payishi |
| Kunlik xulosa / haftalik hisobot | Rejalashtirilgan vaqtda (Asia/Tashkent), haftalik — dushanba 08:00, Excel+PDF |

Notanish yuzlar faqat saytdagi **Hodisalar** sahifasida ko'rinadi, Telegramga yuborilmaydi.

Ovozli e'lon (server tomonida, edge-tts) faqat ogohlantirishlar uchun va sukut bo'yicha o'chiq.

## Sozlash tartibi

1. **Xodim qo'shing** — ism, lavozim, ish vaqti (masalan 09:00–18:00).
2. **Yuzni o'rgating** (har xodimga 5–10 namuna):
   - eng yaxshisi — xodim kirish kamerasi oldida turadi → "Kameradan olish" → yuzini bosing;
   - yoki rasm yuklang;
   - yoki "Notanish yuzlar" bo'limidan kirish kamerasi qayd etgan yuzni xodimga biriktiring.
3. **Ish stoli** — xodimga ish stoli kamerasini (CH-05) tanlang va zonani sichqoncha bilan belgilang.
   Yuz ko'rinmasa ham, zonada odam bo'lsa "ish stolida" hisoblanadi.

## Qanday ishlaydi

- **Kirish kameralari** (`ATTENDANCE_CAMERAS=3,2` — tashqi → ichki) faqat ish vaqti oynasida
  (`MONITOR_START`–`MONITOR_END`, ish kunlari) doimiy kuzatiladi: harakat bo'lsa sekundiga 2 kadr, yuz aniqlanadi.
- Ikkala kamera bir o'tishni ko'rsa, **yo'nalish** kameralar tartibidan aniqlanadi (3→2 = kirdi, 2→3 = chiqdi).
  Faqat bittasi ko'rsa — o'tishlar navbatma-navbat (kirdi, chiqdi, ...) deb olinadi.
- **Ish stoli** kamerasi har 5 daqiqada tekshiriladi → effektivlik = ish stolida / ofisda.
- NVR ulanmagan bo'lsa kuzatuv avtomatik kutadi, chat darhol xabar beradi.

## Chat misollari

- "Bugun kim keldi va kim kechikdi?"
- "Aliyev qayerda?" — 17 kameradan jonli qidiradi
- "Karimova bu hafta qancha ishladi?"
- "Bugun kirish yo'lagidan nechta odam kirdi?" — bazadan (kuzatuv qamrovi bilan)
- "5-kamerada Aliyev bormi?" — jonli kadr, tanilgan yuzlar ramkada
- "Kecha omborda qizil kurtkali odamni top" — indekslangan kadrlar bo'yicha semantik qidiruv
- "Bugungi kunning video xulosasini tayyorla" — 30 s montaj (fon vazifasi, progress chatda)
- "9-kameradan 14:30 dagi 30 soniyalik lavha" — NVR arxividan klip
- "12-kamerani chapga bur" — PTZ (faqat PTZ kameralar)

## Cheklovlar

- Yuz kamida ~36 px bo'lishi kerak; kirish kameralari **asosiy oqim**da (yuqori sifat) o'qiladi.
- Bitta 1080p kadrda yuz qidirish ~0.2 s CPU; harakat filtri bo'sh kadrlarni o'tkazib yuboradi.
- Setka sahifasi bitta mozaika oqimidan foydalanadi (brauzer bir serverga 6 tadan ortiq oqim ocholmaydi).
- NVR vaqt chizig'i va PTZ Hikvision ISAPI (HTTP 80, Digest) orqali ishlaydi; NVR'da ISAPI yoqilgan bo'lishi kerak.
- Ma'lumotlar `data/` papkasida (SQLite + yuz rasmlari); ko'rinish rasmlari 60 kundan keyin o'chiriladi.
