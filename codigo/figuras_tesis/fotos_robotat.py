"""Arma la figura de fotos del enjambre sobre la plataforma del Robotat.

Fuente: video grabado el 21 de octubre de 2026, primer día de la campaña con
el obstáculo en movimiento (experimento E19). El video no está en el
repositorio por su tamaño (unos 140 MB).

Primero se extraen los fotogramas con ffmpeg, a los 20, 30, 40 y 50 s del
inicio de la grabación:

    for t in 20 30 40 50; do
        ffmpeg -ss $t -i P13_obstaculo_movil_1080p.mp4 -frames:v 1 f_$t.png
    done

Luego este script recorta la zona de la plataforma en cada fotograma y apila
los cuatro recortes en un solo JPEG. En la tesis, cada subfigura toma su
franja con la opción viewport de includegraphics.

Uso: python fotos_robotat.py <carpeta_con_los_png>
"""
import sys
from PIL import Image

carpeta = sys.argv[1]
tiempos = [20, 30, 40, 50]
recorte = (0, 120, 1700, 790)          # x0, y0, x1, y1 en el fotograma de 1920x1080
ancho_salida = 1275
paneles = []
for t in tiempos:
    img = Image.open(f"{carpeta}/f_{t}.png").convert("RGB").crop(recorte)
    alto = round(img.height * ancho_salida / img.width)
    paneles.append(img.resize((ancho_salida, alto), Image.LANCZOS))
alto_panel = paneles[0].height
lienzo = Image.new("RGB", (ancho_salida, alto_panel * len(paneles)), "white")
for i, p in enumerate(paneles):
    lienzo.paste(p, (0, i * alto_panel))
# 72 ppp para que un píxel valga un punto PostScript en el viewport de LaTeX
lienzo.save("fotos_robotat_21oct.jpg", quality=88, dpi=(72, 72), optimize=True)
print(lienzo.size, alto_panel)
