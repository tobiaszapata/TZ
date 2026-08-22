#!/bin/bash
# Equivalente de actualizar.bat para Mac/Linux (ver cron en el manual).
cd "$(dirname "$0")"
mkdir -p logs
{
  echo "====================================================="
  echo "Corrida del $(date)"
  echo "====================================================="
  python3 -m scripts.actualizar
  echo
} >> logs/actualizar.log 2>&1
