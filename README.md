# IRONVAULT Trading Bot v3.2

Bot de trading automatisé sécurisé avec interface graphique pour Polymarket.

## Stratégies Supportées

### Strategy A - Front-Running
Réaction ultra-rapide aux données externes (Scoreboard/Fast-Data) pour devancer le marché.

- Lock par token pour éviter les positions dupliquées
- Déduplication des triggers (cooldown configurable)
- Cache orderbook (TTL 120-180ms selon capital)
- **v3.2: Exits dynamiques avec targets ajustés à la volatilité**
- **v3.2: Trailing stop corrigé (calcul relatif au high water mark)**

### Strategy B - Market Making
Fourniture de liquidité algorithmique avec découverte autonome des marchés.

- Spread dynamique basé sur la volatilité et l'imbalance
- Multi-market (25-50 marchés selon capital)
- Discovery accéléré avec MarketScanner
- **v3.2: Stratégie de sortie complète (profit target, stop-loss, trailing stop, timeout)**
- **v3.2: Tracking PnL en temps réel par position**

## Priorités de Sécurité

1. Isolation du capital (Segregation par stratégie)
2. Contrôle des risques (Sizing dynamique, Filtres de volatilité)
3. Comportement déterministe (Pas de trading émotionnel)
4. Sécurité opérateur (Vault chiffré, Kill Switch)
5. Utilisabilité (Interface PySide6 moderne)

## Configurations Optimisées

8 configurations pré-optimisées pour différents niveaux de capital:

| Capital | Live Trading | Paper Trading |
|---------|--------------|---------------|
| $100 | `config_100.json` | `config_100_paper.json` |
| $200 | `config_200.json` | `config_200_paper.json` |
| $500 | `config_500.json` | `config_500_paper.json` |
| $1000 | `config_1000.json` | `config_1000_paper.json` |

**Scaling automatique par capital:**
- **$100-200**: Trade size 6-8%, 25 marchés max, spreads conservateurs
- **$500**: Trade size 5-6%, 35 marchés max, spreads moyens
- **$1000**: Trade size 4-5%, 50 marchés max, spreads agressifs

## Nouveautés v3.2

### Exit Logic Complète (Strategy B)
```json
"exit_config": {
    "profit_target_pct": 1.5,
    "stop_loss_pct": 1.0,
    "trailing_stop_pct": 0.5,
    "max_hold_seconds": 300,
    "min_hold_seconds": 10,
    "exit_mode": "dynamic"
}
```

### Trailing Stop Corrigé (Strategy A)
- Calcul du drawdown relatif au **high water mark** (pas à l'entrée)
- Threshold dynamique: max(trailing_stop_pct, profit * 0.3)

### Targets Ajustés à la Volatilité
```python
vol_multiplier = 1.0 + (volatility_score * 0.5)
adjusted_profit_target = base_target * vol_multiplier
adjusted_stop_loss = base_stop * vol_multiplier
```

### Position Tracking Amélioré
- `get_position_summary()`: Vue consolidée de toutes les positions
- `get_unrealized_pnl_all()`: PnL non réalisé en temps réel
- `execution_stats`: Statistiques d'exécution (success rate, fills)

## Nouveautés v3.1

### WebSocket Batch Handling
- Support des messages batch (arrays) de Polymarket
- Parsing robuste des événements multiples par message

## Optimisations v3.0

### Performance
- **Rate Limiter**: Jusqu'à 100 req/s pour $1000 capital
- **Batch sizes**: 15-25 marchés par batch selon capital
- **Délais réduits**: 30-40ms entre batches
- **orjson**: JSON parsing 3-10x plus rapide
- **uvloop**: Event loop optimisé (Linux/macOS)

### WebSocket Polymarket
- Format subscription: `{type: "market", assets_ids: [...]}`
- Multi-event support: `book`, `price_change`
- Fallback REST API si WebSocket stale >30s
- Log spam réduit (1 log par 50 subscriptions)

### Robustesse
- **Log rotation**: 10MB par fichier, 5 backups max
- **Auto-cleanup**: Suppression des vieux logs au démarrage
- **Error handling**: Gestion gracieuse des erreurs JSON/réseau

### Paper Trading Réaliste
- **Slippage**: Base + size factor + depth impact
- **Latence**: 20-140ms selon capital
- **Fill probability**: 91-93%
- **Partial fills**: 8-11% de chance

## Structure du Projet

```
Ironvault/
├── config/
│   ├── config.example.json       # Template
│   ├── config_100.json           # $100 live
│   ├── config_100_paper.json     # $100 paper
│   ├── config_200.json           # $200 live
│   ├── config_200_paper.json     # $200 paper
│   ├── config_500.json           # $500 live
│   ├── config_500_paper.json     # $500 paper
│   ├── config_1000.json          # $1000 live
│   └── config_1000_paper.json    # $1000 paper
├── backend/
│   ├── orchestrator.py           # Coordination centrale
│   ├── execution_engine.py       # Exécution (v3.2: position tracking)
│   ├── market_scanner.py         # Scoring multi-facteurs
│   ├── analytics_engine.py       # Métriques temps réel
│   ├── websocket_client.py       # v3.1: batch message support
│   ├── clob_adapter.py           # Adaptateur CLOB
│   ├── data_feeds/
│   │   ├── base_feed.py
│   │   └── polymarket_feed.py
│   └── strategies/
│       ├── strategy_a_front_running.py  # v3.2: volatility-adjusted exits
│       └── strategy_b_market_making.py  # v3.2: complete exit logic
├── frontend/
│   ├── main_window.py
│   ├── dashboard.py
│   ├── controls.py
│   └── orderbook_visualizer.py
├── main.py
└── requirements.txt
```

## Installation

```bash
# Créer environnement virtuel
python3 -m venv venv
source venv/bin/activate

# Installer dépendances
pip install -r requirements.txt
```

## Configuration

1. Choisir un fichier config selon votre capital: `config/config_XXX.json`
2. Pour le paper trading, utiliser les versions `_paper.json`
3. **Hot-Reload**: Changez de config à la volée via l'interface

## Lancement

```bash
# Via Terminal
python main.py

# Via Raccourci macOS
./Start_Bot.command

# Spécifier une config
python main.py --config config/config_500_paper.json
```

## Interface & Contrôles

- **Dashboard**: Capital, statut stratégies, santé WebSocket, PnL temps réel
- **Config**: Chargement JSON et déverrouillage Vault
- **Commandes**: Start, Pause, Resume, Safe Exit
- **Urgence**: STOP global avec confirmation

## Logs et Analyse

Les logs d'audit (`logs/audit_*.log`) tracent chaque décision et exécution.

```bash
python analyze_logs.py logs/audit_latest.log
```

## Sécurité & Risques

- **Kill Switch**: Déclenchement auto sur perte excessive (6-15% selon capital)
- **Isolation**: Capital séparé par stratégie
- **Max Daily Loss**: Limite quotidienne (20-60$ selon capital)
- **Zéro Persistance**: Aucune clé API en clair sur disque
