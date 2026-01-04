# IRONVAULT Trading Bot v3.0

Bot de trading automatisé sécurisé avec interface graphique pour Polymarket.

## 🎯 Stratégies Supportées

- **Strategy_A (Front-Running)**: Réaction ultra-rapide aux données externes (Scoreboard/Fast-Data) pour devancer le marché.
  - Lock par token pour éviter les positions dupliquées
  - Déduplication des triggers (cooldown 5s)
  - Cache orderbook (TTL 150ms)
  - Exits dynamiques (profit target, stop-loss, trailing stop)

- **Strategy_B (Market Making)**: Fourniture de liquidité algorithmique avec découverte autonome des marchés les plus actifs.
  - Spread dynamique basé sur la volatilité
  - Multi-market (jusqu'à 100 marchés)
  - Discovery accéléré avec MarketScanner

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

## 🚀 Optimisations v3.0

### Performance
- **Rate Limiter**: 50 req/s (burst 100) pour un throughput maximal
- **Batch sizes**: 25 marchés par batch (market scanner), 20 tokens (price monitor)
- **Délais réduits**: 20ms entre batches (vs 100ms précédemment)
- **Timeout API**: 2s (vs 5s) pour une détection d'erreur rapide

### Précision Paper Trading
- **Slippage basé sur profondeur**: `base + (size/100) * factor + noise`
- **Latence réaliste**: 20-100ms
- **Fill probability**: 95%

### Nouveaux Composants
- **MarketScanner**: Scoring multi-facteurs (volume, spread, depth, activité)
- **AnalyticsEngine**: Sharpe Ratio, Max Drawdown, Profit Factor en temps réel
- **PolymarketPriceMonitor**: Détection de price spikes, imbalances, spread compression

## 📁 Structure du Projet

```
Ironvault/
├── config/
│   ├── config.example.json      # Template de configuration
│   ├── super_paper_trading.json # Config paper trading optimisée
│   └── ultra_optimized.json     # Config ultra performance v3.0
├── backend/
│   ├── orchestrator.py          # Coordination centrale
│   ├── execution_engine.py      # Mécanique d'exécution (v3.0: slippage depth-based)
│   ├── market_scanner.py        # v3.0: Scoring multi-facteurs des marchés
│   ├── analytics_engine.py      # v3.0: Métriques temps réel
│   ├── scoreboard_monitor.py    # Monitoring données haute vitesse
│   ├── market_data.py           # Client Gamma API
│   ├── clob_adapter.py          # Adaptateur CLOB (v3.0: timeout 2s)
│   ├── data_feeds/              # v3.0: Data feeds infrastructure
│   │   ├── base_feed.py         # Interface de base
│   │   └── polymarket_feed.py   # Price monitor (spikes, imbalances)
│   └── strategies/
│       ├── strategy_a_front_running.py  # v3.0: locks, cache, trailing stop
│       └── strategy_b_market_making.py  # v3.0: volatility score
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
