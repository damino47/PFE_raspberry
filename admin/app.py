import os
import sys
from flask import Flask, render_template, request, redirect, url_for, flash, jsonify, session
from flask_login import LoginManager, UserMixin, login_user, login_required, logout_user, current_user
from werkzeug.security import generate_password_hash, check_password_hash
import mysql.connector

# Ajouter le répertoire parent au chemin de recherche Python
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from admin.config import *
import json
from datetime import datetime
import os
import cv2
import numpy as np
from ultralytics import YOLO
import easyocr
from PIL import Image
import io
import base64
from decimal import Decimal
import re

# Initialize YOLO and EasyOCR
yolo_model = YOLO('yolov8n.pt')
reader = easyocr.Reader(['en'])

app = Flask(__name__)
app.config['SECRET_KEY'] = SECRET_KEY
login_manager = LoginManager()
login_manager.init_app(app)
login_manager.login_view = 'login'

# Connexion à la base de données
def get_db_connection():
    return mysql.connector.connect(**DATABASE_CONFIG)

class User(UserMixin):
    def __init__(self, id, username, role=None):
        self.id = id
        self.username = username
        self.role = role
        self.username = username
        self.role = role

@login_manager.user_loader
def load_user(user_id):
    conn = get_db_connection()
    cursor = conn.cursor(dictionary=True)
    cursor.execute('SELECT * FROM users WHERE id = %s', (user_id,))
    user = cursor.fetchone()
    cursor.close()
    conn.close()
    
    if user:
        return User(user['id'], user['username'], user['role'])
    return None

@app.route('/')
@login_required
def index():
    if not current_user.is_authenticated:
        return redirect(url_for('login'))
    return redirect(url_for('historique'))

@app.route('/users')
@login_required
def users():
    if current_user.role != 'admin':
        return redirect(url_for('index'))
    return render_template('users.html')

@app.route('/recettes')
@login_required
def recettes():
    return render_template('recettes.html')

@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        username = request.form['username']
        password = request.form['password']
        
        conn = get_db_connection()
        cursor = conn.cursor(dictionary=True)
        cursor.execute('SELECT id, username, password, role FROM users WHERE username = %s', (username,))
        user = cursor.fetchone()
        cursor.close()
        conn.close()

        if user and check_password_hash(user['password'], password):
            user_obj = User(user['id'], user['username'], user['role'])
            login_user(user_obj)
            return redirect(url_for('index'))
        
        flash('Invalid username or password')
    return render_template('login.html')

@app.route('/logout')
@login_required
def logout():
    logout_user()
    return redirect(url_for('login'))

@app.route('/api/places')
@login_required
def get_places():
    conn = get_db_connection()
    cursor = conn.cursor(dictionary=True)
    cursor.execute('SELECT * FROM places')
    places = cursor.fetchall()
    cursor.close()
    conn.close()
    return jsonify(places)

@app.route('/api/notifications')
@login_required
def get_notifications():
    conn = get_db_connection()
    cursor = conn.cursor(dictionary=True)
    cursor.execute('SELECT * FROM notifications ORDER BY created_at DESC LIMIT 10')
    notifications = cursor.fetchall()
    cursor.close()
    conn.close()
    return jsonify(notifications)

@app.route('/api/sessions')
@login_required
def get_sessions():
    conn = get_db_connection()
    cursor = conn.cursor(dictionary=True)
    cursor.execute('''
        SELECT s.*, p.montant_paye, p.status_paiement 
        FROM sessions s 
        LEFT JOIN paiements p ON s.id = p.session_id 
        ORDER BY s.heure_entree DESC
    ''')
    sessions = cursor.fetchall()
    cursor.close()
    conn.close()
    return jsonify(sessions)

@app.route('/api/equipment/status')
@login_required
def get_equipment_status():
    conn = get_db_connection()
    cursor = conn.cursor(dictionary=True)
    cursor.execute('SELECT * FROM equipment_status')
    status = cursor.fetchall()
    cursor.close()
    conn.close()
    return jsonify(status)

@app.route('/api/parking/status')
@login_required
def get_parking_status():
    conn = get_db_connection()
    cursor = conn.cursor(dictionary=True)
    
    # Récupérer toutes les places de parking avec leur statut
    cursor.execute('''
        SELECT 
            p.numero,
            CASE WHEN s.id IS NOT NULL THEN 1 ELSE 0 END as occupied,
            s.immatriculation,
            s.heure_entree,
            s.duree,
            s.montant
        FROM (
            SELECT 1 as numero UNION SELECT 2 UNION SELECT 3 
            UNION SELECT 4 UNION SELECT 5 UNION SELECT 6
        ) p
        LEFT JOIN (
            SELECT * FROM sessions WHERE heure_sortie IS NULL
        ) s ON p.numero = s.place_numero
        ORDER BY p.numero;
    ''')
    
    places = cursor.fetchall()
    
    # Récupérer les statistiques
    cursor.execute('''
        SELECT 
            6 as total,
            SUM(CASE WHEN heure_sortie IS NULL THEN 1 ELSE 0 END) as occupied
        FROM sessions;
    ''')
    
    stats = cursor.fetchone()
    # Préparer la réponse
    formatted_places = []
    for place in places:
        formatted_place = {
            'numero': f'P{place["numero"]}',
            'occupied': place['occupied'],
            'status': 'occupée' if place['occupied'] else 'libre',
            'color': 'red' if place['occupied'] else 'green',
            'immatriculation': place['immatriculation'] if place['immatriculation'] else None,
            'heure_entree': place['heure_entree'].strftime('%H:%M:%S') if place['heure_entree'] else None,
            'duree': place['duree'] if place['duree'] else 0,
            'montant': float(place['montant']) if place['montant'] else 0
        }
        formatted_places.append(formatted_place)
    
    cursor.close()
    conn.close()
    
    return jsonify({
        'places': formatted_places,
        'stats': {
            'total': stats['total'],
            'occupied': stats['occupied'] or 0,
            'available': stats['total'] - (stats['occupied'] or 0)
        }
    })

@app.route('/api/recettes')
@login_required
def get_recettes():
    conn = get_db_connection()
    cursor = conn.cursor(dictionary=True)
    
    # Récupérer les reçus de l'utilisateur
    if current_user.role == 'admin':
        cursor.execute('''
            SELECT 
                r.*,
                s.immatriculation,
                s.duree,
                s.heure_entree,
                s.heure_sortie,
                u.username
            FROM recettes r
            JOIN sessions s ON r.session_id = s.id
            JOIN users u ON r.user_id = u.id
            ORDER BY r.date_recette DESC
        ''')
    else:
        cursor.execute('''
            SELECT 
                r.*,
                s.immatriculation,
                s.duree,
                s.heure_entree,
                s.heure_sortie
            FROM recettes r
            JOIN sessions s ON r.session_id = s.id
            WHERE r.user_id = %s
            ORDER BY r.date_recette DESC;
        ''', (current_user.id,))

    recettes = cursor.fetchall()

    # Récupérer les statistiques
    if current_user.role == 'admin':
        cursor.execute('''
            SELECT 
                COUNT(*) as total_count,
                SUM(montant) as total_montant,
                DATE(date_recette) as date,
                user_id,
                u.username
            FROM recettes r
            JOIN users u ON r.user_id = u.id
            GROUP BY DATE(date_recette), user_id, u.username
            ORDER BY date DESC;
        ''')
    else:
        cursor.execute('''
            SELECT 
                COUNT(*) as total_count,
                SUM(montant) as total_montant,
                DATE(date_recette) as date
            FROM recettes
            WHERE user_id = %s
            GROUP BY DATE(date_recette)
            ORDER BY date DESC;
        ''', (current_user.id,))
    
    stats = cursor.fetchall()
    
    # Formater les reçus
    formatted_recettes = []
    for recette in recettes:
        formatted_recette = {
            'id': recette['id'],
            'montant': float(recette['montant']),
            'date': recette['date_recette'].strftime('%Y-%m-%d %H:%M:%S'),
            'immatriculation': recette['immatriculation'],
            'duree': recette['duree'],
            'heure_entree': recette['heure_entree'].strftime('%H:%M:%S'),
            'heure_sortie': recette['heure_sortie'].strftime('%H:%M:%S') if recette['heure_sortie'] else None
        }
        
        if current_user.role == 'admin':
            formatted_recette['username'] = recette['username']
        
        formatted_recettes.append(formatted_recette)
    
    # Formater les statistiques
    formatted_stats = []
    total_montant = 0
    
    for stat in stats:
        formatted_stat = {
            'date': stat['date'].strftime('%Y-%m-%d'),
            'total_count': stat['total_count'],
            'total_montant': float(stat['total_montant']) if stat['total_montant'] else 0
        }
        
        total_montant += formatted_stat['total_montant']
        
        if current_user.role == 'admin':
            formatted_stat.update({
                'user_id': stat['user_id'],
                'username': stat['username']
            })
        
        formatted_stats.append(formatted_stat)
    
    cursor.close()
    conn.close()
    
    return jsonify({
        'recettes': formatted_recettes,
        'statistics': {
            'daily': formatted_stats,
            'total_montant': total_montant
        }
    })

@app.route('/api/recettes/<int:recette_id>')
@login_required
def get_recette(recette_id):
    conn = get_db_connection()
    cursor = conn.cursor(dictionary=True)
    
    if current_user.role == 'admin':
        cursor.execute('''
            SELECT 
                r.*,
                s.immatriculation,
                s.duree,
                s.heure_entree,
                s.heure_sortie,
                u.username
            FROM recettes r
            JOIN sessions s ON r.session_id = s.id
            JOIN users u ON r.user_id = u.id
            WHERE r.id = %s;
        ''', (recette_id,))
    else:
        cursor.execute('''
            SELECT 
                r.*,
                s.immatriculation,
                s.duree,
                s.heure_entree,
                s.heure_sortie
            FROM recettes r
            JOIN sessions s ON r.session_id = s.id
            WHERE r.id = %s AND r.user_id = %s;
        ''', (recette_id, current_user.id))
    
    recette = cursor.fetchone()
    
    if not recette:
        cursor.close()
        conn.close()
        return jsonify({
            'error': 'Reçu non trouvé'
        }), 404
    
    # Formater le reçu
    formatted_recu = {
        'id': recette['id'],
        'montant': float(recette['montant']),
        'date': recette['date_recette'].strftime('%Y-%m-%d %H:%M:%S'),
        'immatriculation': recette['immatriculation'],
        'duree': recette['duree'],
        'heure_entree': recette['heure_entree'].strftime('%H:%M:%S'),
        'heure_sortie': recette['heure_sortie'].strftime('%H:%M:%S') if recette['heure_sortie'] else None
    }
    
    if current_user.role == 'admin':
        formatted_recu['username'] = recette['username']
    
    cursor.close()
    conn.close()
    
    return jsonify({
        'recu': formatted_recu
    })

@app.route('/api/detections')
@login_required
def get_detections():
    conn = get_db_connection()
    cursor = conn.cursor(dictionary=True)
    
    # Récupérer les détections
    cursor.execute('''
        SELECT 
            id,
            image_path,
            plaque,
            date_detection,
            confiance
        FROM detections
        ORDER BY date_detection DESC
        LIMIT 50;
    ''')
    
    detections = cursor.fetchall()
    
    # Formater les détections
    formatted_detections = []
    for detection in detections:
        formatted_detection = {
            'id': detection['id'],
            'image': detection['image_path'],
            'plaque': detection['plaque'],
            'date': detection['date_detection'].strftime('%Y-%m-%d %H:%M:%S'),
            'confiance': float(detection['confiance'])
        }
        formatted_detections.append(formatted_detection)
    
    cursor.close()
    conn.close()
    
    return jsonify({
        'detections': formatted_detections
    })

@app.route('/api/users', methods=['GET', 'POST'])
@login_required
def manage_users():
    if current_user.role != 'admin':
        return jsonify({'error': 'Unauthorized'}), 403
    
    if request.method == 'GET':
        conn = get_db_connection()
        cursor = conn.cursor(dictionary=True)
        
        cursor.execute('''
            SELECT 
                id,
                username,
                nom,
                prenom,
                cin,
                adresse,
                role,
                created_at
            FROM users
            WHERE id != %s
            ORDER BY created_at DESC
        ''', (current_user.id,))
        
        users = cursor.fetchall()
        formatted_users = []
        
        for user in users:
            formatted_user = {
                'id': user['id'],
                'username': user['username'],
                'nom': user['nom'],
                'prenom': user['prenom'],
                'cin': user['cin'],
                'adresse': user['adresse'],
                'role': user['role'],
                'created_at': user['created_at'].strftime('%Y-%m-%d %H:%M:%S')
            }
            formatted_users.append(formatted_user)
        
        cursor.close()
        conn.close()
        
        return jsonify({
            'users': formatted_users,
            'total': len(formatted_users)
        })
    
    elif request.method == 'POST':
        data = request.json
        required_fields = ['username', 'password', 'nom', 'prenom', 'cin', 'adresse', 'role']
        
        # Vérifier que tous les champs requis sont présents
        for field in required_fields:
            if not data.get(field):
                return jsonify({
                    'error': f'Le champ {field} est requis'
                }), 400
        
        # Vérifier que le CIN contient exactement 8 chiffres
        if not re.match(r'^\d{8}$', data['cin']):
            return jsonify({
                'error': 'Le numéro CIN doit contenir exactement 8 chiffres'
            }), 400
        
        # Vérifier que le mot de passe fait au moins 8 caractères
        if len(data['password']) < 8:
            return jsonify({
                'error': 'Le mot de passe doit contenir au moins 8 caractères'
            }), 400
        
        conn = get_db_connection()
        cursor = conn.cursor(dictionary=True)
        
        try:
            # Vérifier si le CIN existe déjà
            cursor.execute('SELECT id FROM users WHERE cin = %s', (data['cin'],))
            if cursor.fetchone():
                return jsonify({
                    'error': 'Un utilisateur avec ce numéro CIN existe déjà'
                }), 400
            
            # Créer le nouvel utilisateur
            hashed_password = generate_password_hash(data['password'])
            cursor.execute('''
                INSERT INTO users (username, nom, prenom, cin, adresse, password, role)
                VALUES (%s, %s, %s, %s, %s, %s, %s)
            ''', (data['username'], data['nom'], data['prenom'], data['cin'], 
                  data['adresse'], hashed_password, data['role']))
            
            conn.commit()
            user_id = cursor.lastrowid
            
            # Récupérer l'utilisateur créé
            cursor.execute('''
                SELECT id, username, nom, prenom, cin, adresse, role, created_at
                FROM users WHERE id = %s
            ''', (user_id,))
            
            new_user = cursor.fetchone()
            formatted_user = {
                'id': new_user['id'],
                'username': new_user['username'],
                'nom': new_user['nom'],
                'prenom': new_user['prenom'],
                'cin': new_user['cin'],
                'adresse': new_user['adresse'],
                'role': new_user['role'],
                'created_at': new_user['created_at'].strftime('%Y-%m-%d %H:%M:%S')
            }
            
            cursor.close()
            conn.close()
            
            return jsonify({
                'message': 'Utilisateur créé avec succès',
                'user': formatted_user
            }), 201
            
        except Exception as e:
            cursor.close()
            conn.close()
            return jsonify({
                'error': f'Erreur lors de la création: {str(e)}'
            }), 500

@app.route('/api/users/<int:user_id>', methods=['PUT'])
@login_required
def update_user(user_id):
    if current_user.role != 'admin':
        return jsonify({
            'error': 'Accès non autorisé'
        }), 403
    
    # Vérifier qu'on ne modifie pas l'utilisateur actuel
    if user_id == current_user.id:
        return jsonify({
            'error': 'Vous ne pouvez pas modifier votre propre compte'
        }), 400
    
    data = request.json
    username = data.get('username')
    password = data.get('password')
    role = data.get('role')
    
    if not username or not role:
        return jsonify({
            'error': 'Les champs username et role sont requis'
        }), 400
    
    if role not in ['admin', 'user']:
        return jsonify({
            'error': 'Le rôle doit être "admin" ou "user"'
        }), 400
    
    conn = get_db_connection()
    cursor = conn.cursor(dictionary=True)
    
    try:
        # Vérifier si l'utilisateur existe
        cursor.execute('SELECT id FROM users WHERE id = %s', (user_id,))
        if not cursor.fetchone():
            cursor.close()
            conn.close()
            return jsonify({
                'error': 'Utilisateur non trouvé'
            }), 404
        
        # Vérifier si le nouveau nom d'utilisateur existe déjà
        cursor.execute('SELECT id FROM users WHERE username = %s AND id != %s', 
                       (username, user_id))
        if cursor.fetchone():
            cursor.close()
            conn.close()
            return jsonify({
                'error': 'Un utilisateur avec ce nom existe déjà'
            }), 400
        
        # Mettre à jour l'utilisateur
        if password:
            hashed_password = generate_password_hash(password)
            cursor.execute('''
                UPDATE users 
                SET username = %s,
                    password = %s,
                    role = %s
                WHERE id = %s;
            ''', (username, hashed_password, role, user_id))
        else:
            cursor.execute('''
                UPDATE users 
                SET username = %s,
                    role = %s
                WHERE id = %s;
            ''', (username, role, user_id))
        
        conn.commit()
        
        # Récupérer l'utilisateur mis à jour
        cursor.execute('''
            SELECT 
                id,
                username,
                role,
                created_at
            FROM users
            WHERE id = %s
        ''', (user_id,))
        
        updated_user = cursor.fetchone()
        formatted_user = {
            'id': updated_user['id'],
            'username': updated_user['username'],
            'role': updated_user['role'],
            'created_at': updated_user['created_at'].strftime('%Y-%m-%d %H:%M:%S')
        }
        
        cursor.close()
        conn.close()
        
        return jsonify({
            'message': 'Utilisateur mis à jour avec succès',
            'user': formatted_user
        })
        
    except Exception as e:
        cursor.close()
        conn.close()
        return jsonify({
            'error': f'Erreur lors de la mise à jour: {str(e)}'
        }), 500

@app.route('/api/users/<int:user_id>', methods=['DELETE'])
@login_required
def delete_user(user_id):
    if current_user.role != 'admin':
        return jsonify({
            'error': 'Accès non autorisé'
        }), 403
    
    # Vérifier qu'on ne supprime pas l'utilisateur actuel
    if user_id == current_user.id:
        return jsonify({
            'error': 'Vous ne pouvez pas supprimer votre propre compte'
        }), 400
    
    conn = get_db_connection()
    cursor = conn.cursor(dictionary=True)
    
    try:
        # Vérifier si l'utilisateur existe
        cursor.execute('SELECT username FROM users WHERE id = %s', (user_id,))
        user = cursor.fetchone()
        
        if not user:
            cursor.close()
            conn.close()
            return jsonify({
                'error': 'Utilisateur non trouvé'
            }), 404
        
        # Supprimer l'utilisateur
        cursor.execute('DELETE FROM users WHERE id = %s', (user_id,))
        conn.commit()
        
        cursor.close()
        conn.close()
        
        return jsonify({
            'message': f'Utilisateur {user["username"]} supprimé avec succès'
        })
        
    except Exception as e:
        cursor.close()
        conn.close()
        return jsonify({
            'error': f'Erreur lors de la suppression: {str(e)}'
        }), 500

def get_parking_stats():
    conn = get_db_connection()
    cursor = conn.cursor(dictionary=True)
    
    # Get total revenue for today
    cursor.execute("""
        SELECT COALESCE(SUM(montant_paye), 0) as total_revenue
        FROM paiements
        WHERE DATE(created_at) = CURDATE()
    """)
    revenue = cursor.fetchone()['total_revenue']
    
    # Get current occupancy
    cursor.execute("""
        SELECT 
            COUNT(*) as total_occupied
        FROM sessions
        WHERE heure_sortie IS NULL
    """)
    occupancy = cursor.fetchone()['total_occupied']
    
    cursor.close()
    conn.close()
    
    return {
        'revenue': float(revenue),
        'occupancy': occupancy,
        'total_spaces': 6
    }

@app.route('/api/process-entry', methods=['POST'])
@login_required
def process_entry():
    try:
        # Get image from request
        image_data = request.json.get('image')
        if not image_data:
            return jsonify({'error': 'No image provided'}), 400
            
        # Convert base64 to image
        image_bytes = base64.b64decode(image_data.split(',')[1])
        nparr = np.frombuffer(image_bytes, np.uint8)
        img = cv2.imdecode(nparr, cv2.IMREAD_COLOR)
        
        # Run YOLO detection
        results = yolo_model(img)
        
        # Process YOLO results
        for r in results:
            if len(r.boxes) > 0:
                for box in r.boxes:
                    x1, y1, x2, y2 = map(int, box.xyxy[0])
                    plate_img = img[y1:y2, x1:x2]
                    
                    # Use EasyOCR on the plate region
                    results = reader.readtext(plate_img)
                    if results:
                        plate_number = results[0][1]
                        
                        # Find available parking space
                        conn = get_db_connection()
                        cursor = conn.cursor(dictionary=True)
                        
                        # Get first available space
                        cursor.execute("""
                            SELECT numero FROM (
                                SELECT 1 as numero UNION SELECT 2 UNION SELECT 3 
                                UNION SELECT 4 UNION SELECT 5 UNION SELECT 6
                            ) p
                            WHERE numero NOT IN (
                                SELECT place_numero FROM sessions WHERE heure_sortie IS NULL
                            )
                            LIMIT 1
                        """)
                        
                        space = cursor.fetchone()
                        if not space:
                            return jsonify({'error': 'No available parking spaces'}), 400
                            
                        # Create new session
                        cursor.execute("""
                            INSERT INTO sessions (immatriculation, place_numero, heure_entree)
                            VALUES (%s, %s, NOW())
                        """, (plate_number, space['numero']))
                        
                        conn.commit()
                        cursor.close()
                        conn.close()
                        
                        return jsonify({
                            'success': True,
                            'plate_number': plate_number,
                            'space_number': f"P{space['numero']}"
                        })
                        
        return jsonify({'error': 'No license plate detected'}), 400
                        
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@app.route('/api/process-exit', methods=['POST'])
@login_required
def process_exit():
    try:
        plate_number = request.json.get('plate_number')
        if not plate_number:
            return jsonify({'error': 'No plate number provided'}), 400
            
        conn = get_db_connection()
        cursor = conn.cursor(dictionary=True)
        
        # Get active session
        cursor.execute("""
            SELECT id, heure_entree, place_numero
            FROM sessions
            WHERE immatriculation = %s AND heure_sortie IS NULL
            LIMIT 1
        """, (plate_number,))
        
        session = cursor.fetchone()
        if not session:
            return jsonify({'error': 'No active session found for this plate number'}), 404
            
        # Calculate duration and amount
        cursor.execute("""
            UPDATE sessions
            SET heure_sortie = NOW(),
                duree = TIMESTAMPDIFF(MINUTE, heure_entree, NOW()),
                montant = GREATEST(CEIL(TIMESTAMPDIFF(MINUTE, heure_entree, NOW()) / 15) * 0.5, 0.5)
            WHERE id = %s
        """, (session['id'],))
        
        # Get updated session details
        cursor.execute("""
            SELECT id, duree, montant
            FROM sessions
            WHERE id = %s
        """, (session['id'],))
        
        updated_session = cursor.fetchone()
        conn.commit()
        cursor.close()
        conn.close()
        
        return jsonify({
            'success': True,
            'session_id': updated_session['id'],
            'duration': updated_session['duree'],
            'amount': float(updated_session['montant'])
        })
        
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@app.route('/api/process-payment', methods=['POST'])
@login_required
def process_payment():
    try:
        session_id = request.json.get('session_id')
        amount_paid = Decimal(str(request.json.get('amount_paid', 0)))
        
        if not session_id:
            return jsonify({'error': 'No session ID provided'}), 400
            
        conn = get_db_connection()
        cursor = conn.cursor(dictionary=True)
        
        # Get session details
        cursor.execute("""
            SELECT montant
            FROM sessions
            WHERE id = %s
        """, (session_id,))
        
        session = cursor.fetchone()
        if not session:
            return jsonify({'error': 'Session not found'}), 404
            
        amount_due = Decimal(str(session['montant']))
        
        if amount_paid < amount_due:
            return jsonify({'error': 'Insufficient payment'}), 400
            
        # Record payment
        cursor.execute("""
            INSERT INTO paiements (session_id, montant_paye, montant_change, status_paiement)
            VALUES (%s, %s, %s, 'completed')
        """, (session_id, float(amount_paid), float(amount_paid - amount_due)))
        
        conn.commit()
        cursor.close()
        conn.close()
        
        return jsonify({
            'success': True,
            'amount_paid': float(amount_paid),
            'change': float(amount_paid - amount_due)
        })
        
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@app.route('/historique')
@login_required
def historique():
    conn = get_db_connection()
    cursor = conn.cursor(dictionary=True)
    
    # Récupérer les statistiques initiales
    cursor.execute("""
        SELECT 
            COUNT(*) as total_vehicules,
            COALESCE(SUM(montant), 0) as recette_totale,
            COUNT(CASE WHEN temps_sortie IS NULL THEN 1 END) as vehicules_presents,
            COUNT(CASE WHEN DATE(temps_entree) = CURDATE() THEN 1 END) as vehicules_aujourd_hui
        FROM historique_stationnement
    """)
    stats = cursor.fetchone()
    
    cursor.close()
    conn.close()
    
    return render_template('historique.html', 
                         stats_globales=stats,
                         active_page='historique')

@app.route('/api/historique')
@login_required
def get_historique():
    try:
        date_debut = request.args.get('date_debut')
        date_fin = request.args.get('date_fin')
        
        conn = get_db_connection()
        cursor = conn.cursor(dictionary=True)
        
        # Base query
        query = '''
            SELECT 
                id,
                plaque,
                place,
                temps_entree as heure_entree,
                temps_sortie as heure_sortie,
                duree_minutes as duree,
                montant as montant_total,
                montant as montant_paye,  -- Ajuster si nécessaire selon la logique de paiement
                0 as montant_change,      -- Ajuster si nécessaire selon la logique de paiement
                status_paiement,
                CASE 
                    WHEN temps_sortie IS NULL AND status_paiement = 'en_attente' THEN 'en_cours'
                    WHEN status_paiement = 'payé' THEN 'terminé'
                    ELSE 'en_attente'
                END as statut_session
            FROM historique_stationnement
            WHERE 1=1
        '''
        params = []
        
        if date_debut and date_fin:
            query += " AND DATE(temps_entree) BETWEEN %s AND %s"
            params.extend([date_debut, date_fin])
        
        query += " ORDER BY temps_entree DESC"
        
        cursor.execute(query, params)
        historique = cursor.fetchall()
        
        # Get statistics
        stats_query = '''
            SELECT 
                COUNT(*) as total_vehicules,
                COALESCE(SUM(montant), 0) as revenu_total,
                COUNT(CASE WHEN temps_sortie IS NULL THEN 1 END) as vehicules_presents,
                COUNT(CASE WHEN DATE(temps_entree) = CURDATE() THEN 1 END) as vehicules_aujourd_hui
            FROM historique_stationnement
            WHERE 1=1
        '''
        
        if date_debut and date_fin:
            stats_query += " AND DATE(temps_entree) BETWEEN %s AND %s"
        
        cursor.execute(stats_query, params if params else [])
        stats = cursor.fetchone()
        
        # Format the data
        formatted_historique = []
        for entry in historique:
            formatted_entry = {
                'id': entry['id'],
                'plaque': entry['plaque'],
                'place': entry['place'],
                'temps_entree': entry['heure_entree'].strftime('%d/%m/%Y %H:%M') if entry['heure_entree'] else None,
                'temps_sortie': entry['heure_sortie'].strftime('%d/%m/%Y %H:%M') if entry['heure_sortie'] else None,
                'duree_formatee': f"{entry['duree']} min" if entry['duree'] else '-',
                'montant_total': float(entry['montant_total']) if entry['montant_total'] else 0,
                'montant_paye': float(entry['montant_paye']) if entry['montant_paye'] else 0,
                'montant_change': float(entry['montant_change']) if entry['montant_change'] else 0,
                'status_paiement': entry['status_paiement'],
                'statut_session': entry['statut_session']
            }
            formatted_historique.append(formatted_entry)
        
        cursor.close()
        conn.close()
        
        return jsonify({
            'historique': formatted_historique,
            'stats': {
                'total_vehicules': stats['total_vehicules'],
                'revenu_total': float(stats['revenu_total']),
                'vehicules_presents': stats['vehicules_presents'],
                'vehicules_aujourd_hui': stats['vehicules_aujourd_hui']
            }
        })
        
    except Exception as e:
        return jsonify({'error': str(e)}), 500

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5001, debug=True)


