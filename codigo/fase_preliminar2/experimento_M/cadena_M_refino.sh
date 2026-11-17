#!/bin/bash
# Refinamiento del cruce (Exp M): puntos intermedios dentro del par que encierra
# el cruce, cuartiles geométricos redondeados a múltiplos de 8.
#   256x256: cruce entre 512 y 1024  -> 608 720 864
#   512x512: cruce entre 128 y 256   -> 152 184 216
#   1024x1024: cruce ausente (GPU gana en todo el rango) -> no se refina
# Se miden ambas arquitecturas en todos los puntos (celdas baratas).
# Mismo orden intercalado y control de banco que la cadena principal.
cd "/c/Users/velas/OneDrive/Documents/tesis/fase_preliminar2/experimento_M"
VENV="/c/Users/velas/venv_lab4/Scripts/python.exe"
TESIS="python"
MB="152 184 216 608 720 864"
AR="256x256 512x512"
mkdir -p resultados/logs
echo "INICIO $(date)"
for REP in refino_rep1 refino_rep2; do
  echo "== $REP gpu ==";         "$VENV"  banco_M.py --fase medir --condicion gpu         --dispositivo cuda --sufijo $REP --minilotes $MB --arquitecturas $AR > resultados/logs/${REP}_gpu.log 2>&1; RC=$?;         echo "fin $REP gpu $(date) rc=$RC"
  echo "== $REP cpu_control =="; "$VENV"  banco_M.py --fase medir --condicion cpu_control --dispositivo cpu  --sufijo $REP --minilotes $MB --arquitecturas $AR > resultados/logs/${REP}_cpu_control.log 2>&1; RC=$?; echo "fin $REP cpu_control $(date) rc=$RC"
  echo "== $REP referencia ==";  "$TESIS" banco_M.py --fase medir --condicion referencia  --dispositivo cpu  --sufijo $REP --minilotes $MB --arquitecturas $AR > resultados/logs/${REP}_referencia.log 2>&1; RC=$?;  echo "fin $REP referencia $(date) rc=$RC"
done
echo "FIN $(date)"
