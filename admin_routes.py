# admin_routes.py
"""
Routes untuk Admin Panel
- Login/Logout Admin
- CRUD Makanan
- Kelola Kategori
- Upload Excel
"""
from flask import Blueprint, render_template, request, redirect, url_for, flash, jsonify
from flask_login import login_user, logout_user, login_required, current_user
from werkzeug.utils import secure_filename
from functools import wraps
import os
import pandas as pd
from database import db, User, Food, FoodCategory, StapleType, AllergenMapping, ActivityLog
import json
from datetime import datetime

# Buat Blueprint untuk admin
admin_bp = Blueprint('admin', __name__, url_prefix='/admin')

# Decorator untuk memastikan user adalah admin
def admin_required(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if not current_user.is_authenticated:
            flash('Silakan login terlebih dahulu', 'warning')
            return redirect(url_for('admin.login'))
        if not current_user.is_admin:
            flash('Akses ditolak. Hanya admin yang dapat mengakses halaman ini.', 'danger')
            return redirect(url_for('home'))
        return f(*args, **kwargs)
    return decorated_function


# ============================================================================
# AUTHENTICATION ROUTES
# ============================================================================

@admin_bp.route('/login', methods=['GET', 'POST'])
def login():
    """Login page untuk admin"""
    if current_user.is_authenticated:
        if current_user.is_admin:
            return redirect(url_for('admin.dashboard'))
        else:
            return redirect(url_for('home'))
    
    if request.method == 'POST':
        username = request.form.get('username')
        password = request.form.get('password')
        remember = request.form.get('remember', False)
        
        user = User.query.filter_by(username=username).first()
        
        if user and user.check_password(password):
            if user.is_admin:
                login_user(user, remember=remember)
                flash(f'Selamat datang, {user.username}!', 'success')
                
                # Log aktivitas login
                log_activity(user.id, 'LOGIN', 'users', user.id, 'Admin login')
                
                next_page = request.args.get('next')
                return redirect(next_page or url_for('admin.dashboard'))
            else:
                flash('Akses ditolak. Hanya admin yang dapat login di sini.', 'danger')
        else:
            flash('Username atau password salah', 'danger')
    
    return render_template('admin/login.html')


@admin_bp.route('/logout')
@login_required
def logout():
    """Logout admin"""
    log_activity(current_user.id, 'LOGOUT', 'users', current_user.id, 'Admin logout')
    logout_user()
    flash('Anda telah logout', 'info')
    return redirect(url_for('admin.login'))


# ============================================================================
# DASHBOARD
# ============================================================================

@admin_bp.route('/dashboard')
@admin_required
def dashboard():
    """Admin dashboard - ringkasan statistik"""
    stats = {
        'total_foods': Food.query.count(),
        'total_categories': FoodCategory.query.count(),
        'total_allergens': db.session.query(AllergenMapping.allergen_name).distinct().count(),
        'recent_foods': Food.query.order_by(Food.created_at.desc()).limit(5).all(),
        'foods_by_category': db.session.query(
            FoodCategory.name, 
            db.func.count(Food.id)
        ).join(Food).group_by(FoodCategory.name).all(),
    }
    
    return render_template('admin/dashboard.html', stats=stats)


# ============================================================================
# FOOD MANAGEMENT (CRUD)
# ============================================================================

@admin_bp.route('/foods')
@admin_required
def list_foods():
    """Daftar semua makanan dengan filter dan pagination"""
    page = request.args.get('page', 1, type=int)
    per_page = request.args.get('per_page', 20, type=int)
    category_filter = request.args.get('category', '')
    search_query = request.args.get('search', '')
    
    # Query dasar
    query = Food.query
    
    # Filter kategori
    if category_filter:
        query = query.join(FoodCategory).filter(FoodCategory.name == category_filter)
    
    # Filter pencarian
    if search_query:
        query = query.filter(Food.nama_bahan.ilike(f'%{search_query}%'))
    
    # Pagination
    foods = query.order_by(Food.nama_bahan).paginate(
        page=page, per_page=per_page, error_out=False
    )
    
    # Ambil semua kategori untuk dropdown filter
    categories = FoodCategory.query.all()
    
    return render_template('admin/foods/list.html', 
                          foods=foods, 
                          categories=categories,
                          current_category=category_filter,
                          search_query=search_query)


@admin_bp.route('/foods/add', methods=['GET', 'POST'])
@admin_required
def add_food():
    """Tambah makanan baru"""
    if request.method == 'POST':
        try:
            # Ambil data dari form
            nama_bahan = request.form.get('nama_bahan').strip()
            category_id = int(request.form.get('category_id'))
            staple_type_id = request.form.get('staple_type_id')
            
            # Validasi nama makanan tidak duplikat
            existing = Food.query.filter_by(nama_bahan=nama_bahan).first()
            if existing:
                flash(f'Makanan "{nama_bahan}" sudah ada di database', 'warning')
                return redirect(url_for('admin.add_food'))
            
            # Buat record food
            food = Food(
                nama_bahan=nama_bahan,
                bdd=float(request.form.get('bdd', 100)),
                energi=float(request.form.get('energi')),
                protein=float(request.form.get('protein')),
                lemak=float(request.form.get('lemak')),
                karbohidrat=float(request.form.get('karbohidrat')),
                serat=float(request.form.get('serat', 0)),
                category_id=category_id,
                staple_type_id=int(staple_type_id) if staple_type_id else None,
                created_by=current_user.id
            )
            
            db.session.add(food)
            db.session.flush()  # Dapatkan ID
            
            # Tambah allergen mapping
            allergens = request.form.getlist('allergens[]')
            for allergen in allergens:
                if allergen.strip():
                    allergen_map = AllergenMapping(
                        food_id=food.id,
                        allergen_name=allergen.strip().lower()
                    )
                    db.session.add(allergen_map)
            
            db.session.commit()
            
            # Log aktivitas
            log_activity(current_user.id, 'CREATE', 'foods', food.id, 
                        f'Menambahkan makanan: {nama_bahan}')
            
            flash(f'Makanan "{nama_bahan}" berhasil ditambahkan', 'success')
            return redirect(url_for('admin.list_foods'))
        
        except Exception as e:
            db.session.rollback()
            flash(f'Error: {str(e)}', 'danger')
    
    # GET request
    categories = FoodCategory.query.all()
    staple_types = StapleType.query.all()
    
    # Daftar alergen umum
    common_allergens = ['kacang', 'susu', 'seafood', 'telur', 'kedelai', 'gluten', 
                       'ikan', 'udang', 'gandum']
    
    return render_template('admin/foods/add.html', 
                          categories=categories, 
                          staple_types=staple_types,
                          common_allergens=common_allergens)


@admin_bp.route('/foods/edit/<int:id>', methods=['GET', 'POST'])
@admin_required
def edit_food(id):
    """Edit makanan"""
    food = Food.query.get_or_404(id)
    
    if request.method == 'POST':
        try:
            # Update data
            food.nama_bahan = request.form.get('nama_bahan').strip()
            food.bdd = float(request.form.get('bdd', 100))
            food.energi = float(request.form.get('energi'))
            food.protein = float(request.form.get('protein'))
            food.lemak = float(request.form.get('lemak'))
            food.karbohidrat = float(request.form.get('karbohidrat'))
            food.serat = float(request.form.get('serat', 0))
            food.category_id = int(request.form.get('category_id'))
            
            staple_type_id = request.form.get('staple_type_id')
            food.staple_type_id = int(staple_type_id) if staple_type_id else None
            
            food.updated_at = datetime.utcnow()
            
            # Update allergen mapping
            # Hapus mapping lama
            AllergenMapping.query.filter_by(food_id=food.id).delete()
            
            # Tambah mapping baru
            allergens = request.form.getlist('allergens[]')
            for allergen in allergens:
                if allergen.strip():
                    allergen_map = AllergenMapping(
                        food_id=food.id,
                        allergen_name=allergen.strip().lower()
                    )
                    db.session.add(allergen_map)
            
            db.session.commit()
            
            # Log aktivitas
            log_activity(current_user.id, 'UPDATE', 'foods', food.id, 
                        f'Mengupdate makanan: {food.nama_bahan}')
            
            flash(f'Makanan "{food.nama_bahan}" berhasil diupdate', 'success')
            return redirect(url_for('admin.list_foods'))
        
        except Exception as e:
            db.session.rollback()
            flash(f'Error: {str(e)}', 'danger')
    
    # GET request
    categories = FoodCategory.query.all()
    staple_types = StapleType.query.all()
    common_allergens = ['kacang', 'susu', 'seafood', 'telur', 'kedelai', 'gluten',
                       'ikan', 'udang', 'gandum']
    
    # Dapatkan allergen yang sudah di-assign
    current_allergens = [a.allergen_name for a in food.allergens]
    
    return render_template('admin/foods/edit.html', 
                          food=food,
                          categories=categories, 
                          staple_types=staple_types,
                          common_allergens=common_allergens,
                          current_allergens=current_allergens)


@admin_bp.route('/foods/delete/<int:id>', methods=['POST'])
@admin_required
def delete_food(id):
    """Hapus makanan"""
    food = Food.query.get_or_404(id)
    nama = food.nama_bahan
    
    try:
        # Log sebelum dihapus
        log_activity(current_user.id, 'DELETE', 'foods', food.id, 
                    f'Menghapus makanan: {nama}')
        
        db.session.delete(food)
        db.session.commit()
        
        flash(f'Makanan "{nama}" berhasil dihapus', 'success')
    except Exception as e:
        db.session.rollback()
        flash(f'Error: {str(e)}', 'danger')
    
    return redirect(url_for('admin.list_foods'))


# ============================================================================
# CATEGORY MANAGEMENT
# ============================================================================

@admin_bp.route('/categories')
@admin_required
def list_categories():
    """Daftar kategori makanan"""
    categories = FoodCategory.query.all()
    staple_types = StapleType.query.all()
    
    return render_template('admin/categories/list.html', 
                          categories=categories,
                          staple_types=staple_types)


@admin_bp.route('/categories/add', methods=['POST'])
@admin_required
def add_category():
    """Tambah kategori baru"""
    try:
        name = request.form.get('name').strip()
        description = request.form.get('description', '').strip()
        
        # Validasi tidak duplikat
        existing = FoodCategory.query.filter_by(name=name).first()
        if existing:
            flash(f'Kategori "{name}" sudah ada', 'warning')
            return redirect(url_for('admin.list_categories'))
        
        category = FoodCategory(name=name, description=description)
        db.session.add(category)
        db.session.commit()
        
        log_activity(current_user.id, 'CREATE', 'food_categories', category.id, 
                    f'Menambah kategori: {name}')
        
        flash(f'Kategori "{name}" berhasil ditambahkan', 'success')
    except Exception as e:
        db.session.rollback()
        flash(f'Error: {str(e)}', 'danger')
    
    return redirect(url_for('admin.list_categories'))


@admin_bp.route('/categories/delete/<int:id>', methods=['POST'])
@admin_required
def delete_category(id):
    """Hapus kategori"""
    category = FoodCategory.query.get_or_404(id)
    
    # Cek apakah kategori masih digunakan
    food_count = Food.query.filter_by(category_id=id).count()
    if food_count > 0:
        flash(f'Tidak bisa menghapus kategori "{category.name}". '
              f'Masih ada {food_count} makanan yang menggunakan kategori ini.', 'danger')
        return redirect(url_for('admin.list_categories'))
    
    try:
        name = category.name
        log_activity(current_user.id, 'DELETE', 'food_categories', category.id, 
                    f'Menghapus kategori: {name}')
        
        db.session.delete(category)
        db.session.commit()
        
        flash(f'Kategori "{name}" berhasil dihapus', 'success')
    except Exception as e:
        db.session.rollback()
        flash(f'Error: {str(e)}', 'danger')
    
    return redirect(url_for('admin.list_categories'))


# ============================================================================
# STAPLE TYPE MANAGEMENT
# ============================================================================

@admin_bp.route('/staple-types/add', methods=['POST'])
@admin_required
def add_staple_type():
    """Tambah tipe makanan pokok"""
    try:
        name = request.form.get('name').strip()
        description = request.form.get('description', '').strip()
        
        existing = StapleType.query.filter_by(name=name).first()
        if existing:
            flash(f'Tipe pokok "{name}" sudah ada', 'warning')
            return redirect(url_for('admin.list_categories'))
        
        staple_type = StapleType(name=name, description=description)
        db.session.add(staple_type)
        db.session.commit()
        
        log_activity(current_user.id, 'CREATE', 'staple_types', staple_type.id, 
                    f'Menambah tipe pokok: {name}')
        
        flash(f'Tipe pokok "{name}" berhasil ditambahkan', 'success')
    except Exception as e:
        db.session.rollback()
        flash(f'Error: {str(e)}', 'danger')
    
    return redirect(url_for('admin.list_categories'))


# ============================================================================
# EXCEL UPLOAD
# ============================================================================

@admin_bp.route('/upload', methods=['GET', 'POST'])
@admin_required
def upload_excel():
    """Upload file Excel untuk import data makanan"""
    if request.method == 'POST':
        if 'file' not in request.files:
            flash('Tidak ada file yang dipilih', 'danger')
            return redirect(request.url)
        
        file = request.files['file']
        
        if file.filename == '':
            flash('Tidak ada file yang dipilih', 'danger')
            return redirect(request.url)
        
        if not file.filename.lower().endswith(('.xlsx', '.xls')):
            flash('File harus berformat Excel (.xlsx atau .xls)', 'danger')
            return redirect(request.url)
        
        try:
            # Baca Excel
            df = pd.read_excel(file, engine='openpyxl')
            
            # PENTING: Strip whitespace dari nama kolom
            df.columns = df.columns.str.strip()
            
            # Validasi kolom wajib (sesuai dengan init_db.py)
            required_columns = ['Nama_Bahan', 'Energi (kal)', 'Protein (g)', 
                              'Lemak (g)', 'Karbohidrat (g)', 'Serat (g)']
            missing_columns = [col for col in required_columns if col not in df.columns]
            
            if missing_columns:
                flash(f'Kolom wajib tidak ditemukan: {", ".join(missing_columns)}', 'danger')
                return redirect(request.url)
            
            success_count = 0
            update_count = 0
            insert_count = 0
            error_count = 0
            errors = []
            
            # Helper function untuk konversi nilai aman
            def safe_float(val):
                """Konversi nilai Excel ke float dengan aman"""
                if pd.isna(val):
                    return 0.0
                val_str = str(val).strip().replace(',', '.')
                if val_str in ['-', '', 'nan', 'None']:
                    return 0.0
                try:
                    return float(val_str)
                except:
                    return 0.0
            
            for idx, row in df.iterrows():
                try:
                    # 1. Ambil Nama Bahan (WAJIB)
                    nama_bahan = str(row.get('Nama_Bahan', '')).strip()
                    if not nama_bahan or nama_bahan.lower() in ['nan', 'none', '']:
                        error_count += 1
                        errors.append(f"Baris {idx + 2}: Nama bahan kosong")
                        continue
                    
                    # 2. Ambil BDD (Bahan yang Dapat Dimakan) - opsional
                    bdd = safe_float(row.get('BDD', 100.0))
                    if bdd <= 0 or bdd > 100:
                        bdd = 100.0  # Default BDD 100% jika tidak valid
                    
                    # 3. Ambil Kategori dengan Smart Detection (sesuai init_db.py)
                    # Prioritas: 'Jenis Makanan' > 'Kategori' > default 'Pokok'
                    if 'Jenis Makanan' in df.columns:
                        category_name = str(row.get('Jenis Makanan', 'Pokok')).strip()
                    elif 'Kategori' in df.columns:
                        category_name = str(row.get('Kategori', 'Pokok')).strip()
                    else:
                        category_name = 'Pokok'
                    
                    # Cari kategori di database
                    category = FoodCategory.query.filter_by(name=category_name).first()
                    if not category:
                        # Fallback ke kategori default 'Pokok'
                        category = FoodCategory.query.filter_by(name='Pokok').first()
                        if not category:
                            error_count += 1
                            errors.append(f"Baris {idx + 2}: Kategori '{category_name}' tidak ditemukan")
                            continue
                    
                    # 4. Ambil Tipe Pokok dengan Smart Detection (sesuai init_db.py)
                    # Prioritas: 'Tipe Pokok' > 'Tipe_Pokok' > default 'Sederhana'
                    if 'Tipe Pokok' in df.columns:
                        staple_type_name = str(row.get('Tipe Pokok', 'Sederhana')).strip()
                    elif 'Tipe_Pokok' in df.columns:
                        staple_type_name = str(row.get('Tipe_Pokok', 'Sederhana')).strip()
                    else:
                        staple_type_name = 'Sederhana'
                    
                    # Cari tipe pokok di database
                    staple_type = StapleType.query.filter_by(name=staple_type_name).first()
                    if not staple_type:
                        # Fallback ke tipe default 'Sederhana'
                        staple_type = StapleType.query.filter_by(name='Sederhana').first()
                        if not staple_type:
                            error_count += 1
                            errors.append(f"Baris {idx + 2}: Tipe pokok '{staple_type_name}' tidak ditemukan")
                            continue
                    
                    # 5. Parse Nutrisi (SESUAI NAMA FIELD DI database.py)
                    energi = safe_float(row.get('Energi (kal)', 0))
                    protein = safe_float(row.get('Protein (g)', 0))
                    lemak = safe_float(row.get('Lemak (g)', 0))
                    karbohidrat = safe_float(row.get('Karbohidrat (g)', 0))
                    serat = safe_float(row.get('Serat (g)', 0))
                    
                    # 6. Validasi nilai nutrisi tidak negatif
                    if any(v < 0 for v in [energi, protein, lemak, karbohidrat, serat, bdd]):
                        error_count += 1
                        errors.append(f"Baris {idx + 2}: Nilai nutrisi tidak boleh negatif")
                        continue
                    
                    # 7. UPSERT: Cek apakah makanan sudah ada (berdasarkan nama_bahan)
                    existing_food = Food.query.filter_by(nama_bahan=nama_bahan).first()
                    
                    if existing_food:
                        # UPDATE data yang sudah ada
                        existing_food.bdd = bdd
                        existing_food.category_id = category.id
                        existing_food.staple_type_id = staple_type.id
                        existing_food.energi = energi
                        existing_food.protein = protein
                        existing_food.lemak = lemak
                        existing_food.karbohidrat = karbohidrat
                        existing_food.serat = serat
                        update_count += 1
                    else:
                        # INSERT data baru
                        new_food = Food(
                            nama_bahan=nama_bahan,
                            bdd=bdd,
                            category_id=category.id,
                            staple_type_id=staple_type.id,
                            energi=energi,
                            protein=protein,
                            lemak=lemak,
                            karbohidrat=karbohidrat,
                            serat=serat,
                            created_by=current_user.id
                        )
                        db.session.add(new_food)
                        insert_count += 1
                    
                    success_count += 1
                    
                except Exception as e:
                    error_count += 1
                    errors.append(f"Baris {idx + 2}: {str(e)}")
                    continue
            
            # Commit semua perubahan
            db.session.commit()
            
            # Log aktivitas
            log_activity(current_user.id, 'UPLOAD', 'foods', None, 
                        f'Upload Excel: {insert_count} baru, {update_count} update, {error_count} error')
            
            # Tampilkan hasil dengan detail
            if success_count > 0:
                detail_msg = f'Berhasil memproses {success_count} baris: {insert_count} data baru ditambahkan, {update_count} data diperbarui'
                flash(detail_msg, 'success')
            
            if error_count > 0:
                error_msg = f'{error_count} baris gagal diimport'
                if len(errors) <= 10:
                    error_msg += ':<br>' + '<br>'.join(errors)
                else:
                    error_msg += f':<br>' + '<br>'.join(errors[:10]) + f'<br>...dan {len(errors) - 10} error lainnya'
                flash(error_msg, 'warning')
            
            return redirect(url_for('admin.list_foods'))
            
        except Exception as e:
            db.session.rollback()
            flash(f'Error saat membaca file: {str(e)}', 'danger')
            return redirect(request.url)
    
    return render_template('admin/upload.html')


# ============================================================================
# HELPER FUNCTIONS
# ============================================================================

def log_activity(user_id, action, table_name, record_id, details):
    """Helper untuk logging aktivitas admin"""
    try:
        log = ActivityLog(
            user_id=user_id,
            action=action,
            table_name=table_name,
            record_id=record_id,
            details=details,
            ip_address=request.remote_addr
        )
        db.session.add(log)
        db.session.commit()
    except:
        pass  # Jangan biarkan logging error mengganggu proses utama
