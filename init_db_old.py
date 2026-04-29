# init_db.py
"""
Script untuk inisialisasi database dan import data dari Excel
dengan logika kategori yang lebih fleksibel untuk menghindari data yang ter-skip
"""
import os
import sys
import pandas as pd
from flask import Flask
from database import db, User, FoodCategory, StapleType, Food, AllergenMapping
import re

def create_app():
    """Buat Flask app untuk inisialisasi database"""
    app = Flask(__name__)
    
    # Konfigurasi database
    basedir = os.path.abspath(os.path.dirname(__file__))
    app.config['SQLALCHEMY_DATABASE_URI'] = f'sqlite:///{os.path.join(basedir, "smartdiabetes.db")}'
    app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
    app.config['SECRET_KEY'] = 'your-secret-key-change-this'
    
    return app


def normalize_category(jenis_makanan: str) -> str:
    """
    Normalisasi nama kategori dari Excel ke kategori database yang baku
    
    Args:
        jenis_makanan: String kategori dari kolom 'Jenis Makanan' di Excel
    
    Returns:
        Nama kategori yang sudah dinormalisasi: 'Pokok', 'Lauk', 'Sayur', 'Buah', atau 'Lain-lain'
    """
    if not jenis_makanan or pd.isna(jenis_makanan):
        return 'Lain-lain'
    
    # Konversi ke lowercase untuk matching yang case-insensitive
    jenis_lower = str(jenis_makanan).lower().strip()
    
    # Keyword mapping untuk setiap kategori
    pokok_keywords = ['pokok', 'nasi', 'mie', 'mi', 'roti', 'pasta', 'kentang', 'singkong', 'ubi', 'jagung', 'sagu', 'bihun', 'makaroni', 'spaghetti', 'ketupat', 'lontong']
    lauk_keywords = ['lauk', 'daging', 'ikan', 'telur', 'ayam', 'sapi', 'kambing', 'bebek', 'seafood', 'udang', 'cumi', 'kepiting', 'tempe', 'tahu', 'protein']
    sayur_keywords = ['sayur', 'sayuran', 'vegetable']
    buah_keywords = ['buah', 'fruit']
    
    # Check untuk Pokok
    if any(keyword in jenis_lower for keyword in pokok_keywords):
        return 'Pokok'
    
    # Check untuk Lauk
    if any(keyword in jenis_lower for keyword in lauk_keywords):
        return 'Lauk'
    
    # Check untuk Sayur
    if any(keyword in jenis_lower for keyword in sayur_keywords):
        return 'Sayur'
    
    # Check untuk Buah
    if any(keyword in jenis_lower for keyword in buah_keywords):
        return 'Buah'
    
    # Default: Lain-lain (untuk bumbu, minuman, dll)
    return 'Lain-lain'


def import_from_excel(excel_path: str, admin_user_id: int = 1):
    """
    Import data makanan dari file Excel ke database
    
    Args:
        excel_path: Path ke file Excel TKPI
        admin_user_id: ID user admin yang melakukan import (default: 1)
    """
    print(f"\n📁 Membaca file Excel: {excel_path}")
    
    if not os.path.exists(excel_path):
        print(f"❌ File tidak ditemukan: {excel_path}")
        return False
    
    try:
        # Baca Excel
        df = pd.read_excel(excel_path, engine='openpyxl')
        df.columns = df.columns.str.strip()
        
        print(f"✓ Berhasil membaca {len(df)} baris data")
        print(f"  Kolom yang tersedia: {list(df.columns)}")
        
        # Mapping kolom Excel ke database
        # Sesuaikan dengan nama kolom di Excel Anda
        column_mapping = {
            'Nama_Bahan': 'nama_bahan',
            'BDD ( 100% )': 'bdd',  # Updated column name
            'Energi (kal)': 'energi',
            'Protein (g)': 'protein',
            'Lemak (g)': 'lemak',
            'Karbohidrat (g)': 'karbohidrat',
            'Serat (g)': 'serat',
            'Jenis Makanan': 'kategori',  # Updated: Pokok/Lauk/Sayur/Buah
            'Tipe Pokok': 'tipe_pokok',  # Sederhana/Lengkap (hanya untuk kategori Pokok)
        }
        
        # Ambil kategori dari database
        categories = {cat.name: cat.id for cat in FoodCategory.query.all()}
        staple_types = {st.name: st.id for st in StapleType.query.all()}
        
        print(f"\n📦 Kategori tersedia: {list(categories.keys())}")
        print(f"📦 Tipe pokok tersedia: {list(staple_types.keys())}")
        
        imported_count = 0
        skipped_count = 0
        error_count = 0
        
        # Logging untuk data cleaning
        print(f"\n🔄 Memulai proses pembersihan dan konversi data...")
        print(f"   Total baris untuk diproses: {len(df)}")
        
        # Statistik konversi numerik
        numeric_columns = ['BDD ( 100% )', 'Energi (kal)', 'Protein (g)', 'Lemak (g)', 'Karbohidrat (g)', 'Serat (g)']
        conversion_stats = {col: {'success': 0, 'failed': 0, 'total': 0} for col in numeric_columns}
        
        for idx, row in df.iterrows():
            try:
                # Ambil data dari row
                nama_bahan = str(row.get('Nama_Bahan', '')).strip()
                if not nama_bahan or nama_bahan.lower() == 'nan':
                    skipped_count += 1
                    continue
                
                # Cek apakah sudah ada di database
                existing = Food.query.filter_by(nama_bahan=nama_bahan).first()
                if existing:
                    print(f"  ⚠️  Skip (sudah ada): {nama_bahan}")
                    skipped_count += 1
                    continue
                
                # Ambil kategori
                kategori_name = str(row.get('Jenis Makanan', 'Pokok')).strip()
                category_id = categories.get(kategori_name)
                
                if not category_id:
                    print(f"  ⚠️  Skip (kategori tidak valid): {nama_bahan} - {kategori_name}")
                    skipped_count += 1
                    continue
                
                # Ambil tipe pokok (hanya untuk kategori Pokok)
                staple_type_id = None
                if kategori_name == 'Pokok':
                    tipe_pokok = str(row.get('Tipe_Pokok', 'Sederhana')).strip()
                    staple_type_id = staple_types.get(tipe_pokok)
                
                # Konversi dan validasi data numerik dengan logging
                numeric_data = {}
                for col_name, db_field in [('BDD ( 100% )', 'bdd'), ('Energi (kal)', 'energi'), 
                                           ('Protein (g)', 'protein'), ('Lemak (g)', 'lemak'),
                                           ('Karbohidrat (g)', 'karbohidrat'), ('Serat (g)', 'serat')]:
                    try:
                        value = row.get(col_name, 0 if col_name != 'BDD ( 100% )' else 100.0)
                        numeric_data[db_field] = float(value) if value != '' else (0.0 if col_name != 'BDD ( 100% )' else 100.0)
                        conversion_stats[col_name]['success'] += 1
                        conversion_stats[col_name]['total'] += 1
                    except (ValueError, TypeError) as e:
                        conversion_stats[col_name]['failed'] += 1
                        conversion_stats[col_name]['total'] += 1
                        numeric_data[db_field] = 0.0 if col_name != 'BDD ( 100% )' else 100.0
                        if imported_count < 5:  # Log hanya 5 error pertama
                            print(f"  ⚠️  Konversi gagal untuk {nama_bahan} - {col_name}: {value} -> default")
                
                # Buat record Food
                food = Food(
                    nama_bahan=nama_bahan,
                    bdd=numeric_data['bdd'],
                    energi=numeric_data['energi'],
                    protein=numeric_data['protein'],
                    lemak=numeric_data['lemak'],
                    karbohidrat=numeric_data['karbohidrat'],
                    serat=numeric_data['serat'],
                    category_id=category_id,
                    staple_type_id=staple_type_id,
                    created_by=admin_user_id
                )
                
                db.session.add(food)
                db.session.flush()  # Dapatkan ID untuk mapping alergen
                
                # Auto-detect alergen dari nama makanan
                allergens_detected = detect_allergens(nama_bahan)
                for allergen in allergens_detected:
                    allergen_map = AllergenMapping(
                        food_id=food.id,
                        allergen_name=allergen
                    )
                    db.session.add(allergen_map)
                
                imported_count += 1
                
                if imported_count % 50 == 0:
                    print(f"  ✓ Imported {imported_count} items...")
                    db.session.commit()
            
            except Exception as e:
                print(f"  ❌ Error pada baris {idx}: {e}")
                error_count += 1
                skipped_count += 1
                continue
        
        # Commit terakhir
        db.session.commit()
        
        print(f"\n✅ Import selesai!")
        print(f"   - Berhasil: {imported_count}")
        print(f"   - Dilewati: {skipped_count}")
        print(f"   - Error: {error_count}")
        print(f"   - Total di database: {Food.query.count()}")
        
        # Tampilkan statistik konversi numerik
        print(f"\n📊 Statistik Konversi Data Numerik:")
        print(f"   {'Kolom':<20} {'Berhasil':<10} {'Gagal':<10} {'Total':<10} {'Success Rate':<15}")
        print(f"   {'-'*70}")
        for col_name, stats in conversion_stats.items():
            if stats['total'] > 0:
                success_rate = (stats['success'] / stats['total']) * 100
                print(f"   {col_name:<20} {stats['success']:<10} {stats['failed']:<10} {stats['total']:<10} {success_rate:>6.2f}%")
        
        # Summary
        total_conversions = sum(s['total'] for s in conversion_stats.values())
        total_success = sum(s['success'] for s in conversion_stats.values())
        total_failed = sum(s['failed'] for s in conversion_stats.values())
        
        print(f"\n   {'='*70}")
        print(f"   {'TOTAL':<20} {total_success:<10} {total_failed:<10} {total_conversions:<10} {(total_success/total_conversions*100):>6.2f}%")
        
        if total_failed == 0:
            print(f"\n✨ SEMPURNA! Semua data berhasil dikonversi ke format numerik tanpa error!")
            print(f"   ✓ {total_success} konversi numerik berhasil")
            print(f"   ✓ {imported_count} makanan siap diproses")
            print(f"   ✓ Data siap untuk tahap selanjutnya")
        else:
            print(f"\n⚠️  Terdapat {total_failed} konversi yang menggunakan nilai default")
        
        return True
    
    except Exception as e:
        print(f"❌ Error saat import: {e}")
        db.session.rollback()
        return False


def detect_allergens(nama_bahan: str) -> list:
    """
    Auto-detect alergen dari nama makanan menggunakan regex pattern
    Sama seperti yang ada di model.py
    """
    allergen_patterns = {
        'ikan': r'\b(ikan|kakap|tuna|salmon|gurame|lele|nila|tongkol|bandeng|teri)\b',
        'udang': r'\b(udang|shrimp|rebon|ebi|lobster)\b',
        'seafood': r'\b(cumi|kerang|kepiting|rajungan|terasi)\b',
        'kacang': r'\b(kacang|peanut|almond|mede|kedelai)\b',
        'susu': r'\b(susu|milk|keju|cheese|yogurt|mentega|butter|krim)\b',
        'telur': r'\b(telur|telor|egg)\b',
        'gluten': r'\b(gandum|wheat|terigu|roti|mie|mi|pasta)\b',
    }
    
    detected = []
    nama_lower = nama_bahan.lower()
    
    for allergen, pattern in allergen_patterns.items():
        if re.search(pattern, nama_lower):
            detected.append(allergen)
    
    return detected


def main():
    """Main function untuk inisialisasi database"""
    print("=" * 60)
    print("  SMART DIABETES - Database Initialization")
    print("=" * 60)
    
    app = create_app()
    
    with app.app_context():
        # Inisialisasi database (buat tabel, seed data default)
        init_db(app)
        
        print("\n" + "=" * 60)
        print("  Import Data dari Excel (Opsional)")
        print("=" * 60)
        
        # Tanyakan apakah ingin import dari Excel
        excel_path = input("\nMasukkan path file Excel TKPI (atau Enter untuk skip): ").strip()
        
        if excel_path and os.path.exists(excel_path):
            import_from_excel(excel_path)
        elif excel_path:
            print(f"⚠️  File tidak ditemukan: {excel_path}")
            print("   Database sudah diinisialisasi tanpa data makanan.")
            print("   Anda bisa menambahkan data via Admin Panel nanti.")
        else:
            print("✓ Skip import Excel. Database sudah siap digunakan.")
        
        print("\n" + "=" * 60)
        print("  🎉 Setup Selesai!")
        print("=" * 60)
        print("\n📊 Ringkasan Database:")
        print(f"   - Users: {User.query.count()}")
        print(f"   - Categories: {FoodCategory.query.count()}")
        print(f"   - Staple Types: {StapleType.query.count()}")
        print(f"   - Foods: {Food.query.count()}")
        print(f"   - Allergen Mappings: {AllergenMapping.query.count()}")
        
        print("\n🔐 Akun Admin:")
        admin = User.query.filter_by(username='admin').first()
        if admin:
            print(f"   ✅ Admin account created successfully")
            print(f"   📧 Check your email or contact developer for credentials")
        
        print("\n🚀 Langkah Selanjutnya:")
        print("   1. Install dependencies: pip install -r requirements.txt")
        print("   2. Jalankan aplikasi: python app.py")
        print("   3. Login sebagai admin di: http://localhost:5000/admin/login")
        print("   4. Kelola data makanan via Admin Panel")
        print("\n" + "=" * 60)


if __name__ == '__main__':
    main()
