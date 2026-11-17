"""
test_filtro_cbf.py
==================
Test unitario STANDALONE del filtro CBF (sin Webots). Ejecutar con:

    python test_filtro_cbf.py

Casos:
  1. Lejos de toda pared        → no interviene, u_seg == u_nom exacto.
  2. Pared plana, θ PERPENDICULAR EXACTO (caso degenerado 2 del docstring):
     el coeficiente de ω se anula → solo frena (v → α·h) y la ω de la
     política pasa INTACTA. Sub-caso h≈0: v → 0.
  3. Pared en ángulo (60°)      → interviene: reduce v Y gira alejándose
     (ω≠0 con el signo correcto) — "bordea", no se detiene.
  4. Esquina (2 restricciones)  → ambas satisfechas, v reducida, QP factible.
  5. Violación recuperable      → retroceso forzado (v ≤ −α·|h|).
  6. Violación irrecuperable    → fallback u=(0,0) + RuntimeWarning.

Parámetros idénticos a los del controlador.
"""

from __future__ import annotations

import math
import sys
import warnings
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parent))

from lib.filtro_cbf import FiltroCBFParedes

# Parámetros del plan (idénticos a supervisor_fisica.py).
V_MAX     = 0.31
OMEGA_MAX = 6.2832
FILTRO = FiltroCBFParedes(
    arena_size = (3.0, 3.0),
    ele_a      = 0.05,
    alfa       = 2.0,
    d_segura   = 0.18,
    w_omega    = 0.3,
    v_max      = V_MAX,
    omega_max  = OMEGA_MAX,
)

fallos: list = []


def verificar(nombre: str, condicion: bool, detalle: str = "") -> None:
    """Registra el resultado de un assert con reporte legible."""
    estado = "OK " if condicion else "FALLO"
    print(f"  [{estado}] {nombre}" + (f"  ({detalle})" if detalle else ""))
    if not condicion:
        fallos.append(nombre)


def restricciones_satisfechas(pose: np.ndarray, u: np.ndarray) -> bool:
    """Evalúa las 4 restricciones de pared en u (tolerancia 1e-6)."""
    p  = FILTRO._punto_de_mira(pose)
    th = float(pose[2])
    return all(
        float(r.c @ u) + FILTRO.alfa * r.h >= -1e-6
        for r in FILTRO._barreras_paredes(p, th)
    )


# ── Caso 1: lejos de toda pared ─────────────────────────────────────────────
print("\nCaso 1: lejos de pared (centro de la arena)")
pose = np.array([1.5, 1.5, 0.7])
u_nom = np.array([0.25, 3.0])
r = FILTRO.filtrar(pose, u_nom)
verificar("no interviene", not r.intervino)
verificar("u_seg == u_nom", bool(np.allclose(r.u_seguro, u_nom, atol=1e-9)))
verificar("QP exitoso", r.exito_qp)

# ── Caso 2: pared plana, θ perpendicular EXACTO ─────────────────────────────
print("\nCaso 2: pared superior, θ = 90° exacto (caso degenerado 2)")
# p_y = y + ele_a → h_sup = 3 − p_y − 0.18 = 0.05  ⇒  y = 2.72
pose = np.array([1.5, 2.72, math.pi / 2.0])
omega_politica = 2.0
u_nom = np.array([V_MAX, omega_politica])
r = FILTRO.filtrar(pose, u_nom)
# Restricción activa: v ≤ α·h = 2.0·0.05 = 0.1
verificar("interviene", r.intervino)
verificar("v recortada a α·h = 0.1",
          abs(float(r.u_seguro[0]) - 0.1) < 1e-4,
          f"v_seg={float(r.u_seguro[0]):.5f}")
verificar("ω de la política INTACTA",
          abs(float(r.u_seguro[1]) - omega_politica) < 1e-5,
          f"ω_seg={float(r.u_seguro[1]):.5f}")
verificar("barrera activa = pared_sup", r.barrera_activa == "pared_sup")

print("\nCaso 2b: idem con h ≈ 0 (a ras del margen) → v → 0")
# h_sup = 0 ⇒ y = 2.77
pose = np.array([1.5, 2.77, math.pi / 2.0])
r = FILTRO.filtrar(pose, u_nom)
verificar("v → 0", abs(float(r.u_seguro[0])) < 1e-4,
          f"v_seg={float(r.u_seguro[0]):.6f}")
verificar("ω de la política INTACTA",
          abs(float(r.u_seguro[1]) - omega_politica) < 1e-5)

# ── Caso 3: pared en ángulo (60°) → bordear ─────────────────────────────────
print("\nCaso 3: pared superior, θ = 60° (debe girar y bordear)")
# p_y = y + ele_a·sen60 → h_sup = 0.02  ⇒  y = 2.8 − 0.05·sen60 = 2.75670
theta = math.pi / 3.0
pose = np.array([1.5, 2.8 - 0.05 * math.sin(theta), theta])
u_nom = np.array([V_MAX, 0.0])
r = FILTRO.filtrar(pose, u_nom)
# dh_sup/dω = −ℓa·cosθ < 0 para θ=60° ⇒ el QP debe empujar ω hacia NEGATIVO.
verificar("interviene", r.intervino)
verificar("gira alejándose (ω < 0)", float(r.u_seguro[1]) < -1e-3,
          f"ω_seg={float(r.u_seguro[1]):.4f}")
verificar("sigue avanzando (v > 0)", float(r.u_seguro[0]) > 1e-3,
          f"v_seg={float(r.u_seguro[0]):.4f}")
verificar("restricciones satisfechas", restricciones_satisfechas(pose, r.u_seguro))

# ── Caso 4: esquina superior-derecha, θ = 45° hacia la esquina ──────────────
print("\nCaso 4: esquina sup-der, θ = 45° (2 restricciones activas)")
# h_der = h_sup = 0.03: p = (2.79, 2.79) ⇒ x = y = 2.79 − 0.05·cos45 = 2.75464
theta = math.pi / 4.0
coord = 2.79 - 0.05 * math.cos(theta)
pose = np.array([coord, coord, theta])
u_nom = np.array([V_MAX, 0.0])
r = FILTRO.filtrar(pose, u_nom)
verificar("interviene", r.intervino)
verificar("v reducida", float(r.u_seguro[0]) < V_MAX - 1e-3,
          f"v_seg={float(r.u_seguro[0]):.4f}")
verificar("restricciones satisfechas (ambas paredes)",
          restricciones_satisfechas(pose, r.u_seguro))
verificar("QP exitoso", r.exito_qp)

# ── Caso 5: violación recuperable → retroceso forzado ───────────────────────
print("\nCaso 5: violación h = −0.05 en pared izquierda (recuperable)")
# θ=π (mirando la pared izq): p_x = x − ele_a; h_izq = p_x − 0.18 = −0.05 ⇒ x=0.18
pose = np.array([0.18, 1.5, math.pi])
u_nom = np.array([V_MAX, 0.0])
r = FILTRO.filtrar(pose, u_nom)
# c_izq = (−1, 0): −v ≥ −α·h = +0.1  ⇒  v ≤ −0.1 (retroceso forzado).
verificar("retrocede (v ≤ −0.1)", float(r.u_seguro[0]) <= -0.1 + 1e-5,
          f"v_seg={float(r.u_seguro[0]):.4f}")
verificar("QP exitoso", r.exito_qp)
verificar("h_minima < 0 reportada", r.h_minima < 0.0)

# ── Caso 6: violación irrecuperable → fallback ──────────────────────────────
print("\nCaso 6: violación h = −0.5 (irrecuperable) → fallback (0,0) + warning")
# h_izq = −0.5 ⇒ p_x = −0.32 ⇒ x = −0.27 (sintético). Se exige v ≤ −1 < −V_MAX.
pose = np.array([-0.27, 1.5, math.pi])
u_nom = np.array([V_MAX, 0.0])
with warnings.catch_warnings(record=True) as avisos:
    warnings.simplefilter("always")
    r = FILTRO.filtrar(pose, u_nom)
hubo_warning = any(issubclass(a.category, RuntimeWarning) for a in avisos)
verificar("fallback u = (0,0)", bool(np.allclose(r.u_seguro, [0.0, 0.0])))
verificar("exito_qp = False", not r.exito_qp)
verificar("RuntimeWarning emitido", hubo_warning)

# ── Resultado global ────────────────────────────────────────────────────────
print("\n" + "═" * 60)
if fallos:
    print(f"  {len(fallos)} FALLOS: {fallos}")
    sys.exit(1)
print("  TODOS LOS CASOS OK")
print("═" * 60)
