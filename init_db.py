# init_db.py
"""
Script untuk inisialisasi database dan import data dari Excel
dengan logika kategori yang lebih fleksibel
"""
import os
import pandas as pd
from flask import Flask
from database import db, User, FoodCategory, StapleType, Food, AllergenMapping
import re

def create_app():
    app = Flask(__name__)
    basedir = os.path.abspath(os.path.dirname(__file__))
    app.config["SQLALCHEMY_DATABASE_URI"] = f"sqlite:///{os.path.join(basedir, 'smartdiabetes.db')}"
    app.config["SQLALCHEMY_TRACK_MODIFICATIONS"] = False
    app.config["SECRET_KEY"] = "your-secret-key-change-this"
    return app

def normalize_category(jenis_makanan: str) -> str:
    if not jenis_makanan or pd.isna(jenis_makanan):
        return "Lain-lain"
    jenis_lower = str(jenis_makanan).lower().strip()
    pokok_kw = ["pokok", "nasi", "mie", "mi", "roti", "pasta", "kentang", "singkong", "ubi", "jagung", "sagu", "bihun", "makaroni", "spaghetti", "ketupat", "lontong"]
    lauk_kw = ["lauk", "daging", "ikan", "telur", "ayam", "sapi", "kambing", "bebek", "seafood", "udang", "cumi", "kepiting", "tempe", "tahu", "protein"]
    sayur_kw = ["sayur", "sayuran", "vegetable"]
    buah_kw = ["buah", "fruit"]
    if any(k in jenis_lower for k in pokok_kw): return "Pokok"
    if any(k in jenis_lower for k in lauk_kw): return "Lauk"
    if any(k in jenis_lower for k in sayur_kw): return "Sayur"
    if any(k in jenis_lower for k in buah_kw): return "Buah"
    return "Lain-lain"

def detect_allergens(nama_bahan: str) -> list:
    allergen_patterns = {
        "ikan": r"\b(ikan|kakap|tuna|salmon|gurame|lele|nila|tongkol|bandeng|teri)\b",
        "udang": r"\b(udang|shrimp|rebon|ebi|lobster)\b",
        "seafood": r"\b(cumi|kerang|kepiting|rajungan|terasi)\b",
        "kacang": r"\b(kacang|peanut|almond|mede|kedelai)\b",
        "susu": r"\b(susu|milk|keju|cheese|yogurt|mentega|butter|krim)\b",
        "telur": r"\b(telur|telor|egg)\b",
        "gluten": r"\b(gandum|wheat|terigu|roti|mie|mi|pasta)\b",
    }
    detected = []
    nama_lower = nama_bahan.lower()
    for allergen, pattern in allergen_patterns.items():
        if re.search(pattern, nama_lower):
            detected.append(allergen)
    return detected

def import_from_excel(excel_path: str, admin_user_id: int = 1):
    if not os.path.exists(excel_path):
        print(f"Error: File not found - {excel_path}")
        return False
    try:
        df = pd.read_excel(excel_path, engine="openpyxl")
        df.columns = df.columns.str.strip()
        
        categories = {cat.name: cat.id for cat in FoodCategory.query.all()}
        staple_types = {st.name: st.id for st in StapleType.query.all()}
        
        total_rows = len(df)
        imported_count = 0
        skipped_count = 0
        error_count = 0
        category_stats = {cat: 0 for cat in categories.keys()}
        
        print(f"Reading {total_rows} rows from Excel file...")
        print("Processing data: ", end='', flush=True)
        
        for idx, row in df.iterrows():
            try:
                nama_bahan = str(row.get("Nama_Bahan", "")).strip()
                if not nama_bahan or nama_bahan.lower() in ["nan", "none", ""]:
                    skipped_count += 1
                    continue
                if Food.query.filter_by(nama_bahan=nama_bahan).first():
                    skipped_count += 1
                    continue
                original_category = str(row.get("Jenis Makanan", "")).strip()
                normalized_category = normalize_category(original_category)
                category_id = categories.get(normalized_category)
                if not category_id:
                    skipped_count += 1
                    continue
                staple_type_id = None
                if normalized_category == "Pokok":
                    tipe = str(row.get("Tipe Pokok", "Sederhana")).strip()
                    if tipe in staple_types:
                        staple_type_id = staple_types[tipe]
                def parse_nutrient(value, default=0.0):
                    if pd.isna(value) or value == "-" or value == "":
                        return default
                    try:
                        if isinstance(value, str):
                            value = value.replace(",", ".")
                        return float(value)
                    except:
                        return default
                food = Food(
                    nama_bahan=nama_bahan,
                    bdd=parse_nutrient(row.get("BDD ( 100% )", 100.0), 100.0),
                    energi=parse_nutrient(row.get("Energi (kal)", 0)),
                    protein=parse_nutrient(row.get("Protein (g)", 0)),
                    lemak=parse_nutrient(row.get("Lemak (g)", 0)),
                    karbohidrat=parse_nutrient(row.get("Karbohidrat (g)", 0)),
                    serat=parse_nutrient(row.get("Serat (g)", 0)),
                    category_id=category_id,
                    staple_type_id=staple_type_id,
                    created_by=admin_user_id
                )
                db.session.add(food)
                db.session.flush()
                allergens = detect_allergens(nama_bahan)
                for allergen in allergens:
                    db.session.add(AllergenMapping(food_id=food.id, allergen_name=allergen))
                imported_count += 1
                category_stats[normalized_category] += 1
                
                if imported_count % 50 == 0:
                    print('.', end='', flush=True)
                
                if imported_count % 100 == 0:
                    db.session.commit()
            except Exception as e:
                error_count += 1
                continue
        
        db.session.commit()
        print(" done")
        
        # Summary polos tanpa dekorasi
        success_rate = (imported_count / total_rows * 100) if total_rows > 0 else 0
        print(f"\nImport completed:")
        print(f"  Total records in Excel: {total_rows}")
        print(f"  Successfully imported: {imported_count} ({success_rate:.1f}%)")
        print(f"  Skipped/Invalid: {skipped_count + error_count}")
        print(f"\nData breakdown by category:")
        
        sorted_stats = sorted(category_stats.items(), key=lambda x: x[1], reverse=True)
        for cat, count in sorted_stats:
            cat_display = {
                'Pokok': 'Makanan Pokok',
                'Lauk': 'Lauk Pauk',
                'Sayur': 'Sayur',
                'Buah': 'Buah',
                'Lain-lain': 'Lain-lain'
            }.get(cat, cat)
            print(f"  {cat_display}: {count}")
        
        print("")
        return True
    except Exception as e:
        print(f"Error during import: {e}")
        db.session.rollback()
        return False
        print(f"{'='*70}")
        
        success_rate = (imported_count / total_rows * 100) if total_rows > 0 else 0
        
        print(f"\n📊 RINGKASAN IMPORT:")
        print(f"  • Total Data di Excel        : {total_rows:,} baris")
        print(f"  • Data Valid Masuk Database  : {imported_count:,} items")
        print(f"  • Data Gagal/Duplikat/Kosong : {skipped_count + error_count:,} items")
        print(f"  • Persentase Keberhasilan    : {success_rate:.2f}%")
        
        print(f"\n📂 DISTRIBUSI KATEGORI:")
        sorted_stats = sorted(category_stats.items(), key=lambda x: x[1], reverse=True)
        for cat, count in sorted_stats:
            percentage = (count / imported_count * 100) if imported_count > 0 else 0
            bar_length = int(percentage / 2)  # Max 50 chars
            bar = '█' * bar_length
            print(f"  • {cat:<12} : {count:>4} items  {bar} ({percentage:.1f}%)")
        
        print(f"\n{'='*70}")
        
        if success_rate < 90:
            print(f"\n⚠️  PERINGATAN: Success rate hanya {success_rate:.1f}%")
            print(f"    Periksa data Excel untuk kemungkinan masalah format.")
        else:
            print(f"\n✅ VALIDASI BERHASIL - Database siap digunakan!")
        
        print(f"{'='*70}\n")
        return True
    except Exception as e:
        print(f"❌ Error: {e}")
        db.session.rollback()
        return False

def main():
    print("\nSmartDiabets Database Initialization")
    print("")
    app = create_app()
    with app.app_context():
        db.init_app(app)
        
        print("Dropping existing tables...", end=' ')
        db.drop_all()
        print("OK")
        
        print("Creating database tables...", end=' ')
        db.create_all()
        print("OK")
        
        print("Initializing food categories...", end=' ')
        for cat, desc in [("Pokok", "Karbohidrat"), ("Lauk", "Protein"), ("Sayur", "Serat"), ("Buah", "Vitamin"), ("Lain-lain", "Lainnya")]:
            if not FoodCategory.query.filter_by(name=cat).first():
                db.session.add(FoodCategory(name=cat, description=desc))
        db.session.commit()
        print("OK")
        
        print("Initializing staple types...", end=' ')
        for st in [("Sederhana", "Sederhana"), ("Lengkap", "Lengkap")]:
            if not StapleType.query.filter_by(name=st[0]).first():
                db.session.add(StapleType(name=st[0], description=st[1]))
        db.session.commit()
        print("OK")
        
        print("Creating admin user...", end=' ')
        if not User.query.filter_by(username="admin").first():
            admin = User(username="admin", email="admin@smartdiabetes.com", is_admin=True)
            admin.set_password("admin123")
            db.session.add(admin)
            db.session.commit()
        print("OK")
        print("")
        
        # Import data
        excel_path = input("Excel file path (Enter to skip): ").strip()
        if excel_path and os.path.exists(excel_path):
            import_from_excel(excel_path)
        elif excel_path:
            print("Warning: File not found")
            print("")
        else:
            print("Skipping data import")
            print("")
        
        # Verification
        print("Database verification:")
        print(f"  Total categories: {FoodCategory.query.count()}")
        print(f"  Total food items: {Food.query.count()}")
        print("")
        print("Category details:")
        for cat in FoodCategory.query.all():
            count = Food.query.filter_by(category_id=cat.id).count()
            cat_display = {
                'Pokok': 'Makanan Pokok',
                'Lauk': 'Lauk Pauk',
                'Sayur': 'Sayur',
                'Buah': 'Buah',
                'Lain-lain': 'Lain-lain'
            }.get(cat.name, cat.name)
            print(f"  {cat_display}: {count} items")
        print("")
        print("Database initialization completed successfully")
        print("")

if __name__ == "__main__":
    main()
