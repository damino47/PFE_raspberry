from flask import Flask, render_template_string, jsonify, request, send_file
from datetime import datetime
import mysql.connector
from reportlab.pdfgen import canvas
from reportlab.lib.pagesizes import A4
from reportlab.lib import colors
from reportlab.lib.units import cm
import os
from PIL import Image
import traceback
import shutil
import json

# Configuration de la base de données
DATABASE_CONFIG = {
    'host': 'localhost',
    'user': 'root',
    'password': '',
    'database': 'parking_db'
}

# Initialisation de la base de données
def get_db_connection():
    try:
        conn = mysql.connector.connect(**DATABASE_CONFIG)
        if conn.is_connected():
            return conn
        else:
            print("Erreur : Impossible de se connecter à la base de données")
            return None
    except mysql.connector.Error as e:
        print(f"Erreur de connexion à la base de données : {e}")
        return None


def update_payment_status(vehicle_id):
    try:
        conn = get_db_connection()
        if not conn:
            print("Erreur : Connexion à la base de données échouée")
            return False

        cursor = conn.cursor()
        query = '''
            UPDATE historique_stationnement
            SET status_paiement = 'payé'
            WHERE id = %s
        '''
        cursor.execute(query, (vehicle_id,))
        conn.commit()
        print(f"Statut de paiement mis à jour pour le véhicule ID {vehicle_id}.")
        return True
    except mysql.connector.Error as e:
        print(f"Erreur lors de la mise à jour du statut de paiement : {e}")
        return False
    finally:
        if 'cursor' in locals():
            cursor.close()
        if 'conn' in locals() and conn.is_connected():
            conn.close()


def generer_dashboard_paiement(plaque, place, temps_entree, temps_sortie, duree_minutes, montant):
    try:
        print("Début de la génération du dashboard de paiement...")
        # Chemin du fichier HTML existant
        SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
        html_path = os.path.join(SCRIPT_DIR, 'templates/dashboard_paiement.html')
        print(f"Chemin du fichier HTML : {html_path}")
        
        # Vérifier si le fichier existe
        if not os.path.exists(html_path):
            print(f"Erreur : Le fichier {html_path} n'existe pas.")
            return
        
        # Lire le fichier HTML et remplacer les placeholders
        with open(html_path, 'r', encoding='utf-8') as f:
            html_content = f.read()
        
        html_content = html_content.replace('{{plaque}}', str(plaque))
        html_content = html_content.replace('{{place}}', str(place))
        html_content = html_content.replace('{{temps_entree}}', temps_entree.strftime('%d/%m/%Y %H:%M:%S'))
        html_content = html_content.replace('{{temps_sortie}}', temps_sortie.strftime('%d/%m/%Y %H:%M:%S'))
        html_content = html_content.replace('{{duree_minutes}}', f"{duree_minutes:.1f}")
        html_content = html_content.replace('{{montant}}', f"{montant:.2f} DT")
        
        # Sauvegarder le fichier temporaire
        temp_html_path = os.path.join(SCRIPT_DIR, 'dashboard_paiement.html')
        with open(temp_html_path, 'w', encoding='utf-8') as f:
            f.write(html_content)
        
        # Ouvrir le fichier HTML
        os.startfile(temp_html_path)
        print(f"Dashboard de paiement affiché avec succès depuis {temp_html_path}")
    except Exception as e:
        print(f"Erreur lors de l'affichage du dashboard de paiement : {e}")
        raise  # Relancer l'exception pour la capturer dans le contexte d'appel


# Connexion à la base de données
conn = get_db_connection()
if not conn:
    print("Erreur : Connexion à la base de données échouée")
    exit()

# Requête SQL pour récupérer les données
query = '''
    SELECT 
        plaque, 
        place, 
        temps_entree, 
        temps_sortie, 
        duree_minutes, 
        montant 
    FROM historique_stationnement
    WHERE id = %s
'''

# Constantes pour les champs de la table historique_stationnement
plaque = 'plaque'
place = 'place'
temps_entree = 'temps_entree'
temps_sortie = 'temps_sortie'
duree_minutes = 'duree_minutes'
montant = 'montant'

# Exemple d'ID pour récupérer les données
vehicle_id = 29

cursor = conn.cursor(dictionary=True)
cursor.execute(query, (vehicle_id,))
data = cursor.fetchone()


# Vérifiez si les données existent
if data:
    # Calculer les champs dynamiques si nécessaire
    data['temps_entree'] = data['temps_entree'].strftime('%d/%m/%Y %H:%M:%S') if data['temps_entree'] else 'N/A'
    data['temps_sortie'] = data['temps_sortie'].strftime('%d/%m/%Y %H:%M:%S') if data['temps_sortie'] else 'N/A'
    data['duree_minutes'] = f"{data['duree_minutes']:.1f}" if data['duree_minutes'] else 'N/A'
    data['montant'] = f"{data['montant']:.2f}" if data['montant'] else 'N/A'

    # Appeler la fonction pour générer le tableau de bord
    generer_dashboard_paiement(
        plaque=data['plaque'],
        place=data['place'],
        temps_entree=datetime.strptime(data['temps_entree'], '%d/%m/%Y %H:%M:%S'),
        temps_sortie=datetime.strptime(data['temps_sortie'], '%d/%m/%Y %H:%M:%S'), 
        duree_minutes=float(data['duree_minutes']),       
        montant=float(data['montant'])
    )


    # Mettre à jour le statut de paiement
    if update_payment_status(vehicle_id):
        print("Statut de paiement mis à jour avec succès.")
    else:
        print("Échec de la mise à jour du statut de paiement.")
else:
    print("Aucune donnée trouvée pour l'ID spécifié.")

# Fermer la connexion
cursor.close()
conn.close()