#!/bin/bash
# IRONVAULT Cleanup Script

echo "🧹 Nettoyage des processus IRONVAULT en cours..."

# Trouver et tuer tout processus python qui exécute main.py dans le dossier Ironvault
PIDs=$(ps aux | grep -i "Ironvault" | grep -i "python" | grep -v grep | awk '{print $2}')

if [ -z "$PIDs" ]; then
    echo "✅ Aucun processus bot en cours trouvé."
else
    echo "🛑 Arrêt des processus PIDs: $PIDs"
    kill -9 $PIDs
    echo "✅ Processus arrêtés."
fi

echo "🚀 Vous pouvez maintenant relancer le bot via Start_Bot.command"
