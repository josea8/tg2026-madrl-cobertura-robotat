"""
verificar_cifras_fase0.py
=========================
Recalcula desde los datos CRUDOS cada cifra del reporte de la Fase 0 de la
demo del obstáculo móvil (`REPORTE_2026-10-02_obstaculo_fase0.md`) y la
compara con el valor TAL COMO APARECE en el texto. Imprime una línea por
cifra (SÍ / NO) y termina con código 1 si alguna no coincide.

    python verificar_cifras_fase0.py <campaña_final> <segunda_confirmación>

Las rutas que empiezan con "conf2:" se leen de la SEGUNDA confirmación
(tras el arreglo de la obediencia); "comparacion:", de la comparación de las
dos confirmaciones; el resto, de la campaña final (diseño + 1.ª
confirmación).

Las cifras se calculan con `cifras_fase0.calcular`; acá sólo se listan con
la ruta al dato, el formato con que se escribieron y el valor del reporte.

Autor: José — Tesis Mecatrónica UVG.
"""

from __future__ import annotations

import sys
from pathlib import Path
from typing import Any, Dict, List, Tuple

sys.path.insert(0, str(Path(__file__).resolve().parent))
import cifras_fase0 as C


def _ruta(c: Dict[str, Any], ruta: str) -> Any:
    v: Any = c
    for parte in ruta.split("/"):
        v = v[int(parte)] if isinstance(v, list) else v[parte]
    return v


#: (descripción, ruta en el dict de cifras, formato, valor en el reporte)
CIFRAS: List[Tuple[str, str, str, str]] = [
    # ── §1, §4 y §5.1: 2.ª confirmación (decide) ──
    ("2.ª conf: corridas", "conf2:confirmacion/n", "{}", "116"),
    ("2.ª conf: válidas (medición)", "conf2:confirmacion/validas", "{}", "116"),
    ("2.ª conf: completas", "conf2:confirmacion/completas", "{}", "116"),
    ("2.ª conf: bajo 0.15 m", "conf2:confirmacion/bajo_015", "{}", "0"),
    ("2.ª conf: bajo 0.185 m", "conf2:confirmacion/bajo_0185", "{}", "1"),
    ("2.ª conf: mínimo (m)", "conf2:confirmacion/d_min", "{:.4f}", "0.1815"),
    ("2.ª conf: caso del mínimo", "conf2:confirmacion/caso_min", "{}", "C5_encierro_trio_sinrampa"),
    ("2.ª conf: τ del mínimo", "conf2:confirmacion/tau_min", "{:.2f}", "0.85"),
    ("2.ª conf: mínimo medido a 10 Hz (m)", "conf2:confirmacion/d_min_medida_10hz", "{:.4f}", "0.1818"),
    ("2.ª conf: casos guionados por variante", "conf2:conf_guionada|0.45|con/n", "{}", "19"),
    ("2.ª conf: tomas por variante", "conf2:conf_tomas|0.45|con/n", "{}", "10"),
    ("2.ª conf guionados τ0.45 con: mínimo", "conf2:conf_guionada|0.45|con/d_min", "{:.4f}", "0.2800"),
    ("2.ª conf guionados τ0.45 con: caso", "conf2:conf_guionada|0.45|con/caso_min", "{}", "C2_espaldas_reversa_l-0.06"),
    ("2.ª conf guionados τ0.45 sin: mínimo", "conf2:conf_guionada|0.45|sin/d_min", "{:.4f}", "0.2035"),
    ("2.ª conf guionados τ0.45 sin: caso", "conf2:conf_guionada|0.45|sin/caso_min", "{}", "C5_encierro_B_corrido_sinrampa"),
    ("2.ª conf guionados τ0.85 con: mínimo", "conf2:conf_guionada|0.85|con/d_min", "{:.4f}", "0.2091"),
    ("2.ª conf guionados τ0.85 con: caso", "conf2:conf_guionada|0.85|con/caso_min", "{}", "C5_encierro_trio"),
    ("2.ª conf guionados τ0.85 sin: mínimo", "conf2:conf_guionada|0.85|sin/d_min", "{:.4f}", "0.1815"),
    ("2.ª conf tomas τ0.45 con: mínimo", "conf2:conf_tomas|0.45|con/d_min", "{:.4f}", "0.2745"),
    ("2.ª conf tomas τ0.45 con: toma", "conf2:conf_tomas|0.45|con/caso_min", "{}", "toma_02_s420102"),
    ("2.ª conf tomas τ0.45 sin: mínimo", "conf2:conf_tomas|0.45|sin/d_min", "{:.4f}", "0.3045"),
    ("2.ª conf tomas τ0.45 sin: toma", "conf2:conf_tomas|0.45|sin/caso_min", "{}", "toma_02_s420102_sinrampa"),
    ("2.ª conf tomas τ0.85 con: mínimo", "conf2:conf_tomas|0.85|con/d_min", "{:.4f}", "0.2752"),
    ("2.ª conf tomas τ0.85 con: toma", "conf2:conf_tomas|0.85|con/caso_min", "{}", "toma_05_s420105"),
    ("2.ª conf tomas τ0.85 sin: mínimo", "conf2:conf_tomas|0.85|sin/d_min", "{:.4f}", "0.2910"),
    ("2.ª conf tomas τ0.85 sin: toma", "conf2:conf_tomas|0.85|sin/caso_min", "{}", "toma_09_s420109_sinrampa"),
    ("2.ª conf guionados τ0.45 con: fallbacks QP", "conf2:conf_guionada|0.45|con/fallbacks_qp", "{}", "0"),
    ("2.ª conf guionados τ0.45 sin: fallbacks QP", "conf2:conf_guionada|0.45|sin/fallbacks_qp", "{}", "8"),
    ("2.ª conf guionados τ0.85 con: fallbacks QP", "conf2:conf_guionada|0.85|con/fallbacks_qp", "{}", "0"),
    ("2.ª conf guionados τ0.85 sin: fallbacks QP", "conf2:conf_guionada|0.85|sin/fallbacks_qp", "{}", "9"),
    ("2.ª conf tomas τ0.45 con: fallbacks QP", "conf2:conf_tomas|0.45|con/fallbacks_qp", "{}", "0"),
    ("2.ª conf tomas τ0.45 sin: fallbacks QP", "conf2:conf_tomas|0.45|sin/fallbacks_qp", "{}", "0"),
    ("2.ª conf tomas τ0.85 con: fallbacks QP", "conf2:conf_tomas|0.85|con/fallbacks_qp", "{}", "8"),
    ("2.ª conf tomas τ0.85 sin: fallbacks QP", "conf2:conf_tomas|0.85|sin/fallbacks_qp", "{}", "0"),
    ("2.ª conf guionados τ0.45 con: freno en sombra", "conf2:conf_guionada|0.45|con/frenos_sombra", "{}", "0"),
    ("2.ª conf guionados τ0.45 sin: freno en sombra", "conf2:conf_guionada|0.45|sin/frenos_sombra", "{}", "1"),
    ("2.ª conf guionados τ0.85 con: freno en sombra", "conf2:conf_guionada|0.85|con/frenos_sombra", "{}", "1"),
    ("2.ª conf guionados τ0.85 sin: freno en sombra", "conf2:conf_guionada|0.85|sin/frenos_sombra", "{}", "2"),
    ("2.ª conf tomas: freno en sombra", "conf2:conf_tomas/frenos_sombra", "{}", "0"),
    ("2.ª conf laterales C4: ángulo mínimo (°)", "conf2:angulo_laterales_conf/0", "{:.0f}", "69"),
    ("2.ª conf laterales C4: ángulo máximo (°)", "conf2:angulo_laterales_conf/1", "{:.0f}", "93"),
    ("2.ª conf cruces C6: ángulo mínimo (°)", "conf2:angulo_cruces_conf/0", "{:.0f}", "90"),
    ("2.ª conf cruces C6: ángulo máximo (°)", "conf2:angulo_cruces_conf/1", "{:.0f}", "140"),
    ("2.ª conf: ritmo mínimo (decisiones/s)", "conf2:ritmo_min_todas", "{:.3f}", "9.985"),
    ("2.ª conf: muestreo de la verdad mínimo (Hz)", "conf2:verdad_hz_min_todas", "{:.1f}", "195.4"),
    ("2.ª conf: corridas en disco", "conf2:corridas", "{}", "116"),
    ("2.ª conf: corridas interrumpidas", "conf2:corridas_interrumpidas", "{}", "0"),
    ("2.ª conf: cortes de la regla de 10 s arreglada", "conf2:regla_10s_arreglada_total", "{}", "0"),
    # ── §4: las dos validez ──
    ("2.ª conf: válidas para la demo", "conf2:confirmacion_demo/validas_demo", "{}", "112"),
    ("2.ª conf: excluidas por freno en guionadas", "conf2:confirmacion_demo/no_demo_por_freno_en_guionadas", "{}", "4"),
    ("2.ª conf: excluidas por freno en tomas", "conf2:confirmacion_demo/no_demo_por_freno_en_tomas", "{}", "0"),
    ("1.ª conf: válidas (medición)", "confirmacion_demo/validas_medicion", "{}", "115"),
    ("1.ª conf: válidas para la demo", "confirmacion_demo/validas_demo", "{}", "111"),
    ("1.ª conf: excluidas por freno en guionadas", "confirmacion_demo/no_demo_por_freno_en_guionadas", "{}", "4"),
    ("1.ª conf: excluidas por freno en tomas", "confirmacion_demo/no_demo_por_freno_en_tomas", "{}", "0"),
    ("diseño: válidas (medición)", "diseno_demo/validas_medicion", "{}", "108"),
    ("diseño: válidas para la demo", "diseno_demo/validas_demo", "{}", "106"),
    ("diseño: excluidas por freno en guionadas", "diseno_demo/no_demo_por_freno_en_guionadas", "{}", "2"),
    ("diseño: excluidas por freno en tomas", "diseno_demo/no_demo_por_freno_en_tomas", "{}", "0"),
    ("tres corridas: corridas con freno", "comparacion:tres_frenos_corridas", "{}", "10"),
    ("tres corridas: con freno en guionadas", "comparacion:tres_frenos_en_guionadas", "{}", "10"),
    ("tres corridas: frenos todos en encierros", "comparacion:tres_frenos_todos_encierro", "{}", "True"),
    ("tres corridas: distancia del freno mínima (m)", "comparacion:tres_frenos_dist/0", "{:.3f}", "0.245"),
    ("tres corridas: distancia del freno máxima (m)", "comparacion:tres_frenos_dist/1", "{:.3f}", "0.250"),
    ("tres corridas: tomas con política", "comparacion:tres_tomas_n", "{}", "120"),
    ("tres corridas: frenos en tomas con política", "comparacion:tres_tomas_frenos", "{}", "0"),
    ("tres corridas: mínimo en tomas con política (m)", "comparacion:tres_tomas_d_min", "{:.4f}", "0.2696"),
    ("diseño + 1.ª conf: tomas", "tomas_n", "{}", "80"),
    ("2.ª conf: tomas", "conf2:tomas_n", "{}", "40"),
    # ── §1 y §5.1: 1.ª confirmación y comparación ──
    ("1.ª conf: corridas", "confirmacion/n", "{}", "116"),
    ("1.ª conf: bajo 0.15 m", "confirmacion/bajo_015", "{}", "0"),
    ("1.ª conf: mínimo (m)", "confirmacion/d_min", "{:.4f}", "0.1836"),
    ("1.ª conf, inválida: decisión del aborto", "invalida_paso_aborto", "{}", "212"),
    ("1.ª conf, inválida: mínimo hasta el aborto (m)", "invalida_d_min_parcial", "{:.4f}", "0.3455"),
    ("1.ª conf, inválida: hueco entre decisiones (s)", "invalida_hueco_max_s", "{:.3f}", "0.374"),
    ("2.ª conf, la antes inválida: válida", "comparacion:antes_invalida_ahora_valida", "{}", "1"),
    ("2.ª conf, la antes inválida: decisiones", "comparacion:antes_invalida_ahora_decisiones", "{}", "500"),
    ("2.ª conf, la antes inválida: mínimo (m)", "comparacion:antes_invalida_ahora_d_min", "{:.4f}", "0.3460"),
    ("2.ª conf: decisiones sin estimación de v", "comparacion:decisiones_sin_estimacion_v_2a", "{}", "0"),
    ("comparación: pares", "comparacion:pares", "{}", "115"),
    ("comparación: media de Δ (m)", "comparacion:delta_media", "{:.4f}", "−0.0015"),
    ("comparación: mediana de |Δ| (mm)", "comparacion:abs_delta_mediana_mm", "{:.2f}", "0.25"),
    ("comparación: p90 de |Δ| (cm)", "comparacion:abs_delta_p90_cm", "{:.1f}", "1.4"),
    ("comparación: máximo de |Δ| (cm)", "comparacion:abs_delta_max_cm", "{:.1f}", "5.5"),
    # ── §5.1: prueba de humo ──
    ("humo de la confirmación: corridas", "comparacion:humo_corridas", "{}", "4"),
    ("humo: trío sin rampa (m)", "comparacion:humo_trio_sinrampa_d_min", "{:.4f}", "0.1801"),
    # ── §1.7 y §6: el encierro ──
    ("encierro: extremo inferior (mixto, m)", "mixto|0.85/d_min", "{:.3f}", "0.176"),
    ("encierro: extremo superior (ruido, m)", "ruido/d_min", "{:.3f}", "0.211"),
    ("ruido: caso del mínimo", "ruido/caso_min", "{}", "E5_encierro_A_quieto_B_hacia_A_ruido1mm"),
    ("mixto: caso del mínimo", "mixto|0.85/caso_min", "{}", "E5_encierro_A_quieto_B_hacia_A_tob0.45"),
    ("ablación τ0.85: caso del mínimo", "ablacion|0.85/caso_min", "{}", "E5_encierro_A_quieto_B_hacia_A_sinpeso"),
    ("diseño τ0.45 sin: caso del mínimo", "guionada|0.45|sin/caso_min", "{}", "E8_sorpresa_espaldas_sinrampa"),
    ("trío: agente del mínimo (B = 1)", "comparacion:trio_agente_min", "{}", "1"),
    ("trío: mínimo de A (m)", "comparacion:trio_d_min_agente_0", "{:.3f}", "0.246"),
    ("trío: rescates de nivel 2", "comparacion:trio_rescates_n2", "{}", "59"),
    ("trío: rescates en total", "comparacion:trio_rescates_total", "{}", "68"),
    ("trío: rescates de nivel 1", "comparacion:trio_rescates_n1", "{}", "4"),
    ("trío: rescates fallidos", "comparacion:trio_rescates_fallidos", "{}", "5"),
    ("E5: decisión del mínimo de A", "comparacion:e5_paso_min_a0", "{}", "87"),
    ("E5: primer escape de A", "comparacion:e5_primer_escape_a0", "{}", "146"),
    ("mixto: decisión del mínimo de A", "comparacion:mixto_paso_min_a0", "{}", "139"),
    ("mixto: primer escape de A", "comparacion:mixto_primer_escape_a0", "{}", "195"),
    # ── §8: ensayo de la L2 ──
    ("ensayo: intentos", "comparacion:ensayo_intentos", "{}", "11"),
    ("ensayo: válidas (medición)", "comparacion:ensayo_validas", "{}", "10"),
    ("ensayo: válidas para la demo", "comparacion:ensayo_validas_demo", "{}", "10"),
    ("ensayo: frenos", "comparacion:ensayo_frenos", "{}", "0"),
    ("ensayo: freno activo en todas", "comparacion:ensayo_freno_activo", "{}", "True"),
    ("ensayo: mínimo (m)", "comparacion:ensayo_d_min", "{:.4f}", "0.2967"),
    ("ensayo: mediana (m)", "comparacion:ensayo_d_mediana", "{:.4f}", "0.3155"),
    ("ensayo: máximo (m)", "comparacion:ensayo_d_max", "{:.4f}", "0.3688"),
    ("ensayo: bajo 0.185", "comparacion:ensayo_bajo_0185", "{}", "0"),
    ("ensayo: toma no válida", "comparacion:ensayo_invalida_toma", "{}", "2"),
    ("ensayo: decisión del corte", "comparacion:ensayo_invalida_decisiones", "{}", "411"),
    ("ensayo: motivo del corte", "comparacion:ensayo_invalida_motivo", "{}", "antigüedad de pose sobre el umbral"),
    ("ensayo: ciclos > 100 ms en las tomas 2, 3 y 9", "comparacion:ensayo_ciclos_100ms_por_toma", "{}", "[0, 1, 1, 0, 0, 0, 0, 0, 1, 0, 0]"),
    ("ensayo: duración de las tomas (s)", "comparacion:ensayo_duracion_tomas_s", "{:.0f}", "541"),
    ("ensayo: recorrido de la 1.ª toma (m)", "comparacion:ensayo_recorrido_toma1", "{:.2f}", "2.24"),
    ("ensayo: recorrido de las demás (m)", "comparacion:ensayo_recorrido_resto_min", "{:.2f}", "2.49"),
    # ── §8: ensayos del 03-10 (intermedio y final) ──
    ("ensayo intermedio: intentos", "comparacion:ensayo_intermedio_intentos", "{}", "10"),
    ("ensayo intermedio: válidas para la demo", "comparacion:ensayo_intermedio_validas_demo", "{}", "10"),
    ("ensayo intermedio: no válidas (medición)", "comparacion:ensayo_intermedio_invalidas", "{}", "[]"),
    ("ensayo intermedio: reglas de parada", "comparacion:ensayo_intermedio_paradas", "{}", "0"),
    ("ensayo intermedio: frenos", "comparacion:ensayo_intermedio_frenos", "{}", "0"),
    ("ensayo intermedio: mínimo (m)", "comparacion:ensayo_intermedio_d_min", "{:.4f}", "0.2996"),
    ("ensayo intermedio: mediana (m)", "comparacion:ensayo_intermedio_d_mediana", "{:.4f}", "0.3182"),
    ("ensayo intermedio: máximo (m)", "comparacion:ensayo_intermedio_d_max", "{:.4f}", "0.4026"),
    ("ensayo intermedio: p95 de ciclo máximo (ms)", "comparacion:ensayo_intermedio_ciclo_p95_max_ms", "{:.0f}", "53"),
    ("ensayo final: intentos", "comparacion:ensayo_final_intentos", "{}", "12"),
    ("ensayo final: válidas para la demo", "comparacion:ensayo_final_validas_demo", "{}", "10"),
    ("ensayo final: no válidas (toma, decisión)", "comparacion:ensayo_final_invalidas", "{}", "[[1, 472], [4, 480]]"),
    ("ensayo final: ciclos > 100 ms por toma", "comparacion:ensayo_final_ciclos_100ms_por_toma", "{}", "[5, 1, 0, 1, 0, 0, 0, 0, 0, 0, 0, 0]"),
    ("ensayo final: reglas de parada", "comparacion:ensayo_final_paradas", "{}", "0"),
    ("ensayo final: frenos", "comparacion:ensayo_final_frenos", "{}", "0"),
    ("ensayo final: freno activo en todas", "comparacion:ensayo_final_freno_activo", "{}", "True"),
    ("ensayo final: mínimo (m)", "comparacion:ensayo_final_d_min", "{:.4f}", "0.3021"),
    ("ensayo final: mediana (m)", "comparacion:ensayo_final_d_mediana", "{:.4f}", "0.3163"),
    ("ensayo final: máximo (m)", "comparacion:ensayo_final_d_max", "{:.4f}", "0.3645"),
    # ── §1 y §5.2: diseño ──
    ("diseño: corridas", "diseno/n", "{}", "108"),
    ("diseño: completas", "diseno/completas", "{}", "108"),
    ("diseño: bajo 0.15 m", "diseno/bajo_015", "{}", "0"),
    ("diseño: mínimo (m)", "diseno/d_min", "{:.4f}", "0.1879"),
    ("diseño guionados τ0.45 con", "guionada|0.45|con/d_min", "{:.4f}", "0.2776"),
    ("diseño guionados τ0.45 sin", "guionada|0.45|sin/d_min", "{:.4f}", "0.2792"),
    ("diseño guionados τ0.85 con", "guionada|0.85|con/d_min", "{:.4f}", "0.1986"),
    ("diseño guionados τ0.85 sin", "guionada|0.85|sin/d_min", "{:.4f}", "0.1879"),
    ("diseño tomas τ0.45 con", "tomas|0.45|con/d_min", "{:.4f}", "0.3043"),
    ("diseño tomas τ0.45 sin", "tomas|0.45|sin/d_min", "{:.4f}", "0.3026"),
    ("diseño tomas τ0.85 con", "tomas|0.85|con/d_min", "{:.4f}", "0.2883"),
    ("diseño tomas τ0.85 sin", "tomas|0.85|sin/d_min", "{:.4f}", "0.2933"),
    ("E6: distancia del agente al camino (no ejercido, m)", "e6_d_min/0", "{:.2f}", "0.62"),
    # ── §3 tabla por caso ──
    ("E2 reversa τ0.85 F0", "por_caso/E2_espaldas_reversa_d+0.00|0.85/F0", "{:.4f}", "0.0175"),
    ("E2 reversa τ0.85 F1", "por_caso/E2_espaldas_reversa_d+0.00|0.85/F1", "{:.4f}", "0.0868"),
    ("E2 reversa τ0.85 F2 sin peso", "por_caso/E2_espaldas_reversa_d+0.00|0.85/F2_sin_peso", "{:.4f}", "0.2427"),
    ("E2 reversa τ0.85 F2", "por_caso/E2_espaldas_reversa_d+0.00|0.85/F2", "{:.4f}", "0.2787"),
    ("E3 afuera τ0.85 F0", "por_caso/E3_quieto_afuera|0.85/F0", "{:.4f}", "0.1293"),
    ("E3 afuera τ0.85 F1", "por_caso/E3_quieto_afuera|0.85/F1", "{:.4f}", "0.1208"),
    ("E3 afuera τ0.85 F2 sin peso", "por_caso/E3_quieto_afuera|0.85/F2_sin_peso", "{:.4f}", "0.2785"),
    ("E3 afuera τ0.85 F2", "por_caso/E3_quieto_afuera|0.85/F2", "{:.4f}", "0.2825"),
    ("E5 A quieto τ0.85 F0", "por_caso/E5_encierro_A_quieto_B_hacia_A|0.85/F0", "{:.4f}", "0.1220"),
    ("E5 A quieto τ0.85 F1", "por_caso/E5_encierro_A_quieto_B_hacia_A|0.85/F1", "{:.4f}", "0.1131"),
    ("E5 A quieto τ0.85 F2 sin peso", "por_caso/E5_encierro_A_quieto_B_hacia_A|0.85/F2_sin_peso", "{:.4f}", "0.1832"),
    ("E5 A quieto τ0.85 F2", "por_caso/E5_encierro_A_quieto_B_hacia_A|0.85/F2", "{:.4f}", "0.1986"),
    ("E5 A y B τ0.85 F0", "por_caso/E5_encierro_A_y_B_hacia_obstaculo|0.85/F0", "{:.4f}", "0.0874"),
    ("E5 A y B τ0.85 F1", "por_caso/E5_encierro_A_y_B_hacia_obstaculo|0.85/F1", "{:.4f}", "0.2200"),
    ("E5 A y B τ0.85 F2 sin peso", "por_caso/E5_encierro_A_y_B_hacia_obstaculo|0.85/F2_sin_peso", "{:.4f}", "0.2945"),
    ("E5 A y B τ0.85 F2", "por_caso/E5_encierro_A_y_B_hacia_obstaculo|0.85/F2", "{:.4f}", "0.3265"),
    ("E2 reversa τ0.45 F0", "por_caso/E2_espaldas_reversa_d+0.00|0.45/F0", "{:.4f}", "0.0482"),
    ("E2 reversa τ0.45 F1", "por_caso/E2_espaldas_reversa_d+0.00|0.45/F1", "{:.4f}", "0.2042"),
    ("E2 reversa τ0.45 F2 sin peso", "por_caso/E2_espaldas_reversa_d+0.00|0.45/F2_sin_peso", "{:.4f}", "0.2381"),
    ("E2 reversa τ0.45 F2", "por_caso/E2_espaldas_reversa_d+0.00|0.45/F2", "{:.4f}", "0.2802"),
    ("campaña previa: E5 A y B τ0.85 (peso incondicional)", "previa_E5_AyB_085", "{:.4f}", "0.1224"),
    ("barrido τ_c = 0.65: peor caso", "barrido_peor_por_tc/0.65", "{:.4f}", "0.2416"),
    ("barrido τ_c = 0.85: peor caso", "barrido_peor_por_tc/0.85", "{:.4f}", "0.1995"),
    ("barrido τ_c = 0.45: peor caso", "barrido_peor_por_tc/0.45", "{:.4f}", "0.2319"),
    # ── §1 y §5.3: control y sensibilidades ──
    ("F1 τ0.85: casos guionados", "propuesta|0.85/n", "{}", "17"),
    ("F1 τ0.85: bajo 0.15", "propuesta|0.85/bajo_015", "{}", "6"),
    ("F1 τ0.85: mínimo", "propuesta|0.85/d_min", "{:.4f}", "0.0868"),
    ("F1: corridas", "propuesta/n", "{}", "34"),
    ("F1: bajo 0.15", "propuesta/bajo_015", "{}", "6"),
    ("control F0: corridas", "control/n", "{}", "34"),
    ("control F0: bajo 0.15", "control/bajo_015", "{}", "12"),
    ("control F0: mínimo", "control/d_min", "{:.4f}", "0.0175"),
    ("ablación: corridas", "ablacion/n", "{}", "34"),
    ("ablación: mínimo", "ablacion/d_min", "{:.4f}", "0.1832"),
    ("ablación: bajo 0.15", "ablacion/bajo_015", "{}", "0"),
    ("mixto (agentes 0.85, obstáculo 0.45): corridas", "mixto|0.85/n", "{}", "17"),
    ("mixto (agentes 0.85, obstáculo 0.45): mínimo", "mixto|0.85/d_min", "{:.4f}", "0.1758"),
    ("mixto (agentes 0.85, obstáculo 0.45): bajo 0.15", "mixto|0.85/bajo_015", "{}", "0"),
    ("mixto (agentes 0.45, obstáculo 0.85): corridas", "mixto|0.45/n", "{}", "17"),
    ("mixto (agentes 0.45, obstáculo 0.85): mínimo", "mixto|0.45/d_min", "{:.4f}", "0.2718"),
    ("mixto (agentes 0.45, obstáculo 0.85): bajo 0.15", "mixto|0.45/bajo_015", "{}", "0"),
    ("ruido 1 mm: corridas", "ruido/n", "{}", "17"),
    ("ruido 1 mm: mínimo", "ruido/d_min", "{:.4f}", "0.2113"),
    ("ruido 1 mm: bajo 0.15", "ruido/bajo_015", "{}", "0"),
    ("lazo del laboratorio: corridas", "lazo_lab/n", "{}", "10"),
    ("lazo del laboratorio: mínimo", "lazo_lab/d_min", "{:.4f}", "0.3108"),
    ("lazo del laboratorio: bajo 0.15", "lazo_lab/bajo_015", "{}", "0"),
    # ── §7.1 regla de 10 s ──
    ("episodios reales pedidos", "regla_real_pedidas/episodios", "{}", "95"),
    ("válidos reales pedidos", "regla_real_pedidas/validos", "{}", "65"),
    ("cortes reales por la regla", "regla_real_pedidas/cortes_reales", "{}", "0"),
    ("exposición máxima, regla actual (s)", "regla_real_pedidas/exposicion_max_actual", "{:.2f}", "5.11"),
    ("exposición máxima en válidos (s)", "regla_real_pedidas/exposicion_max_validos_actual", "{:.2f}", "3.20"),
    ("válidos del 30-09", "regla_real_30_09_validos", "{}", "50"),
    ("válidos del 30-09 que cambian", "regla_real_30_09_validos_que_cambian", "{}", "0"),
    ("campaña: cortes de la regla vieja, conf guionada", "conf_guionada/cortes_regla_10s", "{}", "4"),
    ("campaña: cortes de la regla vieja, diseño guionada", "guionada/cortes_regla_10s", "{}", "4"),
    ("campaña: cortes de la regla arreglada (total)", "regla_10s_arreglada_total", "{}", "0"),
    # ── §12: en disco ──
    ("campaña final: corridas en disco", "corridas", "{}", "387"),
    ("campaña final: corridas interrumpidas conservadas", "corridas_interrumpidas", "{}", "5"),
    ("campaña final: ritmo mínimo (decisiones/s)", "ritmo_min_todas", "{:.3f}", "9.781"),
    ("campaña final: muestreo de la verdad mínimo (Hz)", "verdad_hz_min_todas", "{:.1f}", "187.4"),
    # ── batería ──
    ("batería existente: pruebas", "bateria_total", "{}", "344"),
    ("batería existente: fallas", "bateria_fallas", "{}", "1"),
]


def main() -> int:
    carpeta = Path(sys.argv[1])
    carpeta2 = Path(sys.argv[2])
    fuentes = {"": C.calcular(carpeta), "conf2:": C.calcular(carpeta2),
               "comparacion:": C.comparar_confirmaciones(carpeta, carpeta2)}
    malas = 0
    for desc, ruta, fmt, reportado in CIFRAS:
        pref = next((k for k in ("conf2:", "comparacion:") if ruta.startswith(k)), "")
        c = fuentes[pref]
        ruta = ruta[len(pref):]
        try:
            calculado = fmt.format(_ruta(c, ruta))
        except (KeyError, TypeError, ValueError) as exc:
            calculado = f"ERROR {type(exc).__name__}: {exc}"
        # El reporte escribe el signo menos tipográfico (−).
        ok = calculado.replace("-", "−") == reportado if calculado.startswith("-") \
            else calculado == reportado
        malas += not ok
        print(f"{'SÍ' if ok else 'NO'}  {desc:<70} reporte {reportado:>10}  "
              f"calculado {calculado:>10}")
    print(f"\n{len(CIFRAS) - malas}/{len(CIFRAS)} cifras coinciden.")
    return 1 if malas else 0


if __name__ == "__main__":
    sys.exit(main())
