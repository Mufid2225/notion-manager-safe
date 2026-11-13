# Notion Manager Safe

[English](README.md) · [Bahasa Indonesia](README.id.md)

Skill AI agent yang mengutamakan keamanan untuk mencatat dan mengelola konten workspace Notion melalui REST API resmi Notion.

> Ini skill komunitas independen, bukan produk resmi Notion. Request API dijalankan secara lokal dengan kredensial milik pengguna; repo ini tidak menyediakan layanan hosted.

> **Catatan API dan kebijakan:** REST adalah jalur utama skill ini. Notion secara resmi mendokumentasikan REST API untuk script dan integrasi. Request memerlukan bearer token dan header `Notion-Version`, serta hanya dapat mengakses konten yang diizinkan untuk kredensial tersebut. Patuhi kontrol workspace, batas penggunaan, keamanan kredensial, dan ketentuan Notion. MCP adalah alternatif opsional jika dipilih pengguna; skill tidak berpindah jalur secara diam-diam.

## Fungsi

- Mencatat dan mengatur catatan umum, record, keputusan, riset, ringkasan meeting, dan dokumentasi project di Notion.
- Menemukan page atau data source yang dimaksud lewat judul melalui API, memastikan parent dan schema jika relevan, lalu memeriksa konten yang sudah ada.
- Menyusun draft dari informasi pengguna dan bukti yang relevan, menampilkan target serta payload yang tepat, lalu menunggu persetujuan.
- Membuat atau memperbarui page melalui endpoint REST terdokumentasi, kemudian membaca hasilnya kembali dan melaporkan URL Notion.
- Mengelola page dan data source Notion secara langsung; tidak memerlukan produk workspace lain.

## Cara kerja

Skill menggunakan request HTTPS ke `https://api.notion.com/v1`. Skill tidak melakukan scraping website Notion atau memanggil endpoint yang tidak terdokumentasi.

1. Autentikasi dengan personal access token (PAT) Notion untuk workflow personal/lokal, atau gunakan OAuth yang dikonfigurasi dengan benar untuk integrasi multi-user.
2. Cari page atau data source berdasarkan judul dengan `POST /v1/search`.
3. Pastikan hasil dan parent yang tepat. Untuk data source, temukan ID dan schema properti terbaru. Jangan hanya mengandalkan ID yang pernah dipakai.
4. Periksa konten yang sudah ada sebelum membuat page atau record. Query data source untuk record; periksa isi parent page jika akan menambahkan catatan di sana.
5. Susun draft dan payload API sesuai schema langsung. Tampilkan tujuan, field, dan nilai secara tepat kepada pengguna.
6. Tunggu persetujuan eksplisit, lalu gunakan `POST /v1/pages` untuk membuat atau `PATCH /v1/pages/{page_id}` untuk memperbarui.
7. Baca ulang page dan query data source sekali lagi. Jika hasilnya belum jelas, lakukan verifikasi sebelum retry agar timeout tidak membuat duplikat.

Versi API saat ini memisahkan database ID dan data source ID. Search dapat menemukan page atau data source; `GET /v1/data_sources/{data_source_id}` menyediakan schema untuk record terstruktur. Catatan biasa juga dapat dibuat sebagai child dari page yang sudah diverifikasi. Lihat [referensi API resmi](https://developers.notion.com/reference/intro) dan [panduan data source](https://developers.notion.com/guides/data-apis/working-with-databases).

## Model keamanan

- Gunakan endpoint REST Notion yang terdokumentasi dan header `Notion-Version` yang wajib. Versi pada contoh adalah versi yang didokumentasikan saat README ini ditinjau; cek halaman versioning sebelum mengubahnya.
- Temukan page atau data source tujuan berdasarkan judul. Jika hasil ambigu, tanyakan mana yang benar. Jangan menyimpulkan tujuan hanya dari ID lama atau URL workspace.
- Untuk record terstruktur, periksa database induk, nama, dan tipe properti sebelum menyusun payload. Jangan membuat database, properti, atau template otomatis.
- Periksa duplikat sebelum membuat record. Gunakan pagination jika perlu; jangan menganggap respons pertama mencakup semua record.
- Minta persetujuan eksplisit sebelum setiap create, update, atau archive. Perubahan massal perlu persetujuan terpisah dengan cakupan dan jumlah yang tepat.
- Jangan menghapus konten permanen. Jangan ulangi write sebelum memeriksa apakah request sebelumnya berhasil.
- Jaga PAT dan secret OAuth agar tidak masuk ke chat, source file, argumen command, log, atau Git. Gunakan environment proses atau secret manager, izin minimum, dan bagikan hanya konten yang diperlukan ke koneksi.
- Baca ulang setiap mutasi dan laporkan URL tujuan serta hal yang sudah diverifikasi.

## Pagination dan error API

Query data source menggunakan cursor pagination. Atur `page_size` maksimal `100`. Gabungkan `results` dari setiap respons; selama `has_more` bernilai `true`, kirim `POST /v1/data_sources/{data_source_id}/query` berikutnya dengan `start_cursor` berisi `next_cursor` dari respons sebelumnya. Berhenti hanya ketika `has_more` bernilai `false`. Halaman hasil yang pendek bukan bukti bahwa query sudah lengkap. Notion membatasi satu query hingga 10.000 hasil; periksa setiap respons untuk `request_status.type = "incomplete"`, lalu persempit atau pecah query yang mencapai batas.

Request halaman pertama:

```sh
curl -X POST 'https://api.notion.com/v1/data_sources/<verified_data_source_id>/query' \
  -H "Authorization: Bearer $NOTION_API_KEY" \
  -H 'Notion-Version: 2026-03-11' \
  -H 'Content-Type: application/json' \
  --data '{"page_size":100}'
```

Jika respons memiliki `has_more: true`, gunakan `next_cursor`-nya pada request berikutnya:

```sh
curl -X POST 'https://api.notion.com/v1/data_sources/<verified_data_source_id>/query' \
  -H "Authorization: Bearer $NOTION_API_KEY" \
  -H 'Notion-Version: 2026-03-11' \
  -H 'Content-Type: application/json' \
  --data '{"page_size":100,"start_cursor":"<next_cursor_from_previous_response>"}'
```

| HTTP | Arti | Tindakan aman |
|---|---|---|
| `400` | Request tidak valid atau schema tidak cocok | Baca `code` dan `message`; koreksi endpoint, header version, nama/tipe property, atau body. Jangan ulangi payload yang sama tanpa perubahan. |
| `401` | Bearer token hilang atau tidak valid | Periksa credential lokal dan integrasi yang dimaksud. Jangan mencetak token. |
| `403` | Credential tidak punya izin atau operasi dibatasi | Pastikan resource dibagikan ke connection dan aksi diizinkan. Jangan memperluas izin otomatis. |
| `404` | ID resource salah, tidak tersedia, atau tidak dibagikan ke credential | Cari ulang berdasarkan nama dan verifikasi parent serta ID. Jangan membuat pengganti sebelum memastikan target asli memang tidak dapat diakses. |
| `409` | Konflik saat menyimpan | Baca state saat ini, perbarui nilai yang stale, dan selesaikan konflik sebelum write lagi. |
| `429` | Batas request tercapai | Patuhi `Retry-After` jika ada dan gunakan backoff terbatas. Jangan mengirim retry paralel. |
| `500`, `502`, `503`, `504`, `529` | Kegagalan server/jaringan, timeout, atau overload | Patuhi `Retry-After` atau `additional_data.retry_guidance` jika tersedia. Write bisa saja berhasil walau respons timeout, jadi baca/query perubahan yang dimaksud sebelum retry. |

Jika hasil write tidak jelas, rekonsiliasi dengan membaca page target dan query record yang diharapkan sebelum mencoba lagi. Jangan menganggap respons gagal berarti mutasi pasti gagal.

## Setup autentikasi

Untuk workflow personal/lokal, buat PAT di [Developer portal Notion](https://www.notion.so/developers/tokens), aktifkan capability **Notion API**, lalu pilih workspace yang dimaksud. Admin workspace dapat membatasi pembuatan PAT. PAT menggunakan izin pembuatnya. Untuk integrasi yang digunakan banyak orang, gunakan OAuth Notion alih-alih berbagi PAT milik satu orang.

Simpan token di environment variable `NOTION_API_KEY` pada proses yang menjalankan agent. Jangan tempel token ke chat, menyimpannya di file `.env` project yang berisiko dikomit, atau mengirimnya sebagai argumen command. Izin Notion tetap berlaku; resource yang tidak dapat diakses mungkin perlu dibagikan kepada connection atau dibuka untuk pemilik PAT.

Atur token hanya untuk sesi terminal saat ini. Contoh berikut membaca token tanpa menampilkannya; jalankan agent dari terminal yang sama agar proses agent mewarisi variable tersebut.

**PowerShell (Windows):**

```powershell
$secureToken = Read-Host 'Notion API token' -AsSecureString
$tokenPtr = [Runtime.InteropServices.Marshal]::SecureStringToBSTR($secureToken)
try {
    $env:NOTION_API_KEY = [Runtime.InteropServices.Marshal]::PtrToStringBSTR($tokenPtr)
} finally {
    [Runtime.InteropServices.Marshal]::ZeroFreeBSTR($tokenPtr)
    $secureToken.Dispose()
    Remove-Variable secureToken, tokenPtr
}
```

**macOS/Linux (Bash atau shell yang kompatibel):**

```sh
read -r -s -p 'Notion API token: ' NOTION_API_KEY
printf '\n'
export NOTION_API_KEY
```

Environment variable dapat dibaca proses turunan yang berjalan sebagai user-mu. Gunakan perangkat pribadi tepercaya, jangan mengaktifkan log request verbose, dan utamakan secret manager yang didukung agent jika tersedia. Jika agent dijalankan dari desktop launcher, atur variable lewat mekanisme environment aman milik client tersebut; variable terminal tidak otomatis diteruskan ke aplikasi yang sudah berjalan.

Setiap request memerlukan header berikut:

```http
Authorization: Bearer <token dari NOTION_API_KEY>
Notion-Version: 2026-03-11
Content-Type: application/json
```

Jangan gunakan placeholder tersebut sebagai kredensial. Baca [panduan keamanan kredensial Notion](https://developers.notion.com/guides/authorization/credential-security).

## Gunakan REST helper

Repo ini menyertakan `scripts/notion_api.py`, CLI kecil untuk Python 3.10+ yang hanya memakai standard library. Script membaca `NOTION_API_KEY` dari environment proses saat ini; tidak perlu memasang package.

```powershell
python scripts/notion_api.py search "Project Notes" --object data_source
python scripts/notion_api.py get_database "<verified_database_id>"
python scripts/notion_api.py get_data_source "<verified_data_source_id>"
python scripts/notion_api.py query_data_source "<verified_data_source_id>"
python scripts/notion_api.py get_page "<verified_page_id>"
python scripts/notion_api.py get_block_children "<verified_page_id>"
```

`search` dan `query_data_source` mengembalikan satu halaman respons, termasuk `has_more` dan `next_cursor` jika tersedia. Teruskan cursor ke pemanggilan berikutnya dengan `--start-cursor` dan pertahankan filter query yang sama. Untuk filter atau sort query, berikan body JSON dengan `--payload-file <path>`.

Write memerlukan file payload UTF-8 dan `--confirm`:

```powershell
python scripts/notion_api.py create_page --payload-file "C:\private\notion-create.json" --confirm
python scripts/notion_api.py update_page "<verified_page_id>" --payload-file "C:\private\notion-update.json" --confirm
```

Helper mengharuskan file payload berada di luar repo, memeriksa bentuk target, mengirim write satu kali, lalu membaca ulang page. Jika payload create berisi `markdown` atau `children`, helper juga membaca block page dan mengembalikan field pagination bila hasilnya lebih dari satu halaman. Helper tidak otomatis mengulang write, menghapus page, atau mengarsipkan konten. `--confirm` adalah pengaman kedua, bukan pengganti menampilkan perubahan yang tepat dan meminta persetujuan pengguna. Output command dapat berisi konten Notion privat; tangani respons dengan hati-hati. Jika hasil write tidak jelas, periksa target sebelum retry.

## Contoh: temukan data source

Gunakan judul database yang tepat atau cukup khas, sesuai yang diberikan pengguna. Request read-only ini mencari data source yang dapat diakses oleh kredensial:

```sh
curl -X POST 'https://api.notion.com/v1/search' \
  -H "Authorization: Bearer $NOTION_API_KEY" \
  -H 'Notion-Version: 2026-03-11' \
  -H 'Content-Type: application/json' \
  --data '{"query":"Project Notes","filter":{"property":"object","value":"data_source"}}'
```

Request read-only yang sama dari PowerShell menggunakan `Invoke-RestMethod`:

```powershell
$headers = @{
    Authorization = "Bearer $env:NOTION_API_KEY"
    "Notion-Version" = "2026-03-11"
}
$body = @{
    query = "Project Notes"
    filter = @{ property = "object"; value = "data_source" }
} | ConvertTo-Json -Depth 5

$result = Invoke-RestMethod -Method Post `
    -Uri "https://api.notion.com/v1/search" `
    -Headers $headers `
    -ContentType "application/json" `
    -Body $body
```

Batasi hasil pada workspace yang dimaksud. Jangan mencetak header otorisasi atau token saat debugging.

Periksa judul hasil, database induk, data source ID, dan propertinya. Jika ada beberapa hasil yang mungkin benar, tanyakan sebelum lanjut. Gunakan `data_source_id` dari hasil untuk membaca schema atau query record. Jangan menggunakan ID contoh atau menganggap database ID sama dengan data source ID. Untuk page biasa, cari dengan filter `object = page`, lalu verifikasi page ID dan parent-nya.

## Contoh payload create dan update

Body JSON berikut adalah template, bukan request siap kirim. Ganti semua placeholder dengan data source ID, nama properti, tipe properti, dan opsi yang sudah diverifikasi dari schema langsung. Sertakan hanya properti yang ada dan disetujui pengguna.

Buat record terstruktur dalam data source dengan `POST /v1/pages`:

```json
{
  "parent": {
    "type": "data_source_id",
    "data_source_id": "<verified_data_source_id>"
  },
  "properties": {
    "<exact_title_property_name>": {
      "title": [{ "text": { "content": "<approved record title>" } }]
    },
    "<exact_rich_text_property_name>": {
      "rich_text": [{ "text": { "content": "<approved note text>" } }]
    },
    "<exact_select_property_name>": {
      "select": { "name": "<existing option from schema>" }
    },
    "<exact_number_property_name>": {
      "number": 12
    },
    "<exact_url_property_name>": {
      "url": "<approved related URL>"
    }
  }
}
```

Untuk catatan mandiri di bawah page yang sudah ada, gunakan page terverifikasi sebagai parent dan kirim konten page sebagai Markdown, bukan properti data source:

```json
{
  "parent": {
    "type": "page_id",
    "page_id": "<verified_parent_page_id>"
  },
  "properties": {
    "title": {
      "title": [{ "text": { "content": "<approved note title>" } }]
    }
  },
  "markdown": "<approved note content>"
}
```

Gunakan hanya parent yang memang dimaksud pengguna. Jika pengguna meminta menambahkan konten di dalam page yang sudah ada, gunakan endpoint block content yang terdokumentasi dan verifikasi block hasilnya.

Untuk update, gunakan `PATCH /v1/pages/{verified_page_id}` dan kirim hanya properti yang disetujui untuk diubah. Properti yang tidak dikirim akan tetap memakai nilai saat ini:

```json
{
  "properties": {
    "<exact_rich_text_property_name>": {
      "rich_text": [{ "text": { "content": "<approved replacement text>" } }]
    }
  }
}
```

Nama properti, tipe data, dan opsi select harus berasal dari schema data source tujuan yang dibaca langsung. Properti bertipe `status`, misalnya, perlu bentuk nilai sesuai schema-nya sendiri; jangan menganggapnya bertipe `select` atau `rich_text`. Setelah menulis, ambil kembali page dan verifikasi properti yang berubah.

### Request REST lengkap

Contoh berikut mencakup endpoint, header, dan body. Ganti semua placeholder memakai schema data source yang dibaca langsung dan nilai yang disetujui pengguna. Contoh ini bukan izin untuk langsung menulis; tampilkan target serta payload dan minta persetujuan terlebih dahulu.

Buat page record:

```sh
curl -X POST 'https://api.notion.com/v1/pages' \
  -H "Authorization: Bearer $NOTION_API_KEY" \
  -H 'Notion-Version: 2026-03-11' \
  -H 'Content-Type: application/json' \
  --data-binary @- <<'JSON'
{
  "parent": {
    "type": "data_source_id",
    "data_source_id": "<verified_data_source_id>"
  },
  "properties": {
    "<exact_title_property_name>": {
      "title": [{ "text": { "content": "<approved title>" } }]
    },
    "<exact_rich_text_property_name>": {
      "rich_text": [{ "text": { "content": "<approved text>" } }]
    }
  }
}
JSON
```

Perbarui hanya property yang disetujui pada page yang sudah diverifikasi:

```sh
curl -X PATCH 'https://api.notion.com/v1/pages/<verified_page_id>' \
  -H "Authorization: Bearer $NOTION_API_KEY" \
  -H 'Notion-Version: 2026-03-11' \
  -H 'Content-Type: application/json' \
  --data-binary @- <<'JSON'
{
  "properties": {
    "<exact_rich_text_property_name>": {
      "rich_text": [{ "text": { "content": "<approved replacement text>" } }]
    }
  }
}
JSON
```

Nama property dan bentuk nilainya hanya ilustrasi. Salin nama dan tipe dari schema yang sudah diverifikasi; kirim hanya field yang disetujui. Simpan token di environment proses, jangan mengganti placeholder dengan nilai token literal di command.

Request create lengkap yang setara di PowerShell:

```powershell
$headers = @{
    Authorization = "Bearer $env:NOTION_API_KEY"
    "Notion-Version" = "2026-03-11"
}
$createBody = @{
    parent = @{
        type = "data_source_id"
        data_source_id = "<verified_data_source_id>"
    }
    properties = @{
        "<exact_title_property_name>" = @{
            title = @(@{ text = @{ content = "<approved title>" } })
        }
        "<exact_rich_text_property_name>" = @{
            rich_text = @(@{ text = @{ content = "<approved text>" } })
        }
    }
} | ConvertTo-Json -Depth 10

$created = Invoke-RestMethod -Method Post `
    -Uri "https://api.notion.com/v1/pages" `
    -Headers $headers `
    -ContentType "application/json" `
    -Body $createBody
$created.url
```

Request update yang setara; kirim hanya property yang disetujui untuk diubah:

```powershell
$updateBody = @{
    properties = @{
        "<exact_rich_text_property_name>" = @{
            rich_text = @(@{ text = @{ content = "<approved replacement text>" } })
        }
    }
} | ConvertTo-Json -Depth 10

$updated = Invoke-RestMethod -Method Patch `
    -Uri "https://api.notion.com/v1/pages/<verified_page_id>" `
    -Headers $headers `
    -ContentType "application/json" `
    -Body $updateBody
$updated.url
```

## Contoh interaksi

```text
Pengguna: Simpan keputusan hari ini di database catatan project saya.

Agent: REST search menemukan satu data source “Project Notes”. Saya
memeriksa parent dan schema, lalu mencari record dengan judul yang sama.
Saya menyusun record baru berisi ringkasan keputusan dan tanggal. Apakah kamu
menyetujui nilai-nilai ini?

Pengguna: Ya, buat.

Agent: Page dibuat lewat Notion API, lalu dibaca ulang. URL-nya: <URL Notion>
```

Contoh menggunakan konten workspace fiktif. Temukan tujuan dan schema aktual, lalu minta persetujuan sebelum menulis.

## Transport MCP opsional

Notion juga menyediakan remote MCP resmi di `https://mcp.notion.com/mcp`. REST tetap menjadi default. Gunakan MCP hanya jika REST tidak tersedia, gagal autentikasi/koneksi, tidak dapat menangani operasi dengan aman, atau pengguna secara eksplisit meminta MCP. Jangan berpindah transport diam-diam; laporkan fallback dan rekonsiliasi state sebelum retry write.

Helper menangani transport dan read-back rutin. Skill tetap mengatur penemuan target, pemeriksaan schema dan duplikat, review draft, persetujuan, serta keputusan verifikasi.

## Pasang sebagai agent skill

Clone repo ini, lalu salin `SKILL.md`, folder `scripts/`, dan `agents/` ke direktori skill yang digunakan client-mu:

| Agent | Direktori skill personal |
|---|---|
| Codex | `~/.agents/skills/notion-manager-safe/` |
| Claude Code | `~/.claude/skills/notion-manager-safe/` |
| OpenCode | `~/.config/opencode/skills/notion-manager-safe/` |

Lokasi dan cara menemukan skill bisa berubah; periksa dokumentasi agent jika skill tidak terbaca. Setelah instalasi, panggil helper menggunakan absolute path di dalam folder skill agar dapat dipakai dari project lain. Memasang skill tidak membuat PAT atau memberi akses ke workspace.

## Struktur repo

| Path | Fungsi |
|---|---|
| `SKILL.md` | Instruksi agent dan workflow REST |
| `scripts/notion_api.py` | Helper REST standard library untuk search, read, create/update terjaga, dan read-back |
| `agents/openai.yaml` | Metadata antarmuka agent opsional |
| `README.md` | Dokumentasi bahasa Inggris |
| `README.id.md` | Dokumentasi Bahasa Indonesia |
| `LICENSE` | Lisensi MIT untuk materi repo ini |
| `SECURITY.md` | Panduan pelaporan kerentanan secara privat |

## Referensi resmi

- [Pengantar Notion API](https://developers.notion.com/reference/intro)
- [Quickstart Notion API](https://developers.notion.com/guides/notion-api/quick-start)
- [Search berdasarkan judul](https://developers.notion.com/reference/post-search)
- [Ambil data source](https://developers.notion.com/reference/retrieve-a-data-source)
- [Query data source](https://developers.notion.com/reference/query-a-data-source)
- [Pagination](https://developers.notion.com/reference/pagination)
- [Buat page](https://developers.notion.com/reference/post-page)
- [Update page](https://developers.notion.com/reference/patch-page)
- [Error API](https://developers.notion.com/reference/errors)
- [Batas request](https://developers.notion.com/reference/request-limits)
- [Ringkasan otorisasi](https://developers.notion.com/guides/authorization/overview)
- [Personal access token](https://developers.notion.com/guides/connections-and-tokens/personal-access-tokens)
- [Keamanan kredensial API](https://developers.notion.com/guides/authorization/credential-security)
- [Versioning Notion API](https://developers.notion.com/reference/versioning)
- [Ketentuan Layanan Notion](https://www.notion.so/terms)

## Lisensi dan keamanan

Materi repo ini menggunakan [lisensi MIT](LICENSE). Notion dan konten workspace tetap mengikuti ketentuan Notion serta kontrol pemilik workspace. Laporkan masalah keamanan secara privat melalui fitur **Report a vulnerability** di GitHub; jangan sertakan kredensial atau konten workspace privat. Lihat [SECURITY.md](SECURITY.md).
