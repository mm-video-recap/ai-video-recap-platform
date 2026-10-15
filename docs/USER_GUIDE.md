# အသုံးပြုသူ လမ်းညွှန် (USER GUIDE)

> English version follows below. / အောက်တွင် English ဗားရှင်း ပါဝင်သည်။

---

## မြန်မာ

**AI Video Recap Platform** သည် သင့်ဗီဒီယိုကို အလိုအလျောက် အကျဉ်းချုပ် (recap) ဗီဒီယို အတိုအဖြစ် ပြောင်းပေးသော အခမဲ့ ဝက်ဘ်ဆိုက် ဖြစ်သည်။ API key ထည့်စရာ မလိုပါ — အကောင့်ဖွင့်ပြီး သုံးရုံပဲ။

### ၁။ အကောင့်ဖွင့်ခြင်း / ဝင်ရောက်ခြင်း

1. `/login` စာမျက်နှာကို ဖွင့်ပါ။
2. သင့် email ထည့်ပြီး အကောင့်ဖွင့်ပါ (သို့မဟုတ် ဝင်ပါ)။
3. ဝင်ပြီးပါက **Dashboard** သို့ အလိုအလျောက် ရောက်မည်။

### ၂။ ဗီဒီယို တင်ခြင်း

1. **Upload** (သို့မဟုတ် Dashboard မှ "ဗီဒီယိုအသစ်တင်မည်") ကို နှိပ်ပါ။
2. ဖိုင်ရွေးပါ (သို့မဟုတ် ဆွဲချထည့်ပါ) — mp4 / mov / webm / mkv ရပါသည်။
3. **စတင်မည်** ကို နှိပ်ပါ။ စနစ်က ဖိုင်ကို စစ်ပြီး အလုပ်အသစ် (job) တစ်ခု ဖန်တီးပေးမည်။

> အကြံပြုချက် — ဖိုင်ကြီးလေ၊ စောင့်ရမည့်အချိန် ကြာလေဖြစ်သည်။ နေ့စဉ် အခမဲ့ အသုံးပြုနိုင်သည့် အရေအတွက်ကန့်သတ်ချက် ရှိသည် (fair-use)။

### ၃။ လုပ်ဆောင်နေမှုကို ကြည့်ခြင်း

- တင်ပြီးချင်း `/processing/[jobId]` စာမျက်နှာသို့ ရောက်မည်။
- အဆင့် (၇) ဆင့်ကို တိုက်ရိုက် မြင်ရမည် — အသံထုတ်ယူခြင်း → စာသားမှတ်တမ်းတင်ခြင်း → ခွဲခြမ်းစိတ်ဖြာခြင်း → အသံပြောင်းခြင်း → စာတန်းထိုးခြင်း → ဗီဒီယိုထုတ်လုပ်ခြင်း → ပြီးဆုံးခြင်း။
- စာမျက်နှာကို ပိတ်ထားလည်း ရသည် — ပြီးပါက email (ဖွင့်ထားလျှင်) သို့မဟုတ် Dashboard တွင် အသိပေးမည်။

### ၄။ ရလဒ် ဒေါင်းလုဒ်ဆွဲခြင်း

1. ပြီးဆုံးပါက `/result/[jobId]` တွင် recap ဗီဒီယို (အများအားဖြင့် ၉:၁၆ ဒေါင်လိုက်) ကို ကြည့်နိုင်သည်။
2. မြန်မာ စာတန်းထိုး ပါဝင်ပြီး မြန်မာအသံဖြင့် ဇာတ်ကြောင်းပြောထားသည်။
3. **ဒေါင်းလုဒ်** ခလုတ်ဖြင့် MP4 ရယူပါ၊ စာတန်းဖိုင် (.srt) သီးသန့် ရယူလိုပါက ဒုတိယခလုတ်ကို နှိပ်ပါ။
4. ကြိုက်မှု အဆင့် (၁–၃ ကြယ်) ပေးနိုင်သည် — သင့်အကြိုက်ကို AI က မှတ်ထားပြီး နောက်အကျဉ်းချုပ်များ ပိုကောင်းလာမည်။

### ၅။ မေးလေ့ရှိသောမေးခွန်းများ (FAQ)

**တကယ် အခမဲ့လား?**
ဟုတ်ကဲ့။ ငွေပေးချေမှု လုံးဝမရှိပါ။ Fair-use ကန့်သတ်ချက် (ဥပမာ တစ်နေ့ ၅ ခု) သာရှိသည်။

**ကျွန်တော့်ဗီဒီယို ဘယ်သူမြင်နိုင်လဲ?**
သင့်အကောင့်သာ မြင်နိုင်သည်။ လင့်ခ်ကို သင်ကိုယ်တိုင် မျှဝေမှသာ သူများမြင်နိုင်မည်။

**ဘယ်ဘာသာစကားတွေ ရလဲ?**
ဇာတ်ကြောင်းအသံနှင့် စာတန်းထိုးသည် မြန်မာ (default) ဖြစ်သည်။ English သို့ပြောင်းနိုင်သည်။ မူရင်းဗီဒီယို၏ ဘာသာစကားကို AI က အလိုအလျောက် သိရှိသည်။

**အမှားတစ်ခုခု တွေ့ရင် ဘယ်လိုပြောမလဲ?**
`/contact` စာမျက်နှာမှ bug report ပို့နိုင်သည်၊ သို့မဟုတ် feature အသစ် တောင်းဆိုနိုင်သည်။

**ဗီဒီယိုကို ဖျက်ချင်ရင်?**
Dashboard မှ ဗီဒီယိုကို ရွေးပြီး ဖျက်ပါ — မူရင်းဖိုင်၊ အကျဉ်းချုပ်နှင့် ဆက်စပ်ဖိုင်များ အားလုံး ဖျက်ပစ်မည်။

---

## English

**AI Video Recap Platform** is a 100% free website that turns your videos into short recap videos automatically. No API keys needed — just register and use.

### 1. Register / Login

1. Open the `/login` page.
2. Enter your email to sign up (or sign in).
3. You'll land on your **Dashboard** automatically.

### 2. Upload a video

1. Click **Upload** (or "New video" on the Dashboard).
2. Choose a file (or drag & drop) — mp4 / mov / webm / mkv.
3. Click **Start**. The system validates the file and creates a processing job.

> Tip: larger files take longer. A daily fair-use limit applies (e.g. 5 recaps/day).

### 3. Track processing

- You'll land on `/processing/[jobId]` right after upload.
- Watch all 7 stages live — audio extraction → transcription → analysis → voiceover → captions → rendering → done.
- You can close the page — you'll be notified by email (if enabled) or see it on the Dashboard when finished.

### 4. Download your result

1. When done, `/result/[jobId]` shows your recap (usually 9:16 vertical) with Burmese subtitles and Burmese narration.
2. Use **Download** for the MP4, or the second button for the standalone `.srt` subtitle file.
3. Rate it 1–3 stars — your preference is remembered by the AI to improve future recaps.

### 5. FAQ

**Is it really free?**
Yes. No payments, ever. Only fair-use limits (e.g. 5 recaps/day).

**Who can see my video?**
Only your account, unless you share the link yourself.

**Which languages are supported?**
Narration and subtitles default to Burmese, switchable to English. The AI auto-detects the source video's language.

**How do I report a problem?**
Use the `/contact` page for bug reports or feature requests.

**How do I delete my video?**
Select it on the Dashboard and delete — the original, the recap, and all related files are removed.
