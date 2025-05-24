import mysql.connector
from werkzeug.security import generate_password_hash
import sys
import os

# Ajouter le répertoire parent au chemin de recherche Python
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from admin.config import DATABASE_CONFIG

def init_db():
    # Connexion à MySQL
    conn = mysql.connector.connect(
        host=DATABASE_CONFIG['host'],
        user=DATABASE_CONFIG['user'],
        password=DATABASE_CONFIG['password']
    )
    cursor = conn.cursor()

    # Créer la base de données si elle n'existe pas
    cursor.execute(f"CREATE DATABASE IF NOT EXISTS {DATABASE_CONFIG['database']}")
    cursor.execute(f"USE {DATABASE_CONFIG['database']}")

    # Créer toutes les tables nécessaires
    print("Table pour l'historique des stationnements")
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS historique_stationnement (
            id INT AUTO_INCREMENT PRIMARY KEY,
            plaque VARCHAR(20) NOT NULL,
            place VARCHAR(10) NOT NULL,
            temps_entree DATETIME NOT NULL,
            temps_sortie DATETIME,
            duree_minutes FLOAT NOT NULL,
            montant DECIMAL(10, 2) NOT NULL,
            direction VARCHAR(20) NOT NULL,
            status_paiement VARCHAR(20) DEFAULT 'en_attente',
            INDEX (plaque),
            INDEX (temps_entree)
        ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;
    """)

    print("Table pour les véhicules en stationnement")
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS vehicules_en_stationnement (
            id INT AUTO_INCREMENT PRIMARY KEY,
            plaque VARCHAR(20) NOT NULL,
            place VARCHAR(10) NOT NULL,
            temps_entree DATETIME DEFAULT CURRENT_TIMESTAMP,
            temps_sortie DATETIME NULL,
            status VARCHAR(20) DEFAULT 'en_stationnement',
            UNIQUE KEY (place)
        ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;
    """)

    print("Table pour les paiements")
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS paiements (
            id INT AUTO_INCREMENT PRIMARY KEY,
            plaque VARCHAR(20) NOT NULL,
            temps_entree DATETIME NOT NULL,
            temps_sortie DATETIME NOT NULL,
            montant DECIMAL(10, 2) NOT NULL,
            place VARCHAR(10) NOT NULL,
            montant_paye DECIMAL(10, 2) NOT NULL,
            montant_change DECIMAL(10, 2) NOT NULL,
            date_paiement DATETIME DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (place) REFERENCES places(numero) ON DELETE SET NULL,
            INDEX (date_paiement)
        ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;
    """)

    print("Table pour les utilisateurs")
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS users (
            id INT AUTO_INCREMENT PRIMARY KEY,
            username VARCHAR(100) NOT NULL UNIQUE,
            password VARCHAR(255) NOT NULL,
            role VARCHAR(50) DEFAULT 'user',
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    """)

    print("Table pour les places")
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS places (
            numero INT PRIMARY KEY,
            occupied BOOLEAN DEFAULT FALSE,
            last_update TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    """)

    print("Table pour les sessions")
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS sessions (
            id INT AUTO_INCREMENT PRIMARY KEY,
            immatriculation VARCHAR(20) NOT NULL,
            place_numero INT,
            heure_entree TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            heure_sortie TIMESTAMP NULL,
            duree INT DEFAULT 0,
            montant DECIMAL(10,2) DEFAULT 0,
            status VARCHAR(50) DEFAULT 'en_cours',
            FOREIGN KEY (place_numero) REFERENCES places(numero)
        )
    """)

    print("Table pour les paiements")
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS paiements (
            id INT AUTO_INCREMENT PRIMARY KEY,
            session_id INT NOT NULL,
            montant_paye DECIMAL(10,2) NOT NULL,
            montant_change DECIMAL(10,2) DEFAULT 0,
            status_paiement VARCHAR(50) DEFAULT 'en_attente',
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (session_id) REFERENCES sessions(id)
        )
    """)

    print("Table pour l'état des équipements")
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS equipment_status (
            id INT AUTO_INCREMENT PRIMARY KEY,
            equipment_name VARCHAR(100) NOT NULL,
            status VARCHAR(50) DEFAULT 'ok',
            last_check TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    """)

    print("Table pour les notifications")
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS notifications (
            id INT AUTO_INCREMENT PRIMARY KEY,
            type VARCHAR(50) NOT NULL,
            message TEXT NOT NULL,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            read_at TIMESTAMP NULL
        )
    """)


    print(" Insérer les places de parking par défaut (éviter les doublons avec INSERT IGNORE")
    cursor.execute("""
        INSERT IGNORE INTO places (numero, occupied, last_update) VALUES
        (1, 0, NOW()),
        (2, 0, NOW()),
        (3, 0, NOW()),
        (4, 1, NOW()),
        (5, 1, NOW()),
        (6, 1, NOW())
    """)

    # Créer l'utilisateur admin (éviter les doublons avec INSERT IGNORE)
    admin_password = generate_password_hash('admin123')
    try:
        cursor.execute("""
            INSERT IGNORE INTO users (username, password, role)
            VALUES (%s, %s, %s)
        """, ('admin', admin_password, 'admin'))
        print("Utilisateur admin créé avec succès!")
    except mysql.connector.IntegrityError:
        print("L'utilisateur admin existe déjà.")
        cursor.execute("""
            UPDATE users 
            SET password = %s
            WHERE username = 'admin'
        """, (admin_password,))
        print("Mot de passe admin mis à jour!")

    conn.commit()
    cursor.close()
    conn.close()

if __name__ == '__main__':
    try:
        init_db()
        print("Base de données initialisée avec succès!")
        print("Vous pouvez maintenant vous connecter avec:")
        print("Username: admin")
        print("Password: admin123")
    except Exception as e:
        print(f"Erreur lors de l'initialisation de la base de données: {str(e)}")