# IRONVAULT Trading Bot

Bot de trading automatisé sécurisé avec interface graphique pour Polymarket.

## 🎯 Stratégies Supportées

- **Strategy_A (Front-Running)**: Réaction ultra-rapide aux données externes (Scoreboard/Fast-Data) pour devancer le marché.
- **Strategy_B (Market Making)**: Fourniture de liquidité algorithmique avec découverte autonome des marchés les plus actifs.

## 🛡️ Priorités de Sécurité

1. Isolation du capital (Segregation par stratégie)
2. Contrôle des risques (Sizing dynamique, Filtres de volatilité)
3. Comportement déterministe (Pas de trading émotionnel)
4. Sécurité opérateur (Vault chiffré, Kill Switch)
5. Utilisabilité (Interface PySide6 moderne)

## ✨ Fonctionnalités Clés

- **Front-Running via Scoreboard**: Connexion directe à des flux de données externes pour une exécution en < 100ms.
- **Découverte Autonome (Strategy B)**: Scan automatique des marchés Gamma pour identifier et trader les plus liquides.
- **Intégration Polymarket CLOB**: Exécution d'ordres directe via l'API CLOB avec support FOK et GTC.
- **Interface PySide6 Moderne**: Dashboard complet avec monitoring en temps réel et visualiseur de carnet d'ordres.
- **Fermeture Sécurisée**: Bouton de sortie dédié garantissant l'annulation des ordres et le verrouillage du vault.
- **Support Paper Trading**: Mode simulation complet pour tester les stratégies sans risque financier.
- **Gestion Sécurisée des Credentials**: Clés API stockées en mémoire uniquement dans un Vault sécurisé.
- **Filtre de Volatilité**: Protection automatique contre les mouvements de prix extrêmes et irrationnels.

## 📁 Structure du Projet

```
Ironvault/
├── config/
│   └── config.example.json      # Template de configuration
├── backend/
│   ├── scoreboard_monitor.py    # Monitoring données haute vitesse
│   ├── orchestrator.py          # Coordination centrale
│   ├── execution_engine.py      # Mécanique d'exécution
│   ├── market_data.py           # Client Gamma API
│   ├── clob_adapter.py          # Adaptateur CLOB déterministe
│   └── strategies/
│       ├── strategy_a_front_running.py
│       └── strategy_b_market_making.py
├── frontend/
│   ├── main_window.py           # Fenêtre principale
│   ├── dashboard.py             # Monitoring visuel
│   ├── controls.py              # Commandes opérateur
│   └── orderbook_visualizer.py  # Graphique de profondeur
├── main.py                      # Point d'entrée
└── requirements.txt             # Dépendances
```

## 🚀 Installation

```bash
# Créer environnement virtuel
python3 -m venv venv
source venv/bin/activate

# Installer dépendances
pip install -r requirements.txt
```

## ⚙️ Configuration

1. Copier le template : `cp config/config.example.json config/config.json`
2. Éditer `config/config.json` avec vos clés API et paramètres de risque.
3. **Hot-Reload**: Chargez de nouvelles configurations à la volée via l'interface sans interruption.

## ▶️ Lancement

- **Via Terminal**: `python main.py`
- **Via Raccourci macOS**: `./Start_Bot.command`

## 🖥️ Interface & Contrôles

- **Dashboard**: Monitoring du capital, du statut des stratégies et de la santé du WebSocket.
- **Config & Accès**: Chargement JSON et déverrouillage sécurisé du Vault.
- **Commandes**: Démarrage, Pause, Reprendre et **Fermeture Sécurisée**.
- **Urgence**: Bouton STOP global avec confirmation immédiate.

## 📊 Logs et Analyse

Les logs d'audit (`logs/audit_*.log`) tracent chaque décision, exécution et erreur système pour une analyse post-session complète via `analyze_logs.py`.

## 🚨 Sécurité & Risques

- **Kill Switch**: Déclenchement automatique sur perte excessive ou timeout système.
- **Isolation**: Chaque stratégie dispose de son propre pool de capital verrouillé.
- **Zéro Persistance Plaintext**: Aucune clé API n'est écrite sur disque en clair.
