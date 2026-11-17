#!/bin/bash
# Cadena del Experimento M: barrido principal, dos repeticiones por condición.
# Una condición a la vez, NUNCA dos en paralelo (comparten CPU y bus PCIe).
# Orden intercalado gpu → cpu_control → referencia → (rep2) … para que una
# deriva lenta de la máquina (temperatura, carga ajena) no se alinee con una
# sola condición. Requisito declarado: máquina en reposo y con CA conectada.
# El refinamiento del cruce se lanza aparte, con los pares que identifique
# analizar_M.py --proponer_refinamiento.
cd "/c/Users/velas/OneDrive/Documents/tesis/fase_preliminar2/experimento_M"
VENV="/c/Users/velas/venv_lab4/Scripts/python.exe"
TESIS="python"
mkdir -p resultados/logs
echo "INICIO $(date)"
for REP in rep1 rep2; do
  echo "== $REP gpu ==";         "$VENV"  banco_M.py --fase medir --condicion gpu         --dispositivo cuda --sufijo $REP > resultados/logs/${REP}_gpu.log 2>&1; RC=$?;         echo "fin $REP gpu $(date) rc=$RC"
  echo "== $REP cpu_control =="; "$VENV"  banco_M.py --fase medir --condicion cpu_control --dispositivo cpu  --sufijo $REP > resultados/logs/${REP}_cpu_control.log 2>&1; RC=$?; echo "fin $REP cpu_control $(date) rc=$RC"
  echo "== $REP referencia ==";  "$TESIS" banco_M.py --fase medir --condicion referencia  --dispositivo cpu  --sufijo $REP > resultados/logs/${REP}_referencia.log 2>&1; RC=$?;  echo "fin $REP referencia $(date) rc=$RC"
done
echo "FIN $(date)"
