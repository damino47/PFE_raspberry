from datetime import datetime
import os
import cv2
from ultralytics import YOLO
import easyocr
import numpy as np
import re
import time
from PIL import Image
import mysql.connector
import sys
from admin.init_db import init_db

# Définir le chemin absolu du répertoire du script
SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))

# Ajouter le répertoire parent au chemin de recherche Python
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from admin.config import DATABASE_CONFIG

# Compatibility fix for PIL ANTIALIAS deprecation
if not hasattr(Image, 'ANTIALIAS'):
    Image.ANTIALIAS = Image.LANCZOS

# Définir le chemin du dossier images
IMAGES_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'admin', 'images')
if not os.path.exists(IMAGES_DIR):
    os.makedirs(IMAGES_DIR)

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

def call_init_db():
    conn = get_db_connection()
    cursor = conn.cursor()
    
    try:
        
        init_db()
        cursor.connect()
        conn.commit()
        print("Base de données initialisée avec succès à partir du fichier init_db.sql!")
        
    except Exception as e:
        print(f"Erreur lors de l'initialisation de la base de données : {e}")
        conn.rollback()
    finally:
        cursor.close()
        conn.close()

class PlateDetector:
    def __init__(self):
        self.model = YOLO('yolov8n.pt')
        self.reader = easyocr.Reader(['ar', 'en'])

    def preprocess_image(self, image):
        gray = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)
        clahe = cv2.createCLAHE(clipLimit=3.0, tileGridSize=(8, 8))
        enhanced = clahe.apply(gray)
        denoised = cv2.bilateralFilter(enhanced, 9, 75, 75)
        binary = cv2.adaptiveThreshold(denoised, 255, cv2.ADAPTIVE_THRESH_GAUSSIAN_C, cv2.THRESH_BINARY_INV, 11, 2)
        kernel = np.ones((3, 3), np.uint8)
        morph = cv2.morphologyEx(binary, cv2.MORPH_CLOSE, kernel)
        morph = cv2.morphologyEx(morph, cv2.MORPH_OPEN, kernel)
        return morph, enhanced

    def find_plate_regions(self, binary_img, original_img):
        contours, _ = cv2.findContours(binary_img, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
        regions = []
        img_h, img_w = original_img.shape[:2]

        for cnt in contours:
            x, y, w, h = cv2.boundingRect(cnt)
            aspect_ratio = w / float(h)
            area = w * h
            area_ratio = area / (img_w * img_h)

            if (2.0 <= aspect_ratio <= 5.0 and
                0.01 <= area_ratio <= 0.15 and
                w > 60 and h > 20):
                regions.append((x, y, w, h))

        return regions

    def clean_text(self, text):
        print(f"Texte brut avant nettoyage : '{text}'")
        # Conserver uniquement les chiffres, espaces et caractères arabes spécifiques
        text = re.sub(r'[^\d\s\u062a\u0648\u0646\u0633]', '', text)

        # Remplacer toutes les variantes incorrectes par 'تونس'
        text = re.sub(r'\bتون\b', 'تونس', text)  # Remplace 'تون' par 'تونس'
        text = re.sub(r'\bتونن\b', 'تونس', text)  # Remplace 'تونن' par 'تونس'

        # Supprimer les espaces inutiles
        text = ' '.join(text.split())

        print(f"Texte après nettoyage : '{text}'")
        return text.strip()

    def validate_and_combine_plate(self, detected_texts):
        print(f"Textes détectés avant combinaison : {detected_texts}")

        if not detected_texts:
            print("⚠️ Aucun texte détecté. Impossible de former une plaque.")
            return None

        combined_text = ' '.join(detected_texts).strip()

        numbers_only = [re.sub(r'\D', '', text) for text in detected_texts if re.sub(r'\D', '', text)]

        if len(numbers_only) >= 2:
            part1 = next((n for n in numbers_only if len(n) == 4), None)
            part2 = next((n for n in numbers_only if len(n) == 3 and n != part1), None)
            if part1 and part2:
                combined_text = f"{part1} تونس {part2}"
                print(f"✅ Plaque reconstituée automatiquement : {combined_text}")
                return combined_text

        if 'تونس' not in combined_text:
            if len(detected_texts) >= 2:
                print(f"Ajout de 'تونس' manquant dans ({combined_text})")
                combined_text = f"{detected_texts[0]} تونس {detected_texts[-1]}"
            else:
                print("⚠️ Pas assez de textes pour ajouter 'تونس'")
                return None

        if len(combined_text) < 5:
            print(f"Validation échouée : Texte trop court ({combined_text})")
            return None

        print(f"Plaque combinée et validée : {combined_text}")
        return combined_text




    def detect_plate(self, image_path):
        print(f"\n=== Détection de plaque démarrée ===")
        print(f"Analyse de l'image : {image_path}")

        # Utiliser le chemin complet pour l'image
        full_image_path = os.path.join(IMAGES_DIR, os.path.basename(image_path))
        print(f"Chemin complet de l'image : {full_image_path}")

        # Vérifier si le fichier existe
        if not os.path.exists(full_image_path):
            print(f"ERREUR: Le fichier {full_image_path} n'existe pas!")
            return None

        image = cv2.imread(full_image_path)
        if image is None:
            print(f"ERREUR: Impossible de charger l'image: {full_image_path}")
            return None

        print(f"Taille de l'image chargée: {image.shape}")

        try:
            binary, enhanced = self.preprocess_image(image)
            print("Prétraitement de l'image terminé")

            regions = self.find_plate_regions(binary, image)
            print(f"Nombre de régions détectées: {len(regions)}")

            detected_texts = []

            for i, (x, y, w, h) in enumerate(regions):
                print(f"\nTraitement de la région {i+1} à la position (x={x}, y={y}, w={w}, h={h})")

                margin = 5
                x1 = max(0, x - margin)
                y1 = max(0, y - margin)
                x2 = min(image.shape[1], x + w + margin)
                y2 = min(image.shape[0], y + h + margin)

                roi = enhanced[y1:y2, x1:x2]

                if roi.size == 0:
                    print(f"  ROI vide pour la région {i+1}, passage à la suivante...")
                    continue

                # Sauvegarder la ROI pour le débogage
                roi_filename = f'roi_{i}.jpg'
                cv2.imwrite(roi_filename, roi)
                print(f"  ROI sauvegardée dans {roi_filename}")

                # Utiliser EasyOCR pour lire le texte
                print("  Lecture du texte avec EasyOCR...")
                results = self.reader.readtext(roi, detail=1, paragraph=False)
                print(f"  Résultats EasyOCR bruts: {results}")

                for (bbox, text, conf) in results:
                    print(f"Texte brut détecté : '{text}', Confiance : {conf:.2f}")
                    cleaned_text = self.clean_text(text)
                    print(f"  Texte détecté: '{text}' (nettoyé: '{cleaned_text}'), confiance: {conf:.2f}")

                    # Inclure les textes avec une confiance supérieure à 0.5
                    if conf > 0.5:
                        detected_texts.append(cleaned_text)

            # Combiner et valider les textes détectés
            best_text = self.validate_and_combine_plate(detected_texts)

            if best_text:
                print(f"\nDétection finale: '{best_text}'")
                return best_text
            else:
                print("Aucune plaque valide détectée dans l'image")

            print("=== Détection de plaque terminée ===\n")
            return None

        except Exception as e:
            print(f"ERREUR lors de la détection de plaque: {str(e)}")
            import traceback
            traceback.print_exc()
            return None

class ParkingManager:
    def __init__(self):
        self.places = self.load_places_from_db()

    def load_places_from_db(self):
        """Charge les places de parking depuis la base de données."""
        try:
            conn = get_db_connection()
            if not conn:
                print("Erreur : Connexion à la base de données échouée")
                return {}

            cursor = conn.cursor(dictionary=True)

            # Charger toutes les places depuis la base de données
            cursor.execute("SELECT numero, occupied, last_update FROM places")
            places = cursor.fetchall()

            # Convertir les résultats en un dictionnaire
            places_dict = {}
            for place in places:
                status = 'libre' if place['occupied'] == 0 else 'occupé'
                places_dict[f"P{place['numero']}"] = {
                    'status': status,
                    'description': f"Dernière mise à jour : {place['last_update']}"
                }
            return places_dict
        except Exception as e:
            print(f"Erreur lors du chargement des places : {e}")
            return {}
        finally:
            if cursor:
                cursor.close()
            if conn and conn.is_connected():
                conn.close()
    def get_available_place(self):
        """Retourne la première place disponible."""
        try:
            print("Connexion à la base de données pour obtenir une place disponible...")
            conn = get_db_connection()
            if not conn:
                print("Erreur : Connexion à la base de données échouée")
                return None

            cursor = conn.cursor(dictionary=True)

            # Rechercher les places disponibles
            query = "SELECT numero, last_update FROM places WHERE occupied = 0 ORDER BY numero ASC"
            print(f"Exécution de la requête : {query}")
            cursor.execute(query)
            available_place = cursor.fetchone()  # Lire le premier résultat

            # Consommer tous les résultats restants pour éviter l'erreur "Unread result found"
            cursor.fetchall()

            if available_place:
                place_number = f"P{available_place['numero']}"
                print(f"Place disponible trouvée : {place_number}")
                return place_number, f"Dernière mise à jour : {available_place['last_update']}"

            print("Aucune place disponible")
            return None
        except Exception as e:
            print(f"Erreur en vérifiant les places : {e}")
            raise  # Relancer l'exception pour la capturer dans `surveiller_entree`
        finally:
            if cursor:
                print("Fermeture du curseur après la recherche de place disponible.")
                cursor.close()
            if conn and conn.is_connected():
                print("Fermeture de la connexion à la base de données après la recherche de place disponible.")
                conn.close()

    def update_place_status(self, numero, occupied):
        """
        Met à jour le statut d'une place de parking dans la base de données.
        :param numero: Numéro de la place (int)
        :param occupied: 1 si occupée, 0 si libre (int)
        """
        try:
            #Retirer le préfixe "P" si présent
            if isinstance(numero, str) and numero.startswith("P"):
                numero = int(numero[1:])


            print(f"Mise à jour du statut de la place {numero} à {'occupé' if occupied else 'libre'}...")
            conn = get_db_connection()
            if not conn:
                print("Erreur : Connexion à la base de données échouée")
                return False

            cursor = conn.cursor()
            query = """
                UPDATE places
                SET occupied = %s, last_update = NOW()
                WHERE numero = %s
            """
            cursor.execute(query, (occupied, numero))
            conn.commit()
            print(f"Statut de la place {numero} mis à jour avec succès.")
            return True
        except Exception as e:
            print(f"Erreur lors de la mise à jour du statut de la place : {e}")
            return False
        finally:
            if cursor:
                cursor.close()
            if conn and conn.is_connected():
                conn.close()

def generer_dashboard_entree(plaque, place, description, date_entree):
    try:
        print("Début de la génération du dashboard d'entrée...")
        # Chemin du fichier HTML existant
        html_path = os.path.join(SCRIPT_DIR, 'templates/dashboard_entree.html')
        print(f"Chemin du fichier HTML : {html_path}")
        
        # Vérifier si le fichier existe
        if not os.path.exists(html_path):
            print(f"Erreur : Le fichier {html_path} n'existe pas.")
            return
        
        # Lire le fichier HTML et remplacer les placeholders
        with open(html_path, 'r', encoding='utf-8') as f:
            html_content = f.read()
        
        # Ajouter le préfixe "P" à la place
        html_content = html_content.replace('{{plaque}}', str(plaque))
        html_content = html_content.replace('{{place}}', f"{place}")
        html_content = html_content.replace('{{description}}', str(description))
        html_content = html_content.replace('{{date_entree}}', date_entree.strftime('%d/%m/%Y %H:%M:%S'))
        
        # Sauvegarder le fichier temporaire
        temp_html_path = os.path.join(SCRIPT_DIR, 'dashboard_entree_temp.html')
        with open(temp_html_path, 'w', encoding='utf-8') as f:
            f.write(html_content)
        
        # Ouvrir le fichier HTML
        os.startfile(temp_html_path)
        print(f"Dashboard d'entrée affiché avec succès depuis {temp_html_path}")
    except Exception as e:
        print(f"Erreur lors de l'affichage du dashboard d'entrée : {e}")
        raise  # Relancer l'exception pour la capturer dans `surveiller_entree`

def enregistrer_voiture(plaque, place):
    try:
        print("Connexion à la base de données pour enregistrer le véhicule...")
        conn = get_db_connection()
        if not conn:
            print("Erreur : Connexion à la base de données échouée")
            return

        cursor = conn.cursor()
        date_entree = datetime.now().strftime('%Y-%m-%d %H:%M:%S')

        query = """
            INSERT INTO vehicules_en_stationnement (plaque, place, temps_entree)
            VALUES (%s, %s, %s)
        """
        print(f"Exécution de la requête : {query} avec les paramètres ({plaque}, {place}, {date_entree})")
        cursor.execute(query, (plaque, place, date_entree))
        conn.commit()
        print("Véhicule enregistré avec succès dans la base de données.")
    except mysql.connector.Error as e:
        print(f"Erreur lors de l'enregistrement du véhicule : {e}")
        raise  # Relancer l'exception pour la capturer dans `surveiller_entree`
    finally:
        if cursor:
            print("Fermeture du curseur après l'enregistrement du véhicule.")
            cursor.close()
        if conn and conn.is_connected():
            print("Fermeture de la connexion à la base de données après l'enregistrement du véhicule.")
            conn.close()

def capturer_image(camera_index=0, output_path="voiture_entree.jpg"):
    """
    Capture une image à partir de la webcam.
    :param camera_index: Index de la caméra (0 pour la première caméra USB).
    :param output_path: Chemin où l'image capturée sera sauvegardée.
    """
    print("Ouverture de la caméra pour capturer une image...")
    cap = cv2.VideoCapture(camera_index)
    if not cap.isOpened():
        print("Erreur : Impossible d'accéder à la caméra.")
        return None

    ret, frame = cap.read()
    if ret:
        cv2.imwrite(output_path, frame)
        print(f"Image capturée et sauvegardée dans {output_path}")
    else:
        print("Erreur : Impossible de capturer une image.")
        output_path = None

    cap.release()
    return output_path

def surveiller_entree():
    detector = PlateDetector()
    parking = ParkingManager()

    try:
        print("Début de la détection de plaque...")

        # Capture une image à partir de la caméra d'entrée dans le bon dossier
        image_filename = "voiture_entree.jpg"
        image_path = capturer_image(
            camera_index=0,
            output_path=os.path.join(IMAGES_DIR, image_filename)
        )

        if not image_path:
            print("Erreur : Aucune image capturée.")
            return

        # Détecter la plaque à partir du nom du fichier (non le chemin complet)
        plaque = detector.detect_plate(image_filename)

        if plaque:
            print(f"Plaque détectée : {plaque}")
            place_info = parking.get_available_place()
            if place_info:
                place, description = place_info
                date_entree = datetime.now()
                print(f"Place disponible : {place}, Description : {description}, Date d'entrée : {date_entree}")

                # Enregistrer dans la base de données
                print("Tentative d'enregistrement du véhicule dans la base de données...")
                enregistrer_voiture(plaque, place)
                parking.update_place_status(place, 1)

                print("Véhicule enregistré avec succès dans la base de données.")

                # Générer le dashboard
                print("Tentative de génération du dashboard...")
                generer_dashboard_entree(plaque, place, description, date_entree)
                print("Dashboard généré avec succès.")

                print(f"Véhicule {plaque} enregistré à la place {place}")
            else:
                print("Parking complet")
        else:
            print("Aucune plaque détectée")

    except Exception as e:
        print(f"Erreur : {str(e)}")

    finally:
        print("Fin de la détection de plaque.")


if __name__ == "__main__":
    call_init_db()
    surveiller_entree()
