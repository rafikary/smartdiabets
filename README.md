# Smart Diabetes - Sistem Rekomendasi Makanan

Sistem rekomendasi makanan untuk penderita diabetes dengan admin panel untuk mengelola database makanan.

## 📋 Fitur Utama

### User Features
- ✅ Kalkulator kebutuhan kalori berdasarkan profil (usia, tinggi, berat, aktivitas)
- ✅ Rekomendasi menu makanan 5 waktu (Pagi, Siang, Sore, Snack 1, Snack 2)
- ✅ Filter alergi makanan (kacang, susu, seafood, telur, kedelai, gluten)
- ✅ Fitur ganti menu
- ✅ Perhitungan akurasi nutrisi (RMSE)

### Admin Features (NEW!)
- 🔐 **Login System** untuk admin
- 📊 **Dashboard** dengan statistik dan grafik
- 🍽️ **Kelola Makanan (CRUD)**
  - Tambah makanan manual
  - Edit data makanan
  - Hapus makanan
  - Pencarian dan filter
  - Pagination
- 🏷️ **Kelola Kategori**
  - Kategori: Pokok, Lauk, Sayur, Buah
  - Tipe Pokok: Sederhana, Lengkap
- ☁️ **Upload Excel**
  - Import data TKPI dari file Excel
  - Auto-detect alergen
- 🔍 **Filter & Search**
- 📝 **Activity Log** untuk audit trail

## 🛠️ Teknologi

- **Backend**: Flask (Python)
- **Database**: SQLite (simple, file-based)
- **ORM**: Flask-SQLAlchemy
- **Authentication**: Flask-Login
- **Frontend**: Bootstrap 5 + Bootstrap Icons
- **Data Processing**: Pandas, NumPy
- **Charts**: Chart.js

## 📦 Instalasi

### 1. Install Dependencies

```bash
pip install -r requirements.txt
```

### 2. Inisialisasi Database

```bash
python init_db.py
```

Script ini akan:
- ✅ Membuat database `smartdiabetes.db`
- ✅ Membuat tabel-tabel yang diperlukan
- ✅ Seed kategori default (Pokok, Lauk, Sayur, Buah)
- ✅ Seed tipe pokok default (Sederhana, Lengkap)
- ✅ Membuat akun admin default
- ✅ (Opsional) Import data dari Excel

**Akun Admin Default:**
- Username: `admin`
- Password: `admin123`
- ⚠️ **SEGERA GANTI PASSWORD** setelah login!

### 3. Jalankan Aplikasi

```bash
python app.py
```

Aplikasi akan berjalan di: `http://localhost:5000`

## 🎯 Struktur Database

### Tabel Users
- `id`, `username`, `email`, `password_hash`, `is_admin`

### Tabel Food Categories
- `id`, `name`, `description`
- Default: Pokok, Lauk, Sayur, Buah

### Tabel Staple Types
- `id`, `name`, `description`
- Default: Sederhana, Lengkap

### Tabel Foods
- `id`, `nama_bahan`, `bdd`, `energi`, `protein`, `lemak`, `karbohidrat`, `serat`
- `category_id`, `staple_type_id`
- `created_at`, `updated_at`, `created_by`

### Tabel Allergen Mappings
- `id`, `food_id`, `allergen_name`

### Tabel Activity Logs
- `id`, `user_id`, `action`, `table_name`, `record_id`, `details`

## 🔐 Akses Admin Panel

### Login
1. Buka: `http://localhost:5000/admin/login`
2. Masukkan username dan password
3. Klik **Login**

### Dashboard
- Lihat statistik: total makanan, kategori, alergen
- Grafik distribusi makanan per kategori
- Daftar makanan terbaru
- Tombol aksi cepat

### Kelola Makanan

#### Tambah Makanan Manual
1. Menu: **Kelola Makanan** → **Tambah Makanan**
2. Isi form:
   - Nama Makanan (wajib)
   - Kategori (wajib): Pokok/Lauk/Sayur/Buah
   - Tipe Pokok (jika kategori = Pokok): Sederhana/Lengkap
   - BDD (%)
   - Energi (kkal) - wajib
   - Protein (g) - wajib
   - Lemak (g) - wajib
   - Karbohidrat (g) - wajib
   - Serat (g)
   - Alergen (checkbox)
3. Klik **Simpan Makanan**

#### Edit Makanan
1. Daftar Makanan → Klik tombol **Edit** (icon pensil)
2. Update data
3. Klik **Update Makanan**

#### Hapus Makanan
1. Daftar Makanan → Klik tombol **Hapus** (icon tempat sampah)
2. Konfirmasi penghapusan

#### Filter & Pencarian
- **Search**: Cari berdasarkan nama makanan
- **Filter Kategori**: Tampilkan makanan berdasarkan kategori tertentu
- **Pagination**: Navigasi antar halaman (default 20 item per halaman)

### Upload Excel

#### Format File
File Excel harus memiliki kolom-kolom berikut:

**Kolom Wajib:**
- `Nama_Bahan`
- `Energi (kal)`
- `Protein (g)`
- `Lemak (g)`
- `Karbohidrat (g)`

**Kolom Opsional:**
- `BDD` (default: 100)
- `Serat (g)` (default: 0)
- `Kategori` (default: Pokok)
- `Tipe_Pokok` (hanya untuk kategori Pokok)

#### Contoh Excel

| Nama_Bahan | BDD | Energi (kal) | Protein (g) | Lemak (g) | Karbohidrat (g) | Serat (g) | Kategori | Tipe_Pokok |
|------------|-----|--------------|-------------|-----------|-----------------|-----------|----------|------------|
| Nasi Putih | 100 | 180 | 3.4 | 0.3 | 40.6 | 0.3 | Pokok | Sederhana |
| Nasi Merah | 100 | 149 | 2.8 | 0.4 | 32.5 | 0.8 | Pokok | Lengkap |
| Ayam Bakar | 100 | 164 | 26.2 | 6.2 | 0 | 0 | Lauk | |
| Bayam | 100 | 36 | 3.5 | 0.5 | 6.5 | 2.2 | Sayur | |
| Apel | 100 | 58 | 0.3 | 0.2 | 14.9 | 2.4 | Buah | |

#### Cara Upload
1. Menu: **Upload Excel**
2. Klik **Pilih File** → Pilih file Excel (.xlsx atau .xls)
3. Klik **Upload & Import**
4. Sistem akan:
   - Validasi format file
   - Cek duplikat (skip jika nama makanan sudah ada)
   - Auto-detect alergen dari nama makanan
   - Insert ke database
5. Lihat hasil import (berapa berhasil, berapa dilewati)

### Kelola Kategori & Tipe Pokok

#### Tambah Kategori Baru
1. Menu: **Kelola Kategori**
2. Klik **Tambah** di card "Kategori Makanan"
3. Isi nama dan deskripsi
4. Klik **Simpan**

#### Tambah Tipe Pokok Baru
1. Menu: **Kelola Kategori**
2. Klik **Tambah** di card "Tipe Makanan Pokok"
3. Isi nama dan deskripsi
4. Klik **Simpan**

## 📊 Database Management

### Backup Database
Database disimpan dalam 1 file: `smartdiabetes.db`

Untuk backup, cukup copy file ini:
```bash
# Windows
copy smartdiabetes.db smartdiabetes_backup_YYYY-MM-DD.db

# Linux/Mac
cp smartdiabetes.db smartdiabetes_backup_$(date +%Y-%m-%d).db
```

### Reset Database
Hapus file database dan jalankan ulang init_db.py:
```bash
# Windows
del smartdiabetes.db
python init_db.py

# Linux/Mac
rm smartdiabetes.db
python init_db.py
```

### Export Database ke Excel
```python
import pandas as pd
from database import db, Food

# Buat connection ke database
df = pd.read_sql_query("SELECT * FROM foods", db.engine)
df.to_excel("export_foods.xlsx", index=False)
```

### View Database dengan GUI
Download **DB Browser for SQLite**: https://sqlitebrowser.org/

1. Open Database → Pilih `smartdiabetes.db`
2. Browse Data → Lihat isi tabel
3. Execute SQL → Jalankan query custom

## 🔒 Keamanan

### Password Hashing
- Password admin di-hash menggunakan `werkzeug.security`
- TIDAK disimpan dalam plaintext
- Gunakan password yang kuat!

### Secret Key
Edit file `app.py` dan `init_db.py`, ganti:
```python
app.config['SECRET_KEY'] = 'your-secret-key-change-this-in-production'
```

Generate random secret key:
```python
import secrets
print(secrets.token_hex(32))
```

### Ganti Password Admin
1. Login sebagai admin
2. (Future: akan ada halaman settings)
3. Atau via Python:
```python
from database import db, User
from flask import Flask
from database import init_db

app = Flask(__name__)
app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///smartdiabetes.db'
init_db(app)

with app.app_context():
    admin = User.query.filter_by(username='admin').first()
    admin.set_password('password_baru_anda')
    db.session.commit()
    print("Password berhasil diganti!")
```

## 🐛 Troubleshooting

### Error: No module named 'flask_sqlalchemy'
```bash
pip install -r requirements.txt
```

### Error: Database is locked
Tutup semua aplikasi yang membuka database (DB Browser, dll)

### Error: UNIQUE constraint failed
Data sudah ada di database (nama makanan duplikat). Skip atau ganti nama.

### Error: Template not found
Pastikan semua file template ada di folder `templates/admin/`

### Admin login tidak berhasil
1. Cek username/password
2. Reset database dan jalankan `init_db.py` lagi
3. Cek log error di terminal

## 📝 TODO / Pengembangan Selanjutnya

- [ ] User registration untuk user biasa (non-admin)
- [ ] User profile dan history rekomendasi
- [ ] Export/download rekomendasi ke PDF
- [ ] Fitur feedback/rating menu
- [ ] API endpoint untuk mobile app
- [ ] Multi-language support
- [ ] Email notification untuk admin
- [ ] Advanced analytics & reporting
- [ ] Bulk edit makanan
- [ ] Import/export kategori

## 👥 Tim Pengembang

Smart Diabetes - Sistem Rekomendasi Makanan untuk Penderita Diabetes

## 📄 Lisensi

Copyright © 2026. All rights reserved.

---

**Catatan Penting untuk Dosen Pembimbing:**

Sistem ini sudah dilengkapi dengan admin panel yang memungkinkan pengelolaan dataset makanan secara mandiri tanpa perlu akses langsung ke database. Admin dapat:

1. ✅ Menambah/edit/hapus data makanan via web interface
2. ✅ Upload data TKPI dari Excel secara batch
3. ✅ Mengelola kategori makanan (Pokok, Lauk, Sayur, Buah)
4. ✅ Mengelola tipe makanan pokok (Sederhana, Lengkap)
5. ✅ Melihat log aktivitas perubahan data

Database menggunakan **SQLite** yang sangat simple:
- ✅ Tidak perlu install MySQL/PostgreSQL
- ✅ Satu file database saja
- ✅ Mudah di-backup (copy file)
- ✅ Bisa dibuka dengan GUI (DB Browser for SQLite)
- ✅ Cocok untuk skala project TA/tugas akhir

Jika di masa depan perlu scale up, SQLAlchemy memudahkan migrasi ke MySQL/PostgreSQL hanya dengan mengganti connection string.
