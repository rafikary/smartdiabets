# database.py
"""
Database models dan setup untuk sistem rekomendasi makanan diabetes
Menggunakan SQLite dengan Flask-SQLAlchemy
"""
from flask_sqlalchemy import SQLAlchemy
from flask_login import UserMixin
from werkzeug.security import generate_password_hash, check_password_hash
from datetime import datetime
import json

db = SQLAlchemy()

class User(UserMixin, db.Model):
    """Model untuk user (admin dan user biasa)"""
    __tablename__ = 'users'
    
    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(80), unique=True, nullable=False)
    email = db.Column(db.String(120), unique=True, nullable=False)
    password_hash = db.Column(db.String(255), nullable=False)
    is_admin = db.Column(db.Boolean, default=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    
    def set_password(self, password):
        """Hash password sebelum disimpan"""
        self.password_hash = generate_password_hash(password)
    
    def check_password(self, password):
        """Verifikasi password"""
        return check_password_hash(self.password_hash, password)
    
    def __repr__(self):
        return f'<User {self.username}>'


class FoodCategory(db.Model):
    """Model untuk kategori makanan (Pokok, Lauk, Sayur, Buah)"""
    __tablename__ = 'food_categories'
    
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(50), unique=True, nullable=False)  # Pokok, Lauk, Sayur, Buah
    description = db.Column(db.Text)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    
    # Relasi ke foods
    foods = db.relationship('Food', backref='category', lazy=True, cascade='all, delete-orphan')
    
    def __repr__(self):
        return f'<FoodCategory {self.name}>'


class StapleType(db.Model):
    """Model untuk tipe makanan pokok (Sederhana/Lengkap)"""
    __tablename__ = 'staple_types'
    
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(50), unique=True, nullable=False)  # Sederhana, Lengkap
    description = db.Column(db.Text)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    
    # Relasi ke foods
    foods = db.relationship('Food', backref='staple_type', lazy=True)
    
    def __repr__(self):
        return f'<StapleType {self.name}>'


class Food(db.Model):
    """Model untuk data makanan (TKPI)"""
    __tablename__ = 'foods'
    
    id = db.Column(db.Integer, primary_key=True)
    nama_bahan = db.Column(db.String(200), nullable=False, index=True)
    bdd = db.Column(db.Float, default=100.0)  # Berat Dapat Dimakan
    energi = db.Column(db.Float, nullable=False)  # dalam kkal
    protein = db.Column(db.Float, nullable=False)  # dalam gram
    lemak = db.Column(db.Float, nullable=False)  # dalam gram
    karbohidrat = db.Column(db.Float, nullable=False)  # dalam gram
    serat = db.Column(db.Float, default=0.0)  # dalam gram
    
    # Foreign keys
    category_id = db.Column(db.Integer, db.ForeignKey('food_categories.id'), nullable=False)
    staple_type_id = db.Column(db.Integer, db.ForeignKey('staple_types.id'), nullable=True)  # Hanya untuk Pokok
    
    # Metadata
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    created_by = db.Column(db.Integer, db.ForeignKey('users.id'))  # Admin yang menambahkan
    
    # Relasi ke allergen mapping
    allergens = db.relationship('AllergenMapping', backref='food', lazy=True, cascade='all, delete-orphan')
    
    def to_dict(self):
        """Convert to dictionary for JSON response"""
        return {
            'id': self.id,
            'nama_bahan': self.nama_bahan,
            'bdd': self.bdd,
            'energi': self.energi,
            'protein': self.protein,
            'lemak': self.lemak,
            'karbohidrat': self.karbohidrat,
            'serat': self.serat,
            'category': self.category.name if self.category else None,
            'staple_type': self.staple_type.name if self.staple_type else None,
            'allergens': [a.allergen_name for a in self.allergens]
        }
    
    def __repr__(self):
        return f'<Food {self.nama_bahan}>'


class AllergenMapping(db.Model):
    """Model untuk mapping makanan dengan alergen"""
    __tablename__ = 'allergen_mappings'
    
    id = db.Column(db.Integer, primary_key=True)
    food_id = db.Column(db.Integer, db.ForeignKey('foods.id'), nullable=False)
    allergen_name = db.Column(db.String(50), nullable=False)  # kacang, susu, seafood, dll
    
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    
    # Composite unique constraint: 1 makanan tidak boleh punya duplikat alergen yang sama
    __table_args__ = (
        db.UniqueConstraint('food_id', 'allergen_name', name='unique_food_allergen'),
    )
    
    def __repr__(self):
        return f'<AllergenMapping food_id={self.food_id} allergen={self.allergen_name}>'


class Recommendation(db.Model):
    """Model untuk menyimpan history rekomendasi menu user"""
    __tablename__ = 'recommendations'
    
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False)
    
    # Input parameters
    gender = db.Column(db.String(10))  # male/female
    age = db.Column(db.Integer)
    weight = db.Column(db.Float)  # kg
    height = db.Column(db.Float)  # cm
    activity_level = db.Column(db.String(20))  # rest/light/moderate/heavy/very_heavy
    diabetes_type = db.Column(db.Integer)  # 1 atau 2
    
    # Kalori yang dihitung
    total_calories = db.Column(db.Float)
    
    # Alergi (JSON array)
    allergies = db.Column(db.Text)  # JSON: ["kacang", "susu"]
    
    # Hasil rekomendasi (JSON)
    recommendations_data = db.Column(db.Text, nullable=False)  # JSON lengkap hasil rekomendasi
    
    # Metadata
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    ip_address = db.Column(db.String(50))
    
    # Relasi ke user
    user = db.relationship('User', backref='recommendations')
    
    def get_allergies_list(self):
        """Parse allergies JSON to list"""
        if self.allergies:
            import json
            return json.loads(self.allergies)
        return []
    
    def get_recommendations_dict(self):
        """Parse recommendations JSON to dict"""
        if self.recommendations_data:
            import json
            return json.loads(self.recommendations_data)
        return {}
    
    def __repr__(self):
        return f'<Recommendation user_id={self.user_id} at {self.created_at}>'


class ActivityLog(db.Model):
    """Model untuk logging aktivitas admin (opsional, untuk audit trail)"""
    __tablename__ = 'activity_logs'
    
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False)
    action = db.Column(db.String(100), nullable=False)  # CREATE, UPDATE, DELETE
    table_name = db.Column(db.String(50), nullable=False)  # foods, categories, etc
    record_id = db.Column(db.Integer)  # ID record yang diubah
    details = db.Column(db.Text)  # JSON details perubahan
    ip_address = db.Column(db.String(50))
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    
    user = db.relationship('User', backref='activity_logs')
    
    def __repr__(self):
        return f'<ActivityLog {self.action} on {self.table_name}>'


def init_db(app):
    """Initialize database with app context"""
    db.init_app(app)
    
    with app.app_context():
        # Buat semua tabel
        db.create_all()
        
        # Seed data kategori default jika belum ada
        if FoodCategory.query.count() == 0:
            categories = [
                FoodCategory(name='Pokok', description='Makanan pokok sumber karbohidrat'),
                FoodCategory(name='Lauk', description='Lauk pauk sumber protein'),
                FoodCategory(name='Sayur', description='Sayuran sumber serat dan vitamin'),
                FoodCategory(name='Buah', description='Buah-buahan sumber vitamin'),
            ]
            db.session.add_all(categories)
            db.session.commit()
            print("✓ Kategori makanan default berhasil dibuat")
        
        # Seed data tipe makanan pokok jika belum ada
        if StapleType.query.count() == 0:
            staple_types = [
                StapleType(name='Sederhana', description='Makanan pokok sederhana (nasi putih, roti tawar, dll)'),
                StapleType(name='Lengkap', description='Makanan pokok lengkap (nasi merah, roti gandum, dll)'),
            ]
            db.session.add_all(staple_types)
            db.session.commit()
            print("✓ Tipe makanan pokok default berhasil dibuat")
        
        # Buat akun admin default jika belum ada
        if User.query.filter_by(username='admin').first() is None:
            admin = User(
                username='admin',
                email='admin@smartdiabetes.com',
                is_admin=True
            )
            admin.set_password('admin123')  # Password default, HARUS diganti!
            db.session.add(admin)
            db.session.commit()
            print("✓ Akun admin default berhasil dibuat")
            print("  Username: admin")
            print("  Password: admin123")
            print("  ⚠️  SEGERA GANTI PASSWORD SETELAH LOGIN!")
        
        print("✓ Database initialization selesai!")
