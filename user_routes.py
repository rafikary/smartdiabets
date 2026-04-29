# user_routes.py
"""
Routes untuk User (non-admin)
- Registration
- Login/Logout
- Profile
- History Rekomendasi
"""
from flask import Blueprint, render_template, request, redirect, url_for, flash, session
from flask_login import login_user, logout_user, login_required, current_user
from werkzeug.utils import secure_filename
from database import db, User, Recommendation
import json
from datetime import datetime

# Buat Blueprint untuk user
user_bp = Blueprint('user', __name__, url_prefix='/user')


@user_bp.route('/register', methods=['GET', 'POST'])
def register():
    """Registration page untuk user baru"""
    if current_user.is_authenticated:
        return redirect(url_for('home'))
    
    if request.method == 'POST':
        username = request.form.get('username')
        email = request.form.get('email')
        password = request.form.get('password')
        password_confirm = request.form.get('password_confirm')
        
        # Validasi
        if not username or not email or not password:
            flash('Semua field harus diisi', 'danger')
            return redirect(url_for('user.register'))
        
        if password != password_confirm:
            flash('Password tidak cocok', 'danger')
            return redirect(url_for('user.register'))
        
        if len(password) < 6:
            flash('Password minimal 6 karakter', 'danger')
            return redirect(url_for('user.register'))
        
        # Cek username sudah dipakai
        if User.query.filter_by(username=username).first():
            flash('Username sudah digunakan', 'danger')
            return redirect(url_for('user.register'))
        
        # Cek email sudah dipakai
        if User.query.filter_by(email=email).first():
            flash('Email sudah terdaftar', 'danger')
            return redirect(url_for('user.register'))
        
        # Buat user baru (bukan admin)
        user = User(
            username=username,
            email=email,
            is_admin=False
        )
        user.set_password(password)
        
        db.session.add(user)
        db.session.commit()
        
        flash(f'Akun berhasil dibuat! Silakan login.', 'success')
        return redirect(url_for('user.login'))
    
    return render_template('user/register.html')


@user_bp.route('/login', methods=['GET', 'POST'])
def login():
    """Login page untuk user"""
    if current_user.is_authenticated:
        return redirect(url_for('home'))
    
    if request.method == 'POST':
        username = request.form.get('username')
        password = request.form.get('password')
        remember = request.form.get('remember', False)
        
        user = User.query.filter_by(username=username).first()
        
        if user and user.check_password(password):
            if not user.is_admin:
                login_user(user, remember=remember)
                
                next_page = request.args.get('next')
                return redirect(next_page or url_for('calculator'))
            else:
                flash('Gunakan halaman admin untuk login sebagai admin', 'warning')
                return redirect(url_for('admin.login'))
        else:
            flash('Username atau password salah', 'danger')
    
    return render_template('user/login.html')


@user_bp.route('/logout')
@login_required
def logout():
    """Logout user"""
    logout_user()
    flash('Anda telah logout', 'info')
    return redirect(url_for('home'))


@user_bp.route('/profile')
@login_required
def profile():
    """Profile user - lihat history rekomendasi"""
    # Ambil history dari database, urutkan terbaru dulu, limit 20
    recommendations = Recommendation.query.filter_by(user_id=current_user.id)\
                                          .order_by(Recommendation.created_at.desc())\
                                          .limit(20)\
                                          .all()
    
    # Convert ke format yang bisa di-render template
    history = []
    for rec in recommendations:
        gender_display = 'Pria' if rec.gender in ('male', 'pria') else 'Wanita'
        # Hitung BBI Broca
        try:
            bbi = (rec.height - 100) * 0.9
        except Exception:
            bbi = 0
        history.append({
            'id': rec.id,
            'name': '',
            'saved_at': rec.created_at.strftime('%d %b %Y, %H:%M'),
            'gender': rec.gender,
            'gender_display': gender_display,
            'age': rec.age,
            'weight': rec.weight,
            'height': rec.height,
            'bbi': round(bbi, 1),
            'nutrition_status': rec.diabetes_type or '-',
            'activity_level': rec.activity_level,
            'caloric_needs': rec.total_calories,
            'total_calories': rec.total_calories,
            'diabetes_type': rec.diabetes_type,
            'allergies': rec.get_allergies_list(),
            'recommendations': rec.get_recommendations_dict()
        })
    
    return render_template('user/profile.html', 
                          user=current_user,
                          history=history)


@user_bp.route('/save-recommendation', methods=['POST'])
@login_required
def save_recommendation():
    """Simpan hasil rekomendasi ke database"""
    data = request.get_json()
    
    # Simpan ke database
    recommendation = Recommendation(
        user_id=current_user.id,
        gender=data.get('gender'),
        age=data.get('age'),
        weight=data.get('weight'),
        height=data.get('height'),
        activity_level=data.get('activity_level'),
        diabetes_type=data.get('diabetes_type'),
        total_calories=data.get('total_calories'),
        allergies=json.dumps(data.get('allergies', [])),
        recommendations_data=json.dumps(data.get('recommendations', {})),
        ip_address=request.remote_addr
    )
    
    db.session.add(recommendation)
    db.session.commit()
    
    return {'status': 'success', 'message': 'Rekomendasi berhasil disimpan', 'id': recommendation.id}


@user_bp.route('/delete-recommendation/<int:id>', methods=['POST'])
@login_required
def delete_recommendation(id):
    """Hapus history rekomendasi"""
    recommendation = Recommendation.query.filter_by(id=id, user_id=current_user.id).first()
    
    if not recommendation:
        return {'status': 'error', 'message': 'Rekomendasi tidak ditemukan'}, 404
    
    db.session.delete(recommendation)
    db.session.commit()
    
    return {'status': 'success', 'message': 'Rekomendasi berhasil dihapus'}

