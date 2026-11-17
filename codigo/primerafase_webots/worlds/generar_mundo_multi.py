"""
generar_mundo_multi.py
======================
Generador de los mundos multi-robot con física real. Emite el .wbt completo
para N Pololus + coordinador + 3 esferas de hotspots.

Motivación: cada Pololu son ~150 líneas de VRML (chasis, bumper, 2 HingeJoint
con motores, 2 BallJoint con casters, GPS, Compass, Emitter, Receiver).
Copiarlas a mano N veces es una fuente segura de erratas silenciosas (un
`name` mal escrito o un canal equivocado se manifiesta como "nunca llegó pose
del agente k" en tiempo de ejecución). Generarlas garantiza que los N bloques
sean idénticos salvo índice, posición y color.

Uso
---
    python generar_mundo_multi.py 2    → worlds/lab_robotat_fisica_multi.wbt
    python generar_mundo_multi.py 5    → worlds/lab_robotat_fisica_multi5.wbt

Las posiciones iniciales del .wbt son sólo un arreglo razonable para abrir el
mundo en el editor; el coordinador las sobrescribe por teletransporte al
inicio de cada episodio.

Autor: José — Tesis Mecatrónica UVG.
"""

from __future__ import annotations

import math
import sys
from pathlib import Path
from typing import List, Tuple

_CARPETA: Path = Path(__file__).resolve().parent

# Colores por agente (para distinguirlos visualmente en el render).
COLORES: List[Tuple[float, float, float]] = [
    (0.90, 0.30, 0.30),   # rojo
    (0.30, 0.50, 0.90),   # azul
    (0.30, 0.80, 0.40),   # verde
    (0.90, 0.75, 0.25),   # amarillo
    (0.75, 0.40, 0.85),   # violeta
]


def posiciones_iniciales(n: int) -> List[Tuple[float, float]]:
    """
    Reparte N robots en un círculo centrado, con separación amplia.
    Sólo estética para el editor: el coordinador teletransporta al reset.
    """
    if n == 1:
        return [(0.0, 0.0)]
    radio = 0.9
    return [
        (radio * math.cos(2 * math.pi * i / n),
         radio * math.sin(2 * math.pi * i / n))
        for i in range(n)
    ]


def bloque_robot(indice: int, x: float, y: float) -> str:
    """
    Emite el bloque VRML de un Pololu con física, sensores y comunicación.

    El agente 0 DEFine las formas reutilizables (wheel_1, wheel_2,
    CasterBall_1/2); los demás las referencian con USE para no duplicar
    geometría.
    """
    r, g, b = COLORES[indice % len(COLORES)]
    es_primero = (indice == 0)

    def forma(nombre: str, cuerpo: str) -> str:
        """DEF en el primer robot, USE en los siguientes."""
        return f"DEF {nombre} {cuerpo}" if es_primero else f"USE {nombre}"

    rueda_der = forma("wheel_1", """Shape {
            appearance PBRAppearance {
              baseColor 0 0 0
              roughness 1
              metalness 0
            }
            geometry Cylinder {
              height 0.01
              radius 0.035
            }
          }""")
    rueda_izq = forma("wheel_2", """Shape {
            appearance PBRAppearance {
              baseColor 0 0 0
              roughness 1
              metalness 0
            }
            geometry Cylinder {
              height 0.01
              radius 0.035
            }
          }""")
    caster1 = forma("CasterBall_1", """Shape {
            appearance PBRAppearance {
              baseColor 0.333333 0.333333 0.498039
              roughness 1
              metalness 0
            }
            geometry Sphere {
              radius 0.01
            }
          }""")
    caster2 = forma("CasterBall_2", """Shape {
            appearance PBRAppearance {
              baseColor 0.333333 0.333333 0.498039
              roughness 1
              metalness 0
            }
            geometry Sphere {
              radius 0.01
            }
          }""")

    return f"""
# ── AGENTE {indice} ──────────────────────────────────────────────────────────
DEF p3pi_{indice} Robot {{
  translation {x:.4f} {y:.4f} 0
  rotation 0 0 1 0
  name "p3pi_{indice}"
  controller "controlador_agente"
  contactMaterial "plastic"
  selfCollision TRUE
  children [
    DEF Body_{indice} Pose {{
      translation 0 0 0.0255
      children [
        Shape {{
          appearance PBRAppearance {{
            baseColor {r} {g} {b}
            roughness 1
            metalness 0
          }}
          geometry Cylinder {{
            height 0.019
            radius 0.075
          }}
        }}
      ]
    }}
    Compass {{
      rotation 0 0 1 1.5707996938995747
    }}
    GPS {{
      rotation 0 0 1 1.5707996938995747
    }}
    Emitter {{
      name "emitter"
      channel 1
    }}
    Receiver {{
      name "receiver"
      channel 2
    }}
    Pose {{
      translation 0 0 0.016
      children [
        Shape {{
          appearance PBRAppearance {{
            roughness 1
            metalness 0
          }}
          geometry Mesh {{
            url [
              "../Modelos_3D/Pololu/BumperV2.stl"
            ]
            scale 0.001 0.001 0.001
          }}
          castShadows FALSE
        }}
      ]
    }}
    HingeJoint {{
      jointParameters HingeJointParameters {{
        anchor 0.07 0 0.037
      }}
      device [
        RotationalMotor {{
          name "motor_1"
          maxVelocity 84
        }}
      ]
      endPoint Solid {{
        translation 0.07 0 0.037
        rotation -0.6667195291850914 0.33418188717234326 -0.6661888138426982 2.4960856161980307
        children [
          {rueda_der}
        ]
        boundingObject USE wheel_1
        physics Physics {{
        }}
      }}
    }}
    HingeJoint {{
      jointParameters HingeJointParameters {{
        anchor -0.07 0 0.037
      }}
      device [
        RotationalMotor {{
          name "motor_2"
          maxVelocity 84
        }}
      ]
      endPoint Solid {{
        translation -0.07 0 0.037
        rotation 0 1 0 1.57
        children [
          {rueda_izq}
        ]
        name "solid(1)"
        boundingObject USE wheel_2
        physics Physics {{
        }}
      }}
    }}
    BallJoint {{
      jointParameters BallJointParameters {{
        anchor 0 0.06 0.013
      }}
      jointParameters2 JointParameters {{
        axis 1 0 0
      }}
      jointParameters3 JointParameters {{
        axis 0 1 0
      }}
      endPoint Solid {{
        translation 0 0.06 0.013
        children [
          {caster1}
        ]
        name "solid(2)"
        boundingObject USE CasterBall_1
        physics Physics {{
        }}
      }}
    }}
    BallJoint {{
      jointParameters BallJointParameters {{
        anchor 0 -0.06 0.013
      }}
      jointParameters2 JointParameters {{
        axis 1 0 0
      }}
      jointParameters3 JointParameters {{
        axis 0 1 0
      }}
      endPoint Solid {{
        translation 0 -0.06 0.013
        children [
          {caster2}
        ]
        name "solid(3)"
        boundingObject USE CasterBall_2
        physics Physics {{
        }}
      }}
    }}
  ]
  boundingObject USE Body_{indice}
  physics Physics {{
  }}
}}
"""


def bloque_hotspots() -> str:
    """Tres esferas emisivas R/G/B, sin física (las mueve el coordinador)."""
    colores = [(1, 0, 0), (0, 1, 0), (0, 0, 1)]
    posiciones = [(-0.5, -0.5), (0.0, 0.5), (0.5, -0.5)]
    bloques = []
    for j, ((r, g, b), (x, y)) in enumerate(zip(colores, posiciones), start=1):
        bloques.append(f"""
DEF obs{j} Solid {{
  translation {x} {y} 0.12
  name "obs{j}"
  children [
    Shape {{
      appearance PBRAppearance {{
        baseColor {r} {g} {b}
        emissiveColor {r} {g} {b}
        roughness 1
        metalness 0
      }}
      geometry Sphere {{
        radius 0.05
      }}
    }}
  ]
}}""")
    return "".join(bloques)


def generar(n_agentes: int) -> str:
    """Compone el .wbt completo para N agentes."""
    cabecera = f"""#VRML_SIM R2025a utf8

# lab_robotat_fisica_multi{'' if n_agentes == 2 else n_agentes}.wbt
# ============================================================================
# ARCHIVO GENERADO por worlds/generar_mundo_multi.py — no editar a mano.
#   python generar_mundo_multi.py {n_agentes}
#
# Enjambre multi-robot con física real: {n_agentes} Pololus + coordinador.
#
# Arquitectura (impuesta por Webots: un controlador sólo comanda SUS motores):
#   - {n_agentes} nodos Pololu con física, cada uno con `controlador_agente`
#     (NO supervisores). Devices: motor_1, motor_2, gps, compass, emitter,
#     receiver.
#   - 1 nodo Robot "coordinador" SIN geometría, supervisor TRUE. Corre el env,
#     la política y mueve las esferas de hotspots.
#
# Comunicación:
#   canal 1 (subida) : agentes → coordinador, poses en cada tick.
#   canal 2 (bajada) : coordinador → agentes, acciones cada 10 ticks + resets.
#
# El coordinador AUTODETECTA la cantidad de agentes contando nodos DEF p3pi_i,
# así que el mismo controlador sirve para cualquier N sin editar constantes.
#
# Sincronía: basicTimeStep 10 ms ⇒ una decisión del env (dt=0.1 s) = 10 ticks.

EXTERNPROTO "https://raw.githubusercontent.com/cyberbotics/webots/R2025a/projects/objects/backgrounds/protos/TexturedBackground.proto"
EXTERNPROTO "https://raw.githubusercontent.com/cyberbotics/webots/R2025a/projects/objects/backgrounds/protos/TexturedBackgroundLight.proto"
EXTERNPROTO "https://raw.githubusercontent.com/cyberbotics/webots/R2025a/projects/objects/floors/protos/RectangleArena.proto"

WorldInfo {{
  basicTimeStep 10
  coordinateSystem "ENU"
  gravity 9.81
}}
Viewpoint {{
  orientation -0.4361130076829961 0.48206096816246363 0.7598833249282153 1.744346265750423
  position -0.39142159867184184 -3.9694436769836723 5.426116237234703
}}
TexturedBackground {{
}}
TexturedBackgroundLight {{
}}
RectangleArena {{
  floorSize 3 3
  wallThickness 0.1
  wallHeight 0.15
}}
"""

    partes = [cabecera]
    for i, (x, y) in enumerate(posiciones_iniciales(n_agentes)):
        partes.append(bloque_robot(i, x, y))
    partes.append("\n# ── HOTSPOTS ────────────────────────────────────────"
                  "────────────────────────")
    partes.append(bloque_hotspots())
    partes.append("""

# ── COORDINADOR — supervisor sin geometría ──────────────────────────────────
Robot {
  name "coordinador"
  controller "coordinador_enjambre"
  supervisor TRUE
  children [
    Emitter {
      name "emitter"
      channel 2
    }
    Receiver {
      name "receiver"
      channel 1
    }
  ]
}
""")
    return "".join(partes)


def main() -> None:
    """CLI: genera el mundo para el N indicado."""
    if len(sys.argv) != 2:
        print("Uso: python generar_mundo_multi.py <n_agentes>")
        sys.exit(1)
    n = int(sys.argv[1])
    if not (1 <= n <= len(COLORES)):
        print(f"n_agentes debe estar entre 1 y {len(COLORES)}.")
        sys.exit(1)

    sufijo = "" if n == 2 else str(n)
    ruta = _CARPETA / f"lab_robotat_fisica_multi{sufijo}.wbt"
    ruta.write_text(generar(n), encoding="utf-8")
    print(f"Mundo de {n} agentes escrito → {ruta}")


if __name__ == "__main__":
    main()
