# IRONVAULT Trading Bot

Bot de trading automatisé sécurisé avec interface graphique.

## 🎯 Stratégies Supportées

- **Strategy_A**: Multi-Outcome Dutching
- **Strategy_B**: Automated Market Making

## 🛡️ Priorités de Sécurité

1. Isolation du capital
2. Contrôle des risques
3. Comportement déterministe
4. Sécurité opérateur
5. Utilisabilité

## ✨ Fonctionnalités Clés

- **Intégration Polymarket CLOB**: Exécution d'ordres rapide et directe via l'API CLOB.
- **Support Paper Trading**: Mode simulation sans risque avec `config_paper.json`.
- **Données de Marché Gamma**: Flux de prix en temps réel pour une prise de décision précise.
- **Interface PySide6**: Dashboard moderne et réactif pour le monitoring et le contrôle.
- **Hot-Reload de Configuration**: Chargez de nouveaux réglages ou changez de mode (Paper/Live) sans redémarrer le bot.
- **Gestion Sécurisée des Credentials**: Clés API stockées en mémoire uniquement via un Vault chiffré.
- **Support macOS natif**: Support SSL corrigé via `certifi`.


## 📁 Structure du Projet

```
Ironvault/
├── config/
│   └── config.example.json    # Template de configuration
├── backend/
│   ├── config_loader.py       # Chargement/validation config
│   ├── capital_manager.py     # Gestion pools de capital
│   ├── policy_layer.py        # Validation des actions
│   ├── orchestrator.py        # Coordination stratégies
│   ├── execution_engine.py    # Exécution mécanique
│   ├── kill_switch.py         # Arrêt d'urgence global
│   ├── audit_logger.py        # Journalisation
│   └── strategies/
│       ├── base_strategy.py
│       ├── strategy_a_dutching.py
│       └── strategy_b_market_making.py
├── frontend/
│   ├── main_window.py         # Fenêtre principale
│   ├── dashboard.py           # Tableau de bord
│   ├── controls.py            # Boutons de contrôle
│   └── styles.py              # Styles visuels
├── main.py                    # Point d'entrée
└── requirements.txt           # Dépendances
```

## 🚀 Installation

```bash
# Créer environnement virtuel
python3 -m venv venv
source venv/bin/activate  # macOS/Linux

# Installer dépendances
pip install -r requirements.txt
```

## ⚙️ Configuration

1. Copier le template de configuration:
```bash
cp config/config.example.json config/config.json
```

2. Éditer `config/config.json` avec vos paramètres

3. **Hot-Reload**: Vous pouvez charger une nouvelle configuration directement depuis la GUI pendant que le bot tourne. Les stratégies se réinitialiseront automatiquement avec les nouveaux paramètres.

## ▶️ Lancement

### Mode Paper Trading (Simulation)
Idéal pour tester les stratégies sans risque.
1. Lancer l'application : `python main.py` ou `./Start_Bot.command`
2. Charger `config/config_paper.json`, `config/config_paper_micros.json` ou **`config/config_paper_micros_aggressive.json`** (pour voir le bot trader intensément en Paper Trading).
3. (Optionnel) Déverrouiller le vault (non requis pour le paper trading)
4. Cliquer sur **Lancer**

### Mode Réel
1. Lancer l'application
2. Charger `config/config.json` ou **`config/config_live_micros.json`** (pour un petit capital de 100$)
3. Déverrouiller le vault pour charger les credentials en mémoire
4. Cliquer sur **Lancer**

```bash
# Pour lancer via terminal
python main.py
```

## 🖥️ Interface

### Tableau de Bord (Lecture Seule)
- Capital total / verrouillé / disponible
- Statut des stratégies A et B
- Statut connexion marché
- Indicateur kill switch

### Contrôles (Limités)
- **Charger Config**: Sélectionner fichier JSON
- **Lancer**: Démarrer le bot (config requise)
- **Pause**: Suspendre l'activité
- **Reprendre**: Reprendre depuis pause
- **Arrêt d'Urgence**: Déclenche kill switch (confirmation requise)

## 🚨 Kill Switch

Le kill switch se déclenche sur:
- Commande opérateur manuelle
- Dépassement seuil de perte
- Violation de politique
- Timeout heartbeat
- Signal watchdog externe

**Actions automatiques:**
- Annulation tous ordres
- Gel pools de capital
- Désactivation stratégies
- Nécessite redémarrage manuel

## 📊 Logs et Analyse

Les logs d'audit sont enregistrés dans le dossier `logs/` avec horodatage.
Format: `audit_YYYYMMDD_HHMMSS.log`

### Analyse des Performances (Paper Trading)
Utilisez le script inclus pour analyser vos sessions de paper trading :
```bash
python3 analyze_logs.py
```
Cela affichera un résumé des trades simulés et du volume estimé.

## ⚠️ Règles de Sécurité

- Aucune modification de paramètres depuis la GUI
- Pas de saisie manuelle d'ordres
- Pas de contournement des limites de risque
- Pas de retry automatique sans approbation politique
