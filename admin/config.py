import os

# Configuration de la base de données XAMPP
DATABASE_CONFIG = {
    'host': 'localhost',
    'user': 'root',
    'password': '',  # Mot de passe par défaut de XAMPP est vide
    'database': 'parking_db',
    'port': 3306  # Port par défaut de MySQL dans XAMPP
}

# Configuration des chemins
BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
YOLO_MODEL_PATH = os.path.join(BASE_DIR, 'weights', 'yolov8n.pt')

# Configuration de l'application
SECRET_KEY = 'votre_clé_secrète_ici'
SESSION_TYPE = 'filesystem'

# Configuration du parking
TOTAL_PLACES = 6
PRIX_PAR_HEURE = 2  # en Dinars Tunisiens

# Configuration des notifications
NOTIFICATION_TIMEOUT = 300  # 5 minutes en secondes
EQUIPMENT_CHECK_INTERVAL = 60  # 1 minute en secondes

# Configuration des billets acceptés
BILLETS_ACCEPTES = [1, 2, 5, 10, 20, 50]  # en Dinars Tunisiens

# Configuration des équipements
EQUIPMENT = {
    'camera_entree': {'id': 1, 'name': 'Caméra Entrée'},
    'camera_sortie': {'id': 2, 'name': 'Caméra Sortie'},
    'barriere_entree': {'id': 3, 'name': 'Barrière Entrée'},
    'barriere_sortie': {'id': 4, 'name': 'Barrière Sortie'},
    'unite_paiement': {'id': 5, 'name': 'Unité de Paiement'}
}
#ajoutez les noms des tables utilisées pour stocker les informations.
# Noms des tables de la base de données
TABLES = {
    'vehicules': 'vehicule_en_stationnement',
    'places': 'places'
}
#ajoutez les colonnes utilises pour stocker les informations.
# Colonnes clés pour les tables
COLUMNS = {
    'vehicules_en_stationnement': {
        'id': 'id',
        'plaque': 'plaque',
        'place': 'place',
        'temps_entree': 'temps_entree',
        'temps_sortie': 'temps_sortie',
        'status': 'status'
    }
}
# Statuts des véhicules
VEHICLE_STATUS = {
    'en_stationnement': 'en_stationnement',
    'en_attente_paiement': 'en_attente_paiement',
    'sorti': 'sorti'
}
#Ajoutez une configuration pour les statuts des places de parking (par exemple, libre ou occupée).
# Statuts des places de parking
PLACE_STATUS = {
    'libre': 'libre',
    'occupee': 'occupée'
}
#Ajoutez un format de date pour uniformiser l'enregistrement des dates dans la base de données.
# Format de date pour la base de données
DATE_FORMAT = '%Y-%m-%d %H:%M:%S'